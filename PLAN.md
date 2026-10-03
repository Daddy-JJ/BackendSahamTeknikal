# Autonomous Scanner, Paper Journal & Data Reconciliation Plan — 2026-10-03

Scope: backend and scheduler workflows.
Goal:
1. Reconcile corporate actions and refine data quality rules for 55 held stocks to expand coverage toward 100/100 and unlock RS_BREAKOUT_V1.
2. Implement automated Paper Journal engine (forward signal simulation & performance tracking) strictly isolated from actual journal.
3. Configure scheduled scanner workflows (20:17 WIB primary / 22:17 WIB recovery) with IDX calendar guards.

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
  Action: Add `.github/workflows/scheduled-scanner.yml` with cron schedules `17 13 * * 1-5` (20:17 WIB) and `17 15 * * 1-5` (22:17 WIB recovery).
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

