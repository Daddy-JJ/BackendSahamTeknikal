# Backend architecture reference

Stable local map; [PROJECT_CONTEXT](PROJECT_CONTEXT.md) supplies portable shared context.
The workspace `TECHNICAL_DOC.md` is an optional cross-repository map when available.
[Status](IMPLEMENTATION_STATUS.md) owns dated implementation/release proof.

| Source | Responsibility |
| --- | --- |
| [scanner/src/idx_scanner](scanner/src/idx_scanner) | provider adapters, validation, deterministic signals, paper runtime and research |
| [supabase/migrations](supabase/migrations) | forward SQL, canonical ledger/reporting, RPC, RLS and grants |
| [supabase/functions](supabase/functions) | server-side Edge watchdog dispatch |
| [.github/workflows](.github/workflows) | scheduled scanner/paper recovery, manual workflows and chart artifacts |
| [contracts](contracts/README.md) | versioned schemas, serializer and chart snapshot |
| [config](config) | explicit provider mapping, exchange sessions, universe and source provenance |

Data flows through validation → normalization → indicators/strategy → immutable
signal/run → fill/paper or separate actual ledger → canonical reporting/API.
Inspect downstream consumers and timing/idempotency before changing any stage.

- [SOT](SOT.md): synchronized canonical trading-policy snapshot.
- [Market revisions](docs/MARKET_REVISIONS.md): immutable inputs/digest read-back.
- [Actual journal](docs/ACTUAL_JOURNAL.md): ledger/fills/analytics/CSV contract.
- [Recovery](docs/INCIDENT_RECOVERY_CONTRACT_V1.md): lease fencing, health/watchdog.
- [Chart](contracts/ticker-chart-v1.md): immutable artifacts, bounded owner reader.
- [Supabase](supabase/README.md): RPC/migration/test map.
- [Scanner/paper runbook](docs/SCANNER_RUN.md), [readiness](docs/PRODUCTION_READINESS.md)
  and [backup](docs/BACKUP_RESTORE_RUNBOOK.md): operational procedures.

Paper state persists in Supabase; local JSON is diagnostic. Revision CAS/request
idempotency survives restarts/retries. Raw table DML must not bypass ledger/RLS/RPC.
Inspect exact signatures/grants and consumers from source before contract changes.
Do not replay applied migrations or regenerate historical forward signals as catch-up.
Provider selection is explicit; EODHD never silently replaces Yahoo. The
[collector study](docs/COLLECTOR_REFERENCE_AUDIT.md) explains why another Yahoo
transport is not an independent source and cannot clear missing-data/action holds.
Source provenance references and their date limits live in the [runbook](docs/SCANNER_RUN.md).

Browser code receives no service-role/DB/provider secrets or long-lived dispatch PAT.
Cloud secrets are separately provisioned; ignored operator env is not cloud runtime.
The [pre-cleanup technical specification](docs/archive/TECHNICAL_DOC_BEFORE_DOC_CLEANUP_20261015.md)
retains design history. Old gates and pending paragraphs do not authorize a rollout.
