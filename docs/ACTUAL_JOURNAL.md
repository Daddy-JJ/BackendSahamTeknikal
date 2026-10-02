# M4 actual journal: backend contract and development handoff

Migration `202609290005_actual_journal.sql` was applied on 2026-09-30 to
Supabase development `vgmkpsestahkfahzdtae`, with `data_mode=fixture`.
Production `hcjfxbynqzsaidlwvdfx` stays live and received no test data. This
is a SQL Editor application; inspect the schema before later CLI migration
history reconciliation. All commands below start inside the backend checkout.
Frontend belongs to another chat/repo.

Migration `202609300006_actual_journal_conflict_http.sql` was subsequently
applied to development only. It preserves the 005 function body and changes
stale `expected_revision` failure from SQLSTATE `40001` to `PT412`, with message
`revision_conflict`. PostgREST maps `PT412` to HTTP 412. This is an application
precondition failure, not a transient PostgreSQL serialization error; clients
should refresh the trade and submit a **new request UUID** only for a new intent.
An exact retry of an already successful request retains its original receipt.
Do not retry a stale request indefinitely. This change leaves the ledger,
RLS, analytics and export signatures unchanged. Hosted SQL returned PT412
immediately with no receipt; frontend subsequently confirmed real owner-JWT
HTTP412 in its2026-10-01 two-tab retest. [Supabase documents the custom-40001 retry issue](https://supabase.com/docs/guides/troubleshooting/high-cpu-and-infinite-transaction-retries-when-using-custom-error-codes-in-rpc-functions-77326b).

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
tests remain separate; persistent paper journal/analytics and ambiguity
sensitivity are still open M2/M4 work. Cash ledger, EOD marks and actual equity
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

Frontend integration handoff: use this RPC and fee_quality; keep the existing
four analytics arguments; use entry_finalized_at for controls. No frontend changes
were made here. UI/BFF export wiring and owner-session smoke remain separate gates.

## Development migration handoff and verified rollout

Prerequisites: dev project `vgmkpsestahkfahzdtae`, migrations 001–004,
data_mode=fixture, expected enabled dev owner. Local `.env.development` already
holds SUPABASE_URL and APP_OWNER_USER_ID; do not overwrite it or use `.env`.
The generator needs no service key and makes no network request.

```powershell
cd C:\xampp\htdocs\SahamTeknikal\backend
.\scanner\.venv\Scripts\python.exe supabase\scripts\prepare_dev_actual_setup.py
```

Output: ignored `data/dev-actual-journal-vgmkpsestahkfahzdtae.sql`. The generator
allows only the exact dev HTTPS URL. SQL guards reject live/missing mode, wrong
owner, missing revision/deadline capability, or an existing actual schema. A
table lock prevents a mode change during application. There is no seed or mode
change. SQL itself cannot universally infer the hosted project ref; the URL
check at generation plus SQL mode/owner checks complement verifying SQL Editor's
project before execution. Never change production to fixture to pass a guard.

The generated file was checked against the SQL Editor contents and executed
once on the development project. It returned `actual_journal_ready=true`,
`actual_export_ready=true`, `data_mode=fixture`. All seven actual tables and
the explicit latest-correction embedding returned HTTP 200 through PostgREST.
Do not rerun this guarded creation migration; it rejects an existing schema.
SQL Editor application does not reconcile Supabase CLI migration history.

For an existing development database with 005 but without 006, generate the
guarded 006 handoff with:

```powershell
.\scanner\.venv\Scripts\python.exe supabase\scripts\prepare_dev_actual_conflict_fix.py
```

It writes ignored `data/dev-actual-conflict-fix-vgmkpsestahkfahzdtae.sql`.
The generator checks the exact development URL; its SQL checks fixture mode,
the enabled owner, presence of 005 and its old 40001 clause. It changes only
the function definition, with no seed, fee calculation or policy change. That
exact generated SQL was applied once to development and returned
`actual_conflict_http_ready=true`, `data_mode=fixture`. Do not rerun it; the
guard rejects a function already carrying PT412. Production has not received
006. SQL Editor application does not update CLI migration history.

The following verification was performed with an explicitly labeled synthetic
trade. The hosted rollback-only SQL smoke used `SET LOCAL ROLE authenticated`
and a database-local owner claim, **not** a real owner Auth JWT. It passed the
canonical SOT sample (risk 1200, fee 100, net P&L 1000, R 0.833333333333),
partial position, estimated fee/correction, replay, stale revision, oversell,
and export/analytics equality. A two-connection replay on hosted PostgreSQL
used different backend PIDs; the second waited 7407 ms and returned the
original create receipt while the first committed a note. One TEST trade and
one create receipt remained, at trade revision 2. A second two-session race
submitted different note requests with `expected_revision=2`; one committed
revision 3, and the other returned 40001 `revision_conflict` without a receipt.
This fixture remains in the development audit history. Anonymous API reads/calls were denied (42501); a
real disposable outsider JWT saw empty actual tables/embedding and received
42501 for all three RPCs even after the TEST trade existed; the account was
deleted. Disabled-owner denial was exercised in hosted SQL role simulation.

Frontend status/audit dated 2026-10-01 reports successful real owner-JWT browser
smoke for the SOT ledger, corrections, analytics, one-page closed CSV, identical
replay and logout. Two stale attempts timed out before006. After006, its real
owner two-tab retest passed: winning note revision11→12, stale11 rejected with
PT412/HTTP412 promptly, no additional note/revision. The backend's earlier SQL
role/claim result remains SQL evidence; the real-JWT HTTP result is attributed
to the frontend report, read only and not rerun by this backend chat.

The rollback-only [201-closed-trade cursor smoke](../supabase/tests/dev_actual_cursor_smoke.sql)
also ran in hosted development. The backend RPC built all synthetic trades and
fills inside one transaction, export returned 200 then 1 row with no further
cursor, and analytics returned closed=201/net P&L=2010. After `ROLLBACK`, a
read-only query found zero corresponding trades and request receipts. This
proves hosted SQL pagination. The frontend's two-page HTTP/download flow
remains untested against persistent >200 rows; do not seed immutable journal
history solely to manufacture that proof. Its local HTTP-double test covers
the UI flow, while this rollback-only test covers the backend boundary.

Further real owner-JWT integration checks should use the actual application
session, without service-key owner impersonation:

1. Record 005 readiness and unchanged fixture mode; capture before counts.
2. Create TEST draft; buy 100@100 fee25 and 100@102 fee25; finalize at stop95;
   change current stop; sell 100@105 fee25 then 100@108 fee25.
3. Verify risk1200, fee100, net1000, R0.833333333333, four fills; partial excluded
   from closed metrics. Exact fill replay leaves quantities/audit counts stable;
   changed-body UUID replay and oversell fail without residue.
4. Verify correction/estimated fee quality, original event retention, revision
   conflict, snapshot filter, closed export totals and formula-safe CSV.
5. Test actual owner JWT on PostgREST, and disabled-owner JWT if an appropriate
   disposable membership can be provisioned safely. Anonymous and outsider
   probes above already passed against the populated development ledger.
6. Two hosted sessions proved same-request replay serialization and competing
   different-request revision rejection at the database layer. Repeating through
   real owner JWT/PostgREST remains an integration gate.
   Retain fixture audit rows deliberately in dev; do not delete immutable
   financial history for cleanup.

Remaining gates: production smoke, frontend multi-page HTTP integration,
paper persistence/analytics, cash/equity scope, and tested backup/restore. M2 also
needs authoritative runtime calendar/universe/symbol mappings, 5–10 ticker live
fetch-to-web proof and GitHub runner. No live/provider run is authorized here.

Production preparation and its single go/no-go checklist are in
[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md). As of2026-10-01, production
is live with only foundation001, no CLI migration history, no actual schema,
and GitHub Auth disabled. Neither005 nor006 has been applied to production.

Implementation references checked during this audit:
[PostgreSQL numeric precision and special values](https://www.postgresql.org/docs/current/datatype-numeric.html),
[PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html),
[Supabase function search_path and grants](https://supabase.com/docs/guides/database/functions).
No runtime or dependency versions were changed.
