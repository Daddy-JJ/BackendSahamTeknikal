# AGENTS.md — SahamTeknikal Backend

Operating instructions for the SahamTeknikal backend repository.

Repository path:

```text
C:\xampp\htdocs\SahamTeknikal\backend
```

Sibling frontend repository:

```text
C:\xampp\htdocs\SahamTeknikal\frontend
```

Project-level documentation:

```text
C:\xampp\htdocs\SahamTeknikal\
```

This repository is an independent Git repository.

The root project `AGENTS.md` contains the canonical shared project rules. This file adds backend, scanner, database, API, and trading-engine operating instructions.

---

## 1. Read before changing code

Before substantial work, inspect relevant project documentation when filesystem access permits:

1. `..\AGENTS.md`
2. `..\SOT.md`
3. `..\PRD.md`
4. `..\TECHNICAL_DOC.md`
5. `..\README.md`
6. `..\CODEX_HANDOFF.md`
7. `..\IMPLEMENTATION_STATUS.md`, when present

Also inspect:

- repository Git status;
- relevant backend/scanner code;
- tests;
- schema and migrations;
- RLS policies when applicable;
- environment/configuration conventions;
- `PLAN.md` when active.

Do not assume parent files were automatically loaded merely because they exist above this Git repository.

If parent documentation cannot be accessed, do not invent requirements. Work from available evidence and clearly report what could not be verified.

The latest explicit user instruction takes precedence.

Canonical trading rules are defined in `SOT.md`.

A `DEFAULT` explicitly approved in `SOT.md` may be implemented without repeated confirmation.

---

## 2. Backend responsibility

Default editable scope:

```text
C:\xampp\htdocs\SahamTeknikal\backend
```

The backend agent owns applicable areas including:

- scanner;
- market-data ingestion;
- normalization;
- technical indicators;
- deterministic strategy engine;
- trade/fill logic;
- journal domain logic;
- statistics;
- API/backend services;
- Supabase/PostgreSQL schema;
- migrations;
- RLS;
- scheduled scanner execution;
- backend tests.

Reading the frontend repository and parent documents is allowed when access is available and useful for contract verification.

Do not edit:

```text
..\frontend
```

unless the user explicitly requests cross-repository implementation.

If frontend changes are required, document them precisely in the handoff.

---

## 3. Understand before editing

Before changing backend behavior:

- trace the relevant code path;
- inspect tests;
- inspect data models;
- inspect schema/migrations where relevant;
- inspect API consumers where available;
- inspect signal/fill timing assumptions;
- inspect idempotency requirements;
- inspect configuration/runtime assumptions.

For market-data or trading logic, identify:

```text
source data
↓
validation
↓
normalization
↓
indicator calculation
↓
strategy evaluation
↓
signal
↓
trade/fill
↓
journal
↓
statistics/API
```

Do not modify one stage without considering downstream consumers.

---

## 4. Planning

For small obvious changes:

1. inspect;
2. implement;
3. verify;
4. report.

For complex work, create or update:

```text
PLAN.md
```

Use a plan for:

- strategy changes;
- signal-engine changes;
- API contract changes;
- schema/migration work;
- RLS/auth changes;
- scanner scheduling;
- data-provider changes;
- cross-repository integration;
- architectural changes;
- deployment changes.

Each meaningful step must include:

```text
Action:
Proof:
```

Do not wait for approval solely because the task is long.

Explicit approval is required before:

- changing canonical trading rules;
- changing approved market-data source;
- destructive database operations;
- irreversible migrations;
- materially changing API contracts;
- materially changing auth/RLS architecture;
- replacing hosting/provider architecture;
- adding a major paid service;
- adding a major dependency/framework;
- destructive Git operations.

---

## 5. Smallest safe change

Prefer:

- small diffs;
- existing architecture;
- existing data models;
- existing services;
- existing validation;
- existing dependencies;
- targeted fixes.

Avoid without clear need:

- unrelated refactors;
- speculative abstractions;
- broad renames;
- dependency additions;
- architecture rewrites;
- formatting churn;
- unrelated cleanup.

Do not alter working behavior outside the task.

Correctness, temporal integrity, auditability, reproducibility, and security take precedence over convenience.

---

## 6. Canonical trading invariants

Preserve the canonical invariants from root `AGENTS.md` and `SOT.md`.

At minimum:

- never fabricate market data;
- fixture/mock data must never silently substitute for live production data;
- official rules must remain deterministic;
- AI must not calculate authoritative signals or official statistics;
- fractal pivot date and `available_at` are distinct;
- plotting offsets are not tradable historical availability;
- `next_open` is unknown on signal night;
- no default same-close fill unless explicitly approved;
- stale/missing data is not equivalent to no signal;
- partial universe coverage must remain visible;
- paper and actual trades remain separate;
- original/initial risk is historically preserved;
- daily SL/TP dual hit remains ambiguous when sequence is unknowable;
- signal/trade/fill generation must be idempotent;
- entry rules and exit policies remain separable;
- historical trade configuration/version must remain auditable;
- MA close exit uses confirmed information according to the approved fill convention;
- RS cross-sectional ranking requires the approved complete comparison universe.

If local code conflicts with these invariants, identify the conflict instead of silently redefining the rule.

---

## 7. Market-data integrity

Never fabricate or silently approximate:

- OHLCV;
- price;
- volume;
- index membership;
- timestamps;
- technical indicators;
- corporate actions;
- fees;
- provider responses;
- signals;
- fills;
- statistics.

If upstream data is unavailable:

- report failure explicitly;
- preserve an approved unavailable/stale/partial state;
- do not manufacture successful output.

Maintain relevant provenance where applicable:

- provider/source;
- symbol;
- exchange;
- timeframe;
- market date;
- timestamp;
- timezone;
- adjustment status;
- strategy version;
- configuration version.

Do not present stale data as current/live.

---

## 8. Temporal correctness and lookahead

Avoiding lookahead bias is mandatory.

Distinguish:

```text
event/pivot date
```

from:

```text
date/time information becomes available to the strategy
```

Future information must not influence past decisions.

Pay particular attention to:

- fractals;
- pivots;
- rolling highs/lows;
- RS rankings;
- cross-sectional calculations;
- confirmed closes;
- next-session fills;
- trailing/MA exits.

Tests should prove timing correctness where applicable.

Do not adjust timing merely to improve historical results.

---

## 9. Trading-rule changes

Trading rules are domain contracts.

Before changing a strategy or execution rule, identify:

- previous rule;
- proposed rule;
- reason;
- version impact;
- expected behavioral difference;
- required tests;
- historical compatibility impact.

Do not tune a strategy merely to produce preferred backtest results unless the task explicitly concerns strategy research.

Avoid:

- lookahead bias;
- survivorship assumptions where relevant;
- silently changing execution conventions;
- retroactively modifying historical trade parameters.

AI may assist analysis or explanation but must not become the authoritative deterministic rule engine.

---

## 10. API contracts

Treat consumed APIs as compatibility boundaries.

Do not silently change:

- endpoint paths;
- HTTP methods;
- request schemas;
- response schemas;
- status codes;
- error formats;
- auth requirements;
- RLS assumptions;
- pagination;
- timestamps;
- strategy identifiers;
- signal/trade/fill models.

Before a breaking change:

1. identify current contract;
2. identify proposed contract;
3. identify frontend impact;
4. identify migration/rollout order;
5. obtain approval where required;
6. verify both sides when possible.

Do not change an API contract merely because backend implementation becomes simpler.

---

## 11. Database and migration safety

Before database changes:

- inspect current schema;
- inspect migration history;
- inspect RLS policies;
- inspect related queries/models;
- inspect data compatibility.

Prefer additive and reversible migrations where practical.

Do not modify an already-applied migration merely for convenience unless project policy explicitly permits it.

Prefer a new migration.

Never casually:

- drop the database;
- drop populated tables;
- truncate data;
- destructive-reset environments;
- destroy journal/history records;
- uncontrolled reseeding.

Destructive or irreversible data changes require explicit approval.

---

## 12. RLS, authentication, and authorization

RLS owner-only requirements must be meaningfully tested.

For affected flows verify as applicable:

- unauthenticated access;
- authenticated owner access;
- authenticated non-owner access;
- invalid/expired credentials;
- expected denial behavior.

Do not weaken RLS or authorization simply to make an API call succeed.

Frontend checks are not substitutes for backend/database authorization.

---

## 13. Idempotency and auditability

Signals, trades, fills, scanner runs, and other economic events requiring idempotency must remain idempotent.

Re-running a job must not silently duplicate economic events.

Preserve sufficient metadata to audit where appropriate:

- source/version;
- strategy version;
- configuration;
- timestamps;
- scanner/run identifiers;
- relevant input date;
- trade/fill linkage.

Do not overwrite historical configuration to make current state simpler.

---

## 14. Fill and risk integrity

Execution logic must respect SOT conventions.

Do not assume intraday event sequence from daily OHLC alone.

If both TP and SL lie within a daily candle and ordering cannot be known, mark the result according to the approved ambiguous-state rule.

Do not rewrite initial risk because:

- stop was later moved;
- MA exit became active;
- trade management changed.

Historical initial risk must remain available for analysis.

---

## 15. Journal and monetary ledger

Paper and actual journals must remain logically separated.

For monetary calculations, test applicable elements such as:

- quantity;
- entry price;
- exit price;
- fees;
- gross P&L;
- net P&L;
- initial risk;
- realized R;
- open/closed state.

Do not invent broker fees.

Use only approved fee configuration/data.

Ledger calculations must be deterministic and reproducible.

---

## 16. Secrets and configuration

Never expose or commit:

- Supabase service-role key;
- database password;
- API keys;
- AI provider secrets;
- private keys;
- privileged tokens;
- session secrets.

Do not overwrite `.env` without explicit need.

Do not print secrets during troubleshooting.

When configuration is missing, report:

- variable name;
- expected location;
- expected role;

not its secret value.

Privileged credentials must never be sent to browser code.

---

## 17. Fractal Channel attribution

For code derived from or porting Fractal Channel:

- preserve required © NielsG attribution;
- preserve applicable MPL-2.0 notices;
- distinguish original indicator logic from SahamTeknikal transaction logic.

Do not present project-specific buy/sell/exit rules as part of the original upstream work.

---

## 18. Bug workflow

For backend bugs:

1. reproduce when practical;
2. capture actual failure/output;
3. trace the data/code path;
4. identify root cause;
5. fix the root cause;
6. rerun original reproduction;
7. run relevant regression tests.

Never:

- hide exceptions merely to obtain success;
- fabricate provider responses;
- disable RLS/auth;
- remove validation to force a pass;
- weaken tests merely to turn them green;
- silently convert failure into `no signal`.

---

## 19. Subagents

Use subagents when work can be safely separated.

Preferred roles:

### Explorer
Read-only investigation.

### Worker
One bounded backend implementation.

### Reviewer
Read-only review.

Possible useful splits include:

- schema/RLS investigation;
- signal-engine analysis;
- API-contract review;
- test review.

Every delegated task requires:

- one objective;
- explicit scope;
- done condition;
- expected evidence;
- concise report.

Do not assign two editing agents to the same file simultaneously.

Verify material claims before relying on them.

---

## 20. Failed-attempt rule

After two materially different failed approaches:

1. stop;
2. record attempts and evidence in `PLAN.md`;
3. revisit assumptions;
4. gather new evidence;
5. formulate a new hypothesis.

Do not keep repeating equivalent fixes.

---

## 21. Git safety

Before substantial work:

- inspect `git status`;
- identify pre-existing work;
- keep changes scoped.

Do not destroy unrelated user changes.

Unless explicitly authorized, do not use:

- `git reset --hard`;
- `git clean -fd`;
- force push;
- destructive checkout;
- history rewriting.

Do not modify frontend Git history from the backend repository.

Review the final diff before completion.

---

## 22. Dependency/runtime discipline

Do not add or upgrade dependencies without concrete need.

Pin dependency/runtime versions when required by the project.

When behavior depends on a provider/library/framework version, verify appropriate official documentation.

Do not silently switch:

- yfinance or approved data source;
- Supabase;
- Vercel;
- GitHub Actions;
- authentication approach;
- hosting architecture;
- paid/free service tier.

---

## 23. Verification

Run the strongest relevant checks.

Depending on the task:

- unit tests;
- integration tests;
- deterministic strategy tests;
- temporal/lookahead tests;
- signal timing tests;
- fill ambiguity tests;
- monetary-ledger tests;
- idempotency tests;
- RLS tests;
- API tests;
- schema validation;
- migration tests;
- linting;
- type checking;
- build/runtime checks;
- scanner smoke tests.

Read the output yourself.

An unrun test is not a pass.

Never claim:

- scanner works;
- signal is correct;
- tests pass;
- migration succeeds;
- API works;
- deployment succeeded;
- production is ready;

without evidence.

---

## 24. High-priority regression risks

Prioritize tests for:

### Signal timing
Only information available at decision time may affect the signal.

### Lookahead
Future candles, future opens, future fractal confirmation, or future ranking must not leak backward.

### Fill ambiguity
Daily SL/TP dual-hit cases remain ambiguous when intraday sequence is unknown.

### Monetary ledger
Entry, exit, fees, risk, P&L, and R remain consistent.

### RLS
Users cannot read or modify protected records owned by another user.

### Idempotency
Repeated scanner/trade/fill jobs do not duplicate economic events.

### Partial coverage
Missing/stale universe coverage cannot masquerade as a complete no-signal result.

---

## 25. Cross-repository verification

For backend behavior consumed by frontend, inspect when possible:

```text
frontend expectation
↓
request contract
↓
backend/API
↓
auth/RLS
↓
domain logic
↓
market data/database
↓
response contract
```

If frontend compatibility cannot be inspected/tested, explicitly report:

```text
Frontend compatibility not verified in this session.
```

Do not claim end-to-end completion based only on backend tests.

---

## 26. Implementation status

When meaningful project implementation state changes, identify/update `..\IMPLEMENTATION_STATUS.md` when access permits and the project workflow calls for it.

Status must be evidence-based.

Distinguish:

- planned;
- implemented locally;
- tested locally;
- configured;
- provisioned remotely;
- deployed;
- live smoke-tested.

A migration/configuration/deployment file does not prove the remote resource actually exists or succeeded.

---

## 27. Remote deployment

Without required credentials or authorization:

- continue safe local implementation;
- prepare configuration;
- run local tests;
- document the exact remaining live step.

Do not claim remote success from local configuration alone.

Do not request that secrets be pasted into chat when a safer environment/configuration method is available.

---

## 28. Review before completion

Before finalizing:

1. inspect final diff;
2. remove accidental changes;
3. remove debug code;
4. remove temporary files;
5. check for secrets;
6. inspect schema impact;
7. inspect API impact;
8. inspect trading-rule/timing impact;
9. compare against SOT;
10. run applicable tests;
11. identify frontend dependencies.

For substantial work, use a read-only reviewer when available.

---

## 29. Documentation and handoff

Determine whether implementation requires updates to:

- `..\SOT.md`
- `..\PRD.md`
- `..\TECHNICAL_DOC.md`
- `..\README.md`
- `..\CODEX_HANDOFF.md`
- `..\IMPLEMENTATION_STATUS.md`

Do not rewrite SOT merely to match accidental implementation.

For handoff, record:

- objective;
- backend work completed;
- files/migrations changed;
- contract changes;
- strategy/data implications;
- verification performed;
- failed approaches when relevant;
- required frontend work;
- exact recommended next action.

Keep active backend task state in:

```text
PLAN.md
```

---

## 30. Definition of done

Backend work is complete only when the relevant conditions are satisfied:

- implementation matches approved requirements;
- trading invariants remain intact;
- temporal correctness is preserved;
- no fabricated live data path exists;
- schema/API contracts are consistent;
- relevant migrations are validated;
- RLS/security boundaries remain correct;
- idempotency is preserved where required;
- meaningful tests pass;
- documentation/status impact is identified;
- cross-repository dependencies are reported;
- no deployment claim exceeds evidence.

---

## 31. Final report

Report concisely:

### Changed
What changed and why.

### Verified
Exact tests/checks run and their outcome.

### Not verified
Relevant checks that could not be performed.

### Frontend impact
Required frontend changes or compatibility concerns.

### Data / strategy impact
Changes affecting market data, timing, signals, fills, journal, risk, or statistics.

### Schema / migration impact
Database compatibility and deployment implications.

### Tradeoffs
Only meaningful compromises or deferred work.

Use evidence rather than confidence statements.

---

## 32. Lessons

When the user provides a durable correction, add:

> When X, do Y because Z.

Newest lessons go first.

Lessons must be specific, actionable, and reusable.

Do not add temporary task details.

Do not modify operating sections above `Lessons` unless explicitly requested.

---

## Lessons

<!-- Newest durable backend lessons go first. -->

> When troubleshooting consumer/runner failures against pipeline outputs, inspect the canonical dataclass definition directly (e.g. `PipelineResult.provider_errors` vs `.errors`) and write a contract regression test, because guessing attribute names or silently falling back with `getattr(..., [])` can mask provider errors and cause dangerous false-green scanner runs.

> When investigating GitHub Actions failures, check the exact commit SHA in the run metadata and distinguish "Re-run jobs" (which executes the historical commit of that specific run) from a fresh `workflow_dispatch` trigger (which pulls `main`), because re-running an old run will repeat already-fixed bugs.

> When evaluating target session eligibility in scheduled runners across midnight boundaries (e.g., pre-market 00:00 - 08:59 WIB), target the previous closed exchange session whose publication window remains open, rather than rejecting the unclosed current day's session.