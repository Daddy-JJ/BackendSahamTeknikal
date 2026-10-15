# Production release readiness

This is a reusable checklist, not a dated "all systems PASS" claim. Last recorded chart release:
**15 October 2026**, schema 001-016, frontend Production deployed. Exact source/deployment IDs,
proof and remaining limits live in [current status](../IMPLEMENTATION_STATUS.md).
Earlier NO-GO/preparation checkpoints and unreconciled findings are retained in
[readiness history](archive/PRODUCTION_READINESS_BEFORE_DOC_CLEANUP_20261015.md).
This documentation cleanup did not access production or change any gate.

## Before an authorized release

1. Confirm scope, repository Git status, source SHA, production project/mode and enabled owner.
   Verify runtime capability/history/checksums afresh; never infer current remote state from old docs.
2. Keep applied migration files immutable. Prepare only pending forward versions and exact manifest;
   use pinned CLI dry-run, appropriate local/upgrade/rollback tests and reviewed contract compatibility.
   Do not rerun dated foundation/history-repair commands against an already-upgraded database.
3. Establish a recovery/containment plan appropriate to the change. Use the
   [backup/restore runbook](BACKUP_RESTORE_RUNBOOK.md); absent proof is not a pass. The owner waived
   fresh full backup/populated restore only for the 15 October chart release. That decision does not
   establish full recovery capability or require purchasing a service.
4. For writes/migrations, capture exact automation state and drain/fence active writers. Preserve
   backoff/leases. Compare server-side economic/config fingerprints and paginated reporting before
   and after; export aggregate evidence only. Restore prior automation state after verified outcome;
   uncertain DDL/history requires reconciliation before resume.
5. Verify schema/history, named RPC parameters, owner-only RLS, service-only writers, private helper
   schema/direct-table denial, mode guards and no fixture contamination before enabling consumers.
6. Deploy backend capability before compatible frontend. Record exact deployed SHA/status and test
   the served public alias. Immutable URL protection limits asset-byte proof; record that separately.
7. Run the relevant authenticated owner and denial flows. SQL-role claims, anonymous HTTP, fixture
   smoke and genuine owner/outsider JWT each prove different boundaries; retain NOT VERIFIED labels.
8. For job changes, verify fresh latest-main run and same-input retry/idempotency with unchanged
   financial/config history. Chart changes do not authorize economic replay or historical signals.
9. Record source, timestamps, migration hashes, deployed SHA, checks run, explicit skips and limits
   once in current status. Observe subsequent exchange sessions; a successful job is not a feed SLA.

## Smoke boundaries

- Scanner: selected run membership, failed/partial/full coverage, source freshness and explicit holds;
  incomplete cross-section still holds RS, never "no signal" substituted for data failure.
- Paper/evaluation: next exchange session, frozen signal-close entry, lot/fee budget, immutable initial
  risk, both exit experiments, gap/dual-hit handling, independent 5/10 checkpoints and source linkage.
- Actual: canonical ledger and correction FK, expected revision/idempotency, replay/conflict/PT412,
  partial/closed cohort, no double count across tags, actual fees/CSV and identical pagination filters.
- Chart: bounded immutable source/context contract, owner-only read, service-only write, incomplete/
  unavailable/error states, strict frontend parser and no provider/raw-data fallback.
- Auth: owner read/login/callback/logout; anon and authorized genuine outsider/disabled-owner denial.
  Do not disable the sole real owner or create production QA identities/trades automatically.
- Export: exact contract/exit snapshot and follow every cursor to completion. No synthetic permanent
  production ledger rows; real HTTP mutation smoke requires genuine owner-approved activity or an
  explicitly approved isolation design. SQL rollback tests are not real HTTP lifecycle proof.

## Containment and limits

Prefer feature disable, writer pause and forward fix; do not downgrade/drop additive schema or
restore over newer financial data. Record prior verified frontend and authentication needed for
rollback. Source revert/push rebuild and instant deployment rollback have different prerequisites.
A data replacement requires separate explicit approval, an isolated validated restore and reconciliation
of post-backup writes/RPO/RTO. [Current status](../IMPLEMENTATION_STATUS.md) records the chart rollback
fallback and remaining recovery/auth/future-session gaps.

Use [frontend handoff](FRONTEND_DEPLOYMENT_HANDOFF.md) for environment/contract boundaries.
Local source/fixture tests, hosted SQL-role checks, real JWT/HTTP and browser interactions must stay
separately labelled. Never reinterpret an archived unchecked box as closed without newer evidence.
