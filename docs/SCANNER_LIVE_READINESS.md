# Scanner live and disposable evidence — 2026-10-02

## Decision

Scanner publication remains **BLOCKED**. The five-symbol live provider probe and
the disposable real Auth/HTTP gates passed. Scheduler remains disabled. No
production signal or QA trade was written in this continuation.

User instruction: skip tickers with problematic bars or unreconciled corporate
actions, with visible reasons and coverage, and defer reconciliation. This is
already the backend quality-hold behavior. Preserve provider issues and revisions;
do not turn exclusions into “no signal”. Incomplete cross-section holds RS for
everyone; eligible tickers may still run the other entry strategies. No browser
financial engine or canonical formula was changed.

## Exact source audit

| Input | Actual source/evidence | Status |
|---|---|---|
| 2026 holidays | BEI Peng-00171/BEI.POP/09-2025, published2025-09-23, public [PDF](https://www.idxcarbon.co.id/document/share/158/0a901391-a0ad-4ca5-930e-2788cb7eb27f), SHA5273a6f5724a5ac7f17027bdfcc8205ff8491e8299a6c0230347c59332e25324 | Baseline verified; later-amendment completeness pending |
| 2025 holidays | BEI Peng-00213/BEI.POP/10-2024, published2024-10-16, [PDF](https://www.idxcarbon.co.id/document/share/109/e11c312a-95d6-4525-b71a-f70377cc7777), SHA84cfc174e5eab9257e9f93ce36bb41c76e67a3d8cb99cc9b4a80c76c26638b43 | Download/hash passed; baseline text reviewed |
| 2025 amendment | BEI Peng-00149/BEI.POP/08-2025, published2025-08-08, adds2025-08-18, [PDF](https://www.idxcarbon.co.id/document/share/143/cf878b0d-87c1-45e2-98a5-4c54d6efc8c2), SHAc0f59975d73c136e954b0c10508d483832f15029b91d91d056bfaf5e3e31192c | Download/hash passed; later amendments pending |
| Session rules | Current [official BEI table](https://www.idx.id/en/products-services/trading-hours-and-mechanism/) refers to II-A Kep-00136/BEI/09-2026; regular open09:00, Friday first session ends11:30, other days12:00, afternoon14:00 Friday/13:30 other days, post-closing ends16:15 WIB | Current table reviewed; historical effective dates and daily-open convention pending |
| Historical calendar | No complete runtime source for the warm-up interval; 2024 and (if retaining2023 fetch start)2023 sources absent | BLOCKED; never infer holidays from Yahoo gaps/weekdays |
| KOMPAS100 | Owner-supplied original `data/sources/4. Lamp Peng-00148-BEI POP - KOMPAS100 - Jul 2026 Mayor.xlsx`; sheet1 C10:C109, header Peng-00148/BEI.POP/07-2026 dated2026-07-27 |100/100 unique/order matches transcription |
| Universe provenance | Workbook SHA51b988ab5af2953e40603eb2884883120f2b727887ad014dc496a8c9cb0f4eb5; constituents2026-08-03 through2027-01-29 inclusive, exclusive end2027-01-30; share-weight period through2026-10-30 | Hash/sheet/date gate PASS; independently recovered official attachment URL still absent |
| Yahoo mappings | Live provider identity: symbol, JKT, IDR, EQUITY and issuer name agreed for BBCA.JK, BBRI.JK, BMRI.JK, TLKM.JK, ASII.JK |5 verified;95 pending. Suffix alone does not verify mapping |
| Provider | Existing yfinance1.7.0, explicit auto_adjust=False/actions=True/no fallback; EODHD token absent by presence-only audit | Yahoo connectivity PASS; EODHD not needed for selected Yahoo baseline |
| GitHub runner | Existing run orchestrator/CLI; no committed workflow in releasee339514. New local `.github/workflows/manual-provider-smoke.yml` has workflow_dispatch only, immutable official action SHAs resolved2026-10-02, Python3.12.14, no DB secrets/write | Prepared, not published/dispatched; no runner success claimed |

The workbook was found during this audit; no new workbook input is required.
Reference files remain explicitly non-runtime. Complete dates, hours and
provenance must be assembled before a real scan; the loader's checksum/HTTPS
format checks cannot certify exchange provenance themselves.

## Actual live provider probe

Command: `scanner/.venv/Scripts/python.exe supabase/scripts/probe_live_provider.py`.
Explicit range2023-09-01 through2026-10-01. Raw data remains under ignored
`data/live-provider-20261002/`; sanitized evidence is committed separately.

| Ticker | Complete bars | Latest complete | Provider issue rows | Actions |
|---|---:|---|---:|---:|
| BBCA |737|2026-10-01|5|8|
| BBRI |738|2026-10-01|4|6|
| BMRI |738|2026-10-01|4|5|
| TLKM |738|2026-10-01|4|3|
| ASII |738|2026-10-01|4|6|

First helper execution fetched/saved actual series but its summary incorrectly
referenced `Series.corporate_actions`. Fixed to `Series.actions`; evidence was
reconstructed from those saved actual outputs without repeating the network fetch.
The failure is recorded. Yahoo web-page opens returned429; actual provider API
identity/fetch succeeded. This is connectivity/adapter evidence, not certified
600-session continuity, current-day freshness, reconciled actions, full RS
coverage, storage-to-web publication or a forward scan.

## Actual disposable Auth/HTTP smoke

Target: local `idx-smoke-local-20261002`, PostgreSQL17, migrations001–007 applied
via CLI `migration up --local`, fixture mode. No production identities/data copied.
Generated keys stayed in memory; owner JWTs came from real local Auth logins.

Initial start stalled; bounded minimal startup completed. Despite the custom
loopback network default, published ports initially used all interfaces. Those
containers were stopped before account/trade creation, recreated with actual
127.0.0.1 bindings and existing volumes, and original stopped containers retained.
Generated gateway config/template/certificate files were copied directly in memory
from the stopped original. No keys/cert private data were written to host logs.
Auth health200 and fresh accounts/history checks passed before smoke.

Commands actually executed:

- `python supabase/scripts/smoke_disposable_auth.py`:10 assertion groups PASS.
- `python supabase/scripts/smoke_disposable_followup.py`:5 assertion groups PASS.
- `python supabase/scripts/smoke_disposable_signal.py`:4 assertion groups PASS.
- Targeted pytest runner/engine/provider suite:36 passed.
- Ruff over the four new probe/smoke scripts: PASS.

Verified: two owners see only their rows; outsider/disabled-owner seven-table GETs
return200 with empty rows, analytics/export403, mutation403; anonymous401; direct
owner table mutation403. Empty stop/tag tables establish API/grant checks, not
nonempty cross-owner row evidence for those two tables.

Actual journal: create/multiple buys/finalize/partial sell/correction/close,
oversell rejection, identical replay, changed-payload400/23514, stale412 with
revision_conflict and unchanged failed-request receipts/audit/revision/notes.
Canonical risk1200/fee100/net1000/R0.833333333333. Fee quality flips estimated/actual
through correction; explicit latest-correction FK embedding succeeds. Analytics
p_exit_snapshot agrees with ledger. Export closed/limit200 follows p_after pages
200+1 to has_more=false,201 unique trades/net2010. Those201 fixture trades were
created using local SQL claims plus backend RPC; reads used real Auth JWT/HTTP.
Two independently issued Auth sessions/HTTP clients prove concurrent200/412 and
identical concurrent200/200 with one receipt/audit/revision mutation.

Scanner action007: fixture scan generated by existing deterministic backend and
published locally, real Auth replay200, changed UUID payload400/23514, stale412,
outsider/disabled403, independent sessions200/412 with one mutation.

These gates pass on the disposable target. Hosted production outsider/disabled
and mutation/concurrency proof remain separate. Frontend's2026-10-02 report
documents production owner login/read and tested anon401; this backend audit
read the report without rerunning those sessions.

## Remaining GO requirements

1. Complete official historical calendar/amendments and session-rule periods,
   including next-session timing. Keep available-at and next-open SOT behavior.
2. Verify remaining95 Yahoo mappings, fetch the full effective universe and report
   every skip/missing/stale/partial case. RS waits for a complete valid cross-section.
3. Publish/dispatch the prepared manual runner under authorized GitHub access and
   retain actual run URL/artifact/status. No schedule is present or enabled.
4. Prove hosted production access/mutation requirements using genuine authorized
   journal activity or a separately approved safe isolation strategy. Disposable
   QA success does not create production lifecycle evidence.
5. Frontend requests separate Vercel deployment authorization and runs actual
   Vercel smoke only after mandatory backend gates pass.

Migration005 source EOF whitespace from prior cleanup was restored to its exact
frozen release checksum. No financial SQL or migration history was changed.
