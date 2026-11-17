# Signal action conflict contract — migration007

Migration `202610010007_signal_action_conflict_http.sql` preserves the original
001 function semantics while changing custom 40001 to PT412 via CREATE OR REPLACE.
Applied migration files remain immutable. No ledger, fee, fill or policy rule changes.
[Status](../IMPLEMENTATION_STATUS.md) owns dated rollout proof; schema 001–016 is
recorded there at the 15 October cutoff, without a fresh remote check here.

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

## Consumer and proof boundaries

A consumer must fail safely on RPC errors, preserve named arguments and surface
stale state explicitly; refresh before a new intent. Scanner annotations never
create fills/trades. Verify the current caller and dedicated conflict UX in its
source rather than treating an older development probe as a production UI audit.

[Original conflict handoff](archive/SIGNAL_ACTION_CONFLICT_BEFORE_HANDOVER_CLEANUP_20261021.md)
retains development application, local tests, SQL-claim rollback and browser limits.
Queued PGlite calls are not independent sessions or genuine JWT/hosted HTTP proof.
Later local-disposable and release evidence remain separately labelled in status.

## Two-session rehearsal to run on an authorized disposable database

This procedure was not executed by the documentation cleanup. Original unexecuted
rehearsal limits are retained in the archive; current credentials/target availability
are unknown here. Use an explicitly authorized isolated PostgreSQL fixture target,
compatible schema with at least the original 001–007 prerequisites, one enabled test
owner and a signal from `tests/export_scan_fixture.py`. Check current migration history
first. Never run this setup on live production or use shared development as a restore target.

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
