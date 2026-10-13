-- OPERATOR ONLY, AFTER SQL012/backup/rehearsal/security review.
-- This script installs capabilities and least-privilege ACLs only; it does not
-- provision a token, activate the feature or dispatch a workflow.
-- Dedicated repository-scoped Actions-write token lives in Edge secrets only.
-- pg_net queue grants cannot be reliably restricted on hosted Supabase; NEVER
-- put PAT, service-role keys, Vault-decrypted values or authorization in its calls.
begin;
create extension if not exists pg_cron;
create extension if not exists pg_net;
commit;

-- After deploying the fixed Edge dispatcher, safely provisioning its dedicated
-- secret and verifying repository scope, ticket consumption and dispatch:
-- select public.configure_paper_watchdog_v1(owner_uuid,'live',true,true);
-- select cron.schedule('idx-paper-watchdog-v1','*/20 * * * *','select public.run_paper_watchdog_v1();');
-- Cron command contains no secret and only the postgres job owner can execute.
-- Rollback (safe: preserves receipts/history): configure(...,false) and
-- select cron.unschedule('idx-paper-watchdog-v1');
