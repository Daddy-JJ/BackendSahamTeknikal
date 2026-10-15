# Backup and restore runbook

Reusable operator procedure. Dated attempts, failures and previous commands are preserved in
[runbook history](archive/BACKUP_RESTORE_RUNBOOK_BEFORE_DOC_CLEANUP_20261015.md).
Read [current status](../IMPLEMENTATION_STATUS.md) for release evidence, not this procedure.
This documentation cleanup performed no backup, connection, restore, migration or deployment.

## Scope and current exception

The owner selected existing resources with no Supabase upgrade. Fresh full backup and populated
restore rehearsal for the **15 October 2026 chart release only** were explicitly skipped:
**SKIPPED_OWNER_WAIVER**, never PASS. Two failed encrypted dumps remain unusable; successful
schema-only/decrypt diagnostics are not full data recovery. Earlier dated backups/rehearsals
remain their own evidence, not a fresh recovery point for the chart release.

Direct encryption of the dump stream is the selected route; do not add a BitLocker/VeraCrypt
requirement. The owner previously accepted temporary unencrypted isolated restore storage and
possible disk/swap residue. Do not claim secure erasure. Keep passphrases separately, private
ciphertext outside Git, and record off-site custody/hash status honestly; older copy waivers do
not prove a latest off-site copy. No paid project, shared-development restore or source reset.

## Capture when authorized and needed

1. Confirm source ref/mode, compatible pinned PostgreSQL/client/CLI/age binaries and their integrity,
   trusted TLS CA, private destination, separate recovery-passphrase custody and isolated restore target.
   Credentials go through the helper's hidden prompt or approved protected operator environment;
   never command arguments, terminal transcription, chat, browser code or committed files.
2. Inventory external secrets/configuration, OAuth, scheduler/Edge settings and Storage bytes
   separately. Database backup does not recover them or role passwords automatically.
3. Capture exact workflow/watchdog/Cron state, pause/drain/fence writers if the authorized window
   requires it, and record start/end UTC. The database dump uses one PostgreSQL snapshot; separate
   role export does not share it. Never mark quiescence verified from assumption.
4. Use [capture helper](../supabase/scripts/backup_production_prompt.py), which streams custom-format
   unfiltered native `pg_dump` plus roles without passwords into age. Resolve TLS with the trusted
   CA, never by reducing `verify-full`. Permission/exclusion failures abort; no hidden table skipping.

```powershell
# From backend, in a trusted console without transcript; paths are private operator choices.
& .\scanner\.venv\Scripts\python.exe .\supabase\scripts\backup_production_prompt.py --check-encryption --output-directory "$env:USERPROFILE\IDXNightScannerBackups"
# Synthetic crypto success is not a backup. Capture only under the authorized procedure:
& .\scanner\.venv\Scripts\python.exe .\supabase\scripts\backup_production_prompt.py --ca-cert "$env:USERPROFILE\Downloads\supabase-production-ca.crt" --output-directory "$env:USERPROFILE\IDXNightScannerBackups"
```

5. Require successful dump and encryption producers, ciphertext hashes and whole-stream decrypt
   hash verification. Failed/partial candidates stay unusable. Capture success means only
   `encrypted_candidate_decrypt_verified_restore_pending`; do not fabricate restore/off-site/
   quiescence/deployment flags. Fixed sanitized diagnostics may identify TLS/closed connection,
   timeout, cancellation, disk, COPY/query or encryption categories; do not publish raw stderr/SQL.
6. Preserve originals, copy ciphertext only to the approved independent location and compare hashes.
   Record the actual copy/custody result, then restore previous automation states safely. If DDL
   or state is uncertain, reconcile it before resuming rather than blindly enabling all jobs.

## Isolated restore and release rehearsal

1. Independently verify an empty local disposable target, rejected production/shared-development
   refs, compatible managed-schema/extension/role ownership and no public/outbound/mail/jobs/OAuth
   activity. A stock public-schema-only restore cannot prove full managed Auth/ACL recovery.
2. Review the selected archive, source database owner/bootstrap role, roles and managed customizations.
   Restore with fail-on-error; never broad-grant or ignore SQL to force success. The
   [restore helper](../supabase/scripts/restore_backup_prompt.py) provides scoped local diagnostics,
   restore and cleanup. Reproduce verified source ownership only on that disposable target.
3. Important tool limit: the existing `--rehearse-release` helper specifically rehearses the
   historical **002-007** chain. It is not a generic current-schema upgrade tool. Review its source
   and select/prepare the exact pending chain for a future authorized release; never use that flag
   as proof of 013-016 or later migrations. Do not rerun old repair commands on production.
4. Compare full required catalog, counts/server-side fingerprints, owner/Auth linkage, ACL/RLS,
   immutable triggers, RPC signatures/bodies, ledger/reporting and migration history. Test the
   relevant failure rollback, replay/stale/idempotency and real independent sessions. PGlite queued
   calls and SQL-role claims do not establish genuine JWT/HTTP or concurrent-session proof.
5. Export only sanitized aggregate results, duration and exclusions. Keep raw data/backup/keys
   private. Set restore/rehearsal flags only after checks actually pass. Remove only the verified
   disposable target using its scoped cleanup; preserve archives and never delete source data.
6. Production replacement is a separate destructive action requiring explicit authorization,
   post-backup write reconciliation and accepted RPO/RTO. Do not restore over newer trades.

## Evidence labels

| Result | What it establishes |
| --- | --- |
| Synthetic encryption/decrypt pass | Tool round trip only |
| Schema-only capture/decrypt pass | Schema diagnostic only |
| Full dump + decrypt/hash pass | Candidate archive, not restore proof |
| Actual populated isolated restore pass | Proven checked recovery scope/exclusions for that archive |
| Pending-migration rehearsal pass | Checked chain on that restored state, not remote deployment |
| Owner waiver | Specific skipped gate, no recovery proof or general waiver |

Do not reuse old dated claims of tool availability, free slot count or backup contents as a fresh
check. Public technical references are preserved in history; review official documentation when
changing tooling/procedure. The active [readiness checklist](PRODUCTION_READINESS.md) owns the
release sequence and authentication/smoke boundaries.
