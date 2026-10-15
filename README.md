# BackendSahamTeknikal

Backend IDX Night Scanner: provider ingestion, deterministic indicators/strategies, persistent
paper journal, actual ledger/reporting, canonical chart artifacts, Supabase migrations and cloud jobs.
Frontend is a [separate repository](https://github.com/Daddy-JJ/FrontEndSahamTeknikal); Vercel builds
that repository root. GitHub Actions runs this backend; Supabase hosts persistence and the watchdog.

## Start here

- [Active plan](PLAN.md): current work only.
- [Current implementation status](IMPLEMENTATION_STATUS.md): dated evidence and remaining limits.
- [Continuation](CODEX_HANDOFF.md): next agent's entry point.
- [SOT](SOT.md): authoritative trading rules; [technical document](TECHNICAL_DOC.md): architecture.
- [Development](DEVELOPMENT.md): local commands; [scanner CLI](docs/SCANNER_RUN.md): execution contract.
- [Market revisions](docs/MARKET_REVISIONS.md), [actual journal](docs/ACTUAL_JOURNAL.md),
  [incident recovery contract](docs/INCIDENT_RECOVERY_CONTRACT_V1.md): task-specific references.

Production chart release is recorded on 15 October 2026 with schema 001-016 and 100/100 chart
coverage. See current status for exact SHAs, tests, waived backup/restore and unverified owner/JWT
boundaries. This README is not a live health check. The frontend-only detail relayout requires no
backend work. Older dated operational claims are preserved in [README history](docs/archive/README_BEFORE_DOC_CLEANUP_20261015.md).

## Local runtime

Python 3.12.14 is pinned in `scanner/.python-version`; dependencies are locked by `uv.lock`.
SQL/PGlite tests run locally without Supabase; native Docker/hosted tests have separate opt-in gates.
Use the commands in `DEVELOPMENT.md` and verify their scope before running them.

Chart writer reads all stored source revisions within a default budget of 256 per ticker
(`--max-revisions`, range 1-500). Over budget yields `chart_revision_budget_exhausted` before
series reads. There is no provenance truncation, provider fetch or ledger mutation. The default
increase from 128 retained 129-131-revision histories; future growth must remain explicitly bounded.
Up to four workers read source receipts within one ticker, preserving source order and RPC count.
Ticker projection, artifact construction and writes remain serial. Invalid/partial source groups
cannot produce an artifact.

## Structure

- `scanner/`: deterministic engine, adapters, paper evaluator, runtime and tests.
- `config/`: versioned live/reference configuration and provenance; use explicit mode guards.
- `fixtures/`: labelled synthetic development inputs.
- `contracts/`: versioned consumer contracts and labelled contract fixtures.
- `supabase/`: migrations, operations, guarded operator helpers, Edge function and tests.
- `.github/`: cloud workflows; `docs/`: focused contracts, runbooks, evidence and dated archive.

Cloud runtime uses configured GitHub Actions secrets, Vercel environment and Supabase managed/Edge
secrets. The laptop operator file is not a runtime dependency; the watchdog restricted dispatch PAT
stays in Edge secrets, never `pg_net`. Keep `.env`, privileged credentials, provider responses and
ignored `data/` outside Git. Development fixtures must remain visibly distinct from production.

Paper entry uses the signal close as its frozen fill reference on the next exchange session,
risk at most Rp1 million including both approved fees, Fixed 2R/SMA10 separate. Evaluation at
5/10 sessions does not close positions. Cash-dividend nominal metadata does not gate valid OHLC;
unknown actions, unresolved splits and invalid/stale/missing price data retain holds per SOT.
Official ledger/risk/statistics remain canonical backend output, not browser calculations.
