# BackendSahamTeknikal

Backend IDX Night Scanner: provider ingestion, deterministic indicators/strategies,
Smart Money Flow & Bandarmology sync pipeline, persistent paper experiments, separate actual ledger/reporting,
signal research, canonical chart artifacts, Supabase migrations and cloud jobs.

## Start here

Read [AGENTS](AGENTS.md), [project context](PROJECT_CONTEXT.md) and [active plan](PLAN.md).
Use [status](IMPLEMENTATION_STATUS.md) for dated source/release evidence and remaining limits.
The frontend is an independent [repository](https://github.com/Daddy-JJ/FrontEndSahamTeknikal).
Vercel builds its root; GitHub Actions runs this backend; Supabase hosts data/Auth/watchdog.

- [Development](DEVELOPMENT.md): local setup/check commands.
- [Architecture](TECHNICAL_DOC.md), [product scope](PRD.md), [SOT snapshot](SOT.md).
- [Contracts](contracts/README.md): schema, ledger/CSV, reporting, recovery and charts.
- [Scanner/paper/recovery runbook](docs/SCANNER_RUN.md): entrypoints and safe operations.
- [Release readiness](docs/PRODUCTION_READINESS.md) and [backup/restore](docs/BACKUP_RESTORE_RUNBOOK.md).

## Local runtime and structure

Python 3.12.14 is pinned in `scanner/.python-version`; dependencies are locked by
`scanner/uv.lock`. PGlite SQL checks run locally without Supabase; native Docker
and hosted checks have distinct opt-in gates. Commands live in DEVELOPMENT.

- `scanner/`: deterministic engine, adapters, paper runtime, broker flow sync pipeline (`daily_broker_flow_sync.py`), research and tests.
- `config/`: explicit versioned live/reference configuration, universe mappings (including master 955-ticker universe `idx-universe-955.json`), and provenance.
- `fixtures/`: labelled synthetic development inputs, never a live fallback.
- `contracts/`: versioned schemas, serializers and labelled contract fixtures.
- `supabase/`: migrations, operations, guarded helpers, Edge function and SQL tests.
- `.github/`: cloud workflows (including `scheduled-scanner.yml` and `scheduled-broker-flow.yml`); `docs/`: contracts, runbooks and historical evidence.

Cloud runtime uses separately configured GitHub Actions, Vercel and Supabase/Edge
secrets. Keep local env, privileged credentials, raw provider/financial payloads
and ignored `data/` outside Git. The watchdog dispatch PAT stays in Edge secrets,
never the `pg_net` queue. No laptop service is required by cloud execution.

Canonical financial/trading rules are in SOT; frontend formats backend output.
Paper entry uses frozen signal-close reference on the next exchange session;
Fixed 2R and SMA10 remain separate experiments and 5/10 checkpoints do not close trades.
Chart projection reads immutable sources within a default 256-revision budget,
hard cap 500, at most four read-only source workers and serial artifact writes.
Invalid/partial/over-budget sources fail explicitly without provider fallback,
provenance truncation or economic writes. See the chart contract and source.

[Earlier README evidence](docs/archive/README_BEFORE_HANDOVER_CLEANUP_20261021.md)
retains the original dated release statements; this entrypoint is not a health check.

<!-- Compatibility anchors for consolidated historical sections. Original content is in docs/archive/README_BEFORE_HANDOVER_CLEANUP_20261021.md. -->
<a id="local-runtime"></a>
<a id="structure"></a>
