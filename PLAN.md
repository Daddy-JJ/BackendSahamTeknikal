## Chart V1 live release — 2026-10-15

Action: completed owner-authorized release on existing resources, no Supabase upgrade. Fresh full
backup/populated restore rehearsal SKIPPED_OWNER_WAIVER, not PASS; no full data recovery established.
Proof: exact013–016 CLI migrations, expanded ACL and18 economic/config fingerprints PASS; canonical
all-page reports matched while paused. After resume, all nonoperational fields match; only captured
watchdog enabled/last_checked_at metadata is projected for comparison. Automation restored/active.
Final backend608 tests PASS/5 native opt-in SKIP, focused43 chart tests/Ruff/review PASS. Default256
source receipts/hard500, max4 read-only requests, ordered/cancel-on-error projection, no source truncation
or trading/provider changes. Cloud100/100 ticker build succeeds, real frontend parser live probes PASS.
Frontend Production deployment/source and full private-receipt evidence tracked in workspace handoff.
Owner browser/real outsider JWT and immutable-to-alias byte proof remain NOT VERIFIED. Existing dev-only
braces release exception retained. Feature rollback keeps additive schema and all journal/source data.

## Chart V1 — explicit release exception, 2026-10-15

Action: owner requests no Supabase upgrade and explicitly permits skipping fresh full backup and
populated restore rehearsal. Record both SKIPPED_OWNER_WAIVER, not PASS. Fix sanitized diagnostic
classification independently; retain exact pending013–016/hash/CLI dry-run, paused automation,
server-side economic/reporting fingerprints, chart ACL and artifact canary before frontend release.
Proof: schema013–016 applied via exact pending-only CLI; postflight confirms18 economic/config
fingerprints and all-page canonical reporting unchanged, expanded chart ACL/owner/outsider/anon checks
PASS. Automation restored exactly. Waiver guards reject10 cases and prevent autoresume after uncertain
DDL. Diagnostics39 tests PASS. Canary38693142193 rejected ADRO131 revisions above128; metadata counts
confirm ADRO/BFIN131, others<=71. Raise shared default to256 (hard maximum500), preserve explicit
over-budget failure/no truncation, then fresh cloud canary before frontend. No financial payload export.
Rollback is feature disable/previous frontend, not full data recovery. This scoped owner decision
supersedes the previous fresh backup/rehearsal gate for this release only; no paid resources added.

## Previous Chart V1 — Tahap 6 authorized release preparation, 2026-10-15

Action: user-authorized commit/push and chart rollout. Read-only hosted preflight proved migration
history001–012; existing013 performance indexes and014 reporting optimization must be rehearsed
together with015/016 from a fresh populated012 backup. Pause/resume exact prior workflow/watchdog/Cron
state; preserve backoff and all economic rows. Optional chart writer remains disabled before capability.
Proof: preflight PASS, credentials present without values emitted; no active jobs/leases/dispatches.
Private operator guards8 negative cases and canonical pagination/money sensitivity PASS. Cloud schema,
chart activation and frontend release are not yet performed. Stage5 backend proof follows.

## Previous Chart V1 — Tahap 5 backend lokal, 2026-10-14

Action: additive 016 private core/public bounded wrapper, response budget 1 MiB tanpa truncation,
indexed null/equality context lookup dan service-only expired-cursor cleanup (maksimum 200k/job).
Proof: full Python 569 PASS / 5 native opt-in SKIPPED; SQL/PGlite 160 PASS, Ruff PASS; native upgrade/
rollback 015/016, ACL dan 18 economic/config fingerprints PASS. Original 015 hash tidak berubah.
Core equivalence test membuktikan logic 015 dipertahankan selain lookup; benchmark canonical
500 slot + 500 marker 287.650 bytes; query plan populated 5k artifacts PASS. Coverage empat modul
chart 90,40% aggregate, minimum 85,17%. Tidak ada provider fetch atau mutasi ekonomi/produksi.

## Previous Chart V1 — Tahap 2 selesai lokal, 2026-10-14

Action: implement immutable canonical artifact, frozen resolver, owner reader/service writer/input loader,
shared limiter, pinned pagination dan migrasi additive 015. Job cloud opsional masih dinonaktifkan.
Proof: Python 568 PASS / 5 native opt-in SKIPPED; SQL 155 PASS; chart 32 PASS dan coverage empat modul
90.13% aggregate, masing-masing >80%. Native upgrade 014→015, rollback, grants dan 18 fingerprint PASS;
Ruff/diff PASS. Canonical Python→SQL→FE fixture PASS. Tidak mengubah ekonomi atau produksi.
Shared [verification](../docs/CHART_V1_LOCAL_VERIFICATION.md) mencatat batas bukti, security dan tindakan berikutnya.
Working tree belum commit; 015 belum diterapkan remote. Berikutnya: Tahap 4 integrasi halaman,
Tahap 5 QA lebih luas, Tahap 6 rilis terotorisasi. Harga aktual dengan basis yang belum terbukti ditahan;
budget sumber/deferred catalog tetap eksplisit, tanpa fallback provider mentah.

## Previous Chart V1 — Tahap 1, 2026-10-14

Status: SPECIFICATION ONLY; belum ada artifact/reader/migrasi chart. Cakupan aktif hanya Tahap 1.
Shared plan: [UX, Action/Proof dan acceptance C01–C18](../docs/CHART_V1_IMPLEMENTATION_PLAN.md).
Contract: [ticker-chart-v1](../contracts/ticker-chart-v1.md). Pada Tahap 2 vendor kontrak versi sama beserta
hash ke repo ini agar CI independen tidak bergantung pada parent workspace.

Action (Tahap 1): rancang bounded owner-only read_ticker_chart_v1, frozen resolver, canonical indicator
artifacts, separate source/event revisions, gaps/provenance dan cloud writer yang tidak memblokir ekonomi.
Proof: inspeksi source/schema/engine dan review dokumen; belum ada tes runtime/migration/live chart.

Next Action (Tahap 2): contract/temporal/RLS RED tests, immutable artifact dan reader additive, writer
idempotent, query bounds/limiter dan native populated upgrade checks. Proof: C01–C10/C16–C18 dan frontend
parser compatibility. Resolusi cutoff digest tidak boleh diasumsikan foreign key signal ke market.
Source inspected: backend667a90d. Audit ulang recovery/provenance pada HEAD ini sebelum live integration;
tidak menyimpulkan perbaikan OHLC/produksi dari judul commit. Tidak melakukan catch-up dalam fitur chart.

## Approved P1-P8 incident remediation - 2026-10-13

Status: RELEASED; P8 catch-up/retry integrity VERIFIED LIVE, full economic resolution PARTIAL due to source holds. User authorization covers source, additive SQL012, independently scheduled Supabase cloud watchdog and latest-main catch-up. Trading/provider/actual-ledger rules unchanged. The dispatch PAT is held only in Edge secrets; pg_net queues only a one-use fixed-purpose ticket, with no long-lived credential.

Proof: Python425 PASS/5 explicit native skips and Ruff PASS; SQL/PGlite139 PASS (including Edge tests, populated upgrade, RLS, lease takeover fencing and ticket/cap/grace cases). Fresh encrypted full backup, isolated populated restore/rehearsal and second encrypted local copy PASS. SQL012 applied with catalog/history/fingerprints matching rehearsal. Compatible frontend Production and public smoke PASS; owner-browser unavailable. GitHub scheduler and */20 Supabase Cron ACTIVE; actual server tick succeeded. The corrective released runtime commits held state atomically, and a fresh retry replays the same revision/request without changing economic rows/events/evaluations/statistics. Original plans/config/actual ledger/publications are preserved. Owner-browser and automatic Cron-to-Edge-to-GitHub dispatch remain separate unverified boundaries at this receipt; three subsequent exchange sessions need monitoring.

Release corrective action: the first fresh-main catch-up exposed SQL22P02 because the incremental query supplied a session date to SQL002's bigint revision cutoff. Remove that incorrect predicate and validate the reconstructed source's last session against the target. Proof: original hosted read-only query400/22P02, corrected query200, real adapter lookup/reconstruction PASS, regression for integer cutoff/future source rejection PASS; full425-test rerun PASS. No migration or financial mutation is needed for this correction. Corrective source was re-released, automation resumed and fresh-main catch-up/retry verified. Both jobs explicitly report paper_data_hold rather than a database exception; do not label missing market data recovered.

1. Action: P1/P2 strict missing-field/session diagnostics, guarded same-Yahoo closed daily short profiles, immutable source captures and persisted incremental history with validated overlap. Proof: positive/negative source tests and read-only probes; source failures remain held without inventing prices or using future bars.
2. Action: P3/P4 independent bounded tracked-book replay, economic chronology, attempted/resolved health and failed held-job outcomes. Proof: restart/missed-session/primary/paper-only/idempotency tests, immutable risk/config and unchanged actual ledger.
3. Action: P5 service-only leases/heartbeat/fenced canonical writers and independently scheduled capped watchdog using Edge-only repository-limited PAT. Proof: local security/policy tests, hosted function/secret/extension provisioning, invalid-ticket400/unreserved409; server Cron and actual dispatch results tracked separately.
4. Action: P6/P7 compatible diagnostics/health readers and frontend release after fresh backup/rehearsal/SQL gate. Proof: hosted reader/parser/ACL checks, frontend40 units/192 browser cases/typecheck/lint/build and public HTTP/asset smoke.
5. Action: P8 fresh latest-main catch-up, per-object reconciliation and retry without economic duplication. Proof: exact job/source receipts and frozen/ledger/event/statistics comparison; source holds must remain honest. At least three subsequent exchange sessions need future monitoring.

## Remediation release verified - 2026-10-10

Action: completed the authorized release after the backup/restore gate; applied the additive backend migration before the compatible frontend and verified the released runtime's recovery and retry behavior.
Proof: local checks recorded below passed. Production deployment, public HTTP/asset checks, hosted reporting contract validation, SQL-role access-denial checks and recovery idempotency were verified. Detailed operator receipts and financial reconciliation are intentionally retained locally and are not published in this repository.

Limits: authenticated owner-browser interaction, real outsider JWT and subsequent-session operational stability remain unverified. Continue monitoring scheduled sessions. Trading rules, historical configuration and the actual ledger remain preserved. Earlier local/historical evidence follows.

## Incident remediation - locally verified, release pending (2026-10-10 WIB)

Status: IMPLEMENTED AND VERIFIED LOCALLY. G01-G17 fixes cover independent persisted paper recovery, verified-calendar cadence, job/checkpoint health, exact-risk/evaluation integrity and canonical journal/reporting. Production/history remains unchanged in this remediation; commit/push/migration/deployment/recovery await separate release authorization.

Action: implement the approved incident plan while preserving signal-close entry, initial risks, both exit experiments, actual ledger/CSV and old book/config. Proof: Python377 PASS/5 native opt-in SKIPPED; Ruff PASS; SQL/PGlite116 PASS, with final SQL01118/release-plan5/persistent-reporting21 subsets PASS after the additive health timestamp update; native PostgreSQL integrity/CAS/RLS probe PASS (six checks). Frontend unit36 PASS; reporting36 and journal69 browser cases PASS across full runs plus corrected-case reruns; production-built scanner66 cases PASS across the full65 passing cases and the affected-case rerun; typecheck/lint/build/diff checks PASS.

Next action: after release authorization, fresh encrypted backup/restore rehearsal, SQL011 capability first, compatible frontend, runtime/workflow, then committed-cohort paper-only Oct9 recovery and live reconciliation. Authenticated production browser, real outsider JWT, current production restore and multi-session stability remain unverified. The native backup/restore subset was PARTIAL due Docker startup/cleanup timeouts; the separate no-network integrity probe passed with test-only bounded startup allowances. Do not infer current production recovery from the local eight-entry/seven-open/one-closed replay. Gap mapping, exact evidence limits, prior failed attempts and release order: [handoff](../docs/REMEDIATION_RELEASE_20261010.md).

# Active audit and remediation plan - entry incident 2026-10-09

Status: REVIEW / RETEST; application source and production data unchanged. User requests root-cause analysis, journal/analytics retest and comprehensive repair planning, not implementation/deployment in this turn. Full evidence, gap register and cross-repo sequencing: [shared audit](../docs/AUDIT_JOURNAL_ENTRY_20261009.md).

- Action: reproduce signal Oct8 / entry Oct9 using persisted production book read-only and fresh verified source; trace scheduler and checkpoint. Proof: live snapshot21:31WIB has8pending/checkpointOct8; local-only replay21:37WIB with3valid tickers gives8entries/7open/1closed, without production writes.
- Action: plan independent existing-book recovery, latest-closed-session selection across weekend/holiday, explicit operational health and bounded provider retries. Proof required: chronological restart/replay, publication failure vs paper success/failure, delayed Friday cron onSaturday, holiday and unknown-calendar cases, no duplicate economic events and visible overdue status.
- Action: plan forward economic uniqueness/evaluation guards, confirmed-untradable input, reporting exclusion/sensitivity eligibility and missing IDR payoff/PF/experiment comparisons. Proof required: adversarial local probes rejected atomically, populated migration rehearsal preserving actual/legacy, native concurrency when available; backend schema/RPC before compatible frontend/runtime rollout.
- Action: retest existing domain/SQL contracts without mutating production. Proof: full Python343PASS/5opt-in nativeSKIP; focused89/scheduler9 are subsets, SQL/PGlite98PASS, live owner-role reporting accepted by four actual frontend parsers. Full limitations/test results in shared audit.

Recovery commit, migration, push and deploy remain future release steps. Preserve original plan/history/config; never reissue historical signals as forward. Earlier plans below are historical.

---

## Production SQL010 verified - 2026-10-09 WIB

Action: apply only frozen SQL010 after frontend unit30/browser102/typecheck/lint/build PASS and backend gates PASS.
Proof: pinned SupabaseCLI dry-run listed only010; remote history now001-010, catalog matches the full populated-backup rehearsal, and all actual/paper/publication rows remained identical. Read-only real owner reporting payloads pass current strict frontend parsers; SQL-role outsider/anon denials and private-helper ACL checks PASS. Existing model/config, eight pending Oct9 plans and actual ledger are preserved. This SQL-role proof is not a real JWT/browser session.

Next: commit/push both tested repos, verify exact Vercel source SHA, run fresh primary/recovery scanner for closed Oct8, and record actual coverage/idempotency/integrity. Shared root release documents retain exact remote receipts after source publication; no persistent QA account or trade was created.

# Active follow-up: OHLC integrity and reporting coverage (2026-10-08)


## Final local evidence - 2026-10-08 follow-up

Action: verify approved cash-dividend metadata exemption, unchanged OHLC, held splits/unknown action coverage, paper/research shared gate, frozen risks, and compatible SQL010 readers before publication.
Proof: full Python suite 343 PASS / 5 native opt-in SKIP; separate explicit native backup/restore/release suites 12 PASS; focused policy tests 19 PASS; Ruff from backend root PASS; SQL/PGlite 98 PASS. Read-only production capture replay: all 100 persisted 2026-10-08 series valid under candidate policy, all OHLC unchanged. This is not a new production scanner result.

Action: prepare reversible metadata migration using current production state, preserving actual ledger, paper model/plans/evaluations and publication history.
Proof: fresh encrypted database/roles backup and verified second local encrypted copy; full isolated no-network restore and SQL010 rehearsal PASS. All persistent public rows and canonical reporting results preserved except additive scanner coverage; production catalog/readback still pending. Backup recovery currently requires this Windows profile/machine; portable/offsite recovery is not verified.

User clarification: cash-dividend nominal metadata does not alter baseline OHLC; eligibility must protect price integrity rather than require matching cash-dividend amounts.

- Action: Version the nonblocking cash-dividend metadata policy for the approved Yahoo `auto_adjust=False` basis; retain exact source-review facts without approving mismatches, preserve matching split approvals, and keep unresolved splits/unknown actions, missing actions, invalid/stale/missing bars held. Preserve prices, ledger, prior signals and immutable paper configuration.
  Proof: Regression tests for changed/new dividends, simultaneous reviewed/unreviewed splits, unsupported basis, missing actions, paper and scanner/RS behavior; replay serialization and unchanged OHLC assertions. Pending.
- Action: Add forward SQL010 scanner coverage metadata independently of journal/observation coverage, without reader arithmetic or authentication changes; release manifest and rehearsal chain remain exact.
  Proof: SQL upgrade/security/latest-scan tests and populated native restore rehearsal before remote migration. Pending.
- Action: Release the compatible frontend labels and unbroken monetary amounts after backend capability; verify exact deployed SHAs and hosted metadata while preserving activation, actual ledger and existing plans.
  Proof: Frontend unit/typecheck/lint/build/browser checks; fresh encrypted backup/restore; remote migration history and contract readback. Pending.

Prior evidence and history follow.

# Close-signal paper and reporting (2026-10-08)

## Production rollout authorization - 2026-10-08

Progress (2026-10-08 18:08 WIB): SQL administrator access is verified via TLS. Legacy scheduled writer is temporarily paused. Fresh encrypted database/roles backup was fully restored into a no-network local target; catalog, actual ledger and owner/Auth linkage match. SQL009 rehearsal passed. A second local encrypted copy is verified; DPAPI recovery requires this Windows profile/machine, and off-site recovery is NOT VERIFIED. SQL008 catalog matches all ten categories exactly, so history008 was reconciled via pinned CLI; dry-run listed only009 and production migration history now contains001-009. Hosted rollback-only smoke passes init/config immutability, CAS/retry/reload, owner/outsider/anon SQL RLS claims, no direct service DML, real frontend parsers and unchanged actual-ledger hashes. No persistent QA trade/account was created. GitHub owner variable is verified. Next: release source to main/Vercel, initialize immutable model and verify fresh released-SHA jobs. Authenticated browser acceptance remains NOT VERIFIED.

Action: user authorized backend migration/production activation, frontend release/full deployment and verification. Inspect remote history and compatible backups first; apply only pending forward migrations, verify RPC/RLS, release frontend before enabling the new scheduled runtime. Existing source candidate is backend e4ed019 / frontend d94f243. Production mutations remain limited to this project and approved model; preserve real actual trades and legacy history.
Proof: record remote migration history/catalog, integrity fingerprints, source SHA/deployment IDs, activation configuration/time, owner/anonymous access and real scheduler receipts. Report unexecuted checks explicitly. No artificial production trade or test account is needed for smoke.

Source publication authorization (2026-10-08): commit and push to `feat/persistent-paper-reporting-v1`. Production main rollout, remote migrations, activation and deployment remain separate gates. A branch push can start existing CI/preview automation; it does not establish hosted acceptance.

Action: Extend existing engine with immutable close-reference entry, fee-inclusive Rp1m lot sizing, separate Fixed2R/SMA10 experiments, persistent Supabase runtime and signal research checkpoints (not time exits).
Proof: full Python 324 PASS / 5 native-Docker SKIPPED; Ruff PASS; full SQL/PGlite 93 PASS including upgrade/RLS/retry/ledger and sibling frontend parsers. Frontend unit 28 PASS; browser desktop/mobile scanner 36, journal 40, reporting 12 PASS; lint/typecheck/production build PASS. Local implementation is complete against available checks. Native Docker follow-up is recorded above; hosted acceptance remains NOT VERIFIED. Production rollout is authorized; verified migration/preflight progress is recorded above.

# Autonomous Scanner, Paper Journal & Data Reconciliation Plan — 2026-10-03

Scope: backend and scheduler workflows.
Goal:
1. Reconcile corporate actions and refine data quality rules for 55 held stocks to expand coverage toward 100/100 and unlock RS_BREAKOUT_V1.
2. Implement automated Paper Journal engine (forward signal simulation & performance tracking) strictly isolated from actual journal.
3. Configure scheduled scanner workflows (18:18 WIB primary / 19:19 WIB recovery) with IDX calendar guards.

## Phase A: Data Quality & Corporate Action Reconciliation (COMPLETED & VERIFIED)
- Step A.1:
  Action: Refine volume and historical suspension rule in `scanner/src/idx_scanner/context.py` so that active trading stocks with volume > 0 on session t and valid history are not permanently held by ancient suspensions (> 60 bars ago), while maintaining `data_quality_hold` for zero volume on session t or unnormalized closed days.
  Proof: Unit tests in `test_calendar_normalization.py` verifying target-session zero volume holds vs historical non-zero sessions pass. `data_quality_hold` count dropped from 30 to 0.
- Step A.2:
  Action: Extract and verify missing KSEI dividend proofs for the 22 cash dividend tickers using collected official KSEI announcements in `data/sources/ksei-research-20261003/`.
  Proof: Updated `config/reference/ksei-reviewed-dividends-20261003.json` with 228 events across 85+ tickers; updated `manual-runner-release.json` with LF SHA256 checksums.
- Step A.3:
  Action: Run local full-universe evaluation via `manual_scanner_smoke.py`.
  Proof: Evaluated count increased from 45 to 90/100; corporate_action_hold reduced to 10 (7 unadjusted stock splits + 3 unconfirmed dividends); zero data_quality_hold.

## Phase B: Automated Paper Journal Simulation Engine (COMPLETED & VERIFIED)
- Step B.1:
  Action: Implement paper trade generation from forward published signals (`pending_entry` at `next_session.opens_at`) with immutable risk basis and default exit policy (`fixed_rr` target_r=2, and modular `ma_close`).
  Proof: Added `paper_book_to_dict`, `paper_book_from_dict`, `step_paper_book`, and `summarize_book` in `scanner/src/idx_scanner/paper.py`. Created standalone runner in `supabase/scripts/paper_journal_runner.py`. Zero cross-contamination with `actual_trades`.
- Step B.2:
  Action: Implement EOD paper position lifecycle evaluation:
  1. Open check: stop gap vs take-profit gap.
  2. High/low check: SL hit, TP hit, or dual hit marked `ambiguous_both_hit` (SL-first baseline).
  3. MA breakdown check for `ma_close`.
  Proof: Deterministic tests in `scanner/tests/test_paper.py` and `scanner/tests/test_paper_journal_runner.py` passed (25 passed).

## Phase C: Automated Scheduler in GitHub Actions (COMPLETED & VERIFIED)
- Step C.1:
  Action: Add `.github/workflows/scheduled-scanner.yml` with cron schedules `18 11 * * 1-5` (18:18 WIB) and `19 12 * * 1-5` (19:19 WIB recovery).
  Proof: Workflow YAML valid, integrates `scheduled_scanner_runner.py` with Asia/Jakarta calendar holiday/weekend guard, market closure guard, paper journal simulation, and idempotent Supabase publication.
- Step C.2:
  Action: Run validation and smoke tests across all components.
  Proof: Pytest 259 passed (5 skipped Docker tests, 0 failures), PGlite 72 passed (0 failures), Ruff check 100% clean across all python files.

## Phase D: Complete Universe Coverage (100/100) & RS_BREAKOUT_V1 Activation (COMPLETED & VERIFIED)
- Step D.1:
  Action: Expand corporate action reconciliation in `scanner/src/idx_scanner/corporate_actions.py` to support exact verified stock splits and bonus shares with official KSEI proof, verified provider basis, and zero candle distortion (`price_changes=False`) per SOT line 56.
  Proof: Added unit test `test_exact_reviewed_split_reconciles_cleanly_without_altering_candles`. All 12 dividend/split reconciliation tests pass.
- Step D.2:
  Action: Reconcile official KSEI corporate actions for the remaining 10 stocks: 7 stock splits/bonus shares (`ISAT`, `PTRO`, `CUAN`, `RAJA`, `RMKE`, `SGER`, `BRPT`) and 3 dividend tickers (`UNVR`, `SCMA`, `INET`). Downloaded and verified primary KSEI announcements in `data/sources/ksei-research-20261003/`.
  Proof: Updated manifest `config/reference/ksei-reviewed-dividends-20261003.json` to 256 verified events (251 unique source files). Updated source archive `reviewed-action-source-archive-20261003.zip` (7.9 MB, sha256 `fca09719...`) and verified via `hydrate_reviewed_sources.py`. Updated `config/live/manual-runner-release.json` checksum.
- Step D.3:
  Action: Evaluate KOMPAS100 full universe in `manual_scanner_smoke.py` and inspect RS cross-section ranking.
  Proof: Full universe evaluation achieved **100/100 evaluated** (`coverage_valid: 100`, `ranking_status: "complete"`, `corporate_action_hold: 0`, `data_quality_hold: 0`). `RS_BREAKOUT_V1` generated candidates with full cross-sectional ranking across 100 tickers, identifying the Top 20% (Top 20 tickers with positive returns up to +82.27% for SGER).
- Step D.4:
  Action: Execute full backend regression test suites.
  Proof: Pytest 260 passed (5 skipped Docker native, 0 failures), PGlite 72 passed (0 failures), Ruff check on scanner package 100% clean.

## Phase E: Post-Audit Hardening & Remediation (Backend Only — 2026-10-04)
Addresses independent audit findings B-01, B-02, B-03, B-05, B-06, B-07, B-09, D-01:
- Step E.1: Fail-Closed Runner & Unknown Calendar Handling (B-06, B-07)
  Action: Update `scheduled_scanner_runner.py` so that unknown calendar dates return `blocked_configuration: calendar_unknown` with exit 1; require Supabase credentials when `--execute` is passed (exit 1 if missing); require `coverage_valid > 0` (exit 1 if 0).
  Proof: CLI tests verify non-zero exit code on missing credentials, zero coverage, and unknown calendar dates.
- Step E.2: Historical Zero-Volume Validation & Paper Quality Hold (B-01, B-02)
  Action:
  1. In `scanner/src/idx_scanner/context.py`, enforce `data_quality_hold` if any bar in the 60-session active evaluation window has `volume == 0`.
  2. In `scanner/src/idx_scanner/paper.py`, enforce `data_valid = (quality(series, session, calendar) == "valid")` so corporate-action / quality holds transition paper trades to `data_hold` without generating false fills or +2R.
  Proof: Unit tests verify penultimate zero-volume yields `data_quality_hold`, and unreconciled corporate actions hold paper trades in `data_hold`.
- Step E.3: Single-Fetch Unified Snapshot & Commit SHA Binding (B-03, B-09)
  Action:
  1. Refactor `scheduled_scanner_runner.py` to eliminate duplicate provider fetches: execute a single authoritative fetch & publication via `run_once`, then pass the committed signals and series to the paper journal simulation.
  2. Bind `GITHUB_SHA` or git HEAD to `source_revision` in `Signal` creation.
  Proof: Run evidence demonstrates identical input digests between scanner publication and paper journal simulation; signal records contain valid commit SHA.
- Step E.4: Cohort Experiment Separation in Paper Book (B-05)
  Action: In `scanner/src/idx_scanner/paper.py:summarize_book()`, add `by_experiment` metrics breakdown to prevent cross-contamination between `fixed_rr` and `ma_close` policies.
  Proof: Summary dictionary outputs distinct metrics per experiment ID.
- Step E.5: Scripts Lint Clean-up & Documentation Reconciliation (D-01)
  Action: Resolve all 10 ruff violations in `supabase/scripts/`, update `IMPLEMENTATION_STATUS.md` with explicit distinction between offline verification and hosted execution.
  Proof: `ruff check supabase/scripts` passes with 0 errors; full pytest 262 passed (5 skipped Docker native, 0 failures), PGlite 72 passed (0 failures). Phase E verified and complete.

## Phase F: Canonical Analytics Contracts & Live Paper Persistence (Paket 1 — 2026-10-04)
Addresses frontend audit gaps R-01 (Paper live persistence) and R-02 (Canonical R-curve & strategy attribution):
- Step F.1: Migration 008 Canonical Analytics & Live Paper Schema
  Action: Create `migrations/202610040008_canonical_analytics_and_paper.sql` providing:
  1. `actual_journal_r_curve`: chronological points, cumulative R, max drawdown, and exact parity with `actual_journal_analytics`.
  2. `actual_journal_attribution`: strategy breakdown, win/loss counts, net P&L IDR, and profit factor status matching aggregate analytics.
  3. `paper_trades` table with owner-only RLS and `read_paper_journal` RPC, preserving total logical isolation from `actual_trades` (Invariant #7).
  Proof: Migration checksum registered in `release-manifest.json` (`55ac81dd10d9eabbec1adf9dbd8cb6a493ec0fab8db4286fea95121a67f7963a`).
- Step F.2: Automated PGlite & Pytest Verification
  Action: Add dedicated test suite `tests/canonical-analytics-paper.test.mjs`, update `release-plan.test.mjs` and rehearsal guards.
  Proof: SQL test suite expanded from 72 to 76 tests (all 76 PASSED, 0 failures). Pytest full suite: 262 PASSED, 5 skipped, 0 failures. Ruff: 0 errors.
