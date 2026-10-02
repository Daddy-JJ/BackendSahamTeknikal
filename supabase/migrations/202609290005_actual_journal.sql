-- M4 actual journal. Apply after 202609290004, on development first.
-- No seed, fixture, or existing trade mutation is performed by this migration.
begin;

create table public.actual_trades (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id),
  data_mode text not null check (data_mode in ('live','fixture')),
  ticker text not null check (ticker ~ '^[A-Z0-9]{2,12}$'),
  primary_strategy text not null check (primary_strategy in
    ('MACD_EMA200_V1','FRACTAL_BREAKOUT_V1','RS_BREAKOUT_V1','PULLBACK_RECLAIM_V1')),
  signal_id text references public.signals(id),
  exit_policy_snapshot jsonb not null check (jsonb_typeof(exit_policy_snapshot) = 'object'),
  initial_stop numeric(20,4) not null check (initial_stop > 0 and initial_stop < 'Infinity'::numeric),
  current_stop numeric(20,4) not null check (current_stop > 0 and current_stop < 'Infinity'::numeric),
  initial_risk_idr numeric(28,4),
  provisional_risk_idr numeric(28,4) not null default 0,
  status text not null default 'draft' check (status in ('draft','open','closed')),
  revision integer not null default 1 check (revision > 0),
  open_quantity bigint not null default 0 check (open_quantity >= 0),
  remaining_cost_idr numeric(28,4) not null default 0,
  realized_pnl_idr numeric(28,4) not null default 0,
  realized_r numeric(28,12),
  fee_total_idr numeric(28,4) not null default 0,
  entry_finalized_at timestamptz,
  closed_at timestamptz,
  created_at timestamptz not null default now(),
  unique (id, owner_id),
  check ((entry_finalized_at is null and initial_risk_idr is null)
      or (entry_finalized_at is not null and initial_risk_idr > 0))
);
create index actual_trades_owner_status on public.actual_trades(owner_id, data_mode, status, closed_at desc);

create table public.actual_fills (
  id uuid primary key default gen_random_uuid(),
  trade_id uuid not null,
  owner_id uuid not null,
  side text not null check (side in ('buy','sell')),
  filled_at timestamptz not null check (isfinite(filled_at)),
  sequence bigint generated always as identity unique,
  quantity bigint not null check (quantity > 0),
  price_idr numeric(20,4) not null check (price_idr > 0 and price_idr < 'Infinity'::numeric),
  fee_idr numeric(20,4) not null check (fee_idr >= 0 and fee_idr < 'Infinity'::numeric),
  fee_status text not null check (fee_status in ('actual','estimated')),
  created_at timestamptz not null default now(),
  foreign key (trade_id, owner_id) references public.actual_trades(id, owner_id),
  unique (id, trade_id, owner_id)
);
create index actual_fills_trade_order on public.actual_fills(trade_id, filled_at, id);

create table public.actual_fill_corrections (
  sequence bigint generated always as identity primary key,
  fill_id uuid not null references public.actual_fills(id),
  filled_at timestamptz not null check (isfinite(filled_at)),
  trade_id uuid not null,
  owner_id uuid not null,
  quantity bigint not null check (quantity > 0),
  price_idr numeric(20,4) not null check (price_idr > 0 and price_idr < 'Infinity'::numeric),
  fee_idr numeric(20,4) not null check (fee_idr >= 0 and fee_idr < 'Infinity'::numeric),
  fee_status text not null check (fee_status in ('actual','estimated')),
  reason text not null check (length(trim(reason)) between 3 and 500),
  created_at timestamptz not null default now(),
  foreign key (trade_id, owner_id) references public.actual_trades(id, owner_id),
  foreign key (fill_id, trade_id, owner_id)
    references public.actual_fills(id, trade_id, owner_id)
);
create index actual_corrections_latest on public.actual_fill_corrections(fill_id, sequence desc);

create table public.actual_stop_events (
  id uuid primary key default gen_random_uuid(),
  trade_id uuid not null,
  owner_id uuid not null,
  old_stop numeric(20,4) not null,
  new_stop numeric(20,4) not null check (new_stop > 0 and new_stop < 'Infinity'::numeric),
  reason text not null check (length(trim(reason)) between 3 and 500),
  occurred_at timestamptz not null default now(),
  foreign key (trade_id, owner_id) references public.actual_trades(id, owner_id)
);
create table public.actual_notes (
  id uuid primary key default gen_random_uuid(),
  trade_id uuid not null,
  owner_id uuid not null,
  body text not null check (length(trim(body)) between 1 and 4000),
  created_at timestamptz not null default now(),
  foreign key (trade_id, owner_id) references public.actual_trades(id, owner_id)
);
create table public.actual_trade_tags (
  trade_id uuid not null,
  owner_id uuid not null,
  tag text not null check (tag ~ '^[A-Za-z0-9_-]{2,40}$'),
  created_at timestamptz not null default now(),
  primary key (trade_id, tag),
  foreign key (trade_id, owner_id) references public.actual_trades(id, owner_id)
);
create table public.actual_journal_requests (
  owner_id uuid not null references auth.users(id),
  request_id uuid not null,
  request jsonb not null,
  result jsonb not null,
  created_at timestamptz not null default now(),
  primary key (owner_id, request_id)
);

do $$
declare t text;
begin
  foreach t in array array['actual_trades','actual_fills','actual_fill_corrections',
    'actual_stop_events','actual_notes','actual_trade_tags','actual_journal_requests']
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from public, anon, authenticated, service_role', t);
    execute format('grant select on public.%I to authenticated, service_role', t);
    execute format('create policy owner_read on public.%I for select to authenticated
      using ((select public.is_app_owner()) and owner_id = (select auth.uid()))', t);
  end loop;
end $$;
revoke all on sequence public.actual_fills_sequence_seq, public.actual_fill_corrections_sequence_seq from public, anon, authenticated;

-- Event rows never change. Corrections append a new revision instead.
do $$
declare t text;
begin
  foreach t in array array['actual_fills','actual_fill_corrections','actual_stop_events',
    'actual_notes','actual_trade_tags','actual_journal_requests']
  loop
    execute format('create trigger immutable_record before update or delete on public.%I
      for each row execute function public.reject_immutable_mutation()', t);
  end loop;
end $$;

-- Rebuild the monetary ledger from effective fill revisions in one transaction.
-- Buy fees enter weighted-average cost; sell fees reduce realized P&L.
create function public.recalculate_actual_trade(p_trade_id uuid, p_restate_risk boolean default false)
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
  v_trade public.actual_trades;
  v_fill record;
  v_held bigint := 0;
  v_cost numeric := 0;
  v_realized numeric := 0;
  v_risk numeric := 0;
  v_fees numeric := 0;
  v_alloc numeric;
  v_sold boolean := false;
  v_last_sell timestamptz;
begin
  select * into strict v_trade from public.actual_trades where id = p_trade_id for update;
  for v_fill in
    select f.side, coalesce(c.filled_at,f.filled_at) as filled_at,
      coalesce(c.quantity, f.quantity) as quantity,
      coalesce(c.price_idr, f.price_idr) as price_idr,
      coalesce(c.fee_idr, f.fee_idr) as fee_idr
    from public.actual_fills f
    left join lateral (
      select quantity, price_idr, fee_idr, filled_at from public.actual_fill_corrections
      where fill_id = f.id order by sequence desc limit 1
    ) c on true
    where f.trade_id = p_trade_id
    order by coalesce(c.filled_at,f.filled_at), f.sequence
  loop
    v_fees := v_fees + v_fill.fee_idr;
    if v_fill.side = 'buy' then
      if v_sold
      then raise exception 'buy_after_exit_or_finalize' using errcode = '23514'; end if;
      if v_fill.price_idr <= v_trade.initial_stop then
        raise exception 'buy_below_initial_stop' using errcode = '23514';
      end if;
      v_held := v_held + v_fill.quantity;
      v_cost := v_cost + v_fill.quantity * v_fill.price_idr + v_fill.fee_idr;
      v_risk := v_risk + v_fill.quantity * (v_fill.price_idr - v_trade.initial_stop);
    else
      v_sold := true;
      if v_trade.entry_finalized_at is null or v_fill.quantity > v_held then
        raise exception 'entry_not_finalized_or_oversell' using errcode = '23514';
      end if;
      v_alloc := v_cost * v_fill.quantity / v_held;
      v_realized := v_realized + v_fill.quantity * v_fill.price_idr - v_fill.fee_idr - v_alloc;
      v_cost := v_cost - v_alloc;
      v_held := v_held - v_fill.quantity;
      v_last_sell := v_fill.filled_at;
    end if;
  end loop;
  if v_trade.entry_finalized_at is not null then
    if v_risk <= 0 then raise exception 'invalid_initial_risk' using errcode = '23514'; end if;
    if v_trade.initial_risk_idr is distinct from v_risk and not p_restate_risk then
      raise exception 'initial_risk_immutable' using errcode = '23514';
    end if;
  end if;
  update public.actual_trades set
    initial_risk_idr = case when entry_finalized_at is not null then v_risk else null end,
    provisional_risk_idr = v_risk,
    open_quantity = v_held,
    remaining_cost_idr = case when v_held = 0 then 0 else v_cost end,
    realized_pnl_idr = v_realized,
    realized_r = case when entry_finalized_at is not null and v_held = 0
      then round(round(v_realized,4) / v_risk,12) else null end,
    fee_total_idr = v_fees,
    status = case when v_held > 0 then 'open'
      when entry_finalized_at is null then 'draft' else 'closed' end,
    closed_at = case when entry_finalized_at is not null and v_held = 0
      then v_last_sell else null end
  where id = p_trade_id;
  return jsonb_build_object('trade_id',p_trade_id,'status',
    case when v_held > 0 then 'open'
      when v_trade.entry_finalized_at is null then 'draft' else 'closed' end,
    'open_quantity',v_held,'remaining_cost_idr',round(v_cost,4),
    'realized_pnl_idr',round(v_realized,4),'fee_total_idr',v_fees,
    'initial_risk_idr',case when v_trade.entry_finalized_at is not null then v_risk else null end,
    'provisional_risk_idr',v_risk,
    'realized_r',case when v_trade.entry_finalized_at is not null and v_held = 0
      then round(round(v_realized,4) / v_risk,12) else null end);
end $$;
revoke all on function public.recalculate_actual_trade(uuid,boolean)
  from public, anon, authenticated, service_role;

create function public.actual_entry_risk(p_trade_id uuid, p_stop numeric)
returns numeric language sql stable security definer set search_path = ''
as $$
  select sum(coalesce(c.quantity,f.quantity) *
    (coalesce(c.price_idr,f.price_idr) - p_stop))
  from public.actual_fills f
  left join lateral (
    select quantity, price_idr from public.actual_fill_corrections
    where fill_id=f.id order by sequence desc limit 1
  ) c on true
  where f.trade_id=p_trade_id and f.side='buy';
$$;
revoke all on function public.actual_entry_risk(uuid,numeric)
  from public, anon, authenticated, service_role;
-- Decimal strings are supported to preserve exact input across JSON clients.
create function public.valid_actual_decimal(p_value text, p_allow_zero boolean default false)
returns boolean language sql immutable set search_path = ''
as $$
  select coalesce(case when p_value ~ '^[0-9]{1,16}(\.[0-9]{1,4})?$'
    then case when p_allow_zero then p_value::numeric >= 0 else p_value::numeric > 0 end
    else false end, false);
$$;
revoke all on function public.valid_actual_decimal(text,boolean)
  from public, anon, authenticated, service_role;

create function public.apply_actual_journal(
  p_action text, p_trade_id uuid, p_payload jsonb, p_request_id uuid
) returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
  v_owner uuid := auth.uid();
  v_request jsonb := jsonb_build_object('action',p_action,'trade_id',p_trade_id,'payload',p_payload);
  v_prior public.actual_journal_requests;
  v_trade public.actual_trades;
  v_fill public.actual_fills;
  v_mode text;
  v_risk numeric;
  v_reason text;
  v_result jsonb;
  v_ledger jsonb;
  v_before jsonb;
  v_allowed text[];
  v_exit jsonb;
begin
  if v_owner is null or not public.is_app_owner() then
    raise exception 'owner_required' using errcode = '42501';
  end if;
  if p_request_id is null or jsonb_typeof(p_payload) is distinct from 'object' then
    raise exception 'invalid_journal_request' using errcode = '22023';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('idx:journal:' || v_owner::text, 0));
  select * into v_prior from public.actual_journal_requests
    where owner_id = v_owner and request_id = p_request_id;
  if found then
    if v_prior.request is distinct from v_request then
      raise exception 'idempotency_conflict' using errcode = '23514';
    end if;
    return v_prior.result;
  end if;
  v_allowed := case p_action
    when 'create' then array['ticker','primary_strategy','signal_id','initial_stop','exit_policy_snapshot']
    when 'fill' then array['expected_revision','side','quantity','price_idr','fee_idr','fee_status','filled_at']
    when 'finalize' then array['expected_revision']
    when 'stop' then array['expected_revision','new_stop','reason']
    when 'note' then array['expected_revision','body']
    when 'tag' then array['expected_revision','tag']
    when 'correct_fill' then array['expected_revision','fill_id','quantity','price_idr','fee_idr',
      'fee_status','reason','restate_initial_risk','filled_at'] end;
  if v_allowed is null or (p_payload - v_allowed) <> '{}'::jsonb then
    raise exception 'unsupported_action_or_field' using errcode = '22023';
  end if;
  if p_action in ('fill','correct_fill') then
    if not public.valid_actual_decimal(p_payload->>'price_idr')
       or not public.valid_actual_decimal(p_payload->>'fee_idr',true)
       or coalesce(p_payload->>'quantity','') !~ '^[1-9][0-9]{0,18}$'
       or coalesce(p_payload->>'fee_status','') not in ('actual','estimated') then
      raise exception 'invalid_fill_values' using errcode = '22023';
    end if;
  end if;
  -- Shared lock keeps deployment mode fixed throughout this mutation.
  select data_mode into strict v_mode from public.deployment_settings where singleton for share;
  if p_action = 'create' then
    v_exit := p_payload->'exit_policy_snapshot';
    if p_trade_id is not null
       or coalesce(p_payload->>'ticker','') !~ '^[A-Z0-9]{2,12}$'
       or coalesce(p_payload->>'primary_strategy','') not in
         ('MACD_EMA200_V1','FRACTAL_BREAKOUT_V1','RS_BREAKOUT_V1','PULLBACK_RECLAIM_V1')
       or not public.valid_actual_decimal(p_payload->>'initial_stop')
       or jsonb_typeof(p_payload->'exit_policy_snapshot') is distinct from 'object'
       or jsonb_typeof(v_exit->'version') is distinct from 'string'
       or coalesce(length(trim(v_exit->>'version')),0) not between 1 and 100
       or coalesce(v_exit->>'mode','') not in ('fixed_rr','ma_close','manual')
    then raise exception 'invalid_trade_draft' using errcode = '22023'; end if;
    if (v_exit - array['version','mode','target_r','ma_type','period','config_hash']) <> '{}'::jsonb
       or (v_exit->>'mode'='fixed_rr' and
          (not public.valid_actual_decimal(v_exit->>'target_r')
           or v_exit ?| array['ma_type','period']))
       or (v_exit->>'mode'='ma_close' and
          (coalesce(v_exit->>'ma_type','') not in ('SMA','EMA')
           or coalesce(v_exit->>'period','') not in ('5','10','20')
           or (v_exit->'target_r' is not null and v_exit->'target_r' <> 'null'::jsonb)))
       or (v_exit->>'mode'='manual' and v_exit ?| array['target_r','ma_type','period']) then
      raise exception 'invalid_exit_policy' using errcode = '22023';
    end if;
    if p_payload->>'signal_id' is not null and not exists (
      select 1 from public.signals where id = p_payload->>'signal_id'
        and ticker = p_payload->>'ticker'
        and strategy = p_payload->>'primary_strategy' and data_mode = v_mode
    ) then raise exception 'signal_context_mismatch' using errcode = '22023'; end if;
    insert into public.actual_trades(owner_id,data_mode,ticker,primary_strategy,
      signal_id,exit_policy_snapshot,initial_stop,current_stop)
    values (v_owner,v_mode,p_payload->>'ticker',p_payload->>'primary_strategy',
      p_payload->>'signal_id',p_payload->'exit_policy_snapshot',
      (p_payload->>'initial_stop')::numeric,(p_payload->>'initial_stop')::numeric)
    returning * into v_trade;
    v_ledger := jsonb_build_object('status','draft','open_quantity',0,'provisional_risk_idr',0);
  else
    select * into v_trade from public.actual_trades
      where id = p_trade_id and owner_id = v_owner for update;
    if not found then raise exception 'trade_not_found' using errcode = '22023'; end if;
    v_before := to_jsonb(v_trade);
    if v_trade.data_mode is distinct from v_mode then
      raise exception 'journal_mode_changed' using errcode = '23514';
    end if;
    if coalesce(p_payload->>'expected_revision','') !~ '^[1-9][0-9]{0,9}$' then
      raise exception 'invalid_expected_revision' using errcode = '22023'; end if;
    if (p_payload->>'expected_revision')::integer is distinct from v_trade.revision then
      raise exception 'revision_conflict' using errcode = '40001';
    end if;
    if p_action = 'fill' then
      if coalesce(p_payload->>'side','') not in ('buy','sell')
         or (p_payload->>'quantity')::bigint <= 0
         or (p_payload->>'price_idr')::numeric <= 0
         or (p_payload->>'fee_idr')::numeric < 0
         or p_payload->>'fee_status' not in ('actual','estimated')
         or p_payload->>'filled_at' is null
      then raise exception 'invalid_fill' using errcode = '22023'; end if;
      if p_payload->>'side' = 'buy' and
        (v_trade.entry_finalized_at is not null or
          (p_payload->>'price_idr')::numeric <= v_trade.initial_stop)
      then raise exception 'entry_batch_closed_or_stop_invalid' using errcode = '23514'; end if;
      if p_payload->>'side' = 'sell' then
        if v_trade.open_quantity < (p_payload->>'quantity')::bigint then
          raise exception 'oversell' using errcode = '23514';
        end if;
        if v_trade.entry_finalized_at is null then
          select public.actual_entry_risk(p_trade_id,v_trade.initial_stop) into v_risk;
          if v_risk is null or v_risk <= 0 then
            raise exception 'invalid_initial_risk' using errcode = '23514';
          end if;
          update public.actual_trades set entry_finalized_at=now(),
            initial_risk_idr=v_risk where id=p_trade_id;
        end if;
      end if;
      if not isfinite((p_payload->>'filled_at')::timestamptz) then
        raise exception 'invalid_fill_time' using errcode = '22023'; end if;
      insert into public.actual_fills(trade_id,owner_id,side,filled_at,quantity,
        price_idr,fee_idr,fee_status)
      values (p_trade_id,v_owner,p_payload->>'side',
        (p_payload->>'filled_at')::timestamptz,(p_payload->>'quantity')::bigint,
        (p_payload->>'price_idr')::numeric,(p_payload->>'fee_idr')::numeric,
        p_payload->>'fee_status') returning * into v_fill;
      v_ledger := public.recalculate_actual_trade(p_trade_id);
      v_ledger := v_ledger || jsonb_build_object('fill_id',v_fill.id);
    elsif p_action = 'finalize' then
      if v_trade.entry_finalized_at is not null or v_trade.open_quantity = 0 then
        raise exception 'cannot_finalize' using errcode = '23514'; end if;
      select public.actual_entry_risk(p_trade_id,v_trade.initial_stop) into v_risk;
      if v_risk is null or v_risk <= 0 then
        raise exception 'invalid_initial_risk' using errcode = '23514'; end if;
      update public.actual_trades set entry_finalized_at=now(),
        initial_risk_idr=v_risk where id=p_trade_id;
      v_ledger := public.recalculate_actual_trade(p_trade_id);
    elsif p_action = 'stop' then
      v_reason := trim(p_payload->>'reason');
      if v_trade.entry_finalized_at is null or v_trade.status='closed'
        or not public.valid_actual_decimal(p_payload->>'new_stop')
        or coalesce(length(v_reason),0) not between 3 and 500
      then raise exception 'invalid_stop_change' using errcode = '22023'; end if;
      insert into public.actual_stop_events(trade_id,owner_id,old_stop,new_stop,reason)
      values (p_trade_id,v_owner,v_trade.current_stop,(p_payload->>'new_stop')::numeric,v_reason);
      update public.actual_trades set current_stop=(p_payload->>'new_stop')::numeric
        where id=p_trade_id;
      v_ledger := jsonb_build_object('initial_risk_idr',v_trade.initial_risk_idr,
        'current_stop', (p_payload->>'new_stop')::numeric);
    elsif p_action = 'note' then
      if coalesce(length(trim(p_payload->>'body')),0) not between 1 and 4000 then
        raise exception 'invalid_note' using errcode = '22023'; end if;
      insert into public.actual_notes(trade_id,owner_id,body)
        values (p_trade_id,v_owner,trim(p_payload->>'body'));
      v_ledger := jsonb_build_object('note_added',true);
    elsif p_action = 'tag' then
      if coalesce(p_payload->>'tag','') !~ '^[A-Za-z0-9_-]{2,40}$' then
        raise exception 'invalid_tag' using errcode = '22023'; end if;
      insert into public.actual_trade_tags(trade_id,owner_id,tag)
        values (p_trade_id,v_owner,p_payload->>'tag')
        on conflict (trade_id,tag) do nothing;
      v_ledger := jsonb_build_object('tag',p_payload->>'tag');
    elsif p_action = 'correct_fill' then
      v_reason := trim(p_payload->>'reason');
      select * into v_fill from public.actual_fills
        where id=(p_payload->>'fill_id')::uuid and trade_id=p_trade_id and owner_id=v_owner;
      if not found or coalesce(length(v_reason),0) not between 3 and 500
         or (p_payload->>'quantity')::bigint <= 0
         or (p_payload->>'price_idr')::numeric <= 0
         or (p_payload->>'fee_idr')::numeric < 0
         or p_payload->>'fee_status' not in ('actual','estimated')
      then raise exception 'invalid_fill_correction' using errcode = '22023'; end if;
      if p_payload ? 'filled_at' and
        (p_payload->>'filled_at' is null or not isfinite((p_payload->>'filled_at')::timestamptz)) then
        raise exception 'invalid_fill_time' using errcode = '22023'; end if;
      if p_payload ? 'restate_initial_risk' and
        jsonb_typeof(p_payload->'restate_initial_risk') is distinct from 'boolean' then
        raise exception 'invalid_restatement_flag' using errcode = '22023'; end if;
      insert into public.actual_fill_corrections(fill_id,trade_id,owner_id,filled_at,
        quantity,price_idr,fee_idr,fee_status,reason)
      values (v_fill.id,p_trade_id,v_owner,
        coalesce((p_payload->>'filled_at')::timestamptz,
          (select filled_at from public.actual_fill_corrections where fill_id=v_fill.id
            order by sequence desc limit 1),v_fill.filled_at),
        (p_payload->>'quantity')::bigint,
        (p_payload->>'price_idr')::numeric,(p_payload->>'fee_idr')::numeric,
        p_payload->>'fee_status',v_reason);
      v_ledger := public.recalculate_actual_trade(p_trade_id,
        v_fill.side='buy' and (p_payload->>'restate_initial_risk')::boolean is true);
      v_ledger := v_ledger || jsonb_build_object('corrected_fill_id',v_fill.id);
    else
      raise exception 'unsupported_journal_action' using errcode = '22023';
    end if;
    update public.actual_trades set revision=revision+1 where id=p_trade_id
      returning * into v_trade;
  end if;
  v_result := jsonb_build_object('trade_id',v_trade.id,'revision',v_trade.revision,
    'action',p_action,'ledger',v_ledger);
  insert into public.actual_journal_requests(owner_id,request_id,request,result)
    values(v_owner,p_request_id,v_request,v_result);
  insert into public.audit_events(owner_id,entity_id,action,details)
    values(v_owner,v_trade.id::text,'actual_journal_' || p_action,
      jsonb_build_object('request_id',p_request_id,'revision',v_trade.revision,
        'payload',p_payload,'before',v_before,'result',v_result));
  return v_result;
end $$;
revoke all on function public.apply_actual_journal(text,uuid,jsonb,uuid)
  from public, anon, service_role;
grant execute on function public.apply_actual_journal(text,uuid,jsonb,uuid)
  to authenticated;
-- Actual-only closed cohort, filtered by exit date in Asia/Jakarta.
-- Open/draft counts describe current positions under the same strategy/version filter.
create function public.actual_journal_analytics(
  p_from date default null, p_to date default null,
  p_strategy text default null, p_exit_version text default null,
  p_exit_snapshot jsonb default null
) returns jsonb language plpgsql stable security definer set search_path = ''
as $$
declare
  v_owner uuid := auth.uid();
  v_mode text;
  v record;
begin
  if v_owner is null or not public.is_app_owner() then
    raise exception 'owner_required' using errcode = '42501';
  end if;
  if p_from > p_to then
    raise exception 'invalid_cohort_range' using errcode = '22023';
  end if;
  select data_mode into strict v_mode from public.deployment_settings where singleton;
  with scoped as (
    select t.* from public.actual_trades t
    where t.owner_id=v_owner and t.data_mode=v_mode
      and (p_strategy is null or t.primary_strategy=p_strategy)
      and (p_exit_version is null or t.exit_policy_snapshot->>'version'=p_exit_version)
      and (p_exit_snapshot is null or t.exit_policy_snapshot=p_exit_snapshot)
  ), closed as (
    select * from scoped
    where status='closed'
      and (p_from is null or (closed_at at time zone 'Asia/Jakarta')::date >= p_from)
      and (p_to is null or (closed_at at time zone 'Asia/Jakarta')::date <= p_to)
  )
  select
    (select count(*) from scoped where status='open') as open_count,
    (select count(*) from scoped where status='draft') as draft_count,
    (select count(distinct f.trade_id) from public.actual_fills f
      join closed c on c.id=f.trade_id
      left join lateral (
        select fee_status from public.actual_fill_corrections
        where fill_id=f.id order by sequence desc limit 1
      ) correction on true
      where coalesce(correction.fee_status,f.fee_status)='estimated'
    ) as estimated_fee_trades,
    count(*) as closed_count,
    count(*) filter (where round(realized_pnl_idr,4)>0) as wins,
    count(*) filter (where round(realized_pnl_idr,4)<0) as losses,
    count(*) filter (where round(realized_pnl_idr,4)=0) as breakeven,
    coalesce(sum(realized_pnl_idr),0) as net_pnl_idr,
    coalesce(sum(realized_pnl_idr) filter (where realized_pnl_idr>0),0) as positive_pnl_idr,
    coalesce(sum(realized_pnl_idr) filter (where realized_pnl_idr<0),0) as negative_pnl_idr,
    avg(realized_r) as expectancy_r,
    avg(realized_pnl_idr) filter (where realized_pnl_idr>0) as mean_win_idr,
    avg(realized_pnl_idr) filter (where realized_pnl_idr<0) as mean_loss_idr
  into v from closed;
  return jsonb_build_object(
    'mode','actual','data_mode',v_mode,'basis','IDR',
    'cohort_date','exit_session_Asia_Jakarta',
    'from',p_from,'to',p_to,'primary_strategy',p_strategy,
    'exit_version',p_exit_version,'exit_snapshot',p_exit_snapshot,
    'fee_quality',case when v.estimated_fee_trades>0 then 'includes_estimates'
      when v.closed_count=0 then 'no_closed' else 'actual' end,
    'closed',v.closed_count,'open',v.open_count,'draft',v.draft_count,
    'estimated_fee_trades',v.estimated_fee_trades,
    'wins',v.wins,'losses',v.losses,'breakeven',v.breakeven,
    'net_pnl_idr',v.net_pnl_idr,
    'win_rate',case when v.closed_count>0 then v.wins::numeric/v.closed_count else null end,
    'expectancy_r',v.expectancy_r,
    'profit_factor',case when v.losses>0
      then v.positive_pnl_idr / abs(v.negative_pnl_idr) else null end,
    'profit_factor_status',case when v.closed_count=0 then 'no_closed'
      when v.losses=0 then 'no_losses' else 'defined' end,
    'payoff_ratio',case when v.wins>0 and v.losses>0
      then v.mean_win_idr / abs(v.mean_loss_idr) else null end,
    'payoff_status',case when v.closed_count=0 then 'no_closed'
      when v.wins=0 then 'no_wins' when v.losses=0 then 'no_losses'
      else 'defined' end
  );
end $$;
revoke all on function public.actual_journal_analytics(date,date,text,text,jsonb)
  from public, anon, service_role;
grant execute on function public.actual_journal_analytics(date,date,text,text,jsonb)
  to authenticated;
-- Backend-owned export read model: explicit actual mode; no paper fallback.
-- Decimal/quantity strings preserve precision when transported through JSON.
create function public.export_actual_journal(
  p_from date default null, p_to date default null,
  p_strategy text default null, p_exit_version text default null,
  p_exit_snapshot jsonb default null,
  p_after uuid default null, p_limit integer default 200, p_status text default null
) returns jsonb language plpgsql stable security definer set search_path = ''
as $$
declare
  v_owner uuid := auth.uid();
  v_mode text;
  v_rows jsonb;
  v_has_more boolean;
begin
  if v_owner is null or not public.is_app_owner() then
    raise exception 'owner_required' using errcode = '42501'; end if;
  if p_from > p_to or p_limit is null or p_limit not between 1 and 200
    or (p_status is not null and p_status not in ('draft','open','closed')) then
    raise exception 'invalid_export_range_or_limit' using errcode = '22023'; end if;
  select data_mode into strict v_mode from public.deployment_settings where singleton;
  with candidates as (
    select t.* from public.actual_trades t
    where t.owner_id=v_owner and t.data_mode=v_mode
      and (p_after is null or t.id>p_after)
      and (p_status is null or t.status=p_status)
      and (p_strategy is null or t.primary_strategy=p_strategy)
      and (p_exit_version is null or t.exit_policy_snapshot->>'version'=p_exit_version)
      and (p_exit_snapshot is null or t.exit_policy_snapshot=p_exit_snapshot)
      -- With date filters only closed trades belong to the requested exit cohort.
      and (p_from is null or (t.closed_at at time zone 'Asia/Jakarta')::date>=p_from)
      and (p_to is null or (t.closed_at at time zone 'Asia/Jakarta')::date<=p_to)
    order by t.id limit p_limit+1
  ), page as (select * from candidates order by id limit p_limit)
  select coalesce(jsonb_agg(jsonb_build_object(
    'contract_version','actual-journal-export-v1','mode','actual','data_mode',t.data_mode,
    'trade_id',t.id,'revision',t.revision,'ticker',t.ticker,'status',t.status,
    'primary_strategy',t.primary_strategy,'signal_id',t.signal_id,
    'exit_policy_snapshot',t.exit_policy_snapshot,
    'planned_rr',case when t.exit_policy_snapshot->>'mode'='fixed_rr'
      then t.exit_policy_snapshot->>'target_r' else null end,
    'initial_stop',t.initial_stop::text,'current_stop',t.current_stop::text,
    'initial_risk_idr',t.initial_risk_idr::text,
    'provisional_risk_idr',t.provisional_risk_idr::text,
    'open_quantity',t.open_quantity::text,'remaining_cost_idr',t.remaining_cost_idr::text,
    'realized_pnl_idr',t.realized_pnl_idr::text,'realized_r',t.realized_r::text,
    'fee_total_idr',t.fee_total_idr::text,
    'fee_quality',case when not exists(select 1 from public.actual_fills where trade_id=t.id)
      then 'no_fills' when exists(
        select 1 from public.actual_fills f left join lateral (
          select fee_status from public.actual_fill_corrections where fill_id=f.id
            order by sequence desc limit 1
        ) c on true where f.trade_id=t.id and coalesce(c.fee_status,f.fee_status)='estimated'
      ) then 'includes_estimates' else 'actual' end,
    'entry_finalized_at',t.entry_finalized_at,'closed_at',t.closed_at,
    'exit_session', (t.closed_at at time zone 'Asia/Jakarta')::date,
    'tags',coalesce((select jsonb_agg(tag order by tag) from public.actual_trade_tags
      where trade_id=t.id),'[]'::jsonb),
    'notes',coalesce((select jsonb_agg(body order by created_at,id) from public.actual_notes
      where trade_id=t.id),'[]'::jsonb)
  ) order by t.id),'[]'::jsonb), (select count(*)>p_limit from candidates)
  into v_rows,v_has_more from page t;
  return jsonb_build_object('contract_version','actual-journal-export-v1',
    'mode','actual','data_mode',v_mode,'cohort_date','exit_session_Asia_Jakarta',
    'from',p_from,'to',p_to,'primary_strategy',p_strategy,'exit_version',p_exit_version,
    'exit_snapshot',p_exit_snapshot,'status',p_status,'rows',v_rows,'has_more',v_has_more,
    'next_after',case when v_has_more then v_rows->-1->>'trade_id' else null end);
end $$;
revoke all on function public.export_actual_journal(date,date,text,text,jsonb,uuid,integer,text)
  from public,anon,service_role;
grant execute on function public.export_actual_journal(date,date,text,text,jsonb,uuid,integer,text)
  to authenticated;

commit;

