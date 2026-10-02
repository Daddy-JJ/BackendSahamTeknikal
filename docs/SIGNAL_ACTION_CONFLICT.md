# Signal action conflict contract — migration007

`202610010007_signal_action_conflict_http.sql` was applied to development
`vgmkpsestahkfahzdtae` on 2026-10-01 (success observed02:47 UTC), with
`data_mode=fixture`. It is not applied to production. It replaces `set_signal_action` with exactly001's
function, changing only CREATE to CREATE OR REPLACE and custom40001 to PT412.
001 remains immutable. No financial engine, signal, fill, fee or policy change.

RPC signature remains `set_signal_action(p_signal_id text, p_action text,
p_expected_revision integer, p_request_id uuid)`. Enabled owner required. Request
UUID is scoped by owner; the advisory transaction lock serializes that owner's
actions. Receipt lookup precedes revision validation: an exact successful retry
returns its original receipt even after a later revision. Changed payload with
the same UUID is23514/idempotency_conflict (HTTP400), stale revision with a new
UUID isPT412/revision_conflict (HTTP412). Neither business error is retryable.
Failures leave no action change, receipt or audit event. Refresh current state;
only a new user intent gets a new UUID. Do not treat a replay receipt as current
state or create a trade from a watchlist/planned annotation.

Frontend was inspected read-only. Its only current `set_signal_action` caller is
the development owner probe in `src/app/auth/check/actions.ts`; it fails safely
on any RPC error and does not retry that error. Backend tests execute that exact
function with injected PT412 and23514, verifying failure redirect, one call and
unchanged named arguments. It has no dedicated scanner conflict message yet.
The existing actual-journal UI already accepts PT412; that does not prove a
production scanner action UI. Frontend must add/verify a dedicated stale message
when exposing scanner mutations. No frontend files were modified.

SQL tests cover exact replay, changed-payload conflict, old receipt after newer
revision, stale revision, no receipt/audit residue, owner isolation and disabled
owner, as well as eight concurrent caller submissions to PGlite. PGlite0.5.8 is
single-connection PostgreSQL18.3 WASM: queued requests do **not** verify two
independent PostgreSQL sessions, advisory lock waiting or hosted HTTP mapping.

Development preflight confirmed005/006, one enabled owner and the old40001
function. A checksum-verified, fixture-guarded SQL Editor handoff applied007;
postcheck returned PT412 present,40001 absent, and one existing signal-action
receipt/audit. `supabase/tests/dev_signal_conflict_smoke.sql` then passed in a
hosted rollback-only transaction: exact replay returned one result, changed
payload returned23514, stale new request returnedPT412, and only the successful
request added a receipt/audit inside the transaction. The final ROLLBACK left
the pre-existing one receipt/audit. This used a SQL-simulated owner claim, **not
a genuine Auth JWT or separate database sessions**. SQL Editor application is
not a Supabase CLI history entry. Real owner JWT/PostgREST and two-session tests
remain open.

On2026-10-01 the local `/auth/check` page showed an active development owner
session and an existing watchlist action at revision1 with one request and one
audit. The page exposed no control for a fresh RPC call, and its probe did not
send a new mutation because that action already exists. It did not expose the
original request UUID/payload needed for an exact replay. No JWT was inspected
or copied; no new action was added to shared fixture data. Therefore the hosted
SQL simulation above remains the only 007 write-path smoke in this task. A new
successful request would add a permanent action/audit to shared development;
run the real HTTP cases on an authorized disposable target or after recovering
the exact existing replay inputs through an approved owner-only path.

## Two-session rehearsal to run on an authorized disposable database

Not executed yet; user has no authorized disposable target/DB credentials.
Use actual PostgreSQL, full001–007 schema, fixture mode, one enabled test owner
and a signal from `tests/export_scan_fixture.py`. Never run this setup on live
production or use shared development as a restore target.

For each scenario choose fresh request UUIDs and record revision before/after.
Both clients BEGIN, SET LOCAL ROLE authenticated and set the same database-local
owner claim. Record `pg_backend_pid()` from each (must differ). Use bounded
statement_timeout=15s. Database-local claims are SQL tests, not real Auth JWTs.

1. Identical replay: A calls RPC at revisionN then keeps its transaction open.
   B sends identical UUID/payload while A is open. Observe B waiting on A's
   advisory lock through pg_stat_activity/pg_locks. Commit A; B must return the
   identical stored result. Commit B. Exactly one receipt/audit and revisionN+1.
2. Competing actions: A/B use different UUIDs, same expectedN. Hold A before
   commit; B waits. Commit A; B returnsPT412, ROLLBACK B. Only A has a receipt/
   audit; revisionN+1. No timeout, retries or additional notes/actions.
3. Changed payload, same UUID: A commits planned; B's skipped payload under that
   UUID returns23514. ROLLBACK B; original action/receipt/audit remain unchanged.
4. Abort winner: A calls then ROLLBACK instead of commit. Waiting B using the
   same request succeeds once atN+1; A leaves no receipt/audit residue.
5. Different enabled owner using the same UUID must have independent ownership
   and must not read/mutate the first owner's action. Verify RLS on the rows.

Record sanitized results and durations; no tokens or financial rows in logs.
Repeat through real Auth JWT/PostgREST after authorized deployment, using
genuine owner signals or the approved isolation method. Do not present this
prepared checklist as an executed concurrency smoke.

References: [PostgREST PT status codes](https://docs.postgrest.org/en/v14/references/errors.html),
[Supabase custom40001 retry issue](https://supabase.com/docs/guides/troubleshooting/high-cpu-and-infinite-transaction-retries-when-using-custom-error-codes-in-rpc-functions-77326b).
