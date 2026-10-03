# Manual publication package — 2026-10-03

## Approved local publication and recovered read-back — 2026-10-03, latest

User approved exactly one local publication of plan838183f9e3fcb5bcfe6c4681be885e87a1410672137d73eeed0f1a3d2ff4ffb0.
Production receipt returned run3c700de4-8389-400e-b862-31f2c8998a64, replayedfalse,
0inserted signals. Stored_at2026-10-03T12:44:34.492091+00:00 (19:44WIB),targetOct2,
digest653f9f9168b20dabfc14dc9fa18090e6ed48f5d63546c897107cc44258dd4110.
This is the LOCAL actual capture20261003T093419Z, not GitHub37114744856 input.
Coverage45evaluated/25actionhold/30qualityhold,0signals,RSincomplete. Scheduleroff.

Initial command FAILED postflight after committed receipt: scan_run_items query
ordered by nonexistent id; GET reproducedHTTP400/42703. Failure evidence retained.
Fixed composite scan orders and performed ONLY fixed-ID GET read-back, no second
publication/replay. Recovery PASS at12:49:31.511972Z:100unique items/exactstatuses,
200expectedraw/derived revision keys,0signals/live/forward/fixtureabsent.
Old latest run digest/stored_at/coverage match prior proof and all3old IDs remain;
complete old snapshot before/after hashes were not retained. NCKL closed/revision5
projection/risk6500/net1244/fee256/R0.191384615385 matches prior ownerCSV; service
GET integrity check is not new ownerJWT/RLS proof. Current7journal table counts
1trade/2fills/1correction/5requests,0stop/note/tag. Full journal before/after
fingerprint equality NOT VERIFIED because original baseline was lost in memory.
Future hash-only checkpoint tested; do not infer no write after interrupted checkpoint.

Local Python254PASS/5explicit Docker skips25.26s (19publisher cases),Ruff/diffPASS;
read-only recovery reviewer PASS with documented limits. NoSQL/migration/Auth/
journal mutation,QAtrade,frontend,.env,commit/push/dispatch or scheduler change.
Original failure and GET-only recovery are separate sanitized evidence files.
HostedGitHubpublisher still untested/environmentabsent. User skipped outsider
and two-session/concurrency NOT VERIFIED; disabled-owner/rawownerreceiptaudit/
hostedjournalerrorpaths NOT VERIFIED. Prior001–007 and oldsnapshot ownerPASS
retained; NEW snapshot owner read now relevant/pending. Complete backend/full-
stack NO-GO; frontend/Vercel needs separate authorization and actual smoke.
See docs/MANUAL_PUBLICATION_RESULT_20261003.md for exact bounds and next action.


Status: locally prepared and reviewed; **no production execution, receipt or
new publication**. Complete backend/full-stack release remains NO-GO. Scheduler
off. This document is a reviewable execution proposal, not execution approval.

## Exact local candidate

- Production allowlist: `hcjfxbynqzsaidlwvdfx`,
  https://hcjfxbynqzsaidlwvdfx.supabase.co, `live`, namespace `forward`.
- Target closed session: 2026-10-02; deadline next open
  2026-10-05T08:58:00+07:00. No next-open price assumed.
- Actual Yahoo capture: ignored `data/manual-scanner-smoke/20261003T093419Z`,
  exactly100 files, every SHA256/input digest and mapping checked. This is the
  local capture, **not** raw input from GitHub37114744856 (that artifact only
  contains summary evidence), and not the old published snapshot.
- Ignored plan: `data/manual-publication/plan-local-20261003.json`.
- SHA256: `838183f9e3fcb5bcfe6c4681be885e87a1410672137d73eeed0f1a3d2ff4ffb0`.
- Engine digest: `653f9f9168b20dabfc14dc9fa18090e6ed48f5d63546c897107cc44258dd4110`.
- Coverage45 evaluated/25 action hold/30 quality hold; zero signals; incomplete
  RS remains held. No approved anomaly or trading-rule change.
- Guard requires each source fetched within24hours, never in future. Therefore
  this exact local candidate expires around4October09:34UTC, earlier than the
  next-open deadline. Re-fetch/new plan requires new review, not changed hashes
  under the existing approval.

Offline command already executed successfully (backend working directory):

```powershell
& .\scanner\.venv\Scripts\python.exe .\supabase\scripts\prepare_manual_publication.py --capture data/manual-scanner-smoke/20261003T093419Z --target 2026-10-02 --plan data/manual-publication/plan-local-20261003.json
```

Default offline never opens a database. Existing plans are not overwritten.
Execution requires `--execute --project-ref hcjfxbynqzsaidlwvdfx
--approved-plan-sha256 <the reviewed SHA256>`. Process variables
`SUPABASE_URL`, `SUPABASE_SECRET_KEY` must be available only to that process.
Do not put key values on the command line/history, into chat/artifacts/repository
or browser configuration. The script does not load/overwrite `.env`.

Local credential preflight inspected only presence/target match: backend ignored
.env exists, production URL matches, publisher secret is present. No key value
printed, credential authenticated, remote call, or .env edit. After approval an
operator may load these two existing values into an isolated child process; the
core script still reads process environment only. This requires no new credential.

For local execution after explicit approval, enter the existing production
backend secret through a local hidden prompt, scope it to the process, and remove
the temporary environment value in a `finally` block. Preserve any pre-existing
process variable. No password/JWT is needed for this service-side market
publisher. This route proves a local publisher, not a hosted GitHub publisher.

## Hosted manual route

Prepared `.github/workflows/manual-scanner-publication.yml` has dispatch only,
no cron/push trigger. `execute_publication` defaults false.

1. Fetch a fresh100-ticker actual capture without Supabase credentials; hydrate
  129 frozen reviewed public sources, evaluate canonical engine, prepare a new
   plan with100 file hashes. Artifact `manual-publication-plan` is public market
   inputs and sanitized evidence only, retained1day. Review this plan's actual
   SHA/digest/counts/timestamps; it is not the local candidate above.
2. If publication is explicitly requested, a second job references environment
   `production-scanner-publisher`. Configure a required user reviewer and main
   branch only; disable administrator bypass in Dashboard when supported.
   Review the generated plan artifact before approving the waiting job.
3. Read-only GitHub API guard checks repository/ref, required reviewers and
   exactly the main deployment branch policy. It rejects unavailable API access
   or missing rules before the Supabase credential step.
4. Environment variable name: `SUPABASE_URL`; environment secret name:
   `SUPABASE_SECRET_KEY`. Keep service credentials at environment scope, out of
   repository-wide secrets available to preparation jobs. Existing placement
   and actual remote configuration remain NOT VERIFIED; no secret was added.
5. Exact plan SHA is transferred as a job output; publisher recomputes capture,
   config, source and run digests before using canonical `run_once`. Credential
   introduced only to the publisher step. No scheduler activation.
6. Store sanitized receipt/read-back artifact `manual-publication-result`7days.
   Copy reviewed proof into backend evidence only after actual execution.

GitHub environment/reviewer availability depends on repository visibility and
plan. On Free/Pro/Team, required reviewers are public-repository features; do
not buy a tier, change visibility, or bypass the guard silently. See
[GitHub environment documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
and [read-only environment API](https://docs.github.com/en/rest/deployments/environments).
If unavailable, the explicit local process route is the fallback; hosted
publisher gate stays unproven. Remote approval/secret configuration and workflow
GET permission still need observation. Naming an environment in YAML does not
prove protection exists. No dispatch/commit/push performed for this package.

## Write and read-back scope

`run_once` only ingests actual raw/derived market revisions and publishes a
separate immutable partial run; existing rules/RPCs001–007 are unchanged.
No journal mutation RPC, Auth/membership change, migrations or frontend writes.
Target/deadline are rechecked before ingestion and immediately before publication;
SQL publication deadline remains authoritative. Reject state with prior signals
until reviewed; reject new signals or counts differing from45/25/30.

Read-back checks exact run ID/digest/live/forward/date/coverage,100unique items
with exact per-ticker status, zero run signals, all old scan rows unchanged,
absence of fixture rows, and unchanged fingerprints of seven journal tables:
trades, fills, corrections, stop events, notes, tags, request receipts. Composite
keys and correction sequence use schema-specific ordering; pages of200 continue
until exhausted. These checks are publisher checks, not journal export tests.
Private row bodies stay in process memory; output only sanitized result flags.
Fingerprint scope excludes global audit_events because publication legitimately
adds its own scan audit; do not claim the whole audit table unchanged.

## Failure and recovery

Ingestion and publication are not one transaction. Failure after an ingest may
leave valid immutable revisions with **no published run**. Failure/timeout during
publication may have an ambiguous committed outcome. A null receipt alone does
not prove no write occurred. Stop, retain sanitized evidence, inspect the exact
planned digest/revisions/run read-back, and request reviewed retry authorization.
Do not delete revisions, reset/truncate, fabricate receipts or automatically
create another plan/run. Exact approved content can be replayed through existing
idempotent backend after outcome inspection. If deadline expires, stop forward
publication; historical/backfill is a separate explicitly reviewed scope.

## Verification actually performed

- Local candidate preparation PASS;100 file/source checks, no DB connection.
- Python251 passed/5explicit native Docker skips,23.03s, including16publisher
  guards: plan tamper/input changes, candle/age/mapping, next-open equality,
  unexpected signals/RS/counts, wrong project/missing secret, pagination201,
  composite keys, missing reviewer/main policy.
- Ruff PASS, final diff check PASS. Existing SQL72/72 remains historical local
  proof only; not rerun because no SQL/domain/RPC change in this package.
- Read-only reviewer identified bad receipt `id` ordering; corrected all affected
  keys and scoped fingerprints to seven journal tables. Re-review: no remaining
  implementation blocker for preparation; remote configuration/execution unproven.
- First offline probe failed source serialization digest mismatch; corrected
  source-token key mapping and verified canonical property parity. First focused
  pytest6passed/3temp setup errors (Windows denied global pytest directory), rerun
  under ignored backend temp passed. Initial Ruff line-length findings fixed.
- Official download-artifact v4.3.0 SHA confirmed via read-only git ls-remote:
  d3f86a106a0bac45b974a628896c90dbdf5c8093. Web open timed out; API open unavailable
  and sandbox Git network failed. Switched with known network evidence to
  approved read-only network access, then succeeded. No provider workaround.

## Observed remote prerequisite

Read-only GitHub Settings > Environments on3October showed “There are no
environments for this repository”. production-scanner-publisher is absent.
Nothing was created or configured and no credential was read/entered. Therefore
publication-enabled dispatch is BLOCKED until configuration is reviewed; a
workflow reference alone could auto-create an unprotected environment, which our
GET guard rejects before the Supabase step.

## Minimum approvals still needed

Choose one explicit publisher execution route and approve its exact candidate:
local plan SHA above before expiration, or reviewed fresh hosted plan. New backend
commit/push/dispatch authorization is needed to publish this prepared workflow;
previous one-dispatch permissions were already consumed. Hosted route also needs
verified supported environment/reviewer/main restrictions and environment-only
credential placement. No frontend/Vercel permission is implied.

Raw real-trade receipts/audit are not exposed by current owner UI; ask the
frontend owner-session tooling to return sanitized receipt actions/revisions/
audit counts without JWT/raw payload leakage, or authorize an equivalent safe
owner-only read endpoint. Do not extract cookies/tokens or substitute service
role as owner proof. Do not guess or replay request UUID/payload.
