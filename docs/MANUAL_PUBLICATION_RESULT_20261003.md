# Authorized local production publication — 2026-10-03

One approved local publication was executed. **Production publication receipt
PASS; recovered GET read-back PASS within the scope below. Complete
backend/full-stack release remains NO-GO.** No second publication/replay was sent.
Scheduler off; no frontend/Vercel, Auth/membership, migration or journal mutation.

| Gate | Result | Actual proof / limit |
|---|---|---|
| Approved production publication | PASS | Plan838183f9e3fcb5bcfe6c4681be885e87a1410672137d73eeed0f1a3d2ff4ffb0; RPC receipt run3c700de4-8389-400e-b862-31f2c8998a64, replayed=false, inserted0/reused0/guard_skips0 |
| Initial publisher postflight | FAIL, retained | HTTP400/42703: scan_run_items ordering referenced nonexistent id; application had already committed |
| Recovered run/items/signals read-back | PASS, GET-only | Exact run/digest/target/live/forward,100unique tickers,45/25/30 exact statuses,0signals,RS incomplete; no publication retry |
| Revision manifest keys | PASS |200expected raw/derived identities present; this recovery sent no full-bar read RPCs |
| Old history | PASS for limited metadata/presence | Previous latest run digest/stored_at/coverage still matches prior evidence; all3old run IDs remain; no complete before/after snapshot hash proof |
| Real trade projection | PASS, publisher integrity scope | NCKL same ID,closed/revision5,risk6500/net1244/fee256/R0.191384615385; service-side GET, not new owner-RLS proof |
| Complete journal before/after equality | NOT VERIFIED | Original7table baseline fingerprints stayed in memory and were lost on postflight error; current fingerprints cannot retroactively prove equality |
| Fixture contamination check | PASS | No fixture rows in scan_runs/market_series_revisions/signals/actual_trades |
| Hosted GitHub publisher | BLOCKED | Local route only; environment absent, no dispatch or credential configuration |
| Outsider/concurrency | SKIPPED AT USER REQUEST / NOT VERIFIED | Waivers retained, not PASS |
| Disabled-owner/hosted journal error paths | NOT VERIFIED | No Auth changes, guessed receipt replay or QAtrade |
| New snapshot owner read / Vercel | PASS / BLOCKED | Owner read of new run 3c700de4 on localhost:3050 PASS (exact digest, partial 45/100, RS held confirmed by owner). Vercel deploy needs separate authorization |

## Exact published run

Production: https://hcjfxbynqzsaidlwvdfx.supabase.co (`live`, `forward`).
Target2026-10-02. Run ID `3c700de4-8389-400e-b862-31f2c8998a64`.
Stored_at from server: `2026-10-03T12:44:34.492091+00:00` (19:44:34 WIB).
Engine/run digest:
`653f9f9168b20dabfc14dc9fa18090e6ed48f5d63546c897107cc44258dd4110`.
Captured inputs: actual LOCAL Yahoo capture20261003T093419Z, verified original
129 reviewed source proofs; not GitHub37114744856 input. Coverage45evaluated,
25corporate_action_hold,30data_quality_hold,0signals,cross_section_incomplete.
Next open2026-10-05T08:58:00+07; price unknown. No source/provider/rule change.

Old run8f634f6c-efae-4837-b1eb-1db04de6ffd2 retains digest0aefe872...c121 and
stored_at2026-10-02T17:50:07.347251+00:00. Other old IDs08fb1080... andb2bba460...
remain. Never attach new fetch/digest evidence to the old run or GitHub artifact.
Operator revision manifest binds expected200input identities to this candidate;
API scan snapshots still lack explicit per-item revision-ID bindings for all
held/no-signal items. Do not select arbitrary latest revisions as chosen-run input.
Original immutable revision fetched_at may precede a replay; no timestamp rewrite.

## Failure recovery and limits

The approved publisher ran once, loading existing backend .env values into an
isolated child process. Values were not printed, passed on a command line, saved
to repo/artifacts or written back to .env. Actual source is locally prepared
uncommitted backend code, not the GitHub runner commit. No commit/push/dispatch.
All source/plan guards passed before production write. Ingestion progressed
(GET-only observed PWON revision at12:42:54Z); old snapshot still latest then.

Publication returned a receipt but original script's item query ordered by
id.asc, although scan_run_items/scan_run_signals use composite keys. Schema
inspection and GET reproduction confirmed400/42703. Kept original failure JSON;
fixed orders to run_id/ticker and run_id/signal_id, added regression cases.
Ran a separate fixed-ID, exact-plan GET-only recovery; succeeded12:49:31.511972Z.
This did not ingest/replay/publish or call owner mutation/analytics/export RPCs.

Current journal counts: trades1,fills2,corrections1,requests5,stops0,notes0,tags0.
Projection matches previously accepted owner CSV. Complete private row equality
and audit-before/after are not proved because the original baseline was not
persisted. Do not infer receipt contents/idempotency/error-path PASS from these
five request rows. Owner path raw receipt/audit inspection remains unavailable.

Future publisher now checkpoints only hashes of7journal tables and old-run rows
before writing. Failure-injection test proves checkpoint survives ingest failure
without private row bodies. This does not recover the missing original baseline.
Abrupt termination after a pre-write checkpoint means outcome UNKNOWN until GET
reconciliation, even if the checkpoint's write flag is false. No destructive
rollback/reset/deletion was performed or proposed.

The current recovery helper also inherits24h freshness/next-open guards through
offline prepare. This successful recovery was inside that window; later historical
reruns need a separately reviewed immutable-input verification mode. Do not bypass
publication guards to re-run forward publication after expiry.

## Checks actually run this continuation

- Git audit/current UTC clock, approved publisher child process once; exit1 after
  receipt because original postflight failed. Do not label initial command PASS.
- GET-only progress query and fixed-ID recovery PASS; safe HTTP/code diagnostic.
- Focused18guard cases PASS after composite scan key fix (0.38s).
- Full Python **254passed,5explicit native Docker skips**,25.26s, including the
 19publisher cases after checkpoint regression. This is local proof only.
- Ruff initially found recovery-helper long lines; fixed and Ruff PASS.
- Diff check PASS; read-only reviewer found no blocker to current GET recovery,
  with freshness/deadline and interrupted-checkpoint limitations recorded above.
- SQL72/72 remains previous local proof, not rerun; no001–007/owner unchanged
  smoke reopened. No hosted outsider/disabled/concurrent or journal mutating test.

Evidence: `docs/evidence/manual-production-publication-attempt-20261003.json`
(original failure with committed receipt) and
`docs/evidence/manual-production-publication-readback-20261003.json`
(GET-only recovery, sanitized200revision manifest and postpublication hashes).
These are separate records; original failure is not overwritten.

Files changed this continuation: publisher table ordering/hash checkpoint,
publisher regression tests, new GET-only recovery helper, these two evidence
records, this report, PLAN/status/readiness/handoff dated updates. Existing
AGENTS.md user edit and earlier prepared workflow/files preserved. No frontend
edit, .env edit, migration change or new paid service.

Next safe action: frontend owner-read this **new** run via existing localhost3050
and confirm100items/status/holds/provenance display; retain prior owner trade
read/MA10CSV proof. Frontend deploy still needs independent authorization and
Vercel smoke. Skipped/unverified access and journal gates remain disclosed;
partial coverage/RS hold and no hosted publisher remain explicit limitations.
