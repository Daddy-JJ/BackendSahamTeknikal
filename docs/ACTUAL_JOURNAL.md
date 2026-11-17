# Actual journal: canonical backend contract

Stable ledger/analytics/export policy. Source: migrations 005/006 and applicable
forward reporting migrations; inspect exact source signatures before changes.
[Status](../IMPLEMENTATION_STATUS.md) records schema 001–016 at the 15 October
evidence cutoff; this document did not recheck production. No historical setup
recipe or report below is permission to apply a migration or create QA trades.

## Ledger and monetary policy

`apply_actual_journal(p_action, p_trade_id, p_payload, p_request_id)` requires an
enabled owner JWT. It atomically writes ledger events, the projected trade,
request receipt and audit. Browser/service roles cannot directly mutate tables;
service_role cannot call journal mutation/analytics/export RPCs. Privileged
database administrators are outside RLS's protection boundary.

- `create`: draft with no fills. Required ticker, primary_strategy, initial_stop,
  exit_policy_snapshot; optional signal_id must match ticker/strategy/data mode.
  Owner and data mode come from the authenticated session/database, never payload.
- `fill`: side, filled_at (ISO timestamp with timezone), quantity, price_idr,
  fee_idr, fee_status (`actual` or `estimated`), expected_revision. Buy changes
  status to **open immediately**, with provisional risk until entry finalization.
  UI must use `entry_finalized_at`, not `status='draft'`, for buy/finalize controls.
- `finalize`: expected_revision; freezes the buy batch/risk. First sell can do
  this atomically. Additional buys after finalization are rejected.
- `stop`: expected_revision, new_stop, reason (3–500 trimmed characters). Applies
  only to finalized open trades; initial stop and risk never follow the new stop.
- `note`: expected_revision, body (1–4000 trimmed characters).
- `tag`: expected_revision, tag (2–40 letters/digits/underscore/hyphen).
- `correct_fill`: expected_revision, fill_id, full replacement quantity,
  price_idr, fee_idr, fee_status, reason; optional filled_at and boolean
  restate_initial_risk. Omitted timestamp preserves the latest effective one.
  Changing finalized buy risk requires explicit `restate_initial_risk=true`.
  Side/trade reassignment and deletion/void are not supported by this contract.

Every non-create mutation requires the current revision. Unknown payload fields
are rejected. Decimal values may be numbers or exact decimal strings; monetary
inputs allow at most 16 integer and 4 fractional digits, no exponent/NaN/Infinity.
Quantity is positive whole shares within bigint bounds; it is not auto-rounded
to lots. This is a manual ledger, not a broker execution/lot-validity guarantee.
Never default missing fees to zero; zero must be explicitly entered and labeled
with its actual/estimated status.

Exit snapshot is immutable. Supported fields: version (nonempty string), mode,
target_r, ma_type, period, optional config_hash. `fixed_rr` requires positive
target_r and forbids MA parameters; `ma_close` requires SMA/EMA and 5/10/20 with
target_r absent/null. `manual` has no target/MA parameters. Planned RR is null
for MA/manual. Snapshot equality filters are available when versions alone do
not distinguish parameter sets. This contract does not execute actual exits.

Effective fills are ordered by timestamp, then a database identity sequence.
Equal timestamps therefore retain input order, never random UUID order.
Corrections append immutable rows and recompute the ledger from the entire
effective history. Invalid chronology, buying below initial stop, or overselling
rolls back every write, including request/audit. A correction can reopen a
closed position; closed_at/realized R clear and closed statistics lose that row.
Audit stores the previous trade projection, correction reason and resulting
ledger; original fills and earlier corrections remain available.

Buy fees enter weighted average basis; sell fees reduce proceeds. No additional
estimated fee model is added over a fill fee. Calculations use PostgreSQL numeric;
allocation keeps intermediate precision and projections round to 4 decimals
(PostgreSQL numeric ties away from zero). Closed R uses rounded net P&L / locked
price risk, rounded to 12 decimals. Partial realized P&L is available, but closed
R is null until all shares are sold. The final sell consumes all remaining basis.
This policy is distinct from IDR display formatting and verified broker rules.

One owner advisory transaction lock serializes requests. Same owner/request UUID
and exact JSONB payload returns the original receipt even after newer revisions;
changed payload under that UUID fails. A failed transaction consumes no receipt.
Use the same UUID for transport retries; generate a new UUID for a new intent.
The response to replay is historical, so refresh current trade state afterward.
New writes lock/check deployment mode; an old receipt replay performs no mutation.

Stale `expected_revision` fails with `PT412/revision_conflict` (HTTP 412), an
application precondition failure rather than transient SQLSTATE `40001`.
Do not retry a stale request indefinitely: refresh the trade, and submit a new
request UUID only for a new intent. An exact retry of an already successful
request still returns its original receipt. Migration 006 changes this conflict
mapping without changing ledger arithmetic, fees, fills or risk policy.

## Analytics and separation

`actual_journal_analytics(p_from=null, p_to=null, p_strategy=null,
p_exit_version=null, p_exit_snapshot=null)` retains existing four named arguments;
the fifth is optional and matches the complete exit snapshot exactly.

Closed cohort dates are **inclusive Asia/Jakarta exit dates**. Open/draft counts
are current positions under the strategy/config/data-mode scope, not exit-date
cohort members. `mode=actual`, `basis=IDR`, sample size, wins/losses/breakeven,
net P&L, expectancy R, win rate, PF/payoff and undefined status codes are returned.
Multiple tags do not multiply a trade. No closed: ratios null. No losses: PF and
payoff null with no-loss status. Losses without wins: PF zero. Breakeven belongs
in the win-rate denominator. `estimated_fee_trades` and `fee_quality` disclose
estimates in the closed cohort; fee corrections change both quality and net P&L.

Actual tables/RPCs never read paper results or create paper fills. Paper engine
tests and persistent paper/reporting contracts remain separate; see the contract
registry and dated implementation status for their evidence. Cash ledger, EOD marks and actual equity
drawdown/return metrics are unavailable and must not be inferred from closed P&L.

## Export contract

`export_actual_journal(p_from=null, p_to=null, p_strategy=null,
p_exit_version=null, p_exit_snapshot=null, p_after=null, p_limit=200,
p_status=null)` is owner-only, actual-only, and scoped to current database mode.

- For export matching closed analytics, pass **p_status='closed'** and identical
  date/strategy/version/snapshot filters. With no status/date filters it includes
  drafts/open/closed; a date filter excludes positions with no exit date.
- Response version is `actual-journal-export-v1`, with explicit mode/data_mode,
  cohort and filter metadata, rows, has_more, next_after. Page size is 1–200.
  Reuse all filters and pass next_after as p_after until has_more=false. Never
  export just the first page without indicating truncation.
- Each row is one trade: trade ID/revision, ticker/status, primary strategy,
  signal ID, immutable exit snapshot, planned RR, initial/current stop, initial
  and provisional risk, open shares, remaining basis, realized P&L/R, total fees,
  fee quality, finalized/closed timestamps, Jakarta exit date, tags and notes.
- Money, quantity, planned RR and R are **decimal strings** (nullable where
  undefined), preserving precision through JSON. Clients format them; they must
  not rebuild official P&L from floating point arithmetic.
- `contracts/actual-journal-export.mjs` owns the ordered CSV headers and
  `actualJournalCsv(page, {header:true})`. Use header=false for subsequent pages.
  UTF-8, CRLF, quoted cells, doubled quotes, null as empty; arrays/config are JSON
  within cells. Text starting with spreadsheet formula characters (including
  whitespace prefixes) is apostrophe-prefixed. Validated signed decimals remain
  numbers, so a negative loss is not rewritten as arbitrary formula text.
- This export is a trade summary, **not a backup** of fills/corrections/audit.
  Individual RPC pages are consistent snapshots; multiple HTTP pages are not one
  database snapshot. Export during a quiet journal session; concurrent edits need
  a future snapshot/export-job mechanism before reproducible archival claims.

Frontend integration: use this RPC and fee_quality; retain the existing four
analytics arguments and use entry_finalized_at for controls. Consumer integration
and genuine hosted owner-session proof must be verified for their exact source.

## Rollout evidence and integration limits

[Original actual-journal development/production handoff](archive/ACTUAL_JOURNAL_BEFORE_HANDOVER_CLEANUP_20261021.md)
preserves every dated test, sample, helper command, environment, correction and
SQL-role vs real-JWT limit. Its dev-only/production-pending statements describe
earlier dates, not the later recorded 001–016 release. Do not rerun those guarded
creation scripts on an initialized database or rewrite immutable history.

Use [Auth/isolation guide](AUTH_AND_DISPOSABLE_SMOKE_GUIDE.md) for an authorized
safe target, [readiness](PRODUCTION_READINESS.md) for releases and
[contract registry](../contracts/README.md) for separate persistent paper/reporting.
The actual journal has no cash ledger/EOD marks/equity return or drawdown; closed
P&L cannot be substituted for those missing metrics. Hosted production lifecycle,
error paths, genuine outsider/disabled-owner and multi-page browser proof retain
their exact dated limits in status. A one-row real owner read or SQL rollback
cursor test does not establish all of those boundaries.

<!-- Compatibility anchors for consolidated historical sections. Original content is in archive/ACTUAL_JOURNAL_BEFORE_HANDOVER_CLEANUP_20261021.md. -->
<a id="m4-actual-journal-backend-contract-and-development-handoff"></a>
<a id="production-real-trade-read-evidence--2026-10-03"></a>
<a id="development-migration-handoff-and-verified-rollout"></a>
