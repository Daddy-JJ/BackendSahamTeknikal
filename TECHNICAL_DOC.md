# Backend architecture reference

Stable map; current status is in [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).
[Workspace architecture](../TECHNICAL_DOC.md) owns the cross-repository map; in a standalone
checkout inspect the local sources below and report missing shared context.

| Source | Responsibility |
| --- | --- |
| scanner/src/idx_scanner | provider adapters, validation, deterministic strategy/paper runtime |
| supabase/migrations | applied/forward SQL, RPC, RLS and grants |
| supabase/functions | server-side Edge watchdog dispatch |
| .github/workflows | schedules, recovery, cloud chart artifacts and CI |
| contracts | versioned schemas/fixtures and chart contract copies |

- [SOT](SOT.md) defines canonical trading rules; this synchronized snapshot is not an independent policy.
- [Actual journal](docs/ACTUAL_JOURNAL.md): ledger/fills and export contract.
- [Recovery](docs/INCIDENT_RECOVERY_CONTRACT_V1.md): health, lease fencing, watchdog and diagnostics.
- [Chart](contracts/ticker-chart-v1.md): canonical source artifacts, owner reader and HTTP consumer.
- [Supabase](supabase/README.md): database setup and local SQL checks.
- [Readiness](docs/PRODUCTION_READINESS.md) and [backup](docs/BACKUP_RESTORE_RUNBOOK.md): operational preconditions.

Paper state is persistent in Supabase; local JSON is diagnostic. Commit revision/idempotency
must survive restart/retry. Provider changes and immutable source revisions stay auditable.
Raw table DML must not bypass ledger/RLS/RPC validation. Browser does not get service-role,
DB/provider credentials or long-lived dispatch PAT. Runtime secrets belong in cloud stores;
operator .env.production-operator.local is not a cloud dependency.

Inspect exact RPC signature/grants and existing consumers from migrations/source before a change.
Do not rerun already-applied migrations or regenerate historical forward signals as catch-up.
[Previous technical specification](docs/archive/TECHNICAL_DOC_BEFORE_DOC_CLEANUP_20261015.md)
preserves detailed design/history; old deployment-pending paragraphs are not current gates.
