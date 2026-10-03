# Scanner recovery report â€” 2026-10-03

Decision: **NO-GO for scheduled scanner and full-stack go-live**. Production has a
verified partial market-data snapshot; the latest fresh Yahoo fetch cannot supply
complete target candles. Scheduler remains disabled. No frontend files, journal
trades, Auth settings or migrations were changed in this recovery step.

## Evidence and boundaries

| Gate | Result | Observed evidence |
| --- | --- | --- |
| Production schema | Prior PASS, unchanged | Release 001â€“007 through 202610010007, applied 2026-10-02T06:57:07Z; not reapplied here |
| Source-backed dividends | PARTIAL | 129 exact proofs across 42 tickers, including seven prior BBCA proofs; hashed sources; no price adjustment |
| Anomalous bars | BLOCKED | 308 zero-volume open-session rows across 30 held tickers; classification file records unresolved dates |
| Fresh Yahoo target candles | FAIL | 100 fetched, zero transport errors, target 2026-10-02 close missing for all 100; latest complete session 2026-10-01 |
| Production partial publication | PASS within scope | 45/100 evaluated, 25 action holds, 30 quality holds, zero signals, RS incomplete; 200 revision digest read-backs |
| EODHD replacement feasibility | BLOCKED | Free account: 20 requests/day; AMMN response 254 bars, insufficient for 600-bar rules; older problem dates absent |
| Full-universe GitHub runner | BLOCKED | Manual-only workflow prepared locally, not pushed or dispatched; no scheduled trigger or database credentials |
| Hosted owner/outsider/disabled-owner mutation RLS | BLOCKED | No new hosted JWT/mutation proof; prior disposable Auth/HTTP tests are local evidence |
| Frontend deployment | NO-GO | Requires remaining backend gates, frontend smoke, and separate deployment authorization |

Production project is `hcjfxbynqzsaidlwvdfx`, data mode `live`, URL
https://hcjfxbynqzsaidlwvdfx.supabase.co. Development remains
`vgmkpsestahkfahzdtae`, fixture; development was not written in this step.

## Production publication

New run `8f634f6c-efae-4837-b1eb-1db04de6ffd2`, target 2026-10-02, stored
2026-10-02T17:50:07.347251Z (3 October 00:50:07 WIB), re-evaluates the original
immutable actual Yahoo capture with new reviewed dividend evidence. It does not
use the later incomplete fetch. Run digest:
`0aefe872fe3aa9ead45f1f98f9980ff96cd819142ddcc0f9f64a0a83c1c4c121`.

Postflight verified 200 raw/derived revision digests, previous runs unchanged,
actual ledger unchanged, fixture rows absent. Coverage improved from 11 to 45.
Zero signals refers to the evaluated subset; it is not a complete-universe
no-setup result. RS remains `cross_section_incomplete`. Production owner JWT
access to this new snapshot was not tested by this publication script.

## Sources and unresolved quality

Read-only [KSEI monthly archives](https://web.ksei.co.id/publications/corporate-action-schedules/cash-dividend)
were collected for December 2023â€“October 2026: 33 of 35 months responded;
November 2024 and February 2026 still failed with HTTP500. There are 291 downloaded
PDFs. The offline review queue retains 110 pending documents, including
amendments, mismatches, ambiguous decimals and unrecognized tables. Four rendered
PDF samples were visually reviewed; not every document was visually reviewed.
Selected proofs use exact regular/negotiated ex-dates and rupiah amounts matching
provider events, source hashes and immutable provenance. Failed archive months
mean the amendment search is incomplete; these proofs do not certify the entire
corporate-action history. Unresolved splits and other actions stay held.

The official [KPEI COIN notice](https://assets-website.idclear.co.id/idclear/storage/43039/SIGNED_PENG-0212_HC_Suspensi_Agunan_COIN_17072025_ndi.pdf)
corroborates a 17 July 2025 suspension and cites BEI's notice. This was reviewed
through the web tool; the local download failed, so it was not approved as a
hashed runtime exception. COIN remains held. Other open-session zero-volume rows
are unresolved. No prices were fabricated or problematic open-session bars
deleted. Five short IPO histories also cannot supply invented warm-up bars.

Fresh Yahoo smoke ran 2026-10-02T17:37:07Zâ€“17:39:16Z. All 100 target closes were
null, so the canonical engine correctly held every ticker. This result was not
published to production and does not invalidate or overwrite the older receipt.

Two authenticated EODHD GET requests were made without logging credentials:
account metadata and AMMN daily prices. The account reported free/20 requests per
day; AMMN returned 254 rows from 2025-10-02 through 2026-10-02, below 600 and
without the three older AMMN problem dates. A paid plan is not activated and
would still require data-quality, actions, coverage and budget verification.
See the official [User API](https://eodhd.com/financial-apis/user-api) and
[pricing](https://eodhd.com/pricing). Provider remains Yahoo; TradingView was not
implemented as a collection source. The external collector was unchanged.

## Commands and local tests

Executed from backend/scanner unless stated otherwise:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --basetemp=C:\xampp\htdocs\SahamTeknikal\backend\data\pytest-ksei-20261003-final
.\.venv\Scripts\ruff.exe check src tests ..\supabase\scripts\collect_ksei_action_sources.py ..\supabase\scripts\review_ksei_dividend_candidates.py ..\supabase\scripts\hydrate_reviewed_sources.py ..\supabase\scripts\manual_scanner_smoke.py ..\supabase\scripts\publish_ksei_reconciled_run.py ..\supabase\scripts\audit_scanner_quality_repairs.py
```

The final full Python run passed **232 tests**, with **five explicit native
Docker skips**, in 33.30 seconds; Ruff passed after import ordering was corrected. An initial
focused run found a test target-date error (fixed) and Windows temporary-directory
ACL error (avoided with a unique backend test directory, without changing ACLs).
Ruff found and corrected import ordering only in the recovery helper.

From backend/supabase, `npm.cmd test` passed **72/72 SQL tests**. These are local
PGlite tests, not hosted RLS/concurrency proof. From backend, `git diff --check`
and seven frozen migration checksums passed. Existing source hydration verified
129 local source hashes and downloaded zero files; clean hosted hydration remains
unproven. Frozen manual-runner configuration checksums verified 100 constituents.

From backend, the following real operations were executed:

```powershell
& .\scanner\.venv\Scripts\python.exe .\supabase\scripts\manual_scanner_smoke.py --execute-fetch
& .\scanner\.venv\Scripts\python.exe .\supabase\scripts\publish_ksei_reconciled_run.py --execute
```

The first only fetched/evaluated locally; the second published actual market
revisions and the partial run. No QA trades were created. Public-source collector,
offline candidate review, source hydration, and read-only EODHD probes also ran.
No commit, push, Vercel deployment, scheduler activation or migration edit occurred.

## Next gates

1. Obtain complete fresh EOD candles and verify 600 valid historical sessions for
   eligible strategies. Re-fetch manually into a new receipt; do not reuse an old
   candle as proof of current freshness. Retain each skip reason and coverage.
2. Resolve remaining actions/open-session anomalies, including archive gaps and
   amendments; RS requires the complete eligible cross-section. Optional EODHD
   upgrade requires the user's choice and feasibility checks before source change.
3. Review and publish the manual workflow with authorization, then dispatch the
   full universe on GitHub. Verify source hydration, pinned configuration, fresh
   candles, artifact evidence and the actual publisher separately. Keep cron off.
4. Close hosted production access gates with real authorized sessions; use an
   authorized disposable target for mutating/concurrent tests. No permanent QA
   ledger and no automatic promotion of login accounts.
5. Frontend may adapt and test the partial snapshot now. Vercel deployment and
   full-stack readiness remain gated. See FRONTEND_DEPLOYMENT_HANDOFF.md.

Evidence files: docs/evidence/scanner-recovery-20261003.json,
docs/evidence/production-ksei-reconciliation-20261003.json,
docs/evidence/fresh-yahoo-scanner-smoke-20261003.json,
docs/evidence/eodhd-feasibility-20261003.json, and
docs/evidence/held-bar-classification-20261003.json. Source PDFs and raw receipts
remain in ignored backend data directories; credentials are excluded.
