-- Chart-only artifacts and bounded owner reader. No market or ledger mutation.
begin;

create schema chart_private;
revoke all on schema chart_private from public,anon,authenticated,service_role;
create table public.ticker_chart_artifacts_v1 (
  revision text not null check(revision ~ '^[a-f0-9]{64}$'),
  owner_id uuid not null references auth.users(id),
  data_mode text not null check(data_mode in ('live','fixture')),
  ticker text not null check(ticker ~ '^[A-Z0-9_-]{1,20}$'),
  context_kind text not null check(context_kind in ('latest','signal','paper','actual')),
  context_id text,
  view text not null check(view in ('snapshot','followup')),
  data jsonb not null check(jsonb_typeof(data)='object'),
  stored_at timestamptz not null default clock_timestamp(),primary key(owner_id,revision),
  check((context_kind='latest')=(context_id is null)),
  check(context_kind<>'latest' or view='followup'),
  check(context_kind<>'actual' or view='followup')
);
create index ticker_chart_lookup_v1 on public.ticker_chart_artifacts_v1
  (owner_id,data_mode,ticker,context_kind,context_id,view,stored_at desc);
alter table public.ticker_chart_artifacts_v1 enable row level security;
revoke all on public.ticker_chart_artifacts_v1 from public,anon,authenticated,service_role;
-- Direct SELECT is deliberately not granted: every public chart read consumes the shared limiter.
create policy owner_read on public.ticker_chart_artifacts_v1 for select to authenticated
  using ((select public.is_app_owner()) and owner_id=(select auth.uid()));
create trigger immutable_chart before update or delete on public.ticker_chart_artifacts_v1
  for each row execute function public.reject_immutable_mutation();

create table chart_private.read_limits_v1 (
  owner_id uuid primary key references auth.users(id),
  reads timestamptz[] not null default '{}',tokens numeric not null default 10,
  updated_at timestamptz not null default now()
);
create table chart_private.cursors_v1 (
  id uuid primary key default gen_random_uuid(),owner_id uuid not null references auth.users(id),
  revision text not null,
  ticker text not null,data_mode text not null,context_kind text not null,context_id text,view text not null,
  page_limit integer not null,kind text not null check(kind in ('bars','overlays')),
  window_from date not null,window_to date not null,lower_bound date not null,overlay_offset integer not null default 0,
  expires_at timestamptz not null default now()+interval '24 hours',
  foreign key(owner_id,revision) references public.ticker_chart_artifacts_v1(owner_id,revision)
);
create index chart_cursor_expiry_v1 on chart_private.cursors_v1(expires_at);
revoke all on all tables in schema chart_private from public,anon,authenticated,service_role;

create function chart_private.failure_v1(p_code text,p_reason text default null) returns jsonb
language sql set search_path='' as $$
  select jsonb_build_object('contract_version','ticker-chart-v1','success',false,'data',null,
    'error',jsonb_build_object('code',p_code,'message',coalesce(p_reason,p_code),
      'request_id',gen_random_uuid()::text,'retryable',p_code in ('RATE_LIMITED','REVISION_UNAVAILABLE','DATA_UNAVAILABLE','BACKEND_NOT_READY')));
$$;

create function chart_private.consume_limit_v1(p_owner uuid) returns boolean
language plpgsql set search_path='' as $$
declare saved chart_private.read_limits_v1; at_time timestamptz:=clock_timestamp(); remaining numeric; recent timestamptz[];
begin
  insert into chart_private.read_limits_v1(owner_id) values(p_owner) on conflict do nothing;
  select * into saved from chart_private.read_limits_v1 where owner_id=p_owner for update;
  select coalesce(array_agg(x),array[]::timestamptz[]) into recent from unnest(saved.reads) x where x>at_time-interval '60 seconds';
  remaining:=least(10,saved.tokens+greatest(0,extract(epoch from at_time-saved.updated_at)));
  if cardinality(recent)>=60 or remaining<1 then return false; end if;
  update chart_private.read_limits_v1 set reads=array_append(recent,at_time),tokens=remaining-1,updated_at=at_time where owner_id=p_owner;
  return true;
end;
$$;

create function chart_private.context_exists_v1(p_owner uuid,p_mode text,p_ticker text,p_kind text,p_id text) returns boolean
language sql stable set search_path='' as $$
  select case p_kind when 'latest' then p_id is null
    when 'signal' then exists(select 1 from public.signals where id=p_id and data_mode=p_mode and ticker=p_ticker)
    when 'paper' then exists(select 1 from public.paper_trades where id=p_id and owner_id=p_owner and data_mode=p_mode and ticker=p_ticker)
    when 'actual' then exists(select 1 from public.actual_trades where id::text=p_id and owner_id=p_owner and data_mode=p_mode and ticker=p_ticker)
    else false end;
$$;

create function chart_private.exact_keys_v1(p_value jsonb,p_keys text[]) returns boolean
language sql immutable set search_path='' as $$
  select case when jsonb_typeof(p_value)='object' then
    (select array_agg(key order by key) from jsonb_object_keys(p_value) key)=
    (select array_agg(key order by key) from unnest(p_keys) key) else false end;
$$;

create function public.persist_ticker_chart_artifact_v1(p_record jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare d jsonb:=p_record->'data'; old public.ticker_chart_artifacts_v1; o uuid; m text; t text; k text; cid text; vw text; rev text;
  src public.market_series_revisions; element jsonb; seen date[]:='{}'; slot_day date; previous date; ind record; sig public.signals;
begin
  o:=(p_record->>'owner_id')::uuid;m:=p_record->>'data_mode';t:=p_record->>'ticker';k:=p_record->>'context_kind';
  cid:=p_record->>'context_id';vw:=p_record->>'view';rev:=p_record->>'revision';
  perform public.assert_paper_owner_v1(o,m);
  if not chart_private.exact_keys_v1(p_record,array['owner_id','data_mode','ticker','context_kind','context_id','view','revision','data'])
    or not chart_private.exact_keys_v1(d,array['ticker','data_mode','timeframe','exchange','timezone','currency','volume_unit','context','revision','source','signal_source','quality','sessions','bars','gaps','indicators','overlays'])
    or not chart_private.exact_keys_v1(d->'context',array['kind','id','view','signal_session','snapshot_cutoff','model_version','experiment','engine_source_revision'])
    or not chart_private.exact_keys_v1(d->'source',array['series_id','input_digest','resolved_input_digest','resolved_cutoff','provider','provider_version','price_basis','scope','fetched_at','stored_at','history_start','last_market_session'])
    or not chart_private.exact_keys_v1(d->'quality',array['completeness','freshness','expected_session','reasons','warnings'])
    or not chart_private.exact_keys_v1(d->'overlays',array['status','reason','levels','markers','has_more','next_cursor'])
    or pg_column_size(d)>16777216
  then raise exception 'invalid_chart_fields' using errcode='22023'; end if;
  if jsonb_typeof(p_record) is distinct from 'object' or jsonb_typeof(d) is distinct from 'object'
    or t is null or t !~ '^[A-Z0-9_-]{1,20}$' or k is null or k not in ('latest','signal','paper','actual')
    or vw is null or vw not in ('snapshot','followup') or rev is null or rev !~ '^[a-f0-9]{64}$'
    or d->>'revision' is distinct from rev or d->>'ticker' is distinct from t or d->>'data_mode' is distinct from m
    or d->>'timeframe' is distinct from '1d' or d->>'exchange' is distinct from 'XIDX'
    or d->>'timezone' is distinct from 'Asia/Jakarta' or d->>'currency' is distinct from 'IDR' or d->>'volume_unit' is distinct from 'shares'
    or d#>>'{context,kind}' is distinct from k or d#>>'{context,id}' is distinct from cid or d#>>'{context,view}' is distinct from vw
    or not chart_private.context_exists_v1(o,m,t,k,cid)
    or (k='latest' and vw<>'followup') or (k='actual' and vw<>'followup')
    or jsonb_typeof(d->'sessions') is distinct from 'array' or jsonb_array_length(d->'sessions') not between 1 and 10000
    or jsonb_typeof(d->'bars') is distinct from 'array' or jsonb_typeof(d->'gaps') is distinct from 'array'
    or jsonb_typeof(d->'indicators') is distinct from 'object' or jsonb_typeof(d->'overlays') is distinct from 'object'
    or jsonb_typeof(d->'quality') is distinct from 'object'
  then raise exception 'invalid_chart_artifact' using errcode='22023'; end if;
  select * into src from public.market_series_revisions where id=(d#>>'{source,series_id}')::uuid and ticker=t and data_mode=m;
  if not found or src.input_digest is distinct from d#>>'{source,input_digest}'
    or src.provider is distinct from d#>>'{source,provider}' or src.provider_version is distinct from d#>>'{source,provider_version}'
    or src.price_basis is distinct from d#>>'{source,price_basis}'
    or d#>>'{source,scope}' not in ('forward','paper_recovery','fixture')
    or (m='fixture') is distinct from (d#>>'{source,scope}'='fixture')
    or (k in ('latest','signal','actual') and d#>>'{source,scope}'='paper_recovery')
    or (d#>>'{source,scope}'='forward' and (src.namespace<>'forward' or (src.metadata->'provenance')::text like '%reviewed_historical_backfill_v1%'))
    or ((src.namespace like 'paper%' or (src.metadata->'provenance')::text like '%reviewed_historical_backfill_v1%') and d#>>'{source,scope}'<>'paper_recovery')
  then raise exception 'invalid_chart_source' using errcode='22023'; end if;
  if k='signal' then select * into sig from public.signals where id=cid;
  elsif k='paper' then select s.* into sig from public.signals s join public.paper_trades p on p.signal_id=s.id where p.id=cid and p.owner_id=o; end if;
  if k in ('signal','paper') and (sig.id is null or d->'signal_source' is null
    or d#>>'{signal_source,resolved_input_digest}' is distinct from sig.input_digest
    or d#>>'{signal_source,resolved_cutoff}' is distinct from sig.session_date::text
    or d#>>'{signal_source,provider}' is distinct from sig.provider
    or d#>>'{signal_source,price_basis}' is distinct from sig.price_basis
    or d#>>'{context,signal_session}' is distinct from sig.session_date::text
    or (vw='snapshot' and (d#>>'{source,resolved_input_digest}' is distinct from sig.input_digest
      or d#>>'{context,snapshot_cutoff}' is distinct from sig.session_date::text))) then
    raise exception 'chart_snapshot_unproven' using errcode='22023'; end if;
  for element in select value from jsonb_array_elements(d->'sessions') loop
    if jsonb_typeof(element)<>'string' or element#>>'{}' !~ '^\d{4}-\d{2}-\d{2}$' then raise exception 'invalid_chart_session' using errcode='22023'; end if;
    slot_day:=(element#>>'{}')::date;
    if previous is not null and slot_day<=previous then raise exception 'invalid_chart_order' using errcode='22023'; end if;
    if m='live' and not exists(select 1 from public.paper_calendar_days_v1() c where c.day=slot_day) then raise exception 'chart_calendar_unavailable' using errcode='22023'; end if;
    seen:=array_append(seen,slot_day);previous:=slot_day;
  end loop;
  if jsonb_array_length(d->'bars')+jsonb_array_length(d->'gaps')<>cardinality(seen)
    or (select count(distinct x->>'session') from (select value x from jsonb_array_elements(d->'bars') union all select value from jsonb_array_elements(d->'gaps')) s)<>cardinality(seen)
    or exists(select 1 from (select value x from jsonb_array_elements(d->'bars') union all select value from jsonb_array_elements(d->'gaps')) s where not ((x->>'session')::date=any(seen)))
  then raise exception 'invalid_chart_partition' using errcode='22023'; end if;
  for element in select value from jsonb_array_elements(d->'bars') loop
    if not chart_private.exact_keys_v1(element,array['session','open','high','low','close','volume']) then raise exception 'invalid_chart_bar_fields' using errcode='22023'; end if;
    if (select count(*) from jsonb_each(element) where key in ('open','high','low','close') and jsonb_typeof(value)='string' and value#>>'{}' ~ '^\d+(\.\d+)?$' and (value#>>'{}')::numeric>0)<>4
      or jsonb_typeof(element->'volume') is distinct from 'string' or element->>'volume' !~ '^\d+$'
      or (element->>'low')::numeric>least((element->>'open')::numeric,(element->>'close')::numeric)
      or (element->>'high')::numeric<greatest((element->>'open')::numeric,(element->>'close')::numeric)
    then raise exception 'invalid_chart_bar' using errcode='22023'; end if;
  end loop;
  if (select array_agg(key order by key) from jsonb_each(d->'indicators')) is distinct from array['ema200','macd','macd_histogram','macd_signal','sma10']::text[] then
    raise exception 'invalid_chart_indicators' using errcode='22023'; end if;
  for ind in select * from jsonb_each(d->'indicators') loop
    if not chart_private.exact_keys_v1(ind.value,array['status','reason','definition_version','artifact_digest','history_count','eligible_from','points'])
      or ind.value->>'status' not in ('ready','unavailable') or jsonb_typeof(ind.value->'points') is distinct from 'array'
      or (ind.value->>'status'='ready' and jsonb_array_length(ind.value->'points')<>cardinality(seen))
      or (ind.value->>'status'='unavailable' and (jsonb_array_length(ind.value->'points')<>0 or ind.value->>'reason' is null))
    then raise exception 'invalid_chart_indicator' using errcode='22023'; end if;
    if ind.value->>'status'='ready' and exists(select 1 from jsonb_array_elements(ind.value->'points') with ordinality e(point,ordinal)
      where point->>'session' is distinct from d->'sessions'->>(ordinal::integer-1)
        or jsonb_typeof(point->'value') not in ('number','null')) then
      raise exception 'invalid_chart_indicator_points' using errcode='22023'; end if;
  end loop;
  if jsonb_typeof(d#>'{overlays,levels}') is distinct from 'array' or jsonb_typeof(d#>'{overlays,markers}') is distinct from 'array'
    or jsonb_array_length(d#>'{overlays,levels}')+jsonb_array_length(d#>'{overlays,markers}')>20000
  then raise exception 'invalid_chart_overlays' using errcode='22023'; end if;
  perform pg_advisory_xact_lock(hashtextextended(o::text||rev,0));
  select * into old from public.ticker_chart_artifacts_v1 where revision=rev and owner_id=o;
  if found then
    if (old.owner_id,old.data_mode,old.ticker,old.context_kind,old.context_id,old.view,old.data) is distinct from (o,m,t,k,cid,vw,d) then
      raise exception 'immutable_chart_conflict' using errcode='23514'; end if;
    return jsonb_build_object('revision',rev,'replayed',true);
  end if;
  insert into public.ticker_chart_artifacts_v1(revision,owner_id,data_mode,ticker,context_kind,context_id,view,data)
    values(rev,o,m,t,k,cid,vw,d);
  return jsonb_build_object('revision',rev,'replayed',false);
end;
$$;
revoke all on function public.persist_ticker_chart_artifact_v1(jsonb) from public,anon,authenticated;
grant execute on function public.persist_ticker_chart_artifact_v1(jsonb) to service_role;

create function chart_private.issue_cursor_v1(p_artifact public.ticker_chart_artifacts_v1,p_limit integer,p_kind text,p_from date,p_to date,p_lower date,p_offset integer default 0) returns text
language plpgsql set search_path='' as $$
declare cursor_id uuid;
begin
  insert into chart_private.cursors_v1(owner_id,revision,ticker,data_mode,context_kind,context_id,view,page_limit,kind,window_from,window_to,lower_bound,overlay_offset)
    values(p_artifact.owner_id,p_artifact.revision,p_artifact.ticker,p_artifact.data_mode,p_artifact.context_kind,p_artifact.context_id,p_artifact.view,p_limit,p_kind,p_from,p_to,p_lower,p_offset)
    returning id into cursor_id;
  return cursor_id::text;
end;
$$;

create function public.read_ticker_chart_v1(p_request jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare o uuid:=auth.uid(); m text; t text; k text; cid text; vw text; n integer; f date; until_day date; cutoff date;
  a public.ticker_chart_artifacts_v1; c chart_private.cursors_v1; d jsonb; selected jsonb; older date; lower_day date;
  overlays jsonb; level_values jsonb; marker_values jsonb; all_events jsonb; total_events integer; offset_events integer:=0;
  bar_cursor text; overlay_cursor text; indicator_values jsonb:='{}'; ind record; points jsonb; expected date; at_time timestamptz:=now();
begin
  if o is null then return chart_private.failure_v1('UNAUTHENTICATED'); end if;
  if not public.is_app_owner() then return chart_private.failure_v1('FORBIDDEN'); end if;
  select data_mode into m from public.deployment_settings where singleton;
  if jsonb_typeof(p_request) is distinct from 'object' then return chart_private.failure_v1('INVALID_REQUEST'); end if;
  if exists(select 1 from jsonb_object_keys(p_request) x where x not in ('ticker','context','context_id','view','timeframe','from','to','limit','cursor'))
    or exists(select 1 from jsonb_each(p_request) where key<>'limit' and jsonb_typeof(value)<>'string')
  then return chart_private.failure_v1('INVALID_REQUEST'); end if;
  t:=p_request->>'ticker';k:=coalesce(p_request->>'context','latest');cid:=p_request->>'context_id';
  vw:=coalesce(p_request->>'view',case when k='signal' then 'snapshot' else 'followup' end);
  if t is null or t !~ '^[A-Z0-9_-]{1,20}$' or k not in ('latest','signal','paper','actual') or vw not in ('snapshot','followup')
    or coalesce(p_request->>'timeframe','1d')<>'1d' or ((k='latest') is distinct from (cid is null))
    or (cid is not null and length(cid) not between 1 and 256)
    or (k='signal' and cid !~ '^[a-f0-9]{64}$') or (k='actual' and cid !~ '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
    or (k in ('latest','actual') and vw<>'followup')
    or (p_request ? 'limit' and (jsonb_typeof(p_request->'limit')<>'number' or p_request->>'limit' !~ '^\d{1,3}$'))
    or (p_request ? 'cursor' and (length(p_request->>'cursor') not between 1 and 2048 or p_request ? 'from' or p_request ? 'to'))
    or (p_request ? 'from' and p_request->>'from' !~ '^\d{4}-\d{2}-\d{2}$')
    or (p_request ? 'to' and p_request->>'to' !~ '^\d{4}-\d{2}-\d{2}$')
  then return chart_private.failure_v1('INVALID_REQUEST'); end if;
  begin n:=coalesce((p_request->>'limit')::integer,250);f:=(p_request->>'from')::date;until_day:=(p_request->>'to')::date;
  exception when invalid_datetime_format or datetime_field_overflow then return chart_private.failure_v1('INVALID_REQUEST'); end;
  if n not between 1 and 500 or (f is not null and until_day is not null and f>until_day) then return chart_private.failure_v1('INVALID_REQUEST'); end if;
  if not chart_private.consume_limit_v1(o) then return chart_private.failure_v1('RATE_LIMITED'); end if;
  if not chart_private.context_exists_v1(o,m,t,k,cid) then return chart_private.failure_v1('NOT_FOUND'); end if;
  if p_request ? 'cursor' then
    if p_request->>'cursor' !~ '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$' then return chart_private.failure_v1('INVALID_REQUEST'); end if;
    select * into c from chart_private.cursors_v1 where id=(p_request->>'cursor')::uuid and owner_id=o;
    if not found then return chart_private.failure_v1('REVISION_UNAVAILABLE'); end if;
    if (c.ticker,c.data_mode,c.context_kind,c.context_id,c.view,c.page_limit) is distinct from (t,m,k,cid,vw,n) then return chart_private.failure_v1('INVALID_REQUEST'); end if;
    if c.expires_at<=at_time then return chart_private.failure_v1('REVISION_UNAVAILABLE'); end if;
    select * into a from public.ticker_chart_artifacts_v1 where revision=c.revision and owner_id=o;
    if not found then return chart_private.failure_v1('REVISION_UNAVAILABLE'); end if;
    f:=c.window_from;until_day:=c.window_to;lower_day:=c.lower_bound;offset_events:=c.overlay_offset;
  else
    select * into a from public.ticker_chart_artifacts_v1 where owner_id=o and data_mode=m and ticker=t and context_kind=k
      and context_id is not distinct from cid and view=vw order by stored_at desc,revision desc limit 1;
    if not found then return chart_private.failure_v1(case when k in ('signal','paper') then 'SNAPSHOT_UNAVAILABLE' else 'DATA_UNAVAILABLE' end); end if;
  end if;
  d:=a.data;
  cutoff:=coalesce((d#>>'{context,snapshot_cutoff}')::date,(d#>>'{source,resolved_cutoff}')::date);
  if until_day is null then until_day:=cutoff; end if;
  if until_day>cutoff then return chart_private.failure_v1('INVALID_REQUEST','outside_closed_cutoff'); end if;
  if m='live' and (until_day<(select min(day) from public.paper_calendar_days_v1())
    or until_day>(select max(day) from public.paper_calendar_days_v1())
    or (f is not null and f<(select min(day) from public.paper_calendar_days_v1()))) then
    return chart_private.failure_v1('DATA_UNAVAILABLE','calendar_unavailable'); end if;
  lower_day:=coalesce(lower_day,f,(d->'sessions'->>0)::date);
  select coalesce(jsonb_agg(s order by s),'[]') into selected from
    (select value s from jsonb_array_elements(d->'sessions') where (value#>>'{}')::date between lower_day and until_day order by value desc limit n) q;
  if selected='[]' then return chart_private.failure_v1('DATA_UNAVAILABLE','window_unavailable'); end if;
  f:=(selected->>0)::date;until_day:=(selected->>-1)::date;
  if c.kind='overlays' then f:=c.window_from;until_day:=c.window_to; end if;
  select coalesce(jsonb_agg(jsonb_build_object('type',typ,'event',event) order by event->>'available_session',event->>'id'),'[]') into all_events from (
    select 'level' typ,value event from jsonb_array_elements(d#>'{overlays,levels}')
      where (value->>'available_session')::date<=cutoff and ((value->>'starts_at')::date<=until_day and coalesce((value->>'ends_at')::date,'infinity'::date)>=f
        or (vw='snapshot' and value->>'status'='planned' and (value->>'starts_at')::date>cutoff))
    union all select 'marker',value from jsonb_array_elements(d#>'{overlays,markers}')
      where (value->>'session')::date between f and until_day and (value->>'available_session')::date<=cutoff
  ) events;
  total_events:=jsonb_array_length(all_events);
  select coalesce(jsonb_agg(x->'event' order by ordinal),'[]') into level_values from jsonb_array_elements(all_events) with ordinality e(x,ordinal)
    where ordinal>offset_events and ordinal<=offset_events+500 and x->>'type'='level';
  select coalesce(jsonb_agg(x->'event' order by ordinal),'[]') into marker_values from jsonb_array_elements(all_events) with ordinality e(x,ordinal)
    where ordinal>offset_events and ordinal<=offset_events+500 and x->>'type'='marker';
  if total_events>offset_events+500 then overlay_cursor:=chart_private.issue_cursor_v1(a,n,'overlays',f,until_day,lower_day,offset_events+500); end if;
  overlays:=(d->'overlays')||jsonb_build_object('levels',level_values,'markers',marker_values,'has_more',overlay_cursor is not null,'next_cursor',overlay_cursor);
  if c.kind='overlays' then selected:='[]'; end if;
  for ind in select * from jsonb_each(d->'indicators') loop
    if c.kind='overlays' then
      indicator_values:=indicator_values||jsonb_build_object(ind.key,ind.value||jsonb_build_object('status','unavailable','reason','overlay_page','points','[]'::jsonb));
    else
      select coalesce(jsonb_agg(value order by value->>'session'),'[]') into points from jsonb_array_elements(ind.value->'points') where selected ? (value->>'session');
      indicator_values:=indicator_values||jsonb_build_object(ind.key,ind.value||jsonb_build_object('points',points));
    end if;
  end loop;
  if c.kind is distinct from 'overlays' then
    select max((value#>>'{}')::date) into older from jsonb_array_elements(d->'sessions') where (value#>>'{}')::date<f and (value#>>'{}')::date>=lower_day;
    if older is not null then bar_cursor:=chart_private.issue_cursor_v1(a,n,'bars',lower_day,older,lower_day); end if;
  end if;
  d:=d||jsonb_build_object('sessions',selected,'bars',(select coalesce(jsonb_agg(value order by value->>'session'),'[]') from jsonb_array_elements(d->'bars') where selected ? (value->>'session')),
    'gaps',(select coalesce(jsonb_agg(value order by value->>'session'),'[]') from jsonb_array_elements(d->'gaps') where selected ? (value->>'session')),
    'indicators',indicator_values,'overlays',overlays,'pagination',jsonb_build_object('window_from',f,'window_to',until_day,'returned_slots',jsonb_array_length(selected),
      'limit',n,'has_more',bar_cursor is not null,'next_cursor',bar_cursor));
  -- Freshness is derived at read time, never from capture or the caller's historical to filter.
  if vw='snapshot' then expected:=cutoff; elsif m='fixture' then expected:=(d#>>'{quality,expected_session}')::date; else
    select max(day) into expected from public.paper_calendar_days_v1() where closes_at<=at_time;
    if (at_time at time zone 'Asia/Jakarta')::date>(select max(day) from public.paper_calendar_days_v1()) then expected:=null; end if;
  end if;
  d:=jsonb_set(d,'{quality}',(d->'quality')||jsonb_build_object('expected_session',expected,'freshness',case
    when d#>'{quality,warnings}' ? 'newer_receipt_unusable' then 'stale'
    when expected is null then 'unknown'
    when (d#>>'{source,last_market_session}')::date<expected then 'stale' else 'current' end,
    'warnings',(select coalesce(jsonb_agg(w order by w),'[]') from (
      select distinct value w from jsonb_array_elements_text((d#>'{quality,warnings}')||
        case when expected is null then '["calendar_current_unknown"]'::jsonb else '[]'::jsonb end)
      order by w limit 20) warnings)));
  return jsonb_build_object('contract_version','ticker-chart-v1','success',true,'data',d,'error',null);
end;
$$;
revoke all on function public.read_ticker_chart_v1(jsonb) from public,anon,service_role;
grant execute on function public.read_ticker_chart_v1(jsonb) to authenticated;

create function public.load_ticker_chart_inputs_v1(p_owner_id uuid,p_ticker text default null) returns jsonb
language plpgsql security definer set search_path='' as $$
declare m text; result jsonb; collection record;
begin
  select data_mode into m from public.deployment_settings where singleton;
  perform public.assert_paper_owner_v1(p_owner_id,m);
  if p_ticker is not null and p_ticker !~ '^[A-Z0-9_-]{1,20}$' then raise exception 'invalid_chart_ticker' using errcode='22023'; end if;
  result:=jsonb_build_object('owner_id',p_owner_id,'data_mode',m,'calendar',(select payload from public.paper_calendar_v1 where singleton));
  if p_ticker is null then
    return result||jsonb_build_object('tickers',(select coalesce(jsonb_agg(ticker order by ticker),'[]') from (
      select ticker from public.market_series_revisions where data_mode=m union select ticker from public.signals where data_mode=m
      union select ticker from public.paper_trades where owner_id=p_owner_id and data_mode=m
      union select ticker from public.actual_trades where owner_id=p_owner_id and data_mode=m) tickers));
  end if;
  result:=result||jsonb_build_object('ticker',p_ticker,
    'market_revisions',(select coalesce(jsonb_agg(to_jsonb(s) order by stored_at desc),'[]') from public.market_series_revisions s where data_mode=m and ticker=p_ticker),
    'signals',(select coalesce(jsonb_agg(to_jsonb(s) order by session_date,id),'[]') from public.signals s where data_mode=m and ticker=p_ticker),
    'paper_trades',(select coalesce(jsonb_agg(to_jsonb(s) order by id),'[]') from public.paper_trades s where owner_id=p_owner_id and data_mode=m and ticker=p_ticker),
    'paper_events',(select coalesce(jsonb_agg(to_jsonb(s) order by trade_id,event_index),'[]') from public.paper_events s where owner_id=p_owner_id and data_mode=m
      and trade_id in(select id from public.paper_trades where owner_id=p_owner_id and data_mode=m and ticker=p_ticker)),
    'actual_trades',(select coalesce(jsonb_agg(to_jsonb(s) order by id),'[]') from public.actual_trades s where owner_id=p_owner_id and data_mode=m and ticker=p_ticker),
    'actual_fills',(select coalesce(jsonb_agg(to_jsonb(s)||case when c.sequence is null then '{}'::jsonb else
      jsonb_build_object('filled_at',c.filled_at,'quantity',c.quantity,'price_idr',c.price_idr,'fee_idr',c.fee_idr,'fee_status',c.fee_status,
        'correction_sequence',c.sequence,'correction_created_at',c.created_at) end order by s.sequence),'[]')
      from public.actual_fills s left join lateral(select * from public.actual_fill_corrections where fill_id=s.id order by sequence desc limit 1) c on true
      where s.owner_id=p_owner_id and s.trade_id in(select id from public.actual_trades where owner_id=p_owner_id and data_mode=m and ticker=p_ticker)),
    'actual_fill_corrections',(select coalesce(jsonb_agg(to_jsonb(s) order by sequence),'[]') from public.actual_fill_corrections s where owner_id=p_owner_id
      and trade_id in(select id from public.actual_trades where owner_id=p_owner_id and data_mode=m and ticker=p_ticker)),
    'actual_stops',(select coalesce(jsonb_agg(to_jsonb(s) order by occurred_at,id),'[]') from public.actual_stop_events s where owner_id=p_owner_id
      and trade_id in(select id from public.actual_trades where owner_id=p_owner_id and data_mode=m and ticker=p_ticker)),
    'evaluations',(select coalesce(jsonb_agg(to_jsonb(s) order by signal_id),'[]') from public.signal_evaluations s where owner_id=p_owner_id and data_mode=m and ticker=p_ticker));
  for collection in select * from jsonb_each(result) where jsonb_typeof(value)='array' loop
    if jsonb_array_length(collection.value)>5000 then raise exception 'chart_input_batch_exceeded' using errcode='54000'; end if;
  end loop;
  return result;
end;
$$;
revoke all on function public.load_ticker_chart_inputs_v1(uuid,text) from public,anon,authenticated;
grant execute on function public.load_ticker_chart_inputs_v1(uuid,text) to service_role;
revoke all on all functions in schema chart_private from public,anon,authenticated,service_role;
commit;
