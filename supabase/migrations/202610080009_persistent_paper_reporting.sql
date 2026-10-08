-- Persistent close-signal paper model. Additive; legacy trades and actual ledger stay intact.
begin;

alter table public.paper_trades drop constraint paper_trades_state_check;
alter table public.paper_trades add constraint paper_trades_state_check
  check (state in ('pending_entry','open','closed','data_hold','skipped','expired','ambiguous_review'));
alter table public.paper_trades
  add column model_version text,
  add column lot_count bigint check (lot_count >= 0),
  add column quantity bigint check (quantity >= 0),
  add column planned_stop_loss_idr numeric(28,4),
  add column net_pnl_idr numeric(28,4),
  add column fee_total_idr numeric(28,4),
  add column actionable boolean not null default true,
  add column cohort text;
-- Runtime writes must pass atomic revision/idempotency and ledger checks.
revoke insert,update on public.paper_trades from service_role;
create index paper_model_reporting on public.paper_trades(owner_id,data_mode,model_version,exit_mode,exit_session);

create table public.paper_models (
  owner_id uuid not null references auth.users(id),
  data_mode text not null check (data_mode in ('live','fixture')),
  model_version text not null default 'close-signal-risk-v1' check (model_version='close-signal-risk-v1'),
  activated_at timestamptz not null default now(),
  config jsonb not null default '{"entry_model":"signal_close","risk_budget_idr":"1000000","lot_size":100,"buy_bps":"15","sell_bps":"25","slippage_bps":"0","exits":["fixed2r","ma10"]}'::jsonb,
  revision bigint not null default 0 check (revision >= 0),
  last_session date,
  book jsonb not null default '{"experiments":{},"trades":{}}'::jsonb,
  evaluations jsonb not null default '{}'::jsonb,
  source_run_id uuid references public.scan_runs(id),
  updated_at timestamptz not null default now(),
  primary key(owner_id,data_mode,model_version)
);
create table public.paper_runtime_requests (
  owner_id uuid not null references auth.users(id), data_mode text not null,
  model_version text not null, request_id text not null check(length(request_id) between 1 and 200),
  request jsonb not null, result jsonb not null, created_at timestamptz not null default now(),
  primary key(owner_id,data_mode,model_version,request_id)
);
create table public.paper_events (
  owner_id uuid not null references auth.users(id), data_mode text not null,
  model_version text not null, trade_id text not null, event_index integer not null,
  event_type text not null, session_date date not null, payload jsonb not null,
  created_at timestamptz not null default now(),
  primary key(owner_id,model_version,trade_id,event_index),
  foreign key(trade_id,owner_id) references public.paper_trades(id,owner_id)
);
create table public.signal_evaluations (
  owner_id uuid not null references auth.users(id), data_mode text not null,
  model_version text not null, signal_id text not null references public.signals(id),
  ticker text not null, strategy text not null, signal_session date not null,
  payload jsonb not null, updated_at timestamptz not null default now(),
  primary key(owner_id,data_mode,model_version,signal_id)
);
do $$ declare t text; begin
  foreach t in array array['paper_models','paper_runtime_requests','paper_events','signal_evaluations'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('revoke all on public.%I from public,anon,authenticated,service_role',t);
    execute format('grant select on public.%I to authenticated,service_role',t);
    execute format('create policy owner_read on public.%I for select to authenticated using ((select public.is_app_owner()) and owner_id=(select auth.uid()))',t);
  end loop;
  foreach t in array array['paper_runtime_requests','paper_events'] loop
    execute format('create trigger immutable_record before update or delete on public.%I for each row execute function public.reject_immutable_mutation()',t);
  end loop;
end $$;

create function public.guard_paper_model_v1() returns trigger language plpgsql set search_path='' as $$
begin
  if (new.owner_id,new.data_mode,new.model_version,new.activated_at,new.config)
      is distinct from (old.owner_id,old.data_mode,old.model_version,old.activated_at,old.config) then
    raise exception 'immutable_paper_model' using errcode='22023';
  end if;
  return new;
end $$;
create trigger immutable_model before update on public.paper_models
for each row execute function public.guard_paper_model_v1();
revoke all on function public.guard_paper_model_v1() from public,anon,authenticated,service_role;

create function public.assert_paper_owner_v1(p_owner_id uuid,p_data_mode text)
returns void language plpgsql security definer set search_path='' as $$
begin
  if not exists(select 1 from public.app_members where user_id=p_owner_id and enabled) then
    raise exception 'owner_required' using errcode='42501';
  end if;
  if not exists(select 1 from public.deployment_settings where singleton and data_mode=p_data_mode) then
    raise exception 'data_mode_mismatch' using errcode='22023';
  end if;
end $$;
revoke all on function public.assert_paper_owner_v1(uuid,text) from public,anon,authenticated,service_role;

create function public.init_paper_model_v1(p_owner_id uuid,p_data_mode text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare r public.paper_models; begin
  perform public.assert_paper_owner_v1(p_owner_id,p_data_mode);
  insert into public.paper_models(owner_id,data_mode) values(p_owner_id,p_data_mode)
    on conflict(owner_id,data_mode,model_version) do nothing;
  select * into strict r from public.paper_models where owner_id=p_owner_id and data_mode=p_data_mode and model_version='close-signal-risk-v1';
  return to_jsonb(r);
end $$;
create function public.load_paper_runtime_v1(p_owner_id uuid,p_data_mode text)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare r public.paper_models; begin
  perform public.assert_paper_owner_v1(p_owner_id,p_data_mode);
  select * into r from public.paper_models where owner_id=p_owner_id and data_mode=p_data_mode and model_version='close-signal-risk-v1';
  if not found then raise exception 'paper_model_not_initialized' using errcode='55000'; end if;
  return to_jsonb(r);
end $$;
revoke all on function public.init_paper_model_v1(uuid,text),public.load_paper_runtime_v1(uuid,text) from public,anon,authenticated,service_role;
grant execute on function public.init_paper_model_v1(uuid,text),public.load_paper_runtime_v1(uuid,text) to service_role;

create function public.commit_paper_session_v1(
  p_owner_id uuid,p_data_mode text,p_expected_revision bigint,p_request_id text,
  p_session date,p_book jsonb,p_evaluations jsonb,p_source_run_id uuid default null
) returns jsonb language plpgsql security definer set search_path='' as $$
declare
  m public.paper_models; req jsonb; saved public.paper_runtime_requests; item record; ev record;
  t jsonb; old_t jsonb; sig public.signals; cfg jsonb; result jsonb; event_count integer;
  lots bigint; qty bigint; entry numeric; stop numeric; risk numeric; planned_loss numeric;
  terminal_event jsonb; event_fee numeric; expected_pnl numeric; expected_lots bigint;
begin
  perform public.assert_paper_owner_v1(p_owner_id,p_data_mode);
  if p_request_id is null or length(p_request_id) not between 1 and 200 or p_session is null
     or p_expected_revision is null or p_expected_revision<0
     or jsonb_typeof(p_book) is distinct from 'object' or jsonb_typeof(p_book->'trades') is distinct from 'object'
     or jsonb_typeof(p_book->'experiments') is distinct from 'object' or jsonb_typeof(p_evaluations) is distinct from 'object' then
    raise exception 'invalid_paper_commit' using errcode='22023';
  end if;
  req:=jsonb_build_object('session',p_session,'book',p_book,'evaluations',p_evaluations);
  select * into strict m from public.paper_models where owner_id=p_owner_id and data_mode=p_data_mode and model_version='close-signal-risk-v1' for update;
  select * into saved from public.paper_runtime_requests where owner_id=p_owner_id and data_mode=p_data_mode and model_version=m.model_version and request_id=p_request_id;
  if found then
    if saved.request is distinct from req then raise exception 'idempotency_conflict' using errcode='PT409'; end if;
    return saved.result||jsonb_build_object('replayed',true);
  end if;
  if m.revision<>p_expected_revision then raise exception 'paper_revision_conflict' using errcode='PT409'; end if;
  if m.last_session is not null and p_session<m.last_session then raise exception 'chronological_replay_required' using errcode='22023'; end if;
  if p_source_run_id is not null and not exists(select 1 from public.scan_runs where id=p_source_run_id and data_mode=p_data_mode and session_date=p_session) then
    raise exception 'source_run_mismatch' using errcode='22023';
  end if;
  if exists(select 1 from jsonb_each(m.book->'trades') x where not (p_book->'trades' ? x.key))
    or exists(select 1 from jsonb_each(m.book->'experiments') x where p_book->'experiments'->x.key is distinct from x.value)
    or exists(select 1 from jsonb_each(m.evaluations) x where not(p_evaluations ? x.key)) then
    raise exception 'paper_history_removed' using errcode='22023';
  end if;
  for item in select * from jsonb_each(p_book->'trades') loop
    t:=item.value; old_t:=m.book->'trades'->item.key; cfg:=t->'experiment';
    if t->>'id' is distinct from item.key or jsonb_typeof(t->'events') is distinct from 'array'
      or cfg->>'model_version' is distinct from m.model_version or cfg->>'entry_model' is distinct from 'signal_close'
      or (cfg->>'risk_budget_idr')::numeric is distinct from 1000000::numeric
      or (cfg->>'lot_size')::integer is distinct from 100
      or (cfg#>>'{costs,buy_bps}')::numeric is distinct from 15::numeric
      or (cfg#>>'{costs,sell_bps}')::numeric is distinct from 25::numeric
      or (cfg#>>'{costs,slippage_bps}')::numeric is distinct from 0::numeric
      or (cfg->>'activated_at')::timestamptz is distinct from m.activated_at
      or (((cfg#>>'{exit,mode}'='fixed_rr' and (cfg#>>'{exit,target_r}')::numeric=2)
        or (cfg#>>'{exit,mode}'='ma_close' and cfg#>>'{exit,ma_type}'='SMA' and (cfg#>>'{exit,period}')::integer=10)) is not true) then
      raise exception 'paper_model_configuration_mismatch' using errcode='22023';
    end if;
    select * into sig from public.signals where id=t#>>'{signal,id}' and data_mode=p_data_mode;
    if not found or cfg->>'strategy' is distinct from sig.strategy
      or t#>>'{signal,ticker}' is distinct from sig.ticker
      or (t#>>'{signal,session}')::date is distinct from sig.session_date
      or sig.published_at<m.activated_at or t->'signal' is distinct from sig.snapshot then
      raise exception 'invalid_paper_signal' using errcode='22023';
    end if;
    entry:=(t->>'planned_entry_price')::numeric; stop:=(t->>'stop')::numeric;
    if entry is distinct from (sig.snapshot#>>'{candidate,reference_close}')::numeric or stop is distinct from (sig.snapshot#>>'{candidate,stop}')::numeric then
      raise exception 'paper_signal_price_mismatch' using errcode='22023';
    end if;
    lots:=(t->>'lots')::bigint; qty:=(t->>'quantity')::bigint;
    if entry is null or stop is null or entry<=stop or stop<=0 or entry>='Infinity'::numeric
       or lots is null or lots<0 or qty is distinct from lots*100 then
      raise exception 'invalid_paper_sizing' using errcode='22023';
    end if;
    if (cfg#>>'{exit,mode}'='fixed_rr' and (t->>'target')::numeric is distinct from entry+2*(entry-stop))
      or (cfg#>>'{exit,mode}'='ma_close' and t->>'target' is not null) then
      raise exception 'paper_target_configuration_mismatch' using errcode='22023';
    end if;
    risk:=qty*(entry-stop);
    planned_loss:=round(risk+round(qty*entry*0.0015,2)+round(qty*stop*0.0025,2),2);
    expected_lots:=floor(1000000/(100*((entry-stop)+entry*0.0015+stop*0.0025)));
    while expected_lots>0 and round(expected_lots*100*(entry-stop)+round(expected_lots*100*entry*0.0015,2)+round(expected_lots*100*stop*0.0025,2),2)>1000000 loop
      expected_lots:=expected_lots-1;
    end loop;
    if lots<>expected_lots or planned_loss>1000000
       or (t->>'planned_stop_loss_idr')::numeric is distinct from planned_loss
       or (t->>'entry_fee_idr')::numeric is distinct from round(qty*entry*0.0015,2)
       or (t->>'initial_risk')::numeric is distinct from risk
       or (t->>'entry' is not null and (t->>'entry')::numeric<>entry)
       or (lots=0 and (t->>'state'<>'skipped' or t->>'reason'<>'skipped_budget')) then
      raise exception 'invalid_paper_sizing' using errcode='22023';
    end if;
    if old_t is not null then
      if exists(select 1 from unnest(array['signal','experiment','planned_entry_price','lots','quantity','planned_stop_loss_idr','initial_risk','stop','target','entry_fee_idr']) k where old_t->k is distinct from t->k)
         or jsonb_array_length(t->'events')<jsonb_array_length(old_t->'events') then
        raise exception 'immutable_paper_plan' using errcode='22023';
      end if;
      event_count:=jsonb_array_length(old_t->'events');
      if exists(select 1 from jsonb_array_elements(old_t->'events') with ordinality e(value,n)
                where e.value is distinct from t->'events'->(e.n::integer-1)) then
        raise exception 'immutable_paper_event' using errcode='22023';
      end if;
      if old_t->>'state' in ('closed','ambiguous_review','skipped','expired') and old_t is distinct from t then
        raise exception 'immutable_terminal_trade' using errcode='22023';
      end if;
    end if;
    select value into terminal_event from jsonb_array_elements(t->'events') with ordinality e(value,n)
      where value->>'kind'='exit' order by n desc limit 1;
    if t->>'state' in ('closed','ambiguous_review') then
      if terminal_event is null or (terminal_event->>'session')::date>p_session then
        raise exception 'missing_paper_exit_event' using errcode='22023';
      end if;
      event_fee:=round(qty*(terminal_event->>'price')::numeric*0.0025,2);
      expected_pnl:=round(qty*((terminal_event->>'price')::numeric-entry)-(t->>'entry_fee_idr')::numeric-event_fee,2);
      if (t->>'exit_fee_idr')::numeric is distinct from event_fee
         or (t->>'net_pnl')::numeric is distinct from expected_pnl
         or (t->>'realized_r')::numeric is null
         or abs((t->>'realized_r')::numeric-expected_pnl/nullif(risk,0))>0.000000000001 then
        raise exception 'paper_ledger_mismatch' using errcode='22023';
      end if;
    end if;
    insert into public.paper_trades(id,owner_id,data_mode,run_id,signal_id,ticker,strategy,experiment_id,exit_mode,state,reason,
      entry_session,entry_price,initial_stop,current_stop,target_price,exit_session,exit_price,exit_reason,realized_r,alternate_r,initial_risk_idr,
      details,model_version,lot_count,quantity,planned_stop_loss_idr,net_pnl_idr,fee_total_idr,actionable,cohort)
    values(item.key,p_owner_id,p_data_mode,p_source_run_id,sig.id,sig.ticker,sig.strategy,cfg->>'id',cfg#>>'{exit,mode}',t->>'state',coalesce(t->>'reason',''),
      sig.planned_entry_session,entry,stop,stop,(t->>'target')::numeric,(terminal_event->>'session')::date,(terminal_event->>'price')::numeric,terminal_event->>'reason',
      (t->>'realized_r')::numeric,(t->>'alternate_r')::numeric,risk,t,m.model_version,lots,qty,planned_loss,(t->>'net_pnl')::numeric,
      case when t->>'entry' is null then 0 else (t->>'entry_fee_idr')::numeric+coalesce((t->>'exit_fee_idr')::numeric,0) end,coalesce((t->>'actionable')::boolean,true),sig.cohort)
    on conflict(id,owner_id) do update set state=excluded.state,reason=excluded.reason,exit_session=excluded.exit_session,exit_price=excluded.exit_price,
      exit_reason=excluded.exit_reason,realized_r=excluded.realized_r,alternate_r=excluded.alternate_r,details=excluded.details,
      net_pnl_idr=excluded.net_pnl_idr,fee_total_idr=excluded.fee_total_idr,actionable=excluded.actionable,updated_at=now();
    for ev in select value,n from jsonb_array_elements(t->'events') with ordinality e(value,n) loop
      insert into public.paper_events(owner_id,data_mode,model_version,trade_id,event_index,event_type,session_date,payload)
        values(p_owner_id,p_data_mode,m.model_version,item.key,ev.n::integer,ev.value->>'kind',(ev.value->>'session')::date,ev.value)
        on conflict do nothing;
    end loop;
  end loop;
  for item in select * from jsonb_each(p_evaluations) loop
    t:=item.value;
    select * into sig from public.signals where id=item.key and data_mode=p_data_mode;
    if not found or sig.published_at<m.activated_at or sig.cohort<>'forward'
       or t->>'signal_id' is distinct from item.key or t->>'ticker' is distinct from sig.ticker or t->>'strategy' is distinct from sig.strategy then
      raise exception 'invalid_signal_evaluation' using errcode='22023';
    end if;
    if m.evaluations ? item.key and exists(select 1 from unnest(array['signal_id','ticker','strategy','signal_session','entry_session','entry_price','initial_stop','target_1r','target_2r']) k
      where m.evaluations->item.key->k is distinct from t->k) then
      raise exception 'immutable_signal_evaluation_plan' using errcode='22023';
    end if;
    if jsonb_typeof(t->'results') is distinct from 'object'
      or not (t->'results' ?& array['target_1r','target_2r','net_5','net_10'])
      or exists(select 1 from jsonb_each_text(t->'results') r where r.key not in ('target_1r','target_2r','net_5','net_10') or r.value not in ('won','lost','pending','ambiguous','data_hold','excluded'))
      or jsonb_typeof(t->'input_digests') is distinct from 'array'
      or (t->>'observed_sessions')::integer is null or (t->>'observed_sessions')::integer<0 then
      raise exception 'invalid_signal_evaluation_state' using errcode='22023';
    end if;
    old_t:=m.evaluations->item.key;
    if old_t is not null and (
      (t->>'observed_sessions')::integer<(old_t->>'observed_sessions')::integer
      or ((old_t->>'last_session') is not null and ((t->>'last_session') is null or (t->>'last_session')::date<(old_t->>'last_session')::date))
      or jsonb_array_length(t->'input_digests')<jsonb_array_length(old_t->'input_digests')
      or exists(select 1 from jsonb_array_elements(old_t->'input_digests') with ordinality e(value,n) where e.value is distinct from t->'input_digests'->(e.n::integer-1))
      or exists(select 1 from jsonb_each_text(old_t->'results') r where r.value in ('won','lost','ambiguous','excluded') and t->'results'->>r.key is distinct from r.value)
    ) then
      raise exception 'immutable_signal_evaluation_history' using errcode='22023';
    end if;
    insert into public.signal_evaluations(owner_id,data_mode,model_version,signal_id,ticker,strategy,signal_session,payload)
      values(p_owner_id,p_data_mode,m.model_version,item.key,sig.ticker,sig.strategy,sig.session_date,t)
      on conflict(owner_id,data_mode,model_version,signal_id) do update set payload=excluded.payload,updated_at=now();
  end loop;
  update public.paper_models set book=p_book,evaluations=p_evaluations,revision=revision+1,last_session=p_session,source_run_id=p_source_run_id,updated_at=now()
    where owner_id=p_owner_id and data_mode=p_data_mode and model_version=m.model_version returning to_jsonb(paper_models) into result;
  insert into public.paper_runtime_requests(owner_id,data_mode,model_version,request_id,request,result)
    values(p_owner_id,p_data_mode,m.model_version,p_request_id,req,result);
  return result||jsonb_build_object('replayed',false);
end $$;
revoke all on function public.commit_paper_session_v1(uuid,text,bigint,text,date,jsonb,jsonb,uuid) from public,anon,authenticated,service_role;
grant execute on function public.commit_paper_session_v1(uuid,text,bigint,text,date,jsonb,jsonb,uuid) to service_role;

-- The pre-v1 reader keeps its original contract and only sees its original cohort.
do $$ declare d text; begin
  select pg_get_functiondef('public.read_paper_journal(text,text,text)'::regprocedure) into d;
  if position('where owner_id = v_owner and data_mode = v_mode' in d)=0 then
    raise exception 'unexpected_legacy_reader_definition';
  end if;
  execute replace(d,'where owner_id = v_owner and data_mode = v_mode',
    'where owner_id = v_owner and data_mode = v_mode and model_version is null');
end $$;

-- Use unrestricted numeric for frozen Decimal prices (no price rounding at persistence).
alter table public.paper_trades alter column entry_price type numeric, alter column initial_stop type numeric,
  alter column current_stop type numeric, alter column target_price type numeric, alter column exit_price type numeric, alter column initial_risk_idr type numeric;

create function public.guard_paper_trade_v1() returns trigger language plpgsql set search_path='' as $$
begin
  if old.model_version is not null or new.model_version is not null then
    if (old.id,old.owner_id,old.data_mode,old.model_version,old.signal_id,old.experiment_id,old.entry_session,
      old.entry_price,old.initial_stop,old.target_price,old.lot_count,old.quantity,old.initial_risk_idr,old.planned_stop_loss_idr)
      is distinct from (new.id,new.owner_id,new.data_mode,new.model_version,new.signal_id,new.experiment_id,new.entry_session,
      new.entry_price,new.initial_stop,new.target_price,new.lot_count,new.quantity,new.initial_risk_idr,new.planned_stop_loss_idr)
      or old.details->'signal' is distinct from new.details->'signal'
      or old.details->'experiment' is distinct from new.details->'experiment' then
      raise exception 'immutable_paper_plan' using errcode='22023';
    end if;
  end if;
  return new;
end $$;
create trigger immutable_new_paper_plan before update on public.paper_trades
for each row execute function public.guard_paper_trade_v1();
revoke all on function public.guard_paper_trade_v1() from public,anon,authenticated,service_role;

-- Private normalized reporting rows; only the owner-checked readers below can execute it.
create function public.trade_reporting_rows_v1(p_owner uuid,p_data text,p_mode text,p_exit text,p_strategy text,p_version text,p_snapshot jsonb)
returns table(id text,ticker text,strategy text,state text,signal_id text,signal_session date,entry_session date,
  entry_price numeric,initial_stop numeric,target_price numeric,lots bigint,initial_price_risk_idr numeric,
  planned_loss_idr numeric,exit_session date,exit_price numeric,fee_total_idr numeric,realized_pnl_idr numeric,
  realized_r numeric,reason text,ambiguous boolean,model_version text,actionable boolean,alternate_pnl numeric,alternate_r numeric,updated_at timestamptz)
language sql stable security definer set search_path='' as $$
  select t.id,t.ticker,t.strategy,t.state,t.signal_id,s.session_date,t.entry_session,t.entry_price,t.initial_stop,t.target_price,
    t.lot_count,t.initial_risk_idr,t.planned_stop_loss_idr,t.exit_session,t.exit_price,t.fee_total_idr,t.net_pnl_idr,t.realized_r,
    t.reason,t.state='ambiguous_review' or t.alternate_r is not null,t.model_version,
    t.actionable and t.cohort='forward',(t.details->>'alternate_net_pnl')::numeric,t.alternate_r,t.updated_at
  from public.paper_trades t left join public.signals s on s.id=t.signal_id
  where p_mode='paper' and t.owner_id=p_owner and t.data_mode=p_data and t.model_version='close-signal-risk-v1'
    and ((p_exit='fixed2r' and t.exit_mode='fixed_rr') or (p_exit='ma10' and t.exit_mode='ma_close'))
    and (p_strategy is null or t.strategy=p_strategy)
  union all
  select t.id::text,t.ticker,t.primary_strategy,case when t.status='draft' then 'pending_entry' else t.status end,t.signal_id,s.session_date,
    (f.first_buy at time zone 'Asia/Jakarta')::date,f.entry_price,t.initial_stop,
    case when t.exit_policy_snapshot->>'mode'='fixed_rr' then f.entry_price+(t.exit_policy_snapshot->>'target_r')::numeric*(f.entry_price-t.initial_stop) else null end,
    null::bigint,t.initial_risk_idr,null::numeric,(t.closed_at at time zone 'Asia/Jakarta')::date,
    f.exit_price,t.fee_total_idr,t.realized_pnl_idr,t.realized_r,null::text,false,null::text,true,null::numeric,null::numeric,
    coalesce(t.closed_at,t.entry_finalized_at,t.created_at)
  from public.actual_trades t left join public.signals s on s.id=t.signal_id
  left join lateral (
    select min(coalesce(c.filled_at,x.filled_at)) filter(where x.side='buy') first_buy,
      sum(coalesce(c.quantity,x.quantity)*coalesce(c.price_idr,x.price_idr)) filter(where x.side='buy')/
        nullif(sum(coalesce(c.quantity,x.quantity)) filter(where x.side='buy'),0) entry_price,
      sum(coalesce(c.quantity,x.quantity)*coalesce(c.price_idr,x.price_idr)) filter(where x.side='sell')/
        nullif(sum(coalesce(c.quantity,x.quantity)) filter(where x.side='sell'),0) exit_price
    from public.actual_fills x left join lateral(select * from public.actual_fill_corrections z where z.fill_id=x.id order by z.sequence desc limit 1)c on true
    where x.trade_id=t.id
  )f on true
  where p_mode='actual' and t.owner_id=p_owner and t.data_mode=p_data
    and (p_strategy is null or t.primary_strategy=p_strategy)
    and (p_version is null or t.exit_policy_snapshot->>'version'=p_version)
    and (p_snapshot is null or t.exit_policy_snapshot=p_snapshot);
$$;
revoke all on function public.trade_reporting_rows_v1(uuid,text,text,text,text,text,jsonb) from public,anon,authenticated,service_role;

create function public.trade_reporting_summary_v1(p_rows jsonb) returns jsonb
language sql immutable set search_path='' as $$
  with r as(select (value->>'realized_pnl_idr')::numeric realized_pnl_idr,(value->>'realized_r')::numeric realized_r,n from jsonb_array_elements(p_rows) with ordinality e(value,n)),
  ordered as(select n,sum(realized_pnl_idr) over(order by n) cum from r),
  dd as(select greatest(0,max(cum) over(order by n))-cum drawdown from ordered)
  select jsonb_build_object('closed',count(*),'wins',count(*) filter(where realized_pnl_idr>0),
    'losses',count(*) filter(where realized_pnl_idr<0),'breakeven',count(*) filter(where realized_pnl_idr=0),
    'net_pnl_idr',coalesce(sum(realized_pnl_idr),0),
    'win_rate',case when count(*)>0 then (count(*) filter(where realized_pnl_idr>0))::numeric/count(*) else null end,
    'expectancy_idr',avg(realized_pnl_idr),'expectancy_r',avg(realized_r),'max_drawdown_idr',(select coalesce(max(drawdown),0) from dd)) from r;
$$;
revoke all on function public.trade_reporting_summary_v1(jsonb) from public,anon,authenticated,service_role;

create function public.read_trade_reporting_v1(
  p_mode text default 'paper',p_from date default null,p_to date default null,p_strategy text default null,
  p_exit_key text default 'fixed2r',p_page integer default 1,p_exit_version text default null,p_exit_snapshot jsonb default null
) returns jsonb language plpgsql stable security definer set search_path='' as $$
declare
  owner uuid:=auth.uid(); dm text; scoped jsonb; closed_rows jsonb; summary jsonb; statuses jsonb;
  curve jsonb; attribution jsonb; trades jsonb; sl_rows jsonb; tp_rows jsonb; model public.paper_models;
  as_of date; updated timestamptz; coverage text; has_more boolean; max_dd numeric; latest_scan date;
begin
  if owner is null or not public.is_app_owner() then raise exception 'owner_required' using errcode='42501'; end if;
  if p_mode not in ('paper','actual') or p_mode is null or (p_mode='paper' and (p_exit_key not in ('fixed2r','ma10') or p_exit_key is null))
    or p_page is null or p_page<1 or p_page>1000000 or p_from>p_to then
    raise exception 'invalid_reporting_filter' using errcode='22023';
  end if;
  select data_mode into strict dm from public.deployment_settings where singleton;
  select * into model from public.paper_models where owner_id=owner and data_mode=dm and model_version='close-signal-risk-v1';
  select coalesce(jsonb_agg(to_jsonb(r)),'[]') into scoped from public.trade_reporting_rows_v1(owner,dm,p_mode,p_exit_key,p_strategy,p_exit_version,p_exit_snapshot)r;
  with r as(select * from jsonb_to_recordset(scoped) x(state text,ambiguous boolean,actionable boolean,exit_session date,realized_pnl_idr numeric,realized_r numeric,id text,ticker text,strategy text,updated_at timestamptz))
  select coalesce(jsonb_agg(to_jsonb(r) order by exit_session,case when p_mode='actual' then updated_at else null end,id),'[]') into closed_rows from r
    where state='closed' and not ambiguous and actionable and (p_from is null or exit_session>=p_from) and (p_to is null or exit_session<=p_to);
  summary:=public.trade_reporting_summary_v1(closed_rows);
  with r as(select * from jsonb_to_recordset(scoped) x(state text,ambiguous boolean))
  select jsonb_build_object('pending_entry',count(*) filter(where state='pending_entry'),'open',count(*) filter(where state='open'),
    'closed',count(*) filter(where state='closed' and not ambiguous),'skipped',count(*) filter(where state='skipped'),
    'expired',count(*) filter(where state='expired'),'data_hold',count(*) filter(where state='data_hold'),
    'ambiguous',count(*) filter(where ambiguous)) into statuses from r;
  with r as(select * from jsonb_to_recordset(closed_rows) x(id text,ticker text,strategy text,exit_session date,realized_pnl_idr numeric,updated_at timestamptz)),
  ordered as(select *,row_number() over(order by exit_session,case when p_mode='actual' then updated_at else null end,id) seq,sum(realized_pnl_idr) over(order by exit_session,case when p_mode='actual' then updated_at else null end,id) cum from r),
  dd as(select *,greatest(0,max(cum) over(order by seq))-cum drawdown from ordered)
  select coalesce(jsonb_agg(jsonb_build_object('sequence',seq,'trade_id',id,'ticker',ticker,'strategy',strategy,'exit_session',exit_session,
    'realized_pnl_idr',realized_pnl_idr,'cumulative_pnl_idr',cum) order by seq),'[]'),coalesce(max(drawdown),0) into curve,max_dd from dd;
  summary:=summary||jsonb_build_object('max_drawdown_idr',max_dd);
  with r as(select * from jsonb_to_recordset(closed_rows) x(strategy text,realized_pnl_idr numeric,realized_r numeric)),
  groups as(select strategy,public.trade_reporting_summary_v1(jsonb_agg(to_jsonb(r))) s from r group by strategy)
  select coalesce(jsonb_agg((s-'max_drawdown_idr')||jsonb_build_object('strategy',strategy) order by (s->>'net_pnl_idr')::numeric desc,strategy),'[]') into attribution from groups;
  with r as(select value from jsonb_array_elements(scoped)), eligible as(
    select value from r where value->>'state' not in ('closed','ambiguous_review')
      or ((p_from is null or (value->>'exit_session')::date>=p_from) and (p_to is null or (value->>'exit_session')::date<=p_to))
  ), page as(select value from eligible order by coalesce((value->>'exit_session')::date,(value->>'entry_session')::date) desc nulls last,value->>'id' limit 25 offset (p_page-1)*25)
  select coalesce(jsonb_agg(value-'actionable'-'alternate_pnl'-'alternate_r'-'updated_at'),'[]'),
    (select count(*)>(p_page::bigint*25) from eligible) into trades,has_more from page;
  with r as(select * from jsonb_to_recordset(scoped)x(state text,ambiguous boolean,actionable boolean,id text,exit_session date,realized_pnl_idr numeric,realized_r numeric,alternate_pnl numeric,alternate_r numeric,updated_at timestamptz))
  select coalesce(jsonb_agg(jsonb_build_object('realized_pnl_idr',realized_pnl_idr,'realized_r',realized_r) order by exit_session,case when p_mode='actual' then updated_at else null end,id),'[]'),
    coalesce(jsonb_agg(jsonb_build_object('realized_pnl_idr',case when ambiguous then alternate_pnl else realized_pnl_idr end,'realized_r',case when ambiguous then alternate_r else realized_r end) order by exit_session,case when p_mode='actual' then updated_at else null end,id),'[]')
    into sl_rows,tp_rows from r where (state='closed' and actionable or ambiguous) and (p_from is null or exit_session>=p_from) and (p_to is null or exit_session<=p_to);
  if p_mode='paper' then
    as_of:=model.last_session; updated:=model.updated_at;
    select max(session_date) into latest_scan from public.scan_runs where data_mode=dm and status<>'failed';
    coverage:=case when model.owner_id is null or model.last_session is null then 'missing'
      when (statuses->>'data_hold')::integer>0 then 'partial'
      when as_of<latest_scan then 'stale' else 'complete' end;
  else
    select max((x->>'exit_session')::date),max((x->>'updated_at')::timestamptz) into as_of,updated from jsonb_array_elements(scoped)x;
    coverage:='complete';
  end if;
  return jsonb_build_object('contract_version',1,'mode',p_mode,'data_mode',dm,'basis','IDR','cohort_date','exit_session_Asia_Jakarta',
    'model_version',case when p_mode='paper' then 'close-signal-risk-v1' else null end,'from',p_from,'to',p_to,'primary_strategy',p_strategy,
    'exit_key',case when p_mode='paper' then p_exit_key else null end,'exit_version',p_exit_version,'exit_snapshot',p_exit_snapshot,
    'as_of_session',as_of,'updated_at',updated,'coverage_status',coverage,'summary',summary,'statuses',statuses,'curve',curve,
    'strategies',attribution,'trades',trades,'paging',jsonb_build_object('page',p_page,'page_size',25,'has_more',has_more),
    'sensitivities',jsonb_build_object('sl_first',public.trade_reporting_summary_v1(sl_rows),'tp_first',public.trade_reporting_summary_v1(tp_rows)));
end $$;
revoke all on function public.read_trade_reporting_v1(text,date,date,text,text,integer,text,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.read_trade_reporting_v1(text,date,date,text,text,integer,text,jsonb) to authenticated;

create function public.read_paper_trade_v1(p_trade_id text) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare owner uuid:=auth.uid(); dm text; t public.paper_trades; tr jsonb; events jsonb; begin
  if owner is null or not public.is_app_owner() then raise exception 'owner_required' using errcode='42501'; end if;
  select data_mode into strict dm from public.deployment_settings where singleton;
  select * into t from public.paper_trades where id=p_trade_id and owner_id=owner and data_mode=dm and model_version='close-signal-risk-v1';
  if not found then return null; end if;
  select to_jsonb(r)-'actionable'-'alternate_pnl'-'alternate_r'-'updated_at' into tr
    from public.trade_reporting_rows_v1(owner,dm,'paper',case when t.exit_mode='fixed_rr' then 'fixed2r' else 'ma10' end,null,null,null)r where id=p_trade_id;
  select coalesce(jsonb_agg(jsonb_build_object('event_id',trade_id||':'||event_index,'event_type',event_type,'session_date',session_date,'payload',payload) order by event_index),'[]') into events
    from public.paper_events where trade_id=p_trade_id and owner_id=owner and model_version=t.model_version;
  return jsonb_build_object('contract_version',1,'mode','paper','data_mode',dm,'model_version',t.model_version,'events',events,
    'trade',tr||jsonb_build_object('current_stop',t.current_stop,'entry_fee_idr',(t.details->>'entry_fee_idr')::numeric,
    'exit_fee_idr',(t.details->>'exit_fee_idr')::numeric,'exit_mode',t.exit_mode,'exit_key',case when t.exit_mode='fixed_rr' then 'fixed2r' else 'ma10' end,
    'config_snapshot',t.details->'experiment','source_digest',t.details#>>'{signal,input_digest}',
    'alternate_pnl_idr',(t.details->>'alternate_net_pnl')::numeric,'alternate_r',t.alternate_r));
end $$;
revoke all on function public.read_paper_trade_v1(text) from public,anon,authenticated,service_role;
grant execute on function public.read_paper_trade_v1(text) to authenticated;

create function public.read_signal_evaluation_v1(p_from date default null,p_to date default null,p_strategy text default null,p_page integer default 1)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare owner uuid:=auth.uid(); dm text; rows_json jsonb; strategies jsonb; evaluations jsonb; model public.paper_models; coverage text; latest_scan date; more boolean;
begin
  if owner is null or not public.is_app_owner() then raise exception 'owner_required' using errcode='42501'; end if;
  if p_page is null or p_page<1 or p_page>1000000 or p_from>p_to then raise exception 'invalid_reporting_filter' using errcode='22023'; end if;
  select data_mode into strict dm from public.deployment_settings where singleton;
  select * into model from public.paper_models where owner_id=owner and data_mode=dm and model_version='close-signal-risk-v1';
  select coalesce(jsonb_agg(payload),'[]') into rows_json from public.signal_evaluations
    where owner_id=owner and data_mode=dm and model_version='close-signal-risk-v1'
      and(p_from is null or signal_session>=p_from) and(p_to is null or signal_session<=p_to) and(p_strategy is null or strategy=p_strategy);
  with rows as(select value from jsonb_array_elements(rows_json)), cells as(
    select r.value->>'strategy' strategy,k.key metric,k.value#>>'{}' state,coalesce(r.value->'exclusion_reasons'->>k.key,'unspecified') exclusion
    from rows r cross join lateral jsonb_each(r.value->'results')k
  ), grouped as(select strategy,metric,count(*) filter(where state='won') wins,count(*) filter(where state in('won','lost')) assessed,
    count(*) filter(where state='pending') pending,count(*) filter(where state='ambiguous') ambiguous,count(*) filter(where state='data_hold') data_hold,
    count(*) filter(where state='excluded') excluded from cells group by strategy,metric), cell_json as(
    select g.strategy,g.metric,jsonb_build_object('wins',g.wins,'assessed',g.assessed,'pending',g.pending,'ambiguous',g.ambiguous,'data_hold',g.data_hold,'excluded',g.excluded,
      'win_rate',case when g.assessed>0 then g.wins::numeric/g.assessed else null end,'excluded_reasons',coalesce((select jsonb_object_agg(exclusion,n) from(
        select exclusion,count(*) n from cells c where c.strategy=g.strategy and c.metric=g.metric and c.state='excluded' group by exclusion)x),'{}')) val from grouped g
  ), strat as(select strategy,jsonb_object_agg(metric,val) cells from cell_json group by strategy)
  select coalesce(jsonb_agg(jsonb_build_object('strategy',s.strategy,'signals',(select count(*) from rows where value->>'strategy'=s.strategy),'cells',s.cells) order by s.strategy),'[]') into strategies from strat s;
  with rows as(select value from jsonb_array_elements(rows_json)), page as(select value from rows order by value->>'signal_session' desc,value->>'signal_id' limit 25 offset(p_page-1)*25)
  select coalesce(jsonb_agg((value-'signal'-'input_digests'-'provider_symbol'-'data_mode'-'model_version')||jsonb_build_object('entry_price',(value->>'entry_price')::numeric,'initial_stop',(value->>'initial_stop')::numeric,'target_1r',(value->>'target_1r')::numeric,'target_2r',(value->>'target_2r')::numeric)),'[]'),(select count(*)>p_page::bigint*25 from rows) into evaluations,more from page;
  select max(session_date) into latest_scan from public.scan_runs where data_mode=dm and status<>'failed';
  coverage:=case when model.owner_id is null or model.last_session is null then 'missing'
    when exists(select 1 from jsonb_array_elements(rows_json)r cross join lateral jsonb_each_text(r->'results')v where v.value='data_hold') then 'partial'
    when model.last_session<latest_scan then 'stale' else 'complete' end;
  return jsonb_build_object('contract_version',1,'mode','signal_evaluation','data_mode',dm,'basis','IDR','cohort_date','signal_session',
    'model_version','close-signal-risk-v1','from',p_from,'to',p_to,'primary_strategy',p_strategy,'exit_key',null,'exit_version',null,'exit_snapshot',null,
    'as_of_session',model.last_session,'updated_at',model.updated_at,'coverage_status',coverage,'strategies',strategies,'evaluations',evaluations,
    'paging',jsonb_build_object('page',p_page,'page_size',25,'has_more',more));
end $$;
revoke all on function public.read_signal_evaluation_v1(date,date,text,integer) from public,anon,authenticated,service_role;
grant execute on function public.read_signal_evaluation_v1(date,date,text,integer) to authenticated;

commit;
