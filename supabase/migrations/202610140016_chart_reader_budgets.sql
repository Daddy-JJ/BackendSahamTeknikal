-- Chart metadata maintenance and response budget only; no economic table changes.
begin;

-- Preserve the reviewed 015 reader implementation behind the same public contract.
alter function public.read_ticker_chart_v1(jsonb) rename to read_ticker_chart_core_v1;
alter function public.read_ticker_chart_core_v1(jsonb) set schema chart_private;
revoke all on function chart_private.read_ticker_chart_core_v1(jsonb)
  from public,anon,authenticated,service_role;

-- Explicit forward copy of the reviewed 015 core: only newest lookup now branches
-- on null/equality so context/view predicates can use the complete lookup index.
create or replace function chart_private.read_ticker_chart_core_v1(p_request jsonb) returns jsonb
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
    if cid is null then
      select * into a from public.ticker_chart_artifacts_v1 where owner_id=o and data_mode=m and ticker=t and context_kind=k
        and context_id is null and view=vw order by stored_at desc,revision desc limit 1;
    else
      select * into a from public.ticker_chart_artifacts_v1 where owner_id=o and data_mode=m and ticker=t and context_kind=k
        and context_id=cid and view=vw order by stored_at desc,revision desc limit 1;
    end if;
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

create function public.read_ticker_chart_v1(p_request jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare result jsonb;
begin
  result:=chart_private.read_ticker_chart_core_v1(p_request);
  -- Measure the complete uncompressed UTF-8 response; do not truncate any prices/events.
  if octet_length(result::text)>1048576 then
    return chart_private.failure_v1('DATA_UNAVAILABLE','payload_budget_exceeded');
  end if;
  return result;
end;
$$;
revoke all on function public.read_ticker_chart_v1(jsonb) from public,anon,service_role;
grant execute on function public.read_ticker_chart_v1(jsonb) to authenticated;

create function public.prune_ticker_chart_cursors_v1(p_limit integer default 1000) returns jsonb
language plpgsql security definer set search_path='' as $$
declare removed integer; remaining boolean; at_time timestamptz:=clock_timestamp();
begin
  if p_limit is null or p_limit not between 1 and 10000 then
    raise exception 'invalid_chart_cleanup_budget' using errcode='22023';
  end if;
  with expired as (
    select id from chart_private.cursors_v1 where expires_at<=at_time
    order by expires_at,id limit p_limit for update skip locked
  ), deleted as (
    delete from chart_private.cursors_v1 c using expired e where c.id=e.id returning c.id
  ) select count(*)::integer into removed from deleted;
  select exists(select 1 from chart_private.cursors_v1 where expires_at<=at_time)
    into remaining;
  return jsonb_build_object('deleted',removed,'has_more',remaining);
end;
$$;
revoke all on function public.prune_ticker_chart_cursors_v1(integer)
  from public,anon,authenticated;
grant execute on function public.prune_ticker_chart_cursors_v1(integer) to service_role;
commit;
