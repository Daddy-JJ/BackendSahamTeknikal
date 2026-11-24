# Project context — backend

Context version: `docs-context-v1-20261021`; snapshot as of 21 October 2026.
This is portable project context, not a new policy or a live-health receipt.

## Shared project facts

SahamTeknikal is an IDX end-of-day scanner, Smart Money Flow & Bandarmology sync engine, and research workspace.
It provides deterministic signals, multi-horizon bandarmology analytics (2D/5D/10D) over 955 IDX tickers,
persistent paper experiments, a separate actual journal, canonical reporting, signal research and immutable canonical chart views.
Financial calculations, indicators, signals, fills, risk, fees, P&L and official
statistics belong to backend/RPC output. The frontend validates and formats them.
Paper and actual books remain separate; AI is not an authoritative trading engine.

The two independent Git repositories are:
- Frontend: [Daddy-JJ/FrontEndSahamTeknikal](https://github.com/Daddy-JJ/FrontEndSahamTeknikal).
- Backend: [Daddy-JJ/BackendSahamTeknikal](https://github.com/Daddy-JJ/BackendSahamTeknikal).

The frontend uses Next.js 16.3.8, React 19.3 and TypeScript, hosted on Vercel.
The backend uses Python 3.12, GitHub Actions, Supabase Auth/PostgreSQL/RPC and
a Supabase Edge/Cron watchdog. Inspect pinned local manifests for exact runtime patches.
Runtime credentials belong in each service's secret store; a local operator file
does not provision GitHub Actions, Vercel or Edge runtime automatically.

## Canonical documents and snapshots

The combined workspace root owns `SOT.md`, `PRD.md`, `TECHNICAL_DOC.md` and
`contracts/ticker-chart-v1.md`. This repository carries versioned local snapshots:
- [SOT.md](SOT.md), SHA-256 `d6e18a844a739a799ca38d0e23dc637f8e817991330de86c7ed62b6ad4f32f06`.
- [Chart V1](contracts/ticker-chart-v1.md), SHA-256 `b31fe96047df61c91c81c91a5bc27c53b398651b9fa08fce4ea4e90d5bc39e63`.

These hashes identify raw-byte snapshots available on 21 October 2026.
Equal hashes prove agreement among available copies; they do not prove freshness
against an unavailable workspace root. Do not invent newer shared requirements.
The parent workspace and sibling checkout are optional aids, not clone prerequisites.
When unavailable, use local rules/contracts and identify any missing context that
blocks safe work; product scope and architecture are summarized locally below.

## Read and maintain

Read [AGENTS](AGENTS.md) → this context → [PLAN](PLAN.md), then relevant source/tests
and SOT/contract sections. Read [status](IMPLEMENTATION_STATUS.md) when evidence/gaps
matter. Reports and archives are on demand; their pending text is not a task queue.
Use [DEVELOPMENT](DEVELOPMENT.md) for setup and [contracts](contracts/README.md) for boundaries.

The agent changing shared context/policy owns synchronization of both repositories'
context and applicable snapshots within the authorized scope. Record source, as-of
date, context version/hash and delivery ref; compare available copies before closing.
If the other repository is unavailable or outside scope, record `sync pending`,
the missing ref and responsible next action. Do not claim both repositories aligned.
This snapshot was coordinated across both local repositories during documentation
cleanup; delivery remains uncommitted until separately authorized.

## Local backend responsibility

Edit backend source, schema, adapters and tests here; document consumer handoffs.
[TECHNICAL_DOC](TECHNICAL_DOC.md) maps implementation; [PRD](PRD.md) states local scope.
Use [SCANNER_RUN](docs/SCANNER_RUN.md) for scanner/paper/recovery procedures.
Existing proof retains its original source, date and environment. Local, fixture,
SQL-role, public HTTP, genuine JWT, hosted browser and deployment proof are distinct.
No context document authorizes a production mutation, Git publication or deployment.
