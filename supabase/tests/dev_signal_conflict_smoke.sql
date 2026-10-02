-- DEVELOPMENT ONLY. SQL role/claim simulation, not a real owner Auth JWT.
-- Entire action, receipt and audit test rolls back. Confirm dev project URL.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '20s';
do $guard$ begin
  if (select data_mode from public.deployment_settings where singleton)
      is distinct from 'fixture' then
    raise exception 'development_fixture_mode_required';
  end if;
  if (select count(*) from public.app_members where role='owner' and enabled) <> 1 then
    raise exception 'expected_one_enabled_development_owner';
  end if;
  if strpos(pg_get_functiondef(to_regprocedure(
      'public.set_signal_action(text,text,integer,uuid)')), 'PT412') = 0 then
    raise exception 'migration_007_required';
  end if;
end $guard$;
do $claim$ begin
  perform set_config('request.jwt.claim.sub',
    (select user_id::text from public.app_members where role='owner' and enabled), true);
end $claim$;
set local role authenticated;
do $smoke$
declare
  v_signal text;
  v_revision integer;
  v_request uuid := gen_random_uuid();
  v_result jsonb;
  v_receipts_before bigint;
  v_audit_before bigint;
begin
  select id into v_signal from public.signals order by id limit 1;
  if v_signal is null then raise exception 'development_fixture_signal_required'; end if;
  select coalesce((select revision from public.signal_actions
      where owner_id=(select auth.uid()) and signal_id=v_signal),0) into v_revision;
  select count(*) into v_receipts_before from public.signal_action_requests
    where owner_id=(select auth.uid());
  select count(*) into v_audit_before from public.audit_events
    where owner_id=(select auth.uid()) and action='signal_action_set';

  v_result := public.set_signal_action(v_signal,'watchlist',v_revision,v_request);
  if public.set_signal_action(v_signal,'watchlist',v_revision,v_request)
      is distinct from v_result then
    raise exception 'identical_replay_changed_result';
  end if;
  begin
    perform public.set_signal_action(v_signal,'planned',v_revision,v_request);
    raise exception 'changed_payload_was_accepted';
  exception when sqlstate '23514' then null;
  end;
  begin
    perform public.set_signal_action(v_signal,'watchlist',v_revision,gen_random_uuid());
    raise exception 'stale_revision_was_accepted';
  exception when sqlstate 'PT412' then null;
  end;
  if (select count(*) from public.signal_action_requests
      where owner_id=(select auth.uid())) <> v_receipts_before + 1 then
    raise exception 'unexpected_receipt_count';
  end if;
  if (select count(*) from public.audit_events
      where owner_id=(select auth.uid()) and action='signal_action_set')
      <> v_audit_before + 1 then
    raise exception 'unexpected_audit_count';
  end if;
  if (select revision from public.signal_actions
      where owner_id=(select auth.uid()) and signal_id=v_signal) <> v_revision+1 then
    raise exception 'unexpected_revision';
  end if;
end $smoke$;
select 'pass' as hosted_sql_role_claim_smoke, 'rollback_only' as persistence;
rollback;
