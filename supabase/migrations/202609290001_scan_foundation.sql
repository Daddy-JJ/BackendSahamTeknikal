-- M2 scan persistence foundation. Apply only to an isolated Supabase dev project.
-- No owner or market fixtures are seeded here. Deployment defaults to LIVE.
begin;

create table public.app_members (
  user_id uuid primary key references auth.users(id),
  role text not null default 'owner' check (role = 'owner'),
  enabled boolean not null default true
);
alter table public.app_members enable row level security;
revoke all on public.app_members from public, anon, authenticated, service_role;
grant select on public.app_members to authenticated, service_role;
create policy own_membership on public.app_members for select to authenticated
  using (user_id = (select auth.uid()));

create function public.is_app_owner() returns boolean
language sql stable security definer set search_path = ''
as $$ select exists (
  select 1 from public.app_members where user_id = (select auth.uid()) and enabled
); $$;
revoke all on function public.is_app_owner() from public, anon;
grant execute on function public.is_app_owner() to authenticated, service_role;

create table public.deployment_settings (
  singleton boolean primary key default true check (singleton),
  data_mode text not null default 'live' check (data_mode in ('live', 'fixture'))
);
insert into public.deployment_settings default values;

create table public.scan_runs (
  id uuid primary key default gen_random_uuid(),
  namespace text not null check (namespace ~ '^[a-z0-9_-]{1,64}$'),
  run_digest text not null check (run_digest ~ '^[a-f0-9]{64}$'),
  data_mode text not null check (data_mode in ('fixture', 'live')),
  session_date date not null,
  status text not null check (status in ('complete','partial','failed')),
  coverage_valid integer not null check (coverage_valid >= 0),
  coverage_total integer not null check (coverage_total > 0 and coverage_valid <= coverage_total),
  snapshot jsonb not null check (jsonb_typeof(snapshot) = 'object'),
  stored_at timestamptz not null default now(),
  unique (namespace, data_mode, run_digest),
  check ((status = 'complete' and coverage_valid = coverage_total)
      or (status = 'partial' and coverage_valid > 0 and coverage_valid < coverage_total)
      or (status = 'failed' and coverage_valid = 0))
);
create index scan_runs_session on public.scan_runs(session_date desc);

create table public.scan_run_items (
  run_id uuid not null references public.scan_runs(id),
  ticker text not null,
  status text not null,
  snapshot jsonb not null check (jsonb_typeof(snapshot) = 'object'),
  primary key (run_id, ticker)
);
create index scan_run_items_status on public.scan_run_items(run_id, status);

create table public.signals (
  id text primary key check (id ~ '^[a-f0-9]{64}$'),
  namespace text not null,
  data_mode text not null check (data_mode in ('fixture','live')),
  ticker text not null,
  strategy text not null check (strategy in (
    'MACD_EMA200_V1','FRACTAL_BREAKOUT_V1','RS_BREAKOUT_V1','PULLBACK_RECLAIM_V1')),
  session_date date not null,
  config_hash text not null check (config_hash ~ '^[a-f0-9]{64}$'),
  input_digest text not null check (input_digest ~ '^[a-f0-9]{64}$'),
  universe_version text not null,
  calendar_version text not null,
  provider text not null check (provider in ('fixture','yfinance','eodhd')),
  price_basis text not null,
  fractal_id text,
  planned_entry_session date not null check (planned_entry_session > session_date),
  cohort text not null check (cohort in ('forward','late_model_only','backtest')),
  published_at timestamptz not null,
  snapshot jsonb not null check (jsonb_typeof(snapshot) = 'object'),
  check ((data_mode = 'fixture') = (provider = 'fixture')),
  unique (namespace, data_mode, strategy, config_hash, universe_version, ticker, session_date)
);
create unique index one_signal_per_fractal on public.signals
  (namespace, data_mode, strategy, config_hash, ticker, fractal_id)
  where fractal_id is not null;
create index signals_session_strategy on public.signals(session_date desc, strategy);

create table public.scan_run_signals (
  run_id uuid not null references public.scan_runs(id),
  signal_id text not null references public.signals(id),
  primary key (run_id, signal_id)
);

create table public.signal_actions (
  owner_id uuid not null references auth.users(id),
  signal_id text not null references public.signals(id),
  action text not null check (action in ('watchlist','planned','skipped','none')),
  revision integer not null check (revision > 0),
  updated_at timestamptz not null default now(),
  primary key (owner_id, signal_id)
);
create table public.signal_action_requests (
  owner_id uuid not null references auth.users(id),
  request_id uuid not null,
  request jsonb not null,
  result jsonb not null,
  primary key (owner_id, request_id)
);
create table public.audit_events (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid references auth.users(id),
  entity_id text not null,
  action text not null,
  details jsonb not null,
  occurred_at timestamptz not null default now()
);

-- Enable RLS and remove permissive default grants explicitly on every new table.
do $$
declare t text;
begin
  foreach t in array array['deployment_settings','scan_runs','scan_run_items',
    'signals','scan_run_signals','signal_actions','signal_action_requests','audit_events']
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from public, anon, authenticated, service_role', t);
    execute format('grant select on public.%I to authenticated, service_role', t);
    if t in ('signal_actions','signal_action_requests') then
      execute format('create policy owner_read on public.%I for select to authenticated
        using ((select public.is_app_owner()) and owner_id = (select auth.uid()))', t);
    elsif t = 'audit_events' then
      execute format('create policy owner_read on public.%I for select to authenticated
        using ((select public.is_app_owner()) and (owner_id is null or owner_id = (select auth.uid())))', t);
    else
      execute format('create policy owner_read on public.%I for select to authenticated
        using ((select public.is_app_owner()))', t);
    end if;
  end loop;
end;
$$;

create function public.reject_immutable_mutation() returns trigger
language plpgsql set search_path = ''
as $$ begin raise exception 'immutable_record' using errcode = '23514'; end; $$;
revoke all on function public.reject_immutable_mutation() from public, anon, authenticated;
do $$
declare t text;
begin
  foreach t in array array['scan_runs','scan_run_items','signals','scan_run_signals',
    'signal_action_requests','audit_events']
  loop
    execute format('create trigger immutable_record before update or delete on public.%I
      for each row execute function public.reject_immutable_mutation()', t);
  end loop;
end;
$$;

-- A single RPC transaction records the cross-section result, immutable signals and audit.
-- Namespace lock serializes this small private scanner and protects the fractal guard.
create function public.publish_scan(p_run jsonb, p_signals jsonb) returns jsonb
language plpgsql security definer set search_path = ''
as $$
declare
  v_namespace text := p_run->>'namespace';
  v_mode text := p_run->>'data_mode';
  v_run_id uuid;
  v_existing public.scan_runs;
  v_signal jsonb;
  v_saved public.signals;
  v_id text;
  v_inserted integer := 0;
  v_reused integer := 0;
  v_guard_skips integer := 0;
  v_item jsonb;
begin
  if jsonb_typeof(p_run) is distinct from 'object'
     or jsonb_typeof(p_signals) is distinct from 'array'
     or jsonb_typeof(p_run->'items') is distinct from 'array'
     or jsonb_typeof(p_run->'ranking') is distinct from 'object'
     or v_namespace is null or v_namespace !~ '^[a-z0-9_-]{1,64}$'
     or v_mode is distinct from (select data_mode from public.deployment_settings where singleton)
     or jsonb_array_length(p_signals) > 1000
     or jsonb_array_length(p_run->'items') <> (p_run->>'coverage_total')::integer
  then raise exception 'invalid_scan_envelope' using errcode = '22023'; end if;

  perform pg_advisory_xact_lock(hashtextextended('idx:publish:' || v_namespace, 0));
  select * into v_existing from public.scan_runs where namespace = v_namespace
    and data_mode = v_mode and run_digest = p_run->>'run_digest';
  if found then
    if v_existing.snapshot is distinct from p_run then
      raise exception 'idempotency_conflict' using errcode = '23514';
    end if;
    return jsonb_build_object('run_id', v_existing.id, 'replayed', true);
  end if;

  insert into public.scan_runs(namespace, data_mode, run_digest, session_date, status,
    coverage_valid, coverage_total, snapshot)
  values (v_namespace, v_mode, p_run->>'run_digest', (p_run->>'session')::date,
    p_run->>'status', (p_run->>'coverage_valid')::integer,
    (p_run->>'coverage_total')::integer, p_run) returning id into v_run_id;

  for v_item in select value from jsonb_array_elements(p_run->'items') loop
    insert into public.scan_run_items values
      (v_run_id, v_item->>'ticker', v_item->>'status', v_item);
  end loop;

  for v_signal in select value from jsonb_array_elements(p_signals) loop
    if v_signal->>'data_mode' is distinct from v_mode
       or (v_signal->>'session')::date is distinct from (p_run->>'session')::date
       or (v_signal#>>'{candidate,triggered}')::boolean is distinct from true
       or not exists (select 1 from public.scan_run_items
         where run_id = v_run_id and ticker = v_signal->>'ticker' and status = 'evaluated')
    then raise exception 'signal_context_mismatch' using errcode = '22023'; end if;

    select * into v_saved from public.signals where id = v_signal->>'id';
    if found then
      -- First published timestamp is authoritative. Other content must be identical.
      if v_saved.namespace is distinct from v_namespace or
         (v_saved.snapshot - 'published_at') is distinct from (v_signal - 'published_at')
      then raise exception 'immutable_signal_conflict' using errcode = '23514'; end if;
      v_id := v_saved.id;
      v_reused := v_reused + 1;
    else
      if v_signal#>>'{candidate,fractal_id}' is not null and exists (
        select 1 from public.signals where namespace = v_namespace and data_mode = v_mode
          and strategy = v_signal#>>'{candidate,strategy}'
          and config_hash = v_signal->>'config_hash' and ticker = v_signal->>'ticker'
          and fractal_id = v_signal#>>'{candidate,fractal_id}'
      ) then
        v_guard_skips := v_guard_skips + 1;
        continue;
      end if;
      v_id := v_signal->>'id';
      insert into public.signals(id, namespace, data_mode, ticker, strategy, session_date,
        config_hash, input_digest, universe_version, calendar_version, provider, price_basis,
        fractal_id, planned_entry_session, cohort, published_at, snapshot)
      values (v_id, v_namespace, v_mode, v_signal->>'ticker', v_signal#>>'{candidate,strategy}',
        (v_signal->>'session')::date, v_signal->>'config_hash', v_signal->>'input_digest',
        v_signal->>'universe_version', v_signal->>'calendar_version', v_signal->>'provider',
        v_signal->>'price_basis', v_signal#>>'{candidate,fractal_id}',
        (v_signal->>'planned_entry_session')::date, v_signal->>'cohort',
        (v_signal->>'published_at')::timestamptz, v_signal);
      v_inserted := v_inserted + 1;
    end if;
    insert into public.scan_run_signals values (v_run_id, v_id);
  end loop;
  insert into public.audit_events(entity_id, action, details) values
    (v_run_id::text, 'scan_published', jsonb_build_object('inserted',v_inserted,
      'reused',v_reused,'guard_skips',v_guard_skips,'run_digest',p_run->>'run_digest'));
  return jsonb_build_object('run_id',v_run_id,'replayed',false,
    'inserted',v_inserted,'reused',v_reused,'guard_skips',v_guard_skips);
end; $$;
revoke all on function public.publish_scan(jsonb,jsonb) from public, anon, authenticated;
grant execute on function public.publish_scan(jsonb,jsonb) to service_role;

-- A watchlist/planned/skipped annotation NEVER creates a trade or fill.
create function public.set_signal_action(
  p_signal_id text, p_action text, p_expected_revision integer, p_request_id uuid
) returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
  v_owner uuid := auth.uid();
  v_request jsonb := jsonb_build_object('signal_id',p_signal_id,'action',p_action,
    'expected_revision',p_expected_revision);
  v_prior public.signal_action_requests;
  v_revision integer;
  v_result jsonb;
begin
  if v_owner is null or not public.is_app_owner() then
    raise exception 'owner_required' using errcode = '42501';
  end if;
  if p_request_id is null or p_action is null
    or p_action not in ('watchlist','planned','skipped','none')
    or p_expected_revision is null or p_expected_revision < 0 then
    raise exception 'invalid_action' using errcode = '22023';
  end if;
  -- Same owner serializes request replay and optimistic revision validation.
  perform pg_advisory_xact_lock(hashtextextended('idx:action:' || v_owner::text, 0));
  select * into v_prior from public.signal_action_requests
    where owner_id = v_owner and request_id = p_request_id;
  if found then
    if v_prior.request is distinct from v_request then
      raise exception 'idempotency_conflict' using errcode = '23514';
    end if;
    return v_prior.result;
  end if;
  if not exists (select 1 from public.signals where id = p_signal_id) then
    raise exception 'signal_not_found' using errcode = '22023';
  end if;
  select revision into v_revision from public.signal_actions
    where owner_id = v_owner and signal_id = p_signal_id;
  if coalesce(v_revision, 0) <> p_expected_revision then
    raise exception 'revision_conflict' using errcode = '40001';
  end if;
  v_revision := coalesce(v_revision,0) + 1;
  insert into public.signal_actions values (v_owner,p_signal_id,p_action,v_revision,now())
  on conflict(owner_id,signal_id) do update
    set action = excluded.action, revision = excluded.revision, updated_at = excluded.updated_at;
  v_result := jsonb_build_object('signal_id',p_signal_id,'action',p_action,'revision',v_revision);
  insert into public.signal_action_requests values (v_owner,p_request_id,v_request,v_result);
  insert into public.audit_events(owner_id,entity_id,action,details)
    values(v_owner,p_signal_id,'signal_action_set',v_result);
  return v_result;
end; $$;
revoke all on function public.set_signal_action(text,text,integer,uuid) from public, anon, service_role;
grant execute on function public.set_signal_action(text,text,integer,uuid) to authenticated;
commit;
