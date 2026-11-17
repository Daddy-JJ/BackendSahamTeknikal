# Backend-to-frontend capability handoff

Stable integration/consumer map, reviewed 21 October 2026. [Status](../IMPLEMENTATION_STATUS.md)
owns dated source/deployment/public-smoke proof and remaining limits; this handoff does
not carry an independent release SHA list. The completed frontend Scanner detail
relayout needs no backend implementation. Only documentation cleanup is active.

## Capability and consumer matrix

| Backend capability | Consumer obligation / canonical reference |
| --- | --- |
| Immutable scanner run/items/signals | Fetch selected run membership together; preserve URL/filter/page/detail semantics, failed/partial/held states and provenance. Old publication is not fresh provider health |
| Signal actions | [Conflict contract](SIGNAL_ACTION_CONFLICT.md); explicit stale state, persistent same-intent UUID/revision semantics; watchlist/planned annotation never creates trade/fill |
| Actual journal | [Ledger](ACTUAL_JOURNAL.md); `apply_actual_journal(text,uuid,jsonb,uuid)`, expected revision, exact UUID retry, PT412/HTTP412 and `entry_finalized_at` controls |
| Corrections | Keep `actual_fill_corrections!actual_fill_corrections_fill_id_fkey`, sequence descending/latest limit 1; do not infer an absent effective correction |
| Actual export/reporting | `actual-journal-export-v1`, closed status/exit snapshot, identical filters, limit 200; follow next_after as p_after until has_more=false; canonical decimal strings/fee quality, no browser arithmetic |
| Persistent paper/reporting | Separate immutable experiments and actual book; parse backend cohort/ambiguity/hold/processing results, independent 5/10 observations, no silent empty fallback |
| Recovery/health | [Recovery V1](INCIDENT_RECOVERY_CONTRACT_V1.md); retain source/attempt/fully-resolved/held meanings and safe metadata, no browser dispatch secrets |
| Canonical charts | [Chart V1](../contracts/ticker-chart-v1.md); strict version/hash/budget/overlay parsing and explicit unavailable/error states, no provider/raw fallback |
| Schemas/CSV copies | [Contract registry](../contracts/README.md); coordinate matching independent-repo versions/checksums without redefining math |

Exports without a snapshot token require a quiet journal for reproducible multi-page
reads. Do not invent another CSV contract or call this trade summary a complete backup.
Held/no-signal historical run items cannot be linked by selecting arbitrary latest
market revisions; verify exact persisted source binding before showing chosen-run provenance.

## Environment and identity boundary

- Frontend repository root is the Vercel build root, not `apps/web`.
- Public alias: `https://sahamteknikal.vercel.app`; a URL is not a new smoke result.
- Frontend: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`,
  `DATA_MODE=live`, `ALLOW_FIXTURE_PREVIEW=false` or unset. Label preview fixture/dev scope.
  URL/public key must identify the intended project.
- Privileged service/DB/provider/OAuth/watchdog secrets remain backend/cloud-side,
  never NEXT_PUBLIC/browser/log/chat. Scanner uses SUPABASE_SECRET_KEY; existing
  APP_OWNER_USER_ID must match enabled owner, never auto-promote a new login.
- Application `/auth/callback` is on the exact permitted origin; provider callback
  belongs to Supabase Auth. Keep dev/prod redirects separate and do not replay old
  Auth setup instructions. Operator env files are not cloud runtime provisioning.

## Next coordination and verification

For a newly authorized change, identify contract/version/consumer effect and delivery
order. Deploy backend capability first only when required. Record exact source,
deployment and served alias separately from genuine owner browser, outsider JWT and
immutable deployment-to-alias asset bytes. Test relevant navigation/refresh/back,
filters/journal/export, mobile/accessibility and error paths for that change.

Use [readiness](PRODUCTION_READINESS.md). No permanent QA production financial rows
or Auth changes follow from this handoff. Public/local/SQL-role proof cannot establish
hosted owner lifecycle/concurrency. The 15 October full-backup/restore waiver is
release-specific, not a permanent exception. Shared context follows local
[PROJECT_CONTEXT](../PROJECT_CONTEXT.md); unavailable sibling delivery is sync pending.

[Original handoff](archive/FRONTEND_DEPLOYMENT_HANDOFF_BEFORE_HANDOVER_CLEANUP_20261021.md)
and [earlier history](archive/FRONTEND_DEPLOYMENT_HANDOFF_BEFORE_DOC_CLEANUP_20261015.md)
retain dated preparation/results; none is a current task assignment or authorization.

<!-- Compatibility anchors for consolidated historical sections. Original content is in archive/FRONTEND_DEPLOYMENT_HANDOFF_BEFORE_HANDOVER_CLEANUP_20261021.md. -->
<a id="backend-to-frontend-handoff"></a>
<a id="current-task"></a>
<a id="integration-boundaries"></a>
<a id="preserve-consumer-contracts"></a>
<a id="release-verification"></a>
