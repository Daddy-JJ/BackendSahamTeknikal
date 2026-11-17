# HISTORICAL / NOT AN ACTIVE TASK / NOT AUTHORIZATION

Archived 21 October 2026 during documentation-only handover cleanup.
Source: `TECHNICAL_DOC.md` at backend `719bc8c7f4deff2f945a0825cc92f6685cf48661`.
Source SHA-256 (original bytes): `8eb95c67dd43ad24e461c92671eb2204313eff7eb1a39e917f98be78366ea473`.
Source dates and proof boundaries remain those stated in the body. Earlier pending,
NO-GO, approval and execution language is historical and authorizes no new action.
Superseded for navigation by [current document](../../TECHNICAL_DOC.md)
and [dated status](../../IMPLEMENTATION_STATUS.md); archiving does not resolve gaps.
Only this wrapper and relative Markdown link rebasing alter the retained original.

---

# Backend architecture reference

Stable map; current status is in [IMPLEMENTATION_STATUS.md](../../IMPLEMENTATION_STATUS.md).
[Workspace architecture](../../../TECHNICAL_DOC.md) owns the cross-repository map; in a standalone
checkout inspect the local sources below and report missing shared context.

| Source | Responsibility |
| --- | --- |
| scanner/src/idx_scanner | provider adapters, validation, deterministic strategy/paper runtime |
| supabase/migrations | applied/forward SQL, RPC, RLS and grants |
| supabase/functions | server-side Edge watchdog dispatch |
| .github/workflows | schedules, recovery, cloud chart artifacts and CI |
| contracts | versioned schemas/fixtures and chart contract copies |

- [SOT](../../SOT.md) defines canonical trading rules; this synchronized snapshot is not an independent policy.
- [Actual journal](../ACTUAL_JOURNAL.md): ledger/fills and export contract.
- [Recovery](../INCIDENT_RECOVERY_CONTRACT_V1.md): health, lease fencing, watchdog and diagnostics.
- [Chart](../../contracts/ticker-chart-v1.md): canonical source artifacts, owner reader and HTTP consumer.
- [Supabase](../../supabase/README.md): database setup and local SQL checks.
- [Readiness](../PRODUCTION_READINESS.md) and [backup](../BACKUP_RESTORE_RUNBOOK.md): operational preconditions.

Paper state is persistent in Supabase; local JSON is diagnostic. Commit revision/idempotency
must survive restart/retry. Provider changes and immutable source revisions stay auditable.
Raw table DML must not bypass ledger/RLS/RPC validation. Browser does not get service-role,
DB/provider credentials or long-lived dispatch PAT. Runtime secrets belong in cloud stores;
operator .env.production-operator.local is not a cloud dependency.

Inspect exact RPC signature/grants and existing consumers from migrations/source before a change.
Do not rerun already-applied migrations or regenerate historical forward signals as catch-up.
[Previous technical specification](TECHNICAL_DOC_BEFORE_DOC_CLEANUP_20261015.md)
preserves detailed design/history; old deployment-pending paragraphs are not current gates.
