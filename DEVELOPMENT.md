# Backend local development

Run backend Git and commands in this independent repository. [PROJECT_CONTEXT](PROJECT_CONTEXT.md)
describes the stack and snapshot boundary; [status](IMPLEMENTATION_STATUS.md) owns dated proof.
This page documents commands; it grants no remote execution or publication permission.

## Python engine

Python 3.12.14 is pinned in `scanner/.python-version`, with locked dependencies.
From backend on Windows PowerShell:

```powershell
cd scanner
uv sync --locked
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m idx_scanner.cli demo --output ..\contracts\demo-snapshot.fixture.json
```

The demo command writes a synthetic contract fixture; run it only for an authorized
fixture/engine update and review the diff. `fixtures/`, `fixture-*` calendars and
demo snapshots never replace missing live provider data. On Windows temporary-path
failures, use a fresh writable task-specific `--basetemp` under ignored `data/`;
do not weaken checks or broadly change ACLs.

## Supabase migration/RLS local

Node.js 22.23.2 and npm 12.0.2 are pinned by `supabase/package.json`.
Install scanner dependencies first because SQL tests generate engine fixtures.

```powershell
cd supabase
npm.cmd ci
npm.cmd test
```

PGlite creates an in-memory PostgreSQL test database with simulated Auth roles/claims.
It proves neither hosted Supabase behavior nor independent sessions/real JWT/HTTP.
Native Docker checks are opt-in; verify an isolated target and actual loopback
bindings before starting accounts or fixture workloads. See the
[Auth/disposable guide](docs/AUTH_AND_DISPOSABLE_SMOKE_GUIDE.md).

## Environment

Use the existing `.env.example` as a local template when a task needs a provider.
Do not overwrite an existing env file; keep secrets in a trusted environment/store,
outside Git/chat/logs. `SUPABASE_SECRET_KEY` and `EODHD_API_TOKEN` stay backend-only.
Development helpers read their specified ignored development env; generic CLI
commands do not implicitly load env files. Check the exact source before use.
Cloud runtime has separate secrets, independent of local operator files.

Verify the intended project URL/ref and live/fixture mode before any connection.
Never change production mode to pass a guard or create persistent production QA
trades. Apply only reviewed pending forward migrations after fresh history/schema
checks; applied migrations are immutable. The [Supabase map](supabase/README.md)
and [release checklist](docs/PRODUCTION_READINESS.md) own those boundaries.

## Implementation and operational evidence

The dated record is schema 001–016 at the 15 October evidence cutoff; no connection
was made to recheck that here. Supabase setup, actual-ledger, paper and scheduler
capabilities must not be inferred from old 001-only/dev-only paragraphs.
[Scanner/paper/recovery commands](docs/SCANNER_RUN.md) map current source entrypoints.
[Actual journal](docs/ACTUAL_JOURNAL.md), [market revisions](docs/MARKET_REVISIONS.md)
and [test matrix](docs/TEST_MATRIX.md) route task-specific contracts and checks.
[Original development notes](docs/archive/DEVELOPMENT_BEFORE_HANDOVER_CLEANUP_20261021.md)
retain historical rollout proof and limitations; do not replay their old migrations.

<!-- Compatibility anchors for consolidated historical sections. Original content is in docs/archive/DEVELOPMENT_BEFORE_HANDOVER_CLEANUP_20261021.md. -->
<a id="supabase-migrationrls-lokal"></a>
<a id="batas-implementasi-saat-ini"></a>
