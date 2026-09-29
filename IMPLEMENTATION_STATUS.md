# Implementation status — IDX Night Scanner backend

Updated: 2026-09-29 (Asia/Jakarta). Status uses verified evidence only.

- M0/M1: local foundation complete; deterministic scanner, four entry strategies,
  paper lifecycle, provider adapters and demo contracts.
- M2: local SQL scan foundation and REST persistence adapter implemented.
  User applied the migration in the Supabase main (PROD) branch. Read-only
  REST checks verified all nine tables, enabled owner membership and live mode.
  No live scan or authenticated owner RLS proof yet.
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
- Remaining M2 gates: provision an isolated development project before
  write-path testing; prove RLS with Auth JWT and real PostgREST;
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
