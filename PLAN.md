# Manual publisher preparation and real-trade audit — 2026-10-03

Scope: backend only. Existing modified AGENTS.md and empty untracked PLAN.md
were user changes; preserved. No commit/push/dispatch/publication authorization
is inferred from this preparation request. Scheduler remains off.

1. Action: read latest backend and frontend evidence, preserve 001–007 and
   unchanged owner scanner-read/full100 runner PASS.
   Proof: reviewed frontend real-trade JSON and continuation; prior runner
   37114744856/b4762fd is evaluation only, publication receipt null.
2. Action: inspect real NCKL trade through the existing owner browser session,
   read-only; never extract JWT, guess request UUID/payload or mutate ledger.
   Proof: record rendered fills/correction and audit access limits; raw receipt
   inspection is not claimed unless actually available through an owner path.
3. Action: prepare a separate manual production publisher using checksum-bound
   captured inputs, exact approved plan, live target/deadline guards, protected
   environment secrets, canonical run_once and read-back. No scheduler.
   Proof: meaningful guard tests, offline plan, lint/diff, read-only review.
4. Action: update readiness/handoff and ask only for remaining concrete execution
   authorization/access. Outsider and independent concurrency are skipped at
   user request; disabled-owner remains NOT VERIFIED.
   Proof: dated report with PASS/PARTIAL/BLOCKED/SKIPPED and no fabricated hosted
   lifecycle, publisher or Vercel success.

Documentation conflict: parent README/TECHNICAL_DOC/HANDOFF describe initial
pre-deployment baseline, whereas current backend dated evidence describes an
applied release. Preserve canonical parent trading rules; use observed dated
backend evidence for operational facts, without rewriting parent/frontend docs.

## Completed preparation / current gates

### Authorized local execution — 2026-10-03

User approved one local publication/read-back for exact plan
838183f9e3fcb5bcfe6c4681be885e87a1410672137d73eeed0f1a3d2ff4ffb0.
Execution started around12:37UTC after Git audit/current clock check. Existing
backend credentials loaded only into an isolated Python child process; no .env
write, Git push/dispatch, Auth/journal mutation or scheduler enablement. Do not
retry while this attempt is unresolved. Final receipt/read-back pending.

- Action1 complete: preserved prior001–007/owner snapshot/GitHub100 evidence.
- Action2 PARTIAL: current owner session rendered fills/correction#2, notes empty;
  downloaded CSV hash/one-row decimals and net/risk ratio verified. First correction
  page unavailable, subsequent owner read succeeded. Raw receipt/audit not exposed,
  no JWT copied, no guessed UUID/payload/replay.
- Action3 locally complete: candidate plan SHA838183f9...4ffb0 and separate capture
  digest653f9f91...4110; new protected manual workflow/script/environment GET guard.
  Python251PASS/5explicit Docker skips;16new guard cases;Ruff/diff PASS. Reviewer
  found incorrect composite/sequence table ordering; fixed and regression tested,
  re-review no remaining implementation blocker for preparation.
- Action4 complete: latest dated status/report/handoff now distinguishes user skips
  from PASS and disclosed estimated fees. GitHub Settings read-only shows no
  environments; hosted publisher environment absent. No config/Auth/ledger/write.

Failed checks and evidence: offline capture reconstruction initially failed digest
serialization; corrected canonical key mapping and parity test. Global pytest temp
failed3setup cases with Windows access denied; backend-owned basetemp passed. Ruff
line length fixed. Official-source web fetch timed out/API inaccessible and sandbox
Git network failed; changed hypothesis to known sandbox network restriction,
read-only escalated git ls-remote verified official download-artifact SHA.

Next action: exact publisher route/plan approval and safe process/env credential
access; no dispatch or write before that. Local candidate expires24h after fetch;
if elapsed, new capture/plan and approval are required. Hosted environment/main
reviewer setup still needed. Raw trade receipt audit requires an authorized owner
read path that exposes rows; never substitute service-role as owner proof.
Outsider/concurrency skipped at user request; disabled owner/hosted error paths
unverified. Complete backend/full-stack NO-GO; scheduler off, Vercel separate.

## Authorized publication outcome — latest continuation

The one approved attempt committed receipt3c700de4-8389-400e-b862-31f2c8998a64
but failed postflight (nonexistent id order on scan_run_items). No repeat write.
Original failure kept; schema/composite order fixed. GET-only recovery PASS
12:49:31Z,100tickers/45/25/30/0signals/incompleteRS,200revision manifest keys.
Oldlatest metadata matches; NCKLprojection revision5/values match. Full7table
before/after fingerprint comparison NOT VERIFIED: original baseline in-memory
was not persisted. Future hash-only checkpoint regression tested; after abrupt
termination checkpoint false-write flag is not proofno write.

Python254PASS/5native skips25.26s;18focused cases before checkpoint test,fullsuite
includes19publisher cases;Ruff/diffPASS. Reviewer recovery safe, notes historical
recovery inherits24h/deadline guards (later rerun needs reviewed read-only mode).

Action complete: approved local publication plus safe read-back; originalfailure
not hidden. Next action is frontend owner-read this NEW run, not another publisher
execution. Outsider/concurrencyskips,disabledowner/rawownerreceiptaudit/errorpath
proofs and Vercel remainunverified; hosted publisherenvironment absent/scheduler
off. Completebackend/full-stackNO-GO. No commit/push/frontend/env/Auth/migration
changes; originaluserAGENTS preserved. Full evidence in manual-production-
publication-attempt/readback files and MANUAL_PUBLICATION_RESULT_20261003.md.
