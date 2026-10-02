-- NOT EXECUTED. Emergency write containment AFTER explicit production approval.
-- Confirm project hcjfxbynqzsaidlwvdfx; preserve financial/audit data and PT412.
-- This is a service interruption, not a schema downgrade or data restore.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '15s';
lock table public.deployment_settings in share mode;
do $$ begin
  if (select data_mode from public.deployment_settings where singleton) is distinct from 'live'
  then raise exception 'production_live_mode_required'; end if;
  if to_regprocedure('public.apply_actual_journal(text,uuid,jsonb,uuid)') is null
  then raise exception 'actual_journal_missing'; end if;
end $$;
revoke execute on function public.apply_actual_journal(text,uuid,jsonb,uuid)
  from public, anon, authenticated, service_role;
notify pgrst, 'reload schema';
commit;
-- Keep reads/analytics/export and all records. Review privileges before resuming.
-- After a tested forward fix and explicit resume approval, restore ONLY the
-- original 005 authenticated EXECUTE grant, then repeat owner/denial smoke.
