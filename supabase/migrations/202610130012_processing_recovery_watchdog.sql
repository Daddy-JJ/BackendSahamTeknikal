-- Additive operational health and a disabled-by-default cloud watchdog.
-- No prices, economic events, historical configuration or trading rules change.
-- Extensions, an Edge-only repository-scoped token and Cron activation are separate
-- operator steps after backup/restore/rehearsal. This migration makes no HTTP call.
begin;

create schema paper_ops_private;
revoke all on schema paper_ops_private from public,anon,authenticated,service_role;

create table paper_ops_private.watchdog_config (
  singleton boolean primary key default true check(singleton),
  owner_id uuid references auth.users(id), data_mode text check(data_mode='live'),
  edge_ready boolean not null default false,enabled boolean not null default false,
  last_checked_at timestamptz, last_dispatch_at timestamptz,
  last_dispatch_status text, backoff_until timestamptz
);
insert into paper_ops_private.watchdog_config(singleton) values(true);

create sequence paper_ops_private.recovery_sequence;
create table paper_ops_private.runtime_lease (
  owner_id uuid not null references auth.users(id),data_mode text not null,
  job_id text not null,session_date date not null,heartbeat_at timestamptz not null,
  expires_at timestamptz not null,recovery_sequence bigint not null default nextval('paper_ops_private.recovery_sequence'),
  primary key(owner_id,data_mode)
);

-- Safe receipts contain no request headers, token, response body or raw exception.
create table public.paper_watchdog_receipts_v1 (
  id bigint generated always as identity primary key,
  owner_id uuid not null references auth.users(id),data_mode text not null check(data_mode='live'),
  session_date date not null,attempt integer not null check(attempt between 1 and 4),
  paper_only boolean not null,requested_at timestamptz not null,
  lease_until timestamptz not null,request_id bigint,
  status text not null check(status in ('dispatching','ticket_claimed','accepted','started','completed','http_failed','auth_failed','rate_limited','transport_failed','expired')),
  http_status integer,job_id text,
  unique(owner_id,data_mode,session_date,attempt)
);
alter table public.paper_watchdog_receipts_v1 enable row level security;
revoke all on public.paper_watchdog_receipts_v1 from public,anon,authenticated,service_role;
grant select on public.paper_watchdog_receipts_v1 to authenticated,service_role;
create policy owner_read on public.paper_watchdog_receipts_v1 for select to authenticated
  using ((select public.is_app_owner()) and owner_id=(select auth.uid()));
create table paper_ops_private.dispatch_ticket (
  ticket uuid primary key default gen_random_uuid(),
  receipt_id bigint not null unique references public.paper_watchdog_receipts_v1(id),
  expires_at timestamptz not null,consumed_at timestamptz
);
revoke all on all tables in schema paper_ops_private from public,anon,authenticated,service_role;

create function public.claim_paper_runtime_lease_v1(p_owner_id uuid,p_data_mode text,p_job_id text,p_session date)
returns jsonb language plpgsql security definer set search_path='' as $$
declare current_lease paper_ops_private.runtime_lease; at_time timestamptz:=clock_timestamp();
  changed integer; rotation bigint;
begin
  perform public.assert_paper_owner_v1(p_owner_id,p_data_mode);
  if p_job_id is null or p_job_id !~ '^[A-Za-z0-9:_./-]{1,160}$' or p_session is null
    or not exists(select 1 from public.paper_calendar_days_v1() where day=p_session and closes_at<=at_time) then
    raise exception 'invalid_runtime_lease' using errcode='22023'; end if;
  perform pg_advisory_xact_lock(130012,1);
  select * into current_lease from paper_ops_private.runtime_lease where owner_id=p_owner_id and data_mode=p_data_mode for update;
  if found and current_lease.job_id<>p_job_id and current_lease.expires_at>at_time then
    return jsonb_build_object('contract_version',1,'acquired',false,'expires_at',current_lease.expires_at);
  end if;
  rotation:=case when current_lease.job_id=p_job_id then current_lease.recovery_sequence
    else nextval('paper_ops_private.recovery_sequence') end;
  insert into paper_ops_private.runtime_lease(owner_id,data_mode,job_id,session_date,heartbeat_at,expires_at,recovery_sequence)
    values(p_owner_id,p_data_mode,p_job_id,p_session,at_time,at_time+interval '10 minutes',rotation)
    on conflict(owner_id,data_mode) do update set job_id=excluded.job_id,session_date=excluded.session_date,
      heartbeat_at=excluded.heartbeat_at,expires_at=excluded.expires_at,recovery_sequence=excluded.recovery_sequence;
  update public.paper_watchdog_receipts_v1 set status='started',job_id=p_job_id,lease_until=at_time
    where id=(select id from public.paper_watchdog_receipts_v1 where owner_id=p_owner_id and data_mode=p_data_mode
      and session_date=p_session and status in ('dispatching','ticket_claimed','accepted') and lease_until>at_time order by id desc limit 1);
  get diagnostics changed=row_count;
  if changed>0 then update paper_ops_private.watchdog_config set last_dispatch_status='started' where singleton; end if;
  return jsonb_build_object('contract_version',1,'acquired',true,'expires_at',at_time+interval '10 minutes','recovery_sequence',rotation);
end $$;
create function public.heartbeat_paper_runtime_lease_v1(p_owner_id uuid,p_data_mode text,p_job_id text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare at_time timestamptz:=clock_timestamp();
begin
  perform public.assert_paper_owner_v1(p_owner_id,p_data_mode);
  update paper_ops_private.runtime_lease set heartbeat_at=at_time,expires_at=at_time+interval '10 minutes'
    where owner_id=p_owner_id and data_mode=p_data_mode and job_id=p_job_id and expires_at>at_time;
  if not found then raise exception 'runtime_lease_lost' using errcode='PT409'; end if;
  return jsonb_build_object('contract_version',1,'acquired',true,'expires_at',at_time+interval '10 minutes');
end $$;
create function public.release_paper_runtime_lease_v1(p_owner_id uuid,p_data_mode text,p_job_id text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare n integer; changed integer;
begin
  perform public.assert_paper_owner_v1(p_owner_id,p_data_mode);
  delete from paper_ops_private.runtime_lease where owner_id=p_owner_id and data_mode=p_data_mode and job_id=p_job_id;
  get diagnostics n=row_count;
  update public.paper_watchdog_receipts_v1 set status='completed',lease_until=clock_timestamp()
    where owner_id=p_owner_id and data_mode=p_data_mode and job_id=p_job_id and status='started';
  get diagnostics changed=row_count;
  if changed>0 then update paper_ops_private.watchdog_config set last_dispatch_status='completed' where singleton; end if;
  return jsonb_build_object('contract_version',1,'released',n>0,'acquired',n>0);
end $$;
revoke all on function public.claim_paper_runtime_lease_v1(uuid,text,text,date),
  public.heartbeat_paper_runtime_lease_v1(uuid,text,text),public.release_paper_runtime_lease_v1(uuid,text,text)
  from public,anon,authenticated,service_role;
grant execute on function public.claim_paper_runtime_lease_v1(uuid,text,text,date),
  public.heartbeat_paper_runtime_lease_v1(uuid,text,text),public.release_paper_runtime_lease_v1(uuid,text,text) to service_role;

-- Fence canonical writes inside their database transaction, not just in the
-- runner's local heartbeat thread. A replaced/expired process cannot win CAS.
create function paper_ops_private.assert_runtime_lease_v1(p_owner_id uuid,p_data_mode text,p_job_id text,p_session date)
returns void language plpgsql security definer set search_path='' as $$
declare lease paper_ops_private.runtime_lease;
begin
  perform public.assert_paper_owner_v1(p_owner_id,p_data_mode);
  select * into lease from paper_ops_private.runtime_lease where owner_id=p_owner_id and data_mode=p_data_mode for update;
  if not found or p_job_id is null or lease.job_id<>p_job_id or lease.expires_at<=clock_timestamp()
    or lease.session_date is distinct from p_session then raise exception 'runtime_lease_lost' using errcode='PT409'; end if;
end $$;
revoke all on function paper_ops_private.assert_runtime_lease_v1(uuid,text,text,date) from public,anon,authenticated,service_role;

alter function public.commit_paper_session_v1(uuid,text,bigint,text,date,jsonb,jsonb,uuid) rename to commit_paper_session_core012;
alter function public.commit_paper_session_core012(uuid,text,bigint,text,date,jsonb,jsonb,uuid) set schema paper_ops_private;
revoke all on function paper_ops_private.commit_paper_session_core012(uuid,text,bigint,text,date,jsonb,jsonb,uuid) from public,anon,authenticated,service_role;
create function public.commit_paper_session_v1(p_owner_id uuid,p_data_mode text,p_expected_revision bigint,p_request_id text,
  p_session date,p_book jsonb,p_evaluations jsonb,p_source_run_id uuid default null)
returns jsonb language plpgsql security definer set search_path='' as $$
begin
  perform pg_advisory_xact_lock(130012,1);
  if exists(select 1 from paper_ops_private.runtime_lease where owner_id=p_owner_id and data_mode=p_data_mode)
    or exists(select 1 from paper_ops_private.watchdog_config where singleton and enabled and owner_id=p_owner_id and data_mode=p_data_mode) then
    raise exception 'runtime_lease_required' using errcode='PT409'; end if;
  return paper_ops_private.commit_paper_session_core012(p_owner_id,p_data_mode,p_expected_revision,p_request_id,p_session,p_book,p_evaluations,p_source_run_id);
end $$;
create function public.commit_paper_session_with_lease_v1(p_owner_id uuid,p_data_mode text,p_expected_revision bigint,p_request_id text,
  p_session date,p_book jsonb,p_evaluations jsonb,p_source_run_id uuid default null,p_job_id text default null)
returns jsonb language plpgsql security definer set search_path='' as $$
begin
  perform paper_ops_private.assert_runtime_lease_v1(p_owner_id,p_data_mode,p_job_id,p_session);
  return paper_ops_private.commit_paper_session_core012(p_owner_id,p_data_mode,p_expected_revision,p_request_id,p_session,p_book,p_evaluations,p_source_run_id);
end $$;
revoke all on function public.commit_paper_session_v1(uuid,text,bigint,text,date,jsonb,jsonb,uuid),
  public.commit_paper_session_with_lease_v1(uuid,text,bigint,text,date,jsonb,jsonb,uuid,text) from public,anon,authenticated,service_role;
grant execute on function public.commit_paper_session_v1(uuid,text,bigint,text,date,jsonb,jsonb,uuid),
  public.commit_paper_session_with_lease_v1(uuid,text,bigint,text,date,jsonb,jsonb,uuid,text) to service_role;

alter function public.publish_scan(jsonb,jsonb) rename to publish_scan_core012;
alter function public.publish_scan_core012(jsonb,jsonb) set schema paper_ops_private;
revoke all on function paper_ops_private.publish_scan_core012(jsonb,jsonb) from public,anon,authenticated,service_role;
create function public.publish_scan(p_run jsonb,p_signals jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
begin
  perform pg_advisory_xact_lock(130012,1);
  if exists(select 1 from paper_ops_private.runtime_lease where data_mode=p_run->>'data_mode')
    or exists(select 1 from paper_ops_private.watchdog_config where singleton and enabled and data_mode=p_run->>'data_mode') then
    raise exception 'runtime_lease_required' using errcode='PT409'; end if;
  return paper_ops_private.publish_scan_core012(p_run,p_signals);
end $$;
create function public.publish_scan_with_lease_v1(p_run jsonb,p_signals jsonb,p_owner_id uuid,p_job_id text) returns jsonb
language plpgsql security definer set search_path='' as $$
begin
  perform paper_ops_private.assert_runtime_lease_v1(p_owner_id,p_run->>'data_mode',p_job_id,(p_run->>'session')::date);
  return paper_ops_private.publish_scan_core012(p_run,p_signals);
end $$;
revoke all on function public.publish_scan(jsonb,jsonb),public.publish_scan_with_lease_v1(jsonb,jsonb,uuid,text) from public,anon,authenticated,service_role;
grant execute on function public.publish_scan(jsonb,jsonb),public.publish_scan_with_lease_v1(jsonb,jsonb,uuid,text) to service_role;

-- A checkpoint is an attempted commit. Compute unresolved work from each cursor.
-- Valid open positions/pending horizons still need daily processing, not closure.
alter function public.paper_processing_health_v1(uuid,text,timestamptz) rename to paper_processing_health_before012;
revoke all on function public.paper_processing_health_before012(uuid,text,timestamptz) from public,anon,authenticated,service_role;
create function public.paper_processing_health_v1(p_owner uuid,p_mode text,p_at timestamptz)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare h jsonb; expected date; attempt_day date; unresolved date; resolved date; activation_day date; required_from date;
  th bigint; eh bigint; filled bigint; unfilled bigint; pending_work date; status_value text; next_close timestamptz;
  lease paper_ops_private.runtime_lease; cfg paper_ops_private.watchdog_config; job public.paper_job_events_v1;
begin
  h:=public.paper_processing_health_before012(p_owner,p_mode,p_at);
  expected:=(h->>'expected_session')::date;attempt_day:=(h->>'processed_session')::date;
  select (activated_at at time zone 'Asia/Jakarta')::date into activation_day from public.paper_models
    where owner_id=p_owner and data_mode=p_mode and model_version='close-signal-risk-v1';
  select least(activation_day,attempt_day,min((t.details#>>'{signal,session}')::date)) into required_from from public.paper_trades t
    where t.owner_id=p_owner and t.data_mode=p_mode and t.model_version='close-signal-risk-v1';
  with work as (
    select case when t.details->>'entry' is null then t.entry_session
      else (select min(day) from public.paper_calendar_days_v1() where day>coalesce((t.details->>'last_session')::date,t.entry_session-1)) end as work_day
    from public.paper_trades t where t.owner_id=p_owner and t.data_mode=p_mode and t.model_version='close-signal-risk-v1'
      and t.state in ('open','pending_entry','data_hold')
    union all
    select case when e.payload->>'last_session' is null then (e.payload->>'entry_session')::date
      else (select min(day) from public.paper_calendar_days_v1() where day>(e.payload->>'last_session')::date) end
    from public.signal_evaluations e where e.owner_id=p_owner and e.data_mode=p_mode and e.model_version='close-signal-risk-v1'
      and exists(select 1 from jsonb_each_text(e.payload->'results') r where r.value in ('pending','data_hold'))
  ) select min(work_day) filter(where work_day<=expected),min(work_day) into unresolved,pending_work from work;
  if expected is not null and (attempt_day is null or attempt_day<expected) then
    select least(unresolved,min(day)) into unresolved from public.paper_calendar_days_v1()
      where closes_at is not null and day>coalesce(attempt_day,activation_day-1) and day<=expected;
  end if;
  select count(*),count(*) filter(where t.details->>'entry' is not null),count(*) filter(where t.details->>'entry' is null)
    into th,filled,unfilled from public.paper_trades t
    where t.owner_id=p_owner and t.data_mode=p_mode and t.model_version='close-signal-risk-v1' and t.state='data_hold';
  select count(*) into eh from public.signal_evaluations e where e.owner_id=p_owner and e.data_mode=p_mode
    and e.model_version='close-signal-risk-v1' and exists(select 1 from jsonb_each_text(e.payload->'results') r where r.value='data_hold');
  resolved:=least(attempt_day,expected);
  if attempt_day is null or expected is null then resolved:=null;
  elsif unresolved is not null then select max(day) into resolved from public.paper_calendar_days_v1()
      where day<unresolved and day<=attempt_day and day>=required_from; end if;
  select * into lease from paper_ops_private.runtime_lease where owner_id=p_owner and data_mode=p_mode;
  select * into cfg from paper_ops_private.watchdog_config where singleton;
  select * into job from public.paper_job_events_v1 where owner_id=p_owner and data_mode=p_mode
    order by recorded_at desc,event_sequence desc limit 1;
  status_value:=h->>'status';
  if status_value<>'calendar_unknown' then
    if lease.expires_at>p_at then status_value:='running';
    elsif lease.expires_at<=p_at and status_value<>'failed' then status_value:=case when th+eh>0 then 'data_hold' else 'overdue' end;
    elsif unresolved is not null and status_value in ('ready','missing') then status_value:='overdue'; end if;
    select min(closes_at) into next_close from public.paper_calendar_days_v1()
      where closes_at is not null and (day=unresolved or (unresolved is null and day>coalesce(attempt_day,activation_day-1)));
  end if;
  return h||jsonb_build_object('status',status_value,'overdue',case when status_value='calendar_unknown' then false else unresolved is not null or coalesce(lease.expires_at<=p_at,false) end,
    'next_eligible_processing_at',next_close,'attempt_session',attempt_day,'last_fully_resolved_session',resolved,
    'earliest_unresolved_session',unresolved,'trade_data_hold_count',th,'evaluation_data_hold_count',eh,
    'filled_trade_data_hold_count',filled,'unfilled_trade_data_hold_count',unfilled,
    'scope','all_experiments_and_evaluations','runtime_heartbeat_at',lease.heartbeat_at,
    'runtime_stalled',coalesce(lease.expires_at<=p_at,false),'operational_failure_code',case when lease.expires_at<=p_at then 'heartbeat_stalled' else null end,
    'latest_job_run_id',job.context->>'run_id',
    'latest_job_source_sha',job.context->>'source_sha',
    'latest_scanner_status',(select j.status from public.paper_job_events_v1 j where j.owner_id=p_owner and j.data_mode=p_mode
      and j.job_id=job.job_id and j.phase='scanner' order by j.recorded_at desc,j.event_sequence desc limit 1),
    'latest_publication_status',(select j.status from public.paper_job_events_v1 j where j.owner_id=p_owner and j.data_mode=p_mode
      and j.job_id=job.job_id and j.phase='publication' order by j.recorded_at desc,j.event_sequence desc limit 1),
    'latest_paper_status',(select j.status from public.paper_job_events_v1 j where j.owner_id=p_owner and j.data_mode=p_mode
      and j.job_id=job.job_id and j.phase='paper' order by j.recorded_at desc,j.event_sequence desc limit 1),
    'watchdog',jsonb_build_object('enabled',coalesce(cfg.enabled,false),'last_checked_at',cfg.last_checked_at,
      'last_dispatch_at',cfg.last_dispatch_at,'last_dispatch_status',cfg.last_dispatch_status));
end $$;
revoke all on function public.paper_processing_health_v1(uuid,text,timestamptz) from public,anon,authenticated,service_role;

-- Pure policy used by the privileged tick and local tests. It cannot dispatch.
create function paper_ops_private.watchdog_plan_v1(p_at timestamptz)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare cfg paper_ops_private.watchdog_config; h jsonb; target date; deadline timestamptz; close_time timestamptz; latest_scan public.scan_runs;
  reason text; paper_only boolean; n integer; failure text;
begin
  select * into strict cfg from paper_ops_private.watchdog_config where singleton;
  if not cfg.enabled then return jsonb_build_object('dispatch',false,'reason','disabled'); end if;
  if not exists(select 1 from public.app_members where user_id=cfg.owner_id and enabled)
    or not exists(select 1 from public.deployment_settings where singleton and data_mode=cfg.data_mode) then
    return jsonb_build_object('dispatch',false,'reason','permanent_configuration'); end if;
  h:=public.paper_processing_health_v1(cfg.owner_id,cfg.data_mode,p_at);
  if h->>'status'='calendar_unknown' then return jsonb_build_object('dispatch',false,'reason','calendar_unknown'); end if;
  target:=(h->>'expected_session')::date;
  if target is null then return jsonb_build_object('dispatch',false,'reason','no_closed_session'); end if;
  select closes_at into close_time from public.paper_calendar_days_v1() where day=target;
  -- Let primary18:18WIB run before consuming the bounded recovery budget.
  if close_time+interval '2 hours 15 minutes'>p_at then return jsonb_build_object('dispatch',false,'reason','primary_grace'); end if;
  select * into latest_scan from public.scan_runs where data_mode=cfg.data_mode and session_date=target
    order by stored_at desc,id desc limit 1;
  select min(opens_at) into deadline from public.paper_calendar_days_v1() where day>target;
  paper_only:=deadline is null or p_at>=deadline;
  -- A complete/partial committed scan is a successful attempt, not an instruction
  -- to hammer individual market holds. Missing/failed scans can recover in-window.
  if not coalesce((h->>'overdue')::boolean,false)
    and (paper_only or latest_scan.status in ('complete','partial')) then
    return jsonb_build_object('dispatch',false,'reason','resolved'); end if;
  if exists(select 1 from paper_ops_private.runtime_lease where owner_id=cfg.owner_id and data_mode=cfg.data_mode and expires_at>p_at)
    or exists(select 1 from public.paper_job_events_v1 j where j.owner_id=cfg.owner_id and j.data_mode=cfg.data_mode
      and j.phase='job' and j.status='running' and j.recorded_at>p_at-interval '30 minutes'
      and not exists(select 1 from public.paper_job_events_v1 f where f.owner_id=j.owner_id and f.data_mode=j.data_mode
        and f.job_id=j.job_id and f.phase='job' and f.status in ('succeeded','failed','skipped'))) then
    return jsonb_build_object('dispatch',false,'reason','runtime_active'); end if;
  if exists(select 1 from public.paper_watchdog_receipts_v1 where owner_id=cfg.owner_id and data_mode=cfg.data_mode
    and status in ('dispatching','ticket_claimed','accepted') and lease_until>p_at) then
    return jsonb_build_object('dispatch',false,'reason','dispatch_pending'); end if;
  if cfg.backoff_until>p_at then return jsonb_build_object('dispatch',false,'reason','backoff'); end if;
  if cfg.last_dispatch_at>p_at-interval '30 minutes' then return jsonb_build_object('dispatch',false,'reason','cooldown'); end if;
  select max(attempt) into n from public.paper_watchdog_receipts_v1 where owner_id=cfg.owner_id and data_mode=cfg.data_mode and session_date=target;
  if coalesce(n,0)>=4 then return jsonb_build_object('dispatch',false,'reason','session_cap'); end if;
  select failure_code into failure from public.paper_job_events_v1 where owner_id=cfg.owner_id and data_mode=cfg.data_mode
    and phase='job' and session_date=target order by recorded_at desc,event_sequence desc limit 1;
  if failure in ('blocked_configuration','invalid_owner','invalid_data_mode','calendar_unknown','universe_unknown',
      'missing_owner','missing_secret','owner_not_active','environment_mismatch','capability_missing','runtime_lease_lost') then
    return jsonb_build_object('dispatch',false,'reason','permanent_configuration'); end if;
  return jsonb_build_object('dispatch',true,'reason','unresolved_closed_session','session',target,
    'paper_only',paper_only,'attempt',coalesce(n,0)+1);
end $$;
revoke all on function paper_ops_private.watchdog_plan_v1(timestamptz) from public,anon,authenticated,service_role;

-- Operator-only configuration: no generic endpoint/ref/command is accepted.
create function public.configure_paper_watchdog_v1(p_owner_id uuid,p_data_mode text,p_enabled boolean,p_edge_ready boolean default false)
returns jsonb language plpgsql security definer set search_path='' as $$
begin
  perform public.assert_paper_owner_v1(p_owner_id,p_data_mode);
  if p_data_mode<>'live' or p_enabled is null or p_edge_ready is null then raise exception 'invalid_watchdog_configuration' using errcode='22023'; end if;
  if p_enabled then
    if to_regprocedure('net.http_post(text,jsonb,jsonb,jsonb,integer)') is null then
      raise exception 'watchdog_extensions_missing' using errcode='22023'; end if;
    if p_edge_ready is distinct from true then raise exception 'watchdog_edge_not_verified' using errcode='22023'; end if;
  end if;
  update paper_ops_private.watchdog_config set owner_id=p_owner_id,data_mode=p_data_mode,edge_ready=p_edge_ready,
    enabled=p_enabled,backoff_until=null,last_dispatch_status=case when p_enabled then 'configured' else 'disabled' end where singleton;
  return jsonb_build_object('contract_version',1,'enabled',p_enabled);
end $$;
revoke all on function public.configure_paper_watchdog_v1(uuid,text,boolean,boolean) from public,anon,authenticated,service_role;

-- The queued ticket allows one already-reserved fixed dispatch only. It cannot
-- mint new work or reveal a GitHub/Supabase credential. Even a reader of pg_net's
-- platform-owned queue cannot change its target, replay it or exceed policy caps.
create function public.consume_paper_watchdog_ticket_v1(p_ticket uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare ticket_row paper_ops_private.dispatch_ticket; r public.paper_watchdog_receipts_v1; at_time timestamptz:=clock_timestamp();
begin
  select * into ticket_row from paper_ops_private.dispatch_ticket where ticket=p_ticket for update;
  if not found or ticket_row.consumed_at is not null or ticket_row.expires_at<=at_time
    or not exists(select 1 from paper_ops_private.watchdog_config where singleton and enabled and edge_ready) then
    raise exception 'watchdog_ticket_invalid' using errcode='42501'; end if;
  select * into strict r from public.paper_watchdog_receipts_v1 where id=ticket_row.receipt_id for update;
  perform public.assert_paper_owner_v1(r.owner_id,r.data_mode);
  if not exists(select 1 from paper_ops_private.watchdog_config where singleton and owner_id=r.owner_id and data_mode=r.data_mode) then
    raise exception 'watchdog_ticket_invalid' using errcode='42501'; end if;
  if r.status<>'dispatching' or r.lease_until<=at_time then raise exception 'watchdog_ticket_invalid' using errcode='42501'; end if;
  update paper_ops_private.dispatch_ticket set consumed_at=at_time where ticket=p_ticket;
  update public.paper_watchdog_receipts_v1 set status='ticket_claimed' where id=r.id;
  return jsonb_build_object('contract_version',1,'receipt_id',r.id,'owner_id',r.owner_id,'data_mode',r.data_mode,
    'target_date',r.session_date,'paper_only',r.paper_only,'expires_at',ticket_row.expires_at);
end $$;
revoke all on function public.consume_paper_watchdog_ticket_v1(uuid) from public,anon,authenticated,service_role;
grant execute on function public.consume_paper_watchdog_ticket_v1(uuid) to service_role;

create function public.complete_paper_watchdog_dispatch_v1(p_receipt_id bigint,p_http_status integer,p_transport_failed boolean default false)
returns jsonb language plpgsql security definer set search_path='' as $$
declare r public.paper_watchdog_receipts_v1; status_value text; at_time timestamptz:=clock_timestamp();
begin
  if p_transport_failed is null or (p_http_status is not null and (p_http_status<100 or p_http_status>599) and not(p_transport_failed and p_http_status=0))
    or (not p_transport_failed and p_http_status is null) then raise exception 'invalid_dispatch_result' using errcode='22023'; end if;
  select * into r from public.paper_watchdog_receipts_v1 where id=p_receipt_id for update;
  -- A fast accepted runner can claim before the Edge persists HTTP204.
  if found and r.status in ('started','completed') and p_http_status=204 and not p_transport_failed then
    update public.paper_watchdog_receipts_v1 set http_status=204 where id=r.id;
    return jsonb_build_object('contract_version',1,'receipt_id',r.id,'status',r.status);
  end if;
  if found and r.status in ('accepted','auth_failed','rate_limited','transport_failed','http_failed')
    and r.http_status is not distinct from p_http_status and (r.status='transport_failed')=p_transport_failed then
    return jsonb_build_object('contract_version',1,'receipt_id',r.id,'status',r.status);
  end if;
  if not found or r.status<>'ticket_claimed' then raise exception 'watchdog_receipt_not_claimed' using errcode='PT409'; end if;
  status_value:=case when p_transport_failed then 'transport_failed' when p_http_status=204 then 'accepted'
    when p_http_status in (401,403) then 'auth_failed' when p_http_status=429 then 'rate_limited' else 'http_failed' end;
  update public.paper_watchdog_receipts_v1 set status=status_value,http_status=p_http_status,
    lease_until=case when status_value='accepted' then lease_until else at_time end where id=r.id;
  update paper_ops_private.watchdog_config set last_dispatch_status=status_value,
    enabled=case when status_value='auth_failed' then false else enabled end,
    backoff_until=case when status_value='rate_limited' then at_time+interval '1 hour' else backoff_until end where singleton;
  return jsonb_build_object('contract_version',1,'receipt_id',r.id,'status',status_value);
end $$;
revoke all on function public.complete_paper_watchdog_dispatch_v1(bigint,integer,boolean) from public,anon,authenticated,service_role;
grant execute on function public.complete_paper_watchdog_dispatch_v1(bigint,integer,boolean) to service_role;

-- Safe response classification. Do not store response content/error_msg/headers.
create function paper_ops_private.collect_watchdog_responses_v1(p_at timestamptz)
returns void language plpgsql security definer set search_path='' as $$
declare r public.paper_watchdog_receipts_v1; response record; next_status text;
begin
  if to_regclass('net._http_response') is null then return; end if;
  for r in select * from public.paper_watchdog_receipts_v1 where status in ('dispatching','ticket_claimed') and request_id is not null loop
    execute 'select status_code,timed_out,error_msg is not null as has_error from net._http_response where id=$1'
      into response using r.request_id;
    if response.has_error is not null then
      -- Only the Edge's service-only completion RPC authenticates GitHub outcome.
      -- A gateway HTTP status does not prove dispatch or an expired PAT.
      next_status:=case when coalesce(response.timed_out,false) or response.has_error then 'transport_failed' else 'http_failed' end;
      update public.paper_watchdog_receipts_v1 set status=next_status,http_status=response.status_code,
        lease_until=case when next_status='accepted' then lease_until else p_at end where id=r.id;
      update paper_ops_private.watchdog_config set last_dispatch_status=next_status where singleton;
    end if;
  end loop;
  update public.paper_watchdog_receipts_v1 set status='expired' where status in ('dispatching','ticket_claimed','accepted') and lease_until<=p_at;
end $$;
revoke all on function paper_ops_private.collect_watchdog_responses_v1(timestamptz) from public,anon,authenticated,service_role;

create function public.run_paper_watchdog_v1()
returns jsonb language plpgsql security definer set search_path='' as $$
declare at_time timestamptz:=clock_timestamp(); cfg paper_ops_private.watchdog_config; plan jsonb;
  ticket_value uuid; request bigint; receipt bigint;
begin
  if not pg_try_advisory_xact_lock(130012,1) then return jsonb_build_object('dispatch',false,'reason','tick_active'); end if;
  perform paper_ops_private.collect_watchdog_responses_v1(at_time);
  update paper_ops_private.watchdog_config set last_checked_at=at_time where singleton;
  plan:=paper_ops_private.watchdog_plan_v1(at_time);
  if not (plan->>'dispatch')::boolean then return plan; end if;
  select * into strict cfg from paper_ops_private.watchdog_config where singleton for update;
  begin
    insert into public.paper_watchdog_receipts_v1(owner_id,data_mode,session_date,attempt,paper_only,requested_at,lease_until,status)
      values(cfg.owner_id,cfg.data_mode,(plan->>'session')::date,(plan->>'attempt')::integer,
        (plan->>'paper_only')::boolean,at_time,at_time+interval '90 minutes','dispatching') returning id into receipt;
    insert into paper_ops_private.dispatch_ticket(receipt_id,expires_at) values(receipt,at_time+interval '10 minutes') returning ticket into ticket_value;
    execute 'select net.http_post(url:=$1,body:=$2,headers:=$3,timeout_milliseconds:=10000)' into request
      using 'https://hcjfxbynqzsaidlwvdfx.supabase.co/functions/v1/idx-paper-watchdog',
        jsonb_build_object('ticket',ticket_value),jsonb_build_object('Content-Type','application/json');
    update public.paper_watchdog_receipts_v1 set request_id=request where id=receipt;
    update paper_ops_private.watchdog_config set last_dispatch_at=at_time,last_dispatch_status='dispatching' where singleton;
  exception when others then
    -- Disable configuration faults rather than retrying blind; keep raw SQLERRM private.
    update paper_ops_private.watchdog_config set enabled=false,last_dispatch_status='configuration_failed' where singleton;
    return jsonb_build_object('dispatch',false,'reason','configuration_failed');
  end;
  return plan||jsonb_build_object('receipt_id',receipt);
end $$;
revoke all on function public.run_paper_watchdog_v1() from public,anon,authenticated,service_role;

-- Economic session dates and persistence times are distinct audit facts.
alter function public.read_paper_trade_v1(text) rename to read_paper_trade_before012;
revoke all on function public.read_paper_trade_before012(text) from public,anon,authenticated,service_role;
create function public.read_paper_trade_v1(p_trade_id text) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare r jsonb; t public.paper_trades; entry_processed timestamptz; unresolved date; events jsonb;
begin
  r:=public.read_paper_trade_before012(p_trade_id);
  if r is null then return null; end if;
  select * into strict t from public.paper_trades where id=p_trade_id and owner_id=auth.uid();
  select min(created_at) into entry_processed from public.paper_events
    where owner_id=t.owner_id and trade_id=t.id and model_version=t.model_version and event_type='entry';
  if t.state in ('pending_entry','open','data_hold') then
    unresolved:=case when t.details->>'entry' is null then t.entry_session
      else (select min(day) from public.paper_calendar_days_v1() where day>coalesce((t.details->>'last_session')::date,t.entry_session-1)) end;
    if not exists(select 1 from public.paper_calendar_days_v1() where day=unresolved and closes_at<=now()) then unresolved:=null; end if;
  end if;
  select coalesce(jsonb_agg(e.value||jsonb_build_object('recorded_at',p.created_at) order by e.n),'[]') into events
    from jsonb_array_elements(r->'events') with ordinality e(value,n)
    left join public.paper_events p on p.owner_id=t.owner_id and p.trade_id=t.id and p.model_version=t.model_version
      and p.trade_id||':'||p.event_index=e.value->>'event_id';
  return r||jsonb_build_object('events',events,'trade',r->'trade'||jsonb_build_object('processing',jsonb_build_object(
    'contract_version',1,'entry_processed_at',entry_processed,'last_processed_session',t.details->>'last_session',
    'earliest_unresolved_session',unresolved)));
end $$;
revoke all on function public.read_paper_trade_v1(text) from public,anon,authenticated,service_role;
grant execute on function public.read_paper_trade_v1(text) to authenticated;

commit;
