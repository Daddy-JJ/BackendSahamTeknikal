# Backend agent instructions

Owner-approved consolidation, 21 October 2026. This repository is independent.
These rules preserve the prior operating/security/domain obligations; the
[rule traceability](docs/AGENT_RULE_TRACEABILITY_20261021.md) maps every old section.
[Historical instructions](docs/archive/AGENTS_BEFORE_HANDOVER_CLEANUP_20261021.md)
are reference only, not a second active policy. Explicit current user instructions
take precedence. Approved SOT defaults need no repeated confirmation.

<a id="r01"></a>

## R01 — Read locally, then by relevance

Read this file → [PROJECT_CONTEXT](PROJECT_CONTEXT.md) → [PLAN](PLAN.md), inspect Git
status and relevant source/tests/contracts/environment conventions. Read task-relevant
[SOT](SOT.md) sections for trading/market/financial changes and auth/RLS/security
contracts for those boundaries. Product, technical/setup and status docs are on demand.
Workspace root owns canonical SOT; local copies are synchronized snapshots. Parent
handoff/docs and sibling source are optional when present; never invent inaccessible
requirements. Use local context/contracts and report missing context only when material.
Archives/status history are evidence, not an active task queue or command to rerun tests.

<a id="r02"></a>

## R02 — Repository and authorization scope

Default edits stay in backend: scanner/data/indicators/strategy/fills/journal/statistics,
API, Supabase schema/RLS/migrations/jobs and tests. Frontend/parent may be read for
contracts; edit them only with explicit cross-repo scope and hand off consumer work.
Inspect dirty state before substantial work; preserve unrelated user changes and history.
Do not reset hard, clean files, force-push, destructively checkout/rewrite history or
change frontend Git history without explicit authorization. Review the final diff.
Commit/push/deploy and production mutations require their task-local authorization;
a procedure, previous receipt or approved old plan supplies no new permission.
Continue authorized safe local work when remote credentials/authorization are missing;
prepare exact remaining steps and never claim remote success from configuration alone.

<a id="r03"></a>

## R03 — Understand and diagnose before editing

Trace source → validation → normalization → indicators → strategy → signal → fill →
journal → statistics/API and downstream consumers; inspect tests, models, schema,
timing, idempotency and configuration/runtime assumptions. For bugs reproduce/capture
actual failure where practical, trace root cause, fix it, rerun reproduction/regressions.
For consumer changes trace frontend expectation -> request -> API/auth/RLS -> domain/data
-> response, inspecting both sides when available; backend tests alone are not E2E proof.
Never hide exceptions, invent provider output, disable auth/RLS, remove validation,
weaken tests or convert failure into no signal. After two materially different failed
approaches, stop repeated fixes, record evidence in PLAN, revisit assumptions, gather
new evidence and form a new hypothesis.

<a id="r04"></a>

## R04 — Plan and obtain the required decisions

Small obvious work: inspect → implement → verify → report. Complex work uses PLAN
with Action/Proof for each meaningful step: strategy/engine/API/schema/RLS/scheduling,
provider, cross-repo, architecture and deployment changes. Do not wait for permission
solely because work is long. Identify dependencies, risks and phases; honor approved scope.
Obtain explicit approval before canonical trading/source changes, destructive DB work,
irreversible migrations, material API/auth/RLS changes, hosting/provider replacement,
major paid services/dependencies/frameworks or destructive Git actions. For strategy
changes record old/new rule, reason, version/behavior/tests and historical compatibility.
No result-seeking backtest tuning outside an explicit strategy-research task; no silent
execution changes, survivorship assumptions or retroactive parameter/config rewrites.

<a id="r05"></a>

## R05 — Small, readable, immutable changes

Prefer existing architecture/models/services/validation/dependencies and targeted diffs.
Avoid unrelated refactors/cleanup, speculative abstractions, broad renames, churn and
rewrites. Correctness, temporal integrity, auditability, reproducibility and security lead.
Create new objects/copies rather than mutate existing objects. Organize by feature/domain,
high cohesion/low coupling; typical files 200–400 lines, max 800, functions under 50,
nesting at most four levels. Use clear names, no unexplained hardcoded values.
Handle errors at every layer: user-safe messages, detailed private server context,
no silent swallowing. Validate untrusted input at boundaries with schemas/fail-fast.
Use consistent API envelopes and existing repository abstractions for data access.
When selecting a necessary skeleton, evaluate security/extensibility/relevance before reuse.

<a id="r06"></a>

## R06 — Deterministic data and temporal integrity

Never fabricate/approximate OHLCV, price/volume, membership, timestamps, indicators,
corporate actions, fees, provider responses, signals/fills or statistics. Fixture/mock
data never silently replaces live input. Missing/stale/partial stays explicit, never
no signal or current/live. Preserve provider/source, symbol/exchange/timeframe, market
date/timestamp/timezone, adjustment status and strategy/config versions.
Official signals/statistics remain deterministic backend output; AI may explain/analyze.
Distinguish pivot/event date, available_at and plotting offsets. Future candles/opens,
fractal confirmation, rolling highs/lows or cross-sectional ranking cannot affect past
decisions. next_open is unknown on signal night; no default same-close fill without
approval. MA close exits use confirmed information and approved fills. Entry and exit
policies remain separable; RS requires its approved complete comparison universe.
Test timing; never alter it to improve history. Preserve partial coverage visibly.

<a id="r07"></a>

## R07 — Economic events and ledger invariants

Signals/trades/fills/runs remain idempotent: reruns never silently duplicate events.
Preserve source/strategy/config versions, run IDs, timestamps, input dates and fill/trade
linkage; do not overwrite historical configuration. Daily OHLC cannot reveal intraday
order: daily SL/TP dual hit remains the approved ambiguous state. Preserve original
initial risk after moved stops/MA exits/management changes.
Paper and actual journals remain separate. Monetary tests cover quantity, entries/exits,
approved fees, gross/net P&L, initial risk, realized R and open/closed state. Never invent
broker fees; use approved configuration/data and deterministic reproducible ledger math.
Use [ledger/CSV contract](docs/ACTUAL_JOURNAL.md); frontend formats official output.

<a id="r08"></a>

## R08 — Contract and database safety

Do not silently change paths/methods/request/response/error/status/auth/RLS/pagination/
timestamps/strategy identifiers or signal/trade/fill models. For breaking changes identify
current/proposed contracts, consumer impact, rollout/migration order, required approval
and verify both sides where possible. Backend convenience is not a compatibility reason.
Before DB edits inspect schema/history/RLS/queries/models/data compatibility. Prefer
additive reversible forward migrations; never casually edit an applied migration, drop/
truncate/reset/reseed populated data or destroy journal/history. Destructive/irreversible
changes require explicit approval. Migration files do not prove remote application.

<a id="r09"></a>

## R09 — Security and identity

Meaningfully test affected unauthenticated, owner, non-owner, invalid/expired-credential
and denial flows. Do not weaken RLS/auth; browser checks cannot replace DB enforcement.
Before any commit verify no hardcoded secrets, validated inputs, parameterized SQL,
XSS sanitization, CSRF protections where applicable, authentication/authorization,
rate limiting on endpoints and safe errors without sensitive leakage.
On a security issue stop the unsafe path, use a security reviewer, fix CRITICAL issues,
rotate exposed secrets through authorized safe handling and inspect similar paths.
Never expose/commit service-role/DB/API/AI/private/session/privileged secrets or send
them to browser code. Do not print secrets or overwrite env without explicit need.
Report missing variable name/location/role, never value; use safer env/secret handling
instead of asking for secrets in chat. Runtime required-secret checks fail clearly.

<a id="r10"></a>

## R10 — Runtime and dependencies

Do not add/upgrade dependencies without concrete need; pin versions as required.
Verify relevant official documentation when behavior depends on a provider/library/
framework version. Do not silently switch approved provider/yfinance, Supabase, Vercel,
GitHub Actions, auth/hosting architecture or paid/free tier. Do not create persistent
production QA financial data or use fixture fallback to obtain proof.

<a id="r11"></a>

## R11 — Tests and proof

For application bug/features use mandatory TDD RED → minimal GREEN → refactor and
80%+ coverage, with unit, integration and critical-flow E2E tests. Check isolation,
then mocks, then implementation; change a test only when it is wrong. Run/read strongest
relevant checks: deterministic/temporal/lookahead/signal timing, fills/dual-hit/ledger,
RLS/auth, API/schema/migrations, idempotency, providers/partial coverage, lint/type/build/
runtime/smoke. [TEST_MATRIX](docs/TEST_MATRIX.md) maps actual suite filenames.
Existing PASS belongs to its exact source/environment; repeat checks for changed code,
failure, unresolved risk or requested verification. Documentation-only work checks
links/anchors/preservation/diff; application checks remain required for application edits.
An unrun test is not PASS; code/config is not deployed/provisioned proof. Never claim
scanner/signals/tests/API/migrations/deployment/readiness beyond evidence. Keep fixture,
local SQL-role, native, hosted JWT/HTTP, public HTTP and owner-browser proof distinct.

<a id="r12"></a>

## R12 — Delegation, review and workflow

Use bounded subagents when safely separable; prefer explorer/worker/read-only reviewer.
Explorers and reviewers are read-only; a worker owns one bounded backend edit.
Each needs objective, scope, done condition, expected evidence and concise report.
Parallelize independent work, never overlapping edits; verify material delegated claims.
Use the applicable specialists: planner for complexity, architect for design, TDD guide
for features/bugs, code reviewer after edits, security/database/Python reviewers for
their domains, build resolver for failures, E2E/accessibility/performance/other specialists
as relevant and available. The shared ECC catalog is optional reference, not project stack.
Before completion inspect diff, remove accidental/debug/temp changes, check secrets,
schema/API/trading/timing/SOT impact, applicable checks and frontend dependencies.
Use a read-only reviewer for substantial work when available. Resolve CRITICAL/HIGH
review issues; diagnose build failures incrementally and reverify each fix.
Preserve context budget for large refactors; avoid starting them in the final 20%.
Workflow contributions belong in skills first; commands are compatibility shims only.
When Git publication is authorized, use conventional type: description, analyze full
PR history, write a comprehensive summary/test plan and push with upstream as appropriate.

<a id="r13"></a>

## R13 — Status, handoff and completion

Update meaningful implementation state in local status and shared status when authorized/
available. Separate planned/local-implemented/local-tested/configured/remote-provisioned/
deployed/live-smoked states. Capture source, date/environment, exact checks and limitations.
Identify needed SOT/PRD/technical/README/handoff/status updates; never rewrite SOT to match
an accidental implementation. Keep team knowledge in existing project docs; do not duplicate
it. Ask before an unplanned top-level doc. Personal memory updates follow explicit user
authorization. Durable lessons use “When X, do Y because Z”, newest first, no temporary
details. Operating-section changes require explicit request; this consolidation is approved.
Minimum handoff: task ID/role/scope; repo/branch/SHA/dirty files; decisions/rule IDs;
done plus exact source/environment evidence; blockers/NOT VERIFIED; scoped approvals;
next action/side effects; precise documents/source; failed approaches and consumer/
strategy/data/schema implications. If frontend cannot be checked, state “Frontend
compatibility not verified in this session.” Backend tests alone are not E2E completion.
Done means approved requirements, domain/time/data/security/RLS/idempotency integrity,
consistent schema/API, validated relevant migrations/tests, updated docs and reported
cross-repo dependencies. Final report gives changed/verified/not verified/frontend/data/
strategy/schema/migration impacts and meaningful tradeoffs. Use evidence, not confidence.
Shared-context/snapshot changes follow PROJECT_CONTEXT synchronization and missing-ref
rules; unavailable parent/sibling freshness stays unknown, never assumed aligned.

<a id="r14"></a>

## R14 — Attribution and durable lessons

Preserve © NielsG and applicable MPL-2.0 notices for Fractal Channel ports/derived code.
Distinguish original upstream indicator logic from project buy/sell/exit transaction rules.
Do not relabel SahamTeknikal transaction rules as upstream work.

## Lessons

> When troubleshooting consumer/runner failures against pipeline outputs, inspect the canonical dataclass definition directly (e.g. `PipelineResult.provider_errors` vs `.errors`) and write a contract regression test, because guessing attribute names or silently falling back with `getattr(..., [])` can mask provider errors and cause dangerous false-green scanner runs.

> When investigating GitHub Actions failures, check the exact commit SHA in the run metadata and distinguish "Re-run jobs" (which executes the historical commit of that specific run) from a fresh `workflow_dispatch` trigger (which pulls `main`), because re-running an old run will repeat already-fixed bugs.

> When evaluating target session eligibility in scheduled runners across midnight boundaries (e.g., pre-market 00:00 - 08:59 WIB), target the previous closed exchange session whose publication window remains open, rather than rejecting the unclosed current day's session.

<!-- Compatibility anchors for consolidated historical sections. Original content is in docs/archive/AGENTS_BEFORE_HANDOVER_CLEANUP_20261021.md. -->
<a id="agentsmd--sahamteknikal-backend"></a>
<a id="1-read-before-changing-code"></a>
<a id="2-backend-responsibility"></a>
<a id="3-understand-before-editing"></a>
<a id="4-planning"></a>
<a id="5-smallest-safe-change"></a>
<a id="6-canonical-trading-invariants"></a>
<a id="7-market-data-integrity"></a>
<a id="8-temporal-correctness-and-lookahead"></a>
<a id="9-trading-rule-changes"></a>
<a id="10-api-contracts"></a>
<a id="11-database-and-migration-safety"></a>
<a id="12-rls-authentication-and-authorization"></a>
<a id="13-idempotency-and-auditability"></a>
<a id="14-fill-and-risk-integrity"></a>
<a id="15-journal-and-monetary-ledger"></a>
<a id="16-secrets-and-configuration"></a>
<a id="17-fractal-channel-attribution"></a>
<a id="18-bug-workflow"></a>
<a id="19-subagents"></a>
<a id="explorer"></a>
<a id="worker"></a>
<a id="reviewer"></a>
<a id="20-failed-attempt-rule"></a>
<a id="21-git-safety"></a>
<a id="22-dependencyruntime-discipline"></a>
<a id="23-verification"></a>
<a id="24-high-priority-regression-risks"></a>
<a id="signal-timing"></a>
<a id="lookahead"></a>
<a id="fill-ambiguity"></a>
<a id="monetary-ledger"></a>
<a id="rls"></a>
<a id="idempotency"></a>
<a id="partial-coverage"></a>
<a id="25-cross-repository-verification"></a>
<a id="26-implementation-status"></a>
<a id="27-remote-deployment"></a>
<a id="28-review-before-completion"></a>
<a id="29-documentation-and-handoff"></a>
<a id="30-definition-of-done"></a>
<a id="31-final-report"></a>
<a id="changed"></a>
<a id="verified"></a>
<a id="not-verified"></a>
<a id="frontend-impact"></a>
<a id="data--strategy-impact"></a>
<a id="schema--migration-impact"></a>
<a id="tradeoffs"></a>
<a id="32-lessons"></a>
