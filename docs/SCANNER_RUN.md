# Scanner, paper and recovery runbook

Reusable source map, reviewed 21 October 2026 without executing commands or probing
services. [Status](../IMPLEMENTATION_STATUS.md) owns dated release/runtime evidence.
A command, cron definition or archived approval is not authorization to publish,
dispatch, change automation, replay history or mutate production.

## Choose the entrypoint

| Source | Purpose and side effects |
| --- | --- |
| [CLI](../scanner/src/idx_scanner/cli.py), [run command](../scanner/src/idx_scanner/run_command.py) | `demo` writes synthetic fixture; `fetch` performs provider IO only; `run` preflights, and `--execute` fetches/persists/publishes |
| [Scheduled runner](../supabase/scripts/scheduled_scanner_runner.py) | scanner plus persistent paper processing; `--target`, `--execute`, `--require-usable`, `--paper-only` are explicit controls |
| [Scheduled workflow](../.github/workflows/scheduled-scanner.yml) | GitHub schedule/dispatch invokes that runner; runtime secrets are cloud-side |
| [Manual provider workflow](../.github/workflows/manual-provider-smoke.yml), [manual scanner smoke](../.github/workflows/manual-scanner-smoke.yml) | connectivity/capture/evaluation proof; do not infer database publication |
| [Manual publisher](../supabase/scripts/prepare_manual_publication.py), [workflow](../.github/workflows/manual-scanner-publication.yml) | offline checksum-bound plan, separately approved publication and protected-environment guard |
| [Chart runner](../supabase/scripts/chart_artifact_runner.py), [workflow](../.github/workflows/chart-artifacts.yml) | persisted canonical sources; reads without `--execute`, artifact writes with it; no provider/economic writes |
| [Local paper helper](../supabase/scripts/paper_journal_runner.py) | local diagnostic JSON/summary; not authoritative persistent cloud paper state |

From backend, inspect source/arguments for the assigned task. These examples
document supported help commands; they were not executed during cleanup:

```powershell
.\scanner\.venv\Scripts\python.exe -m idx_scanner.cli run --help
.\scanner\.venv\Scripts\python.exe supabase\scripts\scheduled_scanner_runner.py --help
.\scanner\.venv\Scripts\python.exe supabase\scripts\chart_artifact_runner.py --help
.\scanner\.venv\Scripts\python.exe supabase\scripts\prepare_manual_publication.py --help
```

## Offline preflight and explicit execution

Generic `idx_scanner.cli run` requires `--provider` (yfinance/eodhd), `--calendar`,
`--universe-metadata`, `--universe-csv`, `--mapping`, `--start`, `--target` and
`--project-ref`; namespace defaults to `forward`. Without `--execute` it validates
local configuration/session timing without provider/database calls or credentials.
It does not implicitly load env files or install a schedule.

Only for an authorized execution, supply process `SUPABASE_URL` and
`SUPABASE_SECRET_KEY`; EODHD also needs `EODHD_API_TOKEN`. Never put keys in
arguments/config/Git/logs. URL must exactly match the intended project ref.
Live-mode/revision/deadline capability is checked before provider IO. Do not switch
a development/production mode to bypass a guard. Missing credentials are reported
by variable/role/location only. Apply/reconcile migrations only through readiness.

Execution loads prior signal state, fetches the configured cross-section, stores
each revision, verifies digest read-back, evaluates and publishes. Provider/storage
failure stays explicit; there is no fixture/provider fallback or invented no-signal.
CLI exit 0 is preflight/complete, 2 is configuration/provider/persistence failure,
3 is a persisted partial/failed scan. Inspect `provider_errors` and coverage.

Evaluation uses UTC wall-clock after IO. Crossing next-open before evaluation
becomes late_model_only; crossing during evaluation blocks forward publication.
SQL004 checks before/after new forward writes and rolls back expired publication
with PT409. A committed identical run can replay after deadline; original timing
is immutable. The database does not authenticate exchange-calendar provenance.

## Source and configuration provenance

- [Runtime calendar](../config/live/idx-calendar-2024-2026.json),
  [universe](../config/live/kompas100-universe.json), [CSV](../config/live/kompas100-universe.csv)
  and [verified mappings](../config/reference/yfinance-kompas100-verified-mappings.json)
  must cover the requested period. Format/checksum checks alone are not source certification.
- Known 2024–2026 calendar/reference sources and the owner-supplied KOMPAS100
  workbook are recorded with explicit provenance. Date-only `historical_days`
  support warm-up, never execution targets/fill timestamps/backtest timing.
  Timed target/next-session methods require their verified exchange-session hours.
  Do not infer 2027, historical execution hours, amendments or later constituents.
- An owner workbook is not an independently downloaded official attachment.
  Keep original bytes/source hashes, effective dates and provider identities distinct.
- Ordinary CLI `--dividend-evidence` retains raw receipt, derives a new immutable
  revision with reviewed provenance and verifies read-back. Source files/checksums
  must match; provider action metadata alone never approves reconciliation.
  Preserve open-session zero volume, missing/invalid OHLCV and unknown actions as holds.
- [Source-review locator](MARKET_SOURCE_STATUS.md), [provider probe](LOCAL_PROVIDER_PROBE.md),
  [collector study](COLLECTOR_REFERENCE_AUDIT.md) and [recovery report](SCANNER_RECOVERY_REPORT_20261003.md)
  preserve dated observations. Another Yahoo transport is not an independent source.
  Old provider counts, plans and source gaps are not a fresh availability check.

## Persistent paper and scheduled recovery

The scheduled workflow source defines primary/recovery slots at 18:18/19:19 WIB
weekdays plus 22:23/06:31 WIB daily; these definitions do not prove remote enablement
or successful dispatch. Workflow dispatch accepts target_date, execute_publication
and paper_only. With a separately authorized operation, the persistent runner form
is `scheduled_scanner_runner.py --target YYYY-MM-DD --execute`; paper-only recovery
adds `--paper-only` and never authorizes historical forward-signal regeneration.

Use the previous closed verified exchange session across midnight, not an unclosed
current date. Preserve writer leases/heartbeats/fencing, revision CAS, idempotency,
backoff and publication windows under [recovery contract V1](INCIDENT_RECOVERY_CONTRACT_V1.md).
A required closed-session hold is failed/held processing; a future pending entry is
a valid wait. A successful held-state commit is not a completed economic session.

Inspect stage outcomes, earliest unresolved/last fully resolved sessions and source
freshness. Preserve the two paper experiments, original risk, frozen signal-close
next-session entry and approved lot/fee budget in SOT. Independent 5/10 checkpoints
are observations and never automatic closes. Actual ledger is separate.

Cloud watchdog uses Cron/Edge one-use tickets with private dispatch credentials,
bounded recovery/cooldown and safe owner health receipts. HTTP204 means accepted,
not completed. No laptop operator env/service is a runtime dependency. Enabling,
disabling or dispatching jobs requires the operation's authorized scope; record and
restore exact previous states rather than enabling everything automatically.

## Manual publication and ambiguous outcomes

Use a fresh actual capture and the current checksum-bound preparation script; never
reuse the expired 3 October candidate/hash/approval. Offline preparation writes an
ignored plan without opening a DB. Publication requires `--execute`, exact reviewed
`--project-ref` and `--approved-plan-sha256`, plus scoped process credentials.
Inspect the workflow's actual environment/protection guard from source; an environment
name in YAML does not prove required reviewers/main restrictions or secret placement.
Do not buy a tier, change visibility or bypass a protection failure silently.

Ingestion and publication are separate transactions. Timeout/null receipt can follow
a committed write. Stop, retain sanitized evidence, reconcile the exact digest/run/
revision IDs by read-only checks and seek scoped retry authorization where required.
Do not delete receipts, invent a receipt, publish a second plan automatically or
bypass expired forward-window guards. Pre-write checkpoint flags cannot prove no
write after interruption. Preserve original failure separately from GET-only recovery.
The [manual result](MANUAL_PUBLICATION_RESULT_20261003.md) records lost original
before/after hashes; later checkpoints do not retroactively recover them.

## Chart and release boundaries

Chart runner requires process Supabase URL/secret and existing owner ID even for
read-only planning. `--max-tickers` defaults 100; source revision budget defaults
256/hard cap 500, at most four read-only workers per ticker, ordered output and serial
artifact writes. Over-budget/invalid/partial sources fail explicitly without truncation.
[Chart V1](../contracts/ticker-chart-v1.md) owns the immutable consumer protocol.

Use [release readiness](PRODUCTION_READINESS.md), [backup/restore](BACKUP_RESTORE_RUNBOOK.md)
and [Auth isolation](AUTH_AND_DISPOSABLE_SMOKE_GUIDE.md) only for the relevant authorized
task. [Original scanner notes](archive/SCANNER_RUN_BEFORE_HANDOVER_CLEANUP_20261021.md)
retain old rollout/test gates. Their no-cron/004-only/pending wording does not override
later dated status. No commands, tests, network probes or operations ran in this cleanup.

<!-- Compatibility anchors for consolidated historical sections. Original content is in archive/SCANNER_RUN_BEFORE_HANDOVER_CLEANUP_20261021.md. -->
<a id="manual-scanner-command-m2"></a>
<a id="reviewed-quality-repair-path"></a>
<a id="latest-configuration-and-execution-scope--2026-10-02"></a>
<a id="offline-preflight"></a>
<a id="explicit-execution"></a>
<a id="current-evidence"></a>
<a id="migration-004-handoff"></a>
