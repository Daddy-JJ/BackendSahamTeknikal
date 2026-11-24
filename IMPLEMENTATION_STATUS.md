# Backend implementation status

Evidence updated: **24 November 2026**; previous documentation reconciled 21 October 2026.
Read [active plan](PLAN.md) for work to do, [handoff](CODEX_HANDOFF.md) for continuation,
and [readiness](docs/PRODUCTION_READINESS.md) for release checks. Older receipts and all dated
unreconciled findings remain in [status history](docs/archive/IMPLEMENTATION_STATUS_BEFORE_DOC_CLEANUP_20261015.md).

## Broker Flow & Bandarmology Sync Pipeline — 24 November 2026

- **Async Sync Engine**: `backend/scanner/src/idx_scanner/daily_broker_flow_sync.py` implemented with `asyncio` and `AsyncMaxTradeMcpClient`.
  - Concurrency: 12 parallel workers with semaphore throttling.
  - Multi-horizon flow metrics: 2D momentum, 5D weekly persistence, 10D structural base queried via MCP `get_broksum_ticker_history` and `get_broksum_signal`.
  - Execution speed: ~40 seconds for full universe scan.
- **IDX Master Universe**: 955 tickers mapped in `backend/scanner/src/idx_scanner/idx_universe.py` and saved to `backend/config/live/idx-universe-955.json`.
- **Cloud Automation**: GitHub Actions workflow `.github/workflows/scheduled-broker-flow.yml` configured to trigger on weekdays at 17:30 and 18:45 WIB (10:30 & 11:45 UTC).
- **Dual-Tier Output**:
  - Direct cloud upsert into Supabase table `broker_flow_ticker_horizons`.
  - Automatic commit and synchronization of lightweight frontend snapshot bundle (`frontend/public/data/broker_flow_horizons.json` < 200KB).
- **Repository Delivery**: Backend commit `5c20d2f` on branch `main` pushed to `origin/main`.

## Current data maintenance — 21 October 2026

Owner-approved production journal reset **COMPLETE**: actual 2→0, paper58→6 pending
(3 per exit), historical evaluations29→3 new pending/zero-session observations.
Retained BUKA/PGEO/SGER signals21October still target entry22October; no synthetic fills.
Canonical hosted SQL-role reporting/retry verified;21 preservation fingerprints equal;
GitHub scanner/chart workflows and Supabase watchdog restored to their prior active state.
Local12/12 fixture tests/security review PASS. Application source/schema/deployment unchanged.
[Reset receipt](docs/JOURNAL_RESET_20261021.md) records scope, scoped encrypted backup,
chart cache exclusion, operational audit retention and owner-browser NOT VERIFIED limits.
This operation supplies no authorization to repeat a reset or publish local documentation.

## Recorded release

| Boundary | Recorded result |
| --- | --- |
| Backend runtime source | `dce85b12274e34fbb3a7b36c962e930b4b80b4d3`; later recorded docs-only main `719bc8c7f4deff2f945a0825cc92f6685cf48661` (earlier docs receipt `298bb557b6339174e2d6899d4e951536a871c980`) |
| Supabase | Migrations 001-016 applied; exact pending 013-016 checksums/CLI dry-run/ACL checked |
| Chart cloud run | `38695021871` SUCCESS; 100/100 latest tickers, 288 immutable artifacts, no fixture artifacts |
| Chart quality | Complete/current through 14 October at recorded verification; future sessions not implied |
| Frontend chart release (earlier 15 October) | Source `92705f9e47c4bedb6872e350ea4093a6fd472761`, Vercel deployment `7085991505` SUCCESS |
| Frontend Scanner relayout (later 15 October) | Source `513870f6020983ddb20ba022c946eaffd223fce6`; Vercel Production `7092738529` SUCCESS, recorded `2026-10-15T12:37:40Z` |
| Repository delivery | Backend documentation-only `719bc8c7f4deff2f945a0825cc92f6685cf48661` and frontend `513870f` were recorded pushed with clean trees; this is historical delivery, not the 21 October working state |
| Public HTTP smoke | Later relayout Production check: 8 routes/14 assets passed; expected CSS markers; anonymous chart/export HTTP401; checked responses/assets had no credential-pattern matches. Earlier chart failure-envelope/no-store checks remain their own proof |
| Financial isolation | 18 economic/config fingerprints and all-page canonical reports matched while paused; after resume all nonoperational fields still matched |
| Operational reconciliation | Raw reports changed at six explicit watchdog enabled/last_checked_at paths; those captured fields alone were normalized for comparison |
| Cloud automation | Prior GitHub workflow, Supabase watchdog and Cron states restored/active; operator laptop is not a runtime dependency |
| Backup/restore | Fresh full backup and populated restore **SKIPPED_OWNER_WAIVER** for this chart release; failed dumps invalid; schema-only check is not full recovery |

Runtime projects bounded immutable chart views from stored source receipts. Default source
budget 256 per ticker, hard maximum 500; at most four read-only source requests within one
ticker, ordered output and serial artifact writes. Over-budget/invalid sources fail explicitly;
no provenance truncation, provider fallback or economic write is used to build a chart.

## Recorded verification

- Final Python: 608 PASS / 5 explicit native Docker opt-in SKIP; focused chart 43 PASS;
  Ruff and independent concurrency/security review PASS.
- Backup diagnostics: 39 PASS. Historical dump root cause was not recovered from lost stderr;
  new sanitized fixed-code diagnostics do not prove a successful full backup.
- SQL/PGlite: 160 PASS; native synthetic upgrade/rollback/grants and 18 fingerprints PASS.
  These are not a fresh populated production restore rehearsal.
- Live SQL-role chart output passed the real frontend parser in 15 latest/signal/paper
  contexts plus one existing actual context. Unverified actual price basis correctly holds overlays.
  Claims/role probes are not genuine owner/outsider JWT or browser proof.
- Frontend 77 unit tests passed at the recorded chart-release source; typecheck/lint/build/browser/performance evidence
  belongs to the unchanged frontend application source and is detailed in the shared chart record.
- Runtime dependency audit 0; approved temporary dev-only `braces` advisory exception remains.

## Backlog/manual reference boundary

The owner attested that the existing 12 October reference was manually entered and validated.
It is not an independently retrieved original BEI export. The recorded read-only verifier found
22 aggregate conditions with zero violations, checkpoint/fully resolved through 14 October,
health ready/no hold; it performed no new replay. Six late SMA trades were non-actionable and
excluded from primary metrics. Both experiments remain separate.

| Signal session | Recorded planned-entry result |
| --- | --- |
| 8 October | 9 October entries already filled |
| 9 October | 12 October entries filled |
| 12 October | No published forward signal; do not manufacture one |
| 13 October | 14 October entries filled |
| 14 October | 15 October plans pending before EOD at this evidence cutoff |

The chart release ran no new economic catch-up, historical forward-signal regeneration or QA
trade. `Waiting` signal evaluation is not proof of a missing entry; 5/10 sessions do not close trades.
Later scheduler outcomes require their own receipt. The exact prior manual operation's effect on
all historical rows was not independently reconstructed by this read-only verifier.

## Remaining limits

- **NOT VERIFIED:** authenticated hosted owner-browser chart interactions; real outsider JWT;
  immutable Vercel deployment-to-alias asset-byte comparison (immutable URL requires Vercel login).
- **NOT VERIFIED by this release:** hosted actual-journal multi-request lifecycle/concurrency,
  disabled-owner and error-path coverage. Earlier local/fixture/SQL proof stays separately labelled;
  archived open findings are not automatically closed by this summary.
- **MONITORING:** later-session feed/job stability, receipt-budget growth, independent automatic
  watchdog dispatch. A recorded healthy session is not prospective availability or a general SLA.
- **SKIPPED_OWNER_WAIVER:** fresh full backup/populated restore for this release only. Older
  backups/rehearsals do not establish a fresh full recovery point for the chart release.
- **ROLLBACK LIMIT:** disable chart job and return previous frontend while retaining additive
  schema/data; prior app source `11234b7`/deployment `7037684774`. Instant CLI rollback unavailable
  without Vercel auth; authorized source revert/push is the fallback, not database recovery.

The four-stage frontend Scanner detail relayout is recorded released on 15 October;
no backend implementation follows from it. The documentation cleanup is complete locally;
no task is active in [PLAN](PLAN.md). No live check, application test, publication or deployment
was performed by this 21 October reconciliation.
The [canonical SOT](SOT.md), actual ledger/CSV and versioned contracts retain authority.
Workspace-level chart proof is optional material at `docs/CHART_V1_LOCAL_VERIFICATION.md`
outside this repo. Use the local recorded summary and [release history](docs/archive/IMPLEMENTATION_STATUS_BEFORE_DOC_CLEANUP_20261015.md)
when it is unavailable; do not infer fresh or missing proof.
Private operator receipts remain ignored locally; never publish raw OHLC, journal/runtime payloads,
credentials or backup contents as documentation evidence.

## Historical limits retained for task-specific review

Documentation cleanup, 21 October: D1-D4 implemented locally; all 285 tracked non-Markdown
files and protected SOT/chart/legal/checksums unchanged. Primary rule/contract review,
archive preservation, links/anchors and diff checks PASS. Independent backend fresh-reader
and workspace reviews PASS; the PT412 contract-documentation omission was restored and
independently rechecked. D1-D5 complete locally. See [traceability](docs/AGENT_RULE_TRACEABILITY_20261021.md)
and [PLAN](PLAN.md); these are uncommitted Markdown edits, not new app/cloud verification.

The [archive index](docs/archive/README.md) preserves original reports, hashes and
all old headings. Their earlier scheduler-off/001-only/dev-only/no-deploy claims
remain scoped to their dates; the release table above supersedes those current-status
claims. Archiving is not a finding resolution or a renewal of old approval.

| Historical source | Limitation retained; next action only within an authorized task |
| --- | --- |
| [Actual journal](docs/archive/ACTUAL_JOURNAL_BEFORE_HANDOVER_CLEANUP_20261021.md) | SQL-role vs real-JWT evidence, multi-page HTTP/download gap, no cash/EOD equity metrics, estimated fees and immutable development audit history stay explicit |
| [Signal conflict](docs/archive/SIGNAL_ACTION_CONFLICT_BEFORE_HANDOVER_CLEANUP_20261021.md) | Queued PGlite calls do not prove independent sessions; dedicated consumer stale/conflict UX and real hosted write-path scope need source-specific verification |
| [Source review](docs/MARKET_SOURCE_STATUS.md), [recovery](docs/SCANNER_RECOVERY_REPORT_20261003.md), [finalization](docs/BACKEND_FINALIZATION_REPORT_20261003.md) | Owner-workbook vs independent attachment provenance; amendments/archive gaps, historical execution-time and warm-up limits remain their own evidence. Do not infer current holds or current provider plan from old counts |
| [Live readiness](docs/SCANNER_LIVE_READINESS.md), [real trade](docs/REAL_TRADE_READINESS_20261003.md) | Outsider/concurrency skips, disabled-owner/raw receipt/error-path gaps and one-row vs >200 export proof are not closed by later public deployment smoke |
| [Manual result](docs/MANUAL_PUBLICATION_RESULT_20261003.md), [candidate plan](docs/MANUAL_PUBLICATION_PLAN_20261003.md) | Original failed postflight followed a committed receipt; GET-only recovery did not recover lost original before/after hashes. Exact old approval/candidate is expired; interrupted checkpoint means outcome unknown until reconciliation |
| [Persisted provenance](docs/archive/BACKEND_FINALIZATION_REPORT_20261003_BEFORE_HANDOVER_CLEANUP_20261021.md#persisted-provenance-contract-limitation) | Old held/no-signal run snapshots lacked complete per-item revision-ID/fetch-time bindings; never select an arbitrary latest revision as that chosen run input. Reassess source/contract before claiming a newer extension closes this |

The temporary dev-only `braces` advisory exception remains a recorded exception;
no dependency patch or new permanent exception is implied. Owner waivers remain
release-specific. Private operator evidence is not copied out of ignored `data/`.
