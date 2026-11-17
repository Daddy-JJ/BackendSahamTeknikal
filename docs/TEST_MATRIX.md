# Backend test and risk matrix

Maintained requirement/risk → source-suite index, reviewed 21 October 2026.
Filenames and selected assertions were inspected; no application tests ran.
Presence in this table is not PASS, coverage percentage, hosted proof or profitability.
Use [DEVELOPMENT](../DEVELOPMENT.md) for commands and [status](../IMPLEMENTATION_STATUS.md)
for exact dated outcomes, source/environment, explicit skips and unresolved gates.

## Deterministic engine, data and execution

| Risk / original handoff IDs | Actual suite files | Proof boundary |
| --- | --- | --- |
| T01–T04/T28 seed/indicator/pivot numerics | [test_indicators_strategies.py](../scanner/tests/test_indicators_strategies.py), [test_contracts_pipeline.py](../scanner/tests/test_contracts_pipeline.py) | deterministic synthetic/reference inputs |
| T05–T09/T25–T27 available-at/lookahead/RS ties/barrier/prior20/reclaim | [test_engine.py](../scanner/tests/test_engine.py), [test_indicators_strategies.py](../scanner/tests/test_indicators_strategies.py) | no future information; complete comparison universe required |
| T10–T13/T21 next session/missing/gap/dual-hit/late | [test_paper.py](../scanner/tests/test_paper.py), [test_ma_lifecycle.py](../scanner/tests/test_ma_lifecycle.py), [test_close_signal_paper.py](../scanner/tests/test_close_signal_paper.py) | approved timing/ambiguous-state rules, no intraday ordering inference |
| T14 idempotency/reload | [test_persistence.py](../scanner/tests/test_persistence.py), [scan.test.mjs](../supabase/tests/scan.test.mjs), [persistent-paper-reporting.test.mjs](../supabase/tests/persistent-paper-reporting.test.mjs) | local SQL/Python; queued PGlite calls are not independent hosted sessions |
| T15–T16 partial/stale/actions/immutable inputs | [test_contracts_pipeline.py](../scanner/tests/test_contracts_pipeline.py), [market-revisions.test.mjs](../supabase/tests/market-revisions.test.mjs), [test_dividend_reconciliation.py](../scanner/tests/test_dividend_reconciliation.py), [test_cash_dividend_price_integrity.py](../scanner/tests/test_cash_dividend_price_integrity.py), [test_verified_untradable.py](../scanner/tests/test_verified_untradable.py) | synthetic/regression source evidence, no automatic source approval |
| Provider dates/retries/null data/safe errors | [test_providers.py](../scanner/tests/test_providers.py), [test_incremental_provider.py](../scanner/tests/test_incremental_provider.py), [test_provider_target_retry.py](../scanner/tests/test_provider_target_retry.py), [test_provider_close_recovery.py](../scanner/tests/test_provider_close_recovery.py) | mocked/captured inputs do not prove fresh feed health |
| Calendar provenance/dated vs timed sessions | [test_calendar_normalization.py](../scanner/tests/test_calendar_normalization.py), [test_historical_calendar_dates.py](../scanner/tests/test_historical_calendar_dates.py), [test_run_command.py](../scanner/tests/test_run_command.py) | no invented exchange hours or official-source certification |
| Manual publication/project/hash/deadline guards | [test_manual_publication_guards.py](../scanner/tests/test_manual_publication_guards.py), [test_first_live_hold_guard.py](../scanner/tests/test_first_live_hold_guard.py), [test_repaired_live_guard.py](../scanner/tests/test_repaired_live_guard.py), [test_ksei_recovery_guards.py](../scanner/tests/test_ksei_recovery_guards.py), [test_eodhd_comparison_guard.py](../scanner/tests/test_eodhd_comparison_guard.py) | guard tests are not remote publication/retry authorization |
| T23 signal research / AI boundary | [test_signal_research.py](../scanner/tests/test_signal_research.py) | research stays separate; AI is not official engine or an enabled product promise |

## Ledger, reporting, access and recovery

| Risk / original handoff IDs | Actual suite files | Proof boundary |
| --- | --- | --- |
| T17–T18 actual fills/corrections/stop/risk/replay/revision | [actual-journal.test.mjs](../supabase/tests/actual-journal.test.mjs), [test_actual_handoff.py](../scanner/tests/test_actual_handoff.py), [actual-setup.test.mjs](../supabase/tests/actual-setup.test.mjs) | local contract coverage exists; hosted lifecycle/error paths retain dated limits |
| T19/T22 closed cohort/null/no-loss/tag attribution/CSV exact decimals | [actual-journal.test.mjs](../supabase/tests/actual-journal.test.mjs), [canonical-analytics-paper.test.mjs](../supabase/tests/canonical-analytics-paper.test.mjs), [persistent-paper-reporting.test.mjs](../supabase/tests/persistent-paper-reporting.test.mjs) | canonical actual/paper cohorts are separate; no inferred cash/EOD equity metrics |
| T20 SQL grants/RLS/owner/spoofed IDs/conflict HTTP | [scan.test.mjs](../supabase/tests/scan.test.mjs), [signal-frontend-contract.test.mjs](../supabase/tests/signal-frontend-contract.test.mjs), [foundation-catalog.test.mjs](../supabase/tests/foundation-catalog.test.mjs), [test_owner_rls_probe.py](../scanner/tests/test_owner_rls_probe.py) | SQL-role/local probes do not become genuine production owner/outsider/disabled JWT proof |
| T29–T33 separate experiments/MA/ambiguity/persistent paper comparison | [test_paper.py](../scanner/tests/test_paper.py), [test_ma_lifecycle.py](../scanner/tests/test_ma_lifecycle.py), [test_paper_runtime.py](../scanner/tests/test_paper_runtime.py), [persistent-paper-reporting.test.mjs](../supabase/tests/persistent-paper-reporting.test.mjs) | specific source assertions, not a claim every product acceptance item is complete |
| Scheduler/source recovery/lease/idempotency/holds | [test_scheduled_scanner_runner.py](../scanner/tests/test_scheduled_scanner_runner.py), [test_paper_scheduler_integration.py](../scanner/tests/test_paper_scheduler_integration.py), [test_paper_runtime_runner.py](../scanner/tests/test_paper_runtime_runner.py), [test_paper_lease.py](../scanner/tests/test_paper_lease.py), [test_entry_incident_recovery.py](../scanner/tests/test_entry_incident_recovery.py), [paper-integrity-health.test.mjs](../supabase/tests/paper-integrity-health.test.mjs) | no prospective provider/job stability guarantee |
| Watchdog dispatch/private tickets/health/fencing | [processing-recovery-watchdog.test.mjs](../supabase/tests/processing-recovery-watchdog.test.mjs), [watchdog-edge.test.mjs](../supabase/tests/watchdog-edge.test.mjs) | mocks/local SQL not independent automatic cloud dispatch receipt |
| Reviewed historical backfill/provenance | [test_reviewed_backfill.py](../scanner/tests/test_reviewed_backfill.py), [test_reviewed_backfill_import.py](../scanner/tests/test_reviewed_backfill_import.py), [test_reviewed_backfill_scheduler.py](../scanner/tests/test_reviewed_backfill_scheduler.py) | no historical forward-signal regeneration or inferred original BEI export |
| Reporting/index performance | [performance-indexes.test.mjs](../supabase/tests/performance-indexes.test.mjs), [optimize-trade-reporting.test.mjs](../supabase/tests/optimize-trade-reporting.test.mjs) | exact local query/semantic tests, not hosted SLA |
| T24 backup/restore/release planning | [test_production_backup.py](../scanner/tests/test_production_backup.py), [test_backup_restore.py](../scanner/tests/test_backup_restore.py), [test_backup_diagnostics.py](../scanner/tests/test_backup_diagnostics.py), [test_backup_inspection.py](../scanner/tests/test_backup_inspection.py), [test_restore_target.py](../scanner/tests/test_restore_target.py), [test_native_release_rehearsal.py](../scanner/tests/test_native_release_rehearsal.py), [release-plan.test.mjs](../supabase/tests/release-plan.test.mjs) | opt-in/native/diagnostic tests never prove a fresh populated production restore |

## Charts and consumer checks

| Risk | Actual suite files | Proof boundary |
| --- | --- | --- |
| Immutable artifact/quality/grants/RPC | [test_chart_artifact.py](../scanner/tests/test_chart_artifact.py), [test_chart_fixture.py](../scanner/tests/test_chart_fixture.py), [chart-artifacts.test.mjs](../supabase/tests/chart-artifacts.test.mjs), [chart-quality.test.mjs](../supabase/tests/chart-quality.test.mjs) | fixture/SQL checks retain their environment |
| Runtime/overlay/source budgets/order/concurrency | [test_chart_runtime.py](../scanner/tests/test_chart_runtime.py), [test_chart_overlays.py](../scanner/tests/test_chart_overlays.py), [test_chart_revision_budget.py](../scanner/tests/test_chart_revision_budget.py), [test_chart_receipt_concurrency.py](../scanner/tests/test_chart_receipt_concurrency.py) | no immutable deployed-byte or authenticated hosted-browser proof |
| Native chart upgrade/rollback/grants | [chart-native-rehearsal.py](../supabase/tests/chart-native-rehearsal.py) | requires explicit isolated native target; no execution implied |
| Frontend UI/Auth/scanner/journal/report/chart | Optional sibling frontend repo: `tests/workspace.spec.ts`, `scanner.spec.ts`, `scanner-chart.spec.ts`, `journal.spec.ts`, `reporting.spec.ts`, `auth.spec.ts`, `chart-journal-integration.spec.ts` | repo [FrontEndSahamTeknikal](https://github.com/Daddy-JJ/FrontEndSahamTeknikal); inspect exact consumer source/ref; absent sibling is NOT VERIFIED |

## Open proof limits

Do not turn the old “remaining T17/T18/T22” list into a claim those suites are absent;
they now exist locally. Conversely, source coverage does not close hosted real-JWT,
production mutation/concurrency, >200-row browser download, owner chart interaction,
immutable deployment/alias bytes, fresh full restore or later-session stability.
The 15 October backup/restore owner waiver is specific to that release. Native
Docker skips and the temporary dev-only dependency advisory remain explicitly scoped.
No source-rule suite proves profitability, live feed availability or TradingView parity.
[Original matrix](archive/TEST_MATRIX_BEFORE_HANDOVER_CLEANUP_20261021.md) preserves
the earlier risk list and its historical gaps without making it a new task queue.

<!-- Compatibility anchors for consolidated historical sections. Original content is in archive/TEST_MATRIX_BEFORE_HANDOVER_CLEANUP_20261021.md. -->
<a id="test-matrix-and-remaining-gates"></a>
