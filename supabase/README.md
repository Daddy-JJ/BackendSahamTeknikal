# Supabase database reference

The database supplies canonical persistence, owner Auth/RLS and versioned RPC.
[Status](../IMPLEMENTATION_STATUS.md) records schema 001–016 at its 15 October 2026
evidence cutoff. This documentation cleanup did not inspect a remote database.
[Development](../DEVELOPMENT.md) owns local setup; [readiness](../docs/PRODUCTION_READINESS.md)
owns release checks. Neither this reference nor an old SQL Editor recipe authorizes execution.

## Capabilities and source map

| Migration source | Contract/capability |
| --- | --- |
| [001 foundation](migrations/202609290001_scan_foundation.sql) | membership/mode, immutable runs/items/signals, publisher and owner signal actions |
| [002 revisions](migrations/202609290002_market_series_revisions.sql), [003 reconstruction](migrations/202609290003_market_series_reconstruction.sql) | immutable normalized inputs, ordered manifests, digest reconstruction |
| [004 deadline](migrations/202609290004_publication_deadline.sql) | transaction-side forward publication deadline |
| [005 actual](migrations/202609290005_actual_journal.sql), [006 actual HTTP conflict](migrations/202609300006_actual_journal_conflict_http.sql) | immutable actual ledger/analytics/export and PT412 stale revision |
| [007 action conflict](migrations/202610010007_signal_action_conflict_http.sql) | signal-action PT412 without changed idempotency semantics |
| [008 canonical analytics/paper](migrations/202610040008_canonical_analytics_and_paper.sql), [009 persistent reporting](migrations/202610080009_persistent_paper_reporting.sql) | canonical reporting/paper persistence |
| [010 scanner coverage](migrations/202610080010_reporting_scanner_coverage.sql), [011 integrity/health](migrations/202610100011_paper_integrity_and_processing_health.sql) | coverage and paper-processing integrity |
| [012 recovery/watchdog](migrations/202610130012_processing_recovery_watchdog.sql) | lease-fenced writers, health and cloud recovery |
| [013 indexes](migrations/202610130013_performance_indexes.sql), [014 reporting](migrations/202610130014_optimize_trade_reporting_rpc.sql) | performance paths with unchanged economic meaning |
| [015 charts](migrations/202610140015_ticker_chart_artifacts.sql), [016 reader budget](migrations/202610140016_chart_reader_budgets.sql) | immutable canonical chart artifacts and bounded owner reads |

Inspect exact signatures/named arguments, grants and current source before edits.
Enabled-owner JWT is required for private reads/actions; anon has no private grants,
non-members cannot read other owners, and frontend checks never replace database
authorization. Browser/service roles cannot directly DML application tables.
Service-only publishers/writers use validated RPC; SECURITY DEFINER search paths/
private helpers remain restricted. Never weaken policies for a successful call.
[Contracts](../contracts/README.md) route ledger/CSV, revision, action, recovery and chart details.

## Local tests without Docker or cloud

PGlite is an ephemeral in-memory test runtime, not the application database.
The suite executes real migration SQL with synthetic Python-engine fixtures.

```powershell
cd supabase
npm.cmd ci
npm.cmd test
```

Start from backend; prepare the scanner venv first. Node/npm pins are in package.json.
[TEST_MATRIX](../docs/TEST_MATRIX.md) maps risks to actual suite files.
Queued requests on one PGlite connection do not prove independent PostgreSQL
sessions, hosted PostgREST mappings, real JWT or production behavior.

## Migration history and isolated development

Applied SQL files remain immutable; prefer reviewed additive forward migrations.
SQL Editor execution does not register CLI migration history. Reconcile only after
fresh target/schema/history/checksum verification, using the exact pending chain.
Never mark history applied on an unverified project or rerun old foundation/setup
generators because an archived report says pending.
The historical `release-manifest.json` / `scripts/plan_production_release.mjs`
cover 001–007; they are not an automatic all-016 release manifest or authorization.

Development helpers under `scripts/` are narrowly URL/ref/mode/owner guarded and
write ignored handoff files. They do not make an already-initialized database fresh.
Use a verified development/disposable target only; preserve immutable fixture
audit history. Never drop/truncate/reseed shared data or switch production to fixture.
[Market revisions](../docs/MARKET_REVISIONS.md) and [actual journal](../docs/ACTUAL_JOURNAL.md)
link the original guarded-setup evidence without making it an active rollout queue.

## Auth, credentials and smoke boundaries

Supabase Dashboard GitHub login is distinct from an application Auth session.
The owner identity must match an existing enabled membership; never auto-promote
a new login. Provider and application callbacks differ and require exact origins.
Service-role, database, OAuth/provider and dispatch secrets stay server-side.

[Auth/disposable guide](../docs/AUTH_AND_DISPOSABLE_SMOKE_GUIDE.md) owns safe account/
JWT/isolation procedures. Actual JWTs come from Auth login, never manual signing or
service-key impersonation. Never paste passwords/JWTs into chat or shell arguments.
SQL-role tests, local Auth/HTTP, hosted genuine owner/outsider and browser proofs
remain separate. Do not create permanent production QA ledger trades or disable
the sole production owner to close a gate.

[Original Supabase notes](../docs/archive/SUPABASE_README_BEFORE_HANDOVER_CLEANUP_20261021.md)
preserve source-specific setup and rollout evidence. Old dev-only/001-only/no-cron
statements are historical. Consult current status for later release evidence.

<!-- Compatibility anchors for consolidated historical sections. Original content is in ../docs/archive/SUPABASE_README_BEFORE_HANDOVER_CLEANUP_20261021.md. -->
<a id="supabase-development--m2-local-foundation"></a>
<a id="yang-tersedia"></a>
<a id="tes-lokal-tanpa-docker-atau-cloud"></a>
<a id="urutan-yang-masih-harus-dikerjakan"></a>
<a id="production-boundary-and-migration-history"></a>
<a id="isolated-development-project-setup"></a>
<a id="development-fixture-rpc-smoke"></a>
<a id="disposable-non-owner-rls-test"></a>
<a id="owner-jwtrls-read-probe"></a>
<a id="market-series-revision-migration-local-only"></a>
