# Implementation status — IDX Night Scanner backend

Updated: 2026-09-29 (Asia/Jakarta). Status uses verified evidence only.

- M0/M1: local foundation complete; deterministic scanner, four entry strategies,
  paper lifecycle, provider adapters and demo contracts.
- M2: local SQL scan foundation and REST persistence adapter implemented.
  User applied the migration in the Supabase main (PROD) branch. Read-only
  REST checks verified all nine tables, enabled owner membership and live mode.
  No live scan yet. Development owner JWT/RLS reads and the signal-action
  RPC write/replay are verified below; journal writes remain unimplemented.
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
- Market-series revision migration 202609290002 and Python ingest adapter are
  implemented and tested only locally. Compact fetch receipts and changed-bar
  rows are immutable; exact replay returns the original receipt. Changed bars
  require a new input digest; digest reuse with changed content is rejected.
  The migration has not been applied to development or production Supabase.
- Remaining M2 gates: apply and verify the revision migration in development,
  integrate ingestion into the run pipeline, official calendar/universe,
  paper persistence, 5–10 ticker live proof and GitHub runner.
- EODHD key has not been supplied. No scheduled scan is active. The frontend
  Vercel production domain responds HTTP 200 with a live-connection placeholder;
  this is not a live scanner deployment.
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
  signal-action proof is recorded below.
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
  owner JWT was copied to chat or shell. The owner then used the app's guarded
  development fixture button to call set_signal_action and replay the same
  request. The user reported success; an independent read-only check found one
  watchlist action at revision 1, one matching idempotency request, one audit
  event, and the same two fixture signals. Production was not written.

- Earlier revision-slice verification: 97 scanner tests, 19 PGlite SQL tests and Ruff
  passed after adding revisioned market-series storage. PGlite tests cover
  fixture-in-production rejection, immutable revisions, replay, unchanged-bar
  reuse, duplicate-session rollback, digest conflict, RLS owner/outsider/anon
  isolation, and denied direct writes. This does not prove remote migration,
  full-series reconstruction, production storage sizing, or provider quality.

- Local M2 orchestration now preflights calendar/universe and mapping before
  database/provider IO, reloads published signal state, fetches the complete
  cross-section, stores each fetched series receipt, and only then publishes
  the run. Provider failures remain explicit and reduce coverage; empty-bar
  results remain auditable missing-data receipts. A revision ingest failure
  prevents publication. Five targeted runner tests passed, including these
  failure paths. No CLI workflow, GitHub schedule, remote migration, or live
  publish has been run.

- Follow-up verification: 101 full scanner tests, 20 PGlite SQL tests, Ruff,
  and five targeted runner tests after the empty-series case. The additional
  runner test was run targeted after the 101-test full suite; no claim of a
  102-test full-suite run is made.
