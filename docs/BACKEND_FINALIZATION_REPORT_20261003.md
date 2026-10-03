# Backend finalization â€” 3 October 2026

Decision: **NO-GO for mandatory backend/full-stack release**. Partial live reads
are working. Remaining hosted mutation/access and full runner/publisher gates
must not be replaced with local tests. User approved backend commit/push and one
manual full-universe dispatch, and declined a disposable hosted test project.
Scheduler stays off; frontend and Vercel are outside this authorization.

| Gate | Result | Evidence |
| --- | --- | --- |
| Production migrations/FK/RPC | Prior PASS, unchanged | 001â€“007 through 202610010007, deployed 2026-10-02T06:57:07Z; not reopened |
| Owner latest snapshot read | PASS | Frontend genuine owner session observed 2026-10-02T22:50:09.953Z, HTTP200 run/items/signals; 4 pages, 100 unique tickers; source evidence hash accepted, not rerun |
| Anonymous hosted reads | PASS | 2026-10-03T09:41:19Z: 12 private tables and analytics/export GET RPC denied HTTP401/42501 |
| Calendar/universe/mapping | PASS within configured dates | 100 mappings/identities, effective 2026-08-03 inclusiveâ€“2027-01-30 exclusive; 651 known history sessions and 72 explicit closures |
| New target candles | PASS for this fetch only | Yahoo 100/100 complete target 2026-10-02, fetched 2026-10-03T09:34:33Zâ€“09:35:01Z; old failed fetch remains FAIL |
| Warm-up | PARTIAL | AADI430, CBDK407, COIN299, EMAS247, RATU410 bars; do not grant 600-bar strategies eligibility |
| Action/anomaly quality | PARTIAL / held | 45 evaluated, 25 action holds, 30 quality holds; unresolved dates/actions not removed; RS incomplete |
| Hosted full-universe fetch/evaluation | PASS, partial-quality scope | Successful retry37114744856,100 fetched,45 evaluated; artifact downloaded/hash verified |
| Hosted production publisher | BLOCKED | Manual workflow is fetch/evaluation only, no database publication or receipt |
| Hosted outsider/disabled-owner/lifecycle/concurrency | BLOCKED | No safe target or genuine approved ledger activity/identities; no permanent QA trades permitted |
| Frontend Vercel smoke | BLOCKED | Separate deployment authorization and actual Vercel smoke still required |

Production remains https://hcjfxbynqzsaidlwvdfx.supabase.co, `live`. Latest
published run remains `8f634f6c-efae-4837-b1eb-1db04de6ffd2`, target 2026-10-02,
stored 2026-10-02T17:50:07.347251Z, digest
`0aefe872fe3aa9ead45f1f98f9980ff96cd819142ddcc0f9f64a0a83c1c4c121`.
It has 45/100 evaluated, 25 corporate action holds, 30 quality holds, zero
published signals and incomplete RS. The newer local capture was not published;
its separate engine digest is
`653f9f9168b20dabfc14dc9fa18090e6ed48f5d63546c897107cc44258dd4110`.
Different fetch/input snapshots must not overwrite published history.

## Sources, scope and tests executed in this continuation

Git status and backend diffs were audited; existing work preserved. Canonical
docs and three frontend release/evidence/prompt files were read only. Imported
owner evidence confirms the same UUID/digest/counts without copying JWT or
repeating owner smoke. Development fixture was not read as live proof or written.

Runtime version `idx-calendar-known-sources-20261002-v2-explicit-closures` and
universe `kompas100-20260803-20270129-workbook-v1` verified against frozen manual
release hashes. Mapping identities are JKT/IDR/EQUITY, exact provider symbols;
source remains the owner-supplied original BEI workbook with recorded SHA256,
not an independently downloaded official attachment. Historical sessions have
date-only provenance; execution timing applies from October 2. Next session
2026-10-05 opens at 08:58 WIB; next-open price remains unknown.

KSEI November 2024 retry now returned HTTP200; its five relevant notices include
ADRO exchange-rate/schedule, UNVR, BBCA and SCMA schedules. They are queued, not
automatically approved. The amendment queue is still incomplete because February
2026 returned HTTP500. Original 129 proof manifest and all holds remain unchanged.
Old COIN source classification and 308 anomalous rows are retained; no additional
runtime suspension exception, split adjustment or price synthesis was introduced.

Commands actually executed:

```powershell
# backend
git status --short
git diff -- scanner/src/idx_scanner
& .\scanner\.venv\Scripts\python.exe .\supabase\scripts\manual_scanner_smoke.py --target 2026-10-02 --execute-fetch --require-usable
# backend/scanner
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --basetemp=C:\xampp\htdocs\SahamTeknikal\backend\data\pytest-finalization-20261003
.\.venv\Scripts\ruff.exe check src tests
# backend/supabase
npm.cmd test
```

Python **232 passed, 5 explicit native Docker skips**, 83.33s; SQL **72/72**,
79.82s, local PGlite. Ruff passed, including six recovery operator helpers.
These tests cover the stable PT412/idempotency, ledger, analytics/export/FK and
revision contracts locally; they are not hosted mutation or independent-session
proof. Metadata-only workflow changes afterward add run URL/commit and explicitly
record no publication; final lint/diff and focused tests are recorded with release.

Read-only audit scripts under ignored `data/` checked raw receipt SHA256/input
digests, prepared digests, source retries and anonymous denials. Only safe
aggregates, dates/statuses and market input hashes were saved under docs/evidence.
No Auth user/member changes, migration/history writes, database publication,
actual QA trade or frontend modification occurred in this continuation.

## Exact remaining input and next action

No more owner snapshot login or migration repair is needed without a relevant
change. Production immutable ledger HTTP tests require either genuine owner
activity that the owner wants retained, or a separately authorized hosted
isolation design. Declining a disposable project leaves that gate BLOCKED;
deployment approval alone cannot safely generate the missing activity. Outsider
and disabled-owner tests also need authorized genuine sessions or approved
temporary Auth/membership isolation. Do not create/promote accounts silently.

The manual workflow is safe for the authorized full-universe smoke: only public
source hydration and Yahoo IO; no production secret, cron or database write.
Its partial-quality success closes only hosted execution, not complete RS or
publisher. A true publisher run needs proven input hydration/coverage, explicit
target and next-open guards, and a controlled production credential environment.

Frontend should retain its current partial adapter and owner-read PASS, unchanged
journal contracts, and lack of provider freshness metadata in the selected run.
New local fetched timestamps belong to the local receipt, not to the older
production run. See FRONTEND_DEPLOYMENT_HANDOFF.md; no Vercel authorization implied.

Evidence: `docs/evidence/backend-finalization-audit-20261003.json`,
`frontend-owner-read-accepted-20261003.json`,
`fresh-yahoo-scanner-recheck-20261003.json`. Historical failed capture remains
`fresh-yahoo-scanner-smoke-20261003.json`.

## Authorized GitHub dispatch result

First dispatch: https://github.com/Daddy-JJ/BackendSahamTeknikal/actions/runs/37114212953
on c22c7d41b8b9b71c9431c086c9f61acc18d3b235, FAILED at09:47:29Z before fetching.
Source hydration rejected changed bytes; artifacts empty, publication not attempted,
receipt null. Local diagnosis confirmed changed BBCA interim HTML bytes; hosted
logs do not identify the specific failing source, so exact hosted source attribution
is not asserted. A reviewed-public-source ZIP (4,033,293 bytes) preserves all129
original hashes. Archive hash/member/path/tamper and existing-file checks reject
changes before any restore. This restores historical evidence reproducibly; it is
not approval of current amendments. User explicitly approved the fix plus one retry.
A checksum audit command initially used a nonexistent manifest field (sha256);
corrected sha256_lf audit passed7/7. No migration change.
Per-fix final Python regression:235 passed,5 explicit skips in29.41s;14 focused
archive guards passed. Ruff/diff checks passed. Clean local archive hydration
restored129 files into an empty ignored directory with unchanged source hashes;
archive credential-pattern scan found0 files. SQL72/72 result remains unchanged.
An operator documentation update encountered Windows cp1252 decoding; rerun used
explicit UTF-8. Archive validation had already passed; no evidence was fabricated.
Retry dispatch https://github.com/Daddy-JJ/BackendSahamTeknikal/actions/runs/37114744856
on b4762fd063f45df6a9b29fb3d0a75b1fbdc8d371 PASSED: hydration129 and fetch100,
finished2026-10-03T09:57:22.242630Z (16:57:22 WIB), partial45/25/30,0 signals,
RS incomplete. Hosted engine digest2ed30d1968c2aa8b6491541d712fc37aca8a475d8d7de9f8e84d247aab512241.
Artifact11270993302 (1875 bytes) was downloaded, ZIP SHA256 independently matches
8f51cb6c35a0b6ce7d3312bb9bb7e679ce2a6e052822bd432c08c3778b781726.
No publication attempt, receipt null; hosted publisher remains unproven.
Original failed run is preserved. Final backend Git status checked after evidence
commit/push; no workflow auto-triggers, new cron, frontend or production writes.

## Persisted provenance contract limitation

Market revision provenance is canonical in `market_series_revisions.fetched_at`,
`input_digest`, `provider_version`, `metadata.provenance` and `metadata_source`.
RPC `read_market_series(p_revision_id)` returns exact source text plus timestamps
under owner RLS. These timestamps describe the original immutable revision:
identical ingest replay does not refresh its fetch time. They are not stored_at.

Current scan_runs.snapshot/scan_run_items.snapshot do not persist an explicit
per-ticker revision-ID/fetch-time binding for every held/no-signal item. Signals
carry input_digest, but this zero-signal run cannot supply that linkage from
signals. Frontend must not pick the latest ticker revision and label it as the
chosen run's input. Operator publication evidence contains revision verification,
but is not a new owner API field. A future versioned run-input metadata extension
would need its own review and smoke; no schema/001–007 was edited here.
