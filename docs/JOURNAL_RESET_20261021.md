# Owner journal reset — 21 October 2026

Status: **COMPLETE — production reset, reporting/retry, preservation and automation verified.**

## Authorized scope and outcome

The owner requested removal of all actual/paper transactions, clearing previous
signal evaluations, and retaining the latest signals still waiting for entry.
The operation applies only to the configured owner's `live` data.

| Boundary | Before | After verified canonical reset |
| --- | --- | --- |
| Actual trades | 2: 1 open, 1 closed | 0 |
| Paper trades | 58: 52 closed, 6 pending | 6 pending; 3 per exit family |
| Signal evaluations | 29 historical observations | 3 fresh observations, all pending and zero sessions |
| Paper events | 113 | 0 |
| Paper runtime revision | 12 | 14; exact retry remains 14 |

Retained signals: BUKA and PGEO Fractal Breakout, SGER Pullback Reclaim,
signal session **21 October 2026**, original entry session **22 October 2026**.
Each has separate Fixed 2R and SMA10 plans. Initial entry/SL/target, lot/quantity,
price risk, planned fee-inclusive loss and fees match the previous pending plans.
No fill was fabricated. New research observations are pending, not old results.

The new owner-approved reset boundary is
`2026-10-21T11:43:33.540112+00:00`, the retained cohort's original publication time.
The stored forward-signal set at/after this cutoff was exactly the three retained
signals. Original scanner signals, timestamps, source runs and market data were not
rewritten. Future eligible signals continue through the existing runtime.

## Execution safeguards and proof

- Active owner and production `live` mode checked against the hosted database.
- Scoped journal export encrypted with Windows DPAPI; decryption verified.
  The private encrypted export is 4,751,718 bytes. It contains complete selected
  journal/ledger/runtime/event rows and operational receipts. Chart artifact identities
  are included; duplicate derived chart bar payloads are excluded and require rebuilding
  from preserved canonical sources if restoring. This is not a full database backup.
- Local synthetic PGlite tests: **12 PASS / 0 FAIL**, including all statuses,
  owner/mode isolation, pending cohorts, canonical reporting, revision/count/edit guards,
  stale writers, receipt retry, midway rollback and immutable trigger restoration.
- Independent security/database source review: **PASS**, no remaining CRITICAL/HIGH
  finding on executed SQL SHA256
  `4aceede07499d3d1537eac1a52275954950271fee2d762922d680ac41cd0a84e`.
- Scanner/chart workflows and watchdog temporarily paused with no active/queued writer;
  transaction took the existing actual-owner/paper advisory locks and table locks.
  Only named business immutability triggers were suspended transactionally; FK/RLS
  and privileges were retained and triggers restored before commit.
- Canonical existing paper engine generated the seed; canonical commit RPC projected it.
  Replaced model kept approved configuration with a monotonic revision fence.
- Canonical hosted reporting checked under the authenticated SQL role: actual empty;
  both exit families have zero closed/P&L and three pending plans; research only the
  retained cohort, pending with no assessed outcomes. Exact commit retry replayed.
- Final native read-only comparison: **21/21 preservation fingerprints equal**,
  no changed keys. Covers scanner/source data, market revisions, calendar, actual
  request receipts, latest/signal charts and owner/mode data outside the reset.
  Auth user count is unchanged. This is scoped preservation proof, not a restore test.
- Both GitHub workflows verified active as before; Supabase watchdog enabled as before.
  Combined final automation receipt reports `restored=true`; no active run at that check.

## Preservation and limits

Actual request receipts and audit remain operational history. They prevent old request
IDs recreating deleted trades; an exact old request may still return its historical
JSON receipt without recreating a row. Reload existing journal forms after reset.
No claim is made that audit/private backup copies were erased.

Owner live paper/actual chart artifacts and related cursors were cleared so reused
pending paper IDs cannot expose an earlier trade overlay. Market latest/signal charts
are outside the reset. Old paper runtime receipts were cleared; a new honest reset
job/audit event records completion. Operational watchdog/job history is preserved.

The Docker export of duplicate chart payloads and a later verification/restore attempt
timed out while local free RAM was about 630 MB. The reset itself committed once;
it was not retried. GitHub workflows and the watchdog were restored independently.
Final read-only proof uses isolated native PostgreSQL tooling; no app dependency changed.

This is data maintenance: no frontend/backend application source, API, trading rule,
schema migration, Git commit/push or application deployment was performed.
Local fixtures and hosted authenticated SQL-role proof are distinct from genuine
owner-browser/JWT acceptance, which was not performed. Private payloads/operator receipts
remain under ignored `data/journal-reset-20261021/`; do not publish them.
