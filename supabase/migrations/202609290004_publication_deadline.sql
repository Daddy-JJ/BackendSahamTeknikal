-- Enforce next-open deadline inside publication; existing snapshots remain immutable.
begin;
create or replace function public.publish_scan(p_run jsonb, p_signals jsonb) returns jsonb
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
  v_deadline timestamptz;
  v_forward_inserted integer := 0;
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
      if v_signal->>'cohort' = 'forward'
        and (v_mode = 'live' or p_run ? 'publication_deadline') then
        if v_namespace <> 'forward'
          or coalesce(p_run->>'publication_deadline','') !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' then
          raise exception 'publication_deadline_required' using errcode='22023';
        end if;
        v_deadline := (p_run->>'publication_deadline')::timestamptz;
        if not isfinite(v_deadline)
          or (v_deadline at time zone 'Asia/Jakarta')::date is distinct from
             (v_signal->>'planned_entry_session')::date
          or v_deadline <= (v_signal->>'published_at')::timestamptz then
          raise exception 'invalid_publication_deadline' using errcode='22023';
        end if;
        if clock_timestamp() >= v_deadline then
          raise exception 'publication_window_elapsed' using errcode='PT409';
        end if;
        v_forward_inserted := v_forward_inserted + 1;
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
  -- Check again after all row writes/triggers. Raising rolls the entire run back.
  if v_forward_inserted > 0 and clock_timestamp() >= v_deadline then
    raise exception 'publication_window_elapsed' using errcode='PT409';
  end if;
  return jsonb_build_object('run_id',v_run_id,'replayed',false,
    'inserted',v_inserted,'reused',v_reused,'guard_skips',v_guard_skips);
end; $$;
revoke all on function public.publish_scan(jsonb,jsonb) from public, anon, authenticated;
grant execute on function public.publish_scan(jsonb,jsonb) to service_role;

create function public.scan_publish_capabilities() returns jsonb
language sql stable security invoker set search_path=''
as $$ select '{"deadline_version":1}'::jsonb $$;
revoke all on function public.scan_publish_capabilities() from public,anon,authenticated;
grant execute on function public.scan_publish_capabilities() to service_role;
commit;
