# Implementation status — IDX Night Scanner backend

Updated: 2026-09-29 (Asia/Jakarta). Status uses verified evidence only.

- M0/M1: local foundation complete; deterministic scanner, four entry strategies,
  paper lifecycle, provider adapters and demo contracts.
- M2: local SQL scan foundation and REST persistence adapter implemented.
  User applied the migration in the Supabase main (PROD) branch. Read-only
  REST checks verified all nine tables, enabled owner membership and live mode.
  No live scan yet. Development owner JWT/RLS read access is verified below;
  owner write/action proof is pending.
- Owner Auth UID supplied via ignored backend/.env. A read-only Auth Admin request
  returned HTTP 200, matched that UID, and found a confirmed, non-anonymous user.
- Backend .env SUPABASE_URL matches project hcjfxbynqzsaidlwvdfx, key is present
  locally; values never go into Git or source.
- Before migration, app_members and deployment_settings returned HTTP 404.
  After user execution, all nine application tables returned HTTP 200 as JSON
  lists through service access; owner membership is enabled and data_mode=live.
  Publishable-key anonymous requests to scan_runs, signals and app_members
  returned HTTP 401. This is not authenticated owner/non-owner RLS proof.
- Backend repo main pushed to GitHub at ea308e6; frontend at bff40cc.
- Earlier local verification: 92 scanner tests, 13 PGlite SQL tests, six frontend
  browser tests, frontend lint/typecheck/build. The standalone backend contract
  fixture path was checked independently: four targeted contract tests passed.
- New isolated development project ref vgmkpsestahkfahzdtae supplied; its
  Auth UID and dev API keys are configured only in ignored local env files.
  Generated dev-only SQL passed an in-memory PGlite execution: nine tables,
  enabled owner, live mode. Owner ran it in dev; read-only API checks confirmed
  nine tables, owner membership, Auth UID, and initial live mode. Dev was
  explicitly switched to fixture for smoke. Anonymous reads/RPC were denied.
  An invalid service RPC returned 22023 and left scan_runs empty.
- Remaining M2 gates: prove owner action RPC with Auth JWT and real PostgREST;
  market-data revisions, official calendar/universe, paper persistence, 5–10
  ticker live proof and GitHub runner.
- EODHD key has not been supplied. No scheduled scan or deployment is active.
- The generated SQL Editor handoff was executed on an in-memory PostgreSQL
  PGlite database: nine application tables created, owner enabled, live mode
  retained. The user then ran it on the production branch; read-only remote
  checks confirmed table availability, owner membership and live mode.
- Dashboard computer access failed in the Windows sandbox. User selected
  the Supabase SQL Editor route; migration history needs reconciliation after
  the remote schema is verified.
- Production boundary: screenshot identifies Supabase branch main (PROD), and
  the owner confirmed this is production. No fixture/live smoke writes, test
  scans, seeds, or repeated migration against this project.
- Dev setup generator now reads only ignored backend/.env.development and
  rejects the known production project ref. Development SQL is applied and
  read-only verified. A labeled synthetic dev scan published once and replayed
  exactly: one run, five items, two signals and one audit event; snapshot reload
  matched. An altered payload with the same digest returned 23514 with no
  duplicate. A disposable non-owner Auth user signed in with a real JWT:
  scan_runs, signals and app_members reads were empty; owner action was denied
  with 42501 and left no residue; the temporary user was deleted. Owner
  write/action proof remains pending; owner read evidence is recorded below.
- Supabase new API keys are sent via `apikey` only in the backend adapter.
  Thirteen persistence tests passed; one read-only production REST call with
  the revised header returned 200 and live mode. No production write was attempted.
- Development credentials are present only in ignored local env files.
  Development data_mode=fixture; production remains live and its dev_smoke_m2
  namespace is empty. The smoke script rejects the production URL and requires
  --execute for writes.
- The owner completed GitHub OAuth on localhost:3050/auth/check. The user-provided
  screenshot shows the development Auth UID matching the enabled owner membership,
  and one dev_smoke_m2 run plus two signals visible through the app's JWT/RLS
  read path. Separate read-only service queries confirmed GitHub Auth enabled,
  development data_mode=fixture, and the same one-run/two-signal counts. No raw
  owner JWT was copied to chat or shell. Owner action/write RPC remains untested.
