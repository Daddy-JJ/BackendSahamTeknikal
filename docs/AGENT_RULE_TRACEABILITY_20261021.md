# Backend rule preservation and handover map

Approved documentation-only consolidation, 21 October 2026. This is traceability,
not new domain policy or permission for production work. The full original guide is
[preserved](archive/AGENTS_BEFORE_HANDOVER_CLEANUP_20261021.md) at source main719bc8c.

| Original operating section | Preserved compact rule |
| --- | --- |
| 1 Read before changing code | R01: local-first context/SOT/source, root/sibling optional, unavailable context explicit |
| 2 Backend responsibility | R02: own backend; frontend/parent edits require cross-repo scope |
| 3 Understand before editing | R03: complete source-to-ledger/data chain, tests/models/config/consumer assumptions |
| 4 Planning | R04: small/complex workflows, Action/Proof, dependencies/risks/approval list |
| 5 Smallest safe change | R05: reuse, targeted diffs, no churn; integrity/security/reproducibility first |
| 6 Canonical trading invariants | R06/R07: no fabricated/future data, deterministic official outputs, separate paper/actual, initial risk, ambiguity, idempotency and configuration audit |
| 7 Market-data integrity | R06: OHLCV/membership/time/actions/fees/provider/signals/fills/statistics; exact provenance, explicit failure/partial |
| 8 Temporal correctness/lookahead | R06: event/pivot vs available-at, plotting offsets, rolling/RS/confirmed-close/next-session timing |
| 9 Trading-rule changes | R04: approval, old/new/reason/version/behavior/tests/history; no result-seeking retrospective tuning |
| 10 API contracts | R08: all contract fields, consumer impact, rollout order, approvals and compatibility checks |
| 11 Database/migration safety | R08: history/RLS/data inspection, additive forward migrations, no destructive/reset/reseed/applied-edit without approval |
| 12 RLS/auth/authz | R09: unauthenticated/owner/outsider/expired/denial tests, DB enforcement not UI-only |
| 13 Idempotency/auditability | R07: retry identity, immutable config/run/source/linkage and events |
| 14 Fill/risk integrity | R06/R07: approved timing, daily dual-hit ambiguity, immutable historical initial risk |
| 15 Journal/monetary ledger | R07: separate books, quantity/price/fee/gross/net/risk/R/state tests, deterministic approved math |
| 16 Secrets/configuration | R09/R10: no printed/committed/browser secrets, missing variable name not value, startup checks, safe cloud stores |
| 17 Fractal Channel attribution | R14 plus unchanged THIRD_PARTY_NOTICES: NielsG/MPL and project transaction-rule distinction |
| 18 Bug workflow | R03: observe/reproduce/trace/root fix/retest, never bypass validation/auth/quality or fake success |
| 19 Subagents (Explorer/Worker/Reviewer) | R12: readonly investigators/reviewers, bounded workers, objective/scope/done/evidence/report, no overlapping writers |
| 20 Failed-attempt rule | R03: stop after two materially different failures; record evidence, revisit assumptions, new hypothesis |
| 21 Git safety | R02/R12: preserve user work/history; destructive operations and publication require explicit scope; no sibling-history edits |
| 22 Dependency/runtime discipline | R10: concrete need, pins, official docs, no silent provider/hosting/auth/tier switch |
| 23 Verification | R11: strongest relevant checks, personally read output, no unrun PASS or unsupported deployment/readiness claims |
| 24 Regression priorities | R06/R07/R09/R11: timing/lookahead/ambiguity/ledger/RLS/idempotency/partial coverage |
| 25 Cross-repository verification | R03/R13: request/API/auth/domain/data/response trace, explicit missing-frontend compatibility statement, no backend-only E2E claim |
| 26 Implementation status | R13: planned/local/tested/configured/provisioned/deployed/live-smoked distinct |
| 27 Remote deployment | R02/R09/R13: safe local progress without credentials/permission, exact remaining steps, no config-as-deploy proof or pasted secrets |
| 28 Completion review | R12: diff/debug/temp/secrets/schema/API/domain/SOT/checks/frontend dependencies and readonly review |
| 29 Documentation/handoff | R13: correct doc owners, no SOT rewrite for accidental code, scope/files/contracts/implications/checks/failures/consumer/next step |
| 30 Definition of done | R13: approved behavior/domain/data/security/contracts/migrations/RLS/idempotency/checks/docs/consumer limits |
| 31 Final report | R13: changed/verified/not verified/frontend/data/strategy/schema/migration/tradeoffs; evidence not confidence |
| 32 Lessons and Lessons body | R13/R14: explicit instruction changes only, When-X format/newest first, durable not temporary; all three original lessons retained verbatim |

## Inherited shared obligations

R04/R12 preserve planner/architect/domain-specialist delegation and independent parallel work.
R05 preserves immutable objects, feature/domain cohesion, file/function/nesting limits,
safe errors, schema validation, API envelopes, repository abstraction and template evaluation.
R09 preserves the full precommit security checklist and security-stop/review/fix/rotation path.
R11 preserves mandatory TDD RED/GREEN/refactor, at least 80% coverage and unit/integration/
critical-flow E2E. Documentation-only checks never replace required checks for app changes.
R12 preserves review before completion, CRITICAL/HIGH resolution, incremental build diagnosis,
context-budget rule, skills-first workflow surfaces and conventional PR/test-plan/upstream Git.
R13 preserves knowledge ownership/no duplicate top-level docs, permissioned personal memory,
honest proof classes and shared snapshot source/date/hash/ref synchronization.
The generic catalog describes relevant roles, not installed tools or extra application frameworks.

## Validation boundary

The original guide and mixed procedure/report bodies are archived without evidence rewriting;
only wrapper/link rebasing was added. Local source/tests/SQL/config/checksums are unchanged.
Parent local checks cover hashes, preservation, links/anchors, policy mapping and clone reading.
Independent frontend, backend and workspace reviews PASS after the initial usage-limit
interruption. Backend review confirmed all32 sections and3 exact lessons; the PT412
stale-revision documentation rule was restored and independently rechecked against the
archived original and unchanged migration006. No substantive finding remains. No new
application, hosted auth, restore, cloud or production outcome is implied.
