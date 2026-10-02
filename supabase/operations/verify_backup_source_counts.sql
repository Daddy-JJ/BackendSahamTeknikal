-- READ ONLY. Run only after confirming Dashboard project hcjfxbynqzsaidlwvdfx.
-- Counts are compared with the user-run 2026-10-01 restored archive.
-- This does not prove capture-time quiescence, row-value equality or RLS.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '15s';
with measured as (
  select jsonb_build_object(
    'app_members', (select count(*) from public.app_members),
    'audit_events', (select count(*) from public.audit_events),
    'deployment_settings', (select count(*) from public.deployment_settings),
    'scan_run_items', (select count(*) from public.scan_run_items),
    'scan_run_signals', (select count(*) from public.scan_run_signals),
    'scan_runs', (select count(*) from public.scan_runs),
    'signal_action_requests', (select count(*) from public.signal_action_requests),
    'signal_actions', (select count(*) from public.signal_actions),
    'signals', (select count(*) from public.signals)
  ) as table_counts,
  (select count(*) from auth.users) as auth_users,
  (select count(*) from auth.identities) as auth_identities,
  (select count(*) from public.app_members where enabled) as enabled_owners,
  (select count(*) from public.app_members m join auth.users u on u.id=m.user_id
    where m.enabled) as linked_owners,
  (select data_mode from public.deployment_settings where singleton) as data_mode
)
select jsonb_build_object(
  'expected_project_ref', 'hcjfxbynqzsaidlwvdfx',
  'project_ref_independently_confirmed', false,
  'checked_at_utc', to_char(clock_timestamp() at time zone 'UTC',
                          'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
  'read_only', current_setting('transaction_read_only') = 'on',
  'production_write', false,
  'data_mode', data_mode,
  'table_counts', table_counts,
  'auth_user_count', auth_users,
  'auth_identity_count', auth_identities,
  'enabled_owner_count', enabled_owners,
  'linked_enabled_owner_count', linked_owners,
  'history_present', to_regclass('supabase_migrations.schema_migrations') is not null,
  'counts_match_restored_archive',
    table_counts = '{"app_members":1,"audit_events":0,"deployment_settings":1,
      "scan_run_items":0,"scan_run_signals":0,"scan_runs":0,
      "signal_action_requests":0,"signal_actions":0,"signals":0}'::jsonb
    and auth_users=1 and auth_identities=1 and enabled_owners=1 and linked_owners=1,
  'writers_quiescent_verified', false,
  'deployment_gate_passed', false
) as sanitized_evidence from measured;
rollback;
