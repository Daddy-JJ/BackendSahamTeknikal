-- NOT EXECUTED. Production-only, apply after verified backup/restore and approval.
-- Operator must independently confirm Dashboard/CLI ref hcjfxbynqzsaidlwvdfx,
-- the ten-group foundation comparison, and an approved maintenance window.
-- This is one targeted privilege reduction before recording migration 001.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '15s';
lock table public.deployment_settings in share mode;
do $guard$
declare v_function pg_proc%rowtype;
begin
  if current_user <> 'postgres' then
    raise exception 'postgres_operator_required';
  end if;
  if (select data_mode from public.deployment_settings where singleton)
      is distinct from 'live' then
    raise exception 'production_live_mode_required';
  end if;
  if to_regclass('supabase_migrations.schema_migrations') is not null then
    raise exception 'history_already_present_review_required';
  end if;
  select * into v_function from pg_proc
    where oid=to_regprocedure('public.reject_immutable_mutation()');
  if not found or v_function.proowner <> 'postgres'::regrole
      or v_function.prorettype <> 'trigger'::regtype
      or v_function.prosecdef
      or v_function.proacl::text <>
        '{postgres=X/postgres,service_role=X/postgres}' then
    raise exception 'unexpected_foundation_trigger_acl_or_definition';
  end if;
  if (select count(*) from pg_trigger
      where tgfoid=v_function.oid and not tgisinternal and tgenabled='O') <> 6 then
    raise exception 'unexpected_foundation_trigger_binding';
  end if;
end
$guard$;
revoke execute on function public.reject_immutable_mutation() from service_role;
do $verify$
begin
  if (select proacl::text from pg_proc
      where oid=to_regprocedure('public.reject_immutable_mutation()'))
      is distinct from '{postgres=X/postgres}' then
    raise exception 'foundation_acl_reconciliation_failed';
  end if;
  if has_function_privilege('service_role',
      'public.reject_immutable_mutation()', 'EXECUTE') then
    raise exception 'service_role_still_has_execute';
  end if;
end
$verify$;
commit;
-- Then rerun all ten read-only foundation catalog groups. Only a full match
-- permits migration-history repair; this script never marks 001 applied.
