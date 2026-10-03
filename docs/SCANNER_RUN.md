# Manual scanner command (M2)


## Reviewed quality-repair path

The ordinary CLI accepts --dividend-evidence <manifest>. It retains the raw
provider receipt, ingests derived provenance as a separate immutable revision,
verifies its read-back digest, then evaluates that derived input. The guarded
one-off quality repair is supabase/scripts/publish_repaired_live_run.py; its
--execute path checks source/capture digests, production project, live schema,
previous run and next-session deadline. It produced zero signals.
publish_first_live_hold_run.py remains hold-only and must not publish repaired
inputs. The BBCA manifest requires source files under ignored data/sources/ and
checks their SHA256. A clean runner must reacquire those exact sources before use.
Provider actions alone never prove a source review.

## Latest configuration and execution scope — 2026-10-02

Runtime candidates are now under config/live: KOMPAS100 original owner-supplied
workbook provenance,100 actual Yahoo identity mappings, and official known
2024–2026 trading dates. The 2024 source is a primary KPEI attachment referencing
BEI;2025 baseline plus known amendment and2026 BEI baseline are reconciled.
Monthly day totals match237/236/239. Review any new exchange amendments before
new runs. Source URL identifies the index landing page where appropriate; it
does not claim an independently downloaded constituent attachment.

Calendar `historical_days` contains dates only, before the first timed session.
They support daily warm-up continuity but cannot be used as execution targets,
paper fill timestamps or historical backtest timing. `get`/`next` still require
timed sessions. The current official BEI table supplies earliest regular price
matching08:58 and post-close16:15 WIB only from2026-10-02 onward. A publication
deadline is not a guaranteed individual-security fill time.2027 remains blocked
until its official calendar is supplied. No financial formula or entry rule changed.

Offline100-ticker preflight and evaluation used actual captured Yahoo bars through
2026-10-02, with digest/byte checksums preserved. All100 are data_quality_hold,
coverage0/100, no entry signal and RS cross_section_incomplete. Zero-volume bars
on known holidays are retained in audit data; no normalization/reconciliation has
been silently performed. Corporate actions remain unreconciled. User accepts
skips with reasons but this result is not a healthy/no-signal scan.

`publish_first_live_hold_run.py` is a fixed-target, guarded, local one-off helper.
Default evaluates offline. Authorized `--execute` stores actual same-day captured
revisions, verifies every read-back digest and publishes only a zero-signal hold
run to hcjfxbynqzsaidlwvdfx. It cannot publish entry signals or schedule jobs.
Its actual production outcome is reported in latest status/evidence; the helper
code alone is not deployment proof. It does not create journal QA trades.

The published manual GitHub provider workflow completed successfully in run
37019450372 on8617e56; artifact checksum verified. Scope: five symbols, historical
provider connectivity only. Full scanner publication on GitHub and scheduling
remain separate gates. Earlier pending statements below are historical.

The run subcommand connects existing adapters and the tested run orchestrator.
It does not install a schedule or load .env files implicitly.

## Offline preflight

From backend, inspect arguments:

    scanner/.venv/Scripts/python.exe -m idx_scanner.cli run --help

Provide --provider (yfinance or eodhd), --calendar, --universe-metadata,
--universe-csv, --mapping, --start, --target and --project-ref. --namespace
defaults to forward. Without --execute, this validates local config and session
timing only: no provider/database calls and no credentials required.

The calendar and universe must have data_mode=live and provenance metadata
required by config_io.py. A source URL/checksum format check does not itself
verify that a publication is official. The owner supplied the BEI KOMPAS100
July 2026 major-evaluation roster (100 unique IDX codes, effective 2026-08-03
through 2027-01-29); it is transcribed under config/reference and is not a runtime
config. The workbook binary checksum/sheet review, complete historical exchange
sessions and next-session hours, and provider mappings must still be verified.
No live config is supplied or implied by synthetic fixture files.

## Explicit execution

Set SUPABASE_URL and SUPABASE_SECRET_KEY in the process environment using your
local secret handling. For EODHD also set EODHD_API_TOKEN. Never pass keys as
command arguments or store them in a committed config.

Only add --execute after reviewing the preflight and destination.
The SUPABASE_URL must exactly match https://<project-ref>.supabase.co.
Before contacting a provider the command requires database live mode and
revision-schema columns plus deadline_version=1 capability (migration 004). The current dev database is fixture, so this command
deliberately refuses to publish live data there until a separately authorized
live-testing configuration is prepared. Do not change mode to bypass this gate.

Execution loads prior signal state, fetches the complete configured cross-section,
stores every fetched revision, verifies read-back digest, then evaluates and
publishes. Provider failures stay explicit in stdout and coverage; no fallback.
The JSON summary contains counts, run ID and safe error codes, never credentials.

Exit 0: preflight passed or complete run.
Exit 2: configuration/provider/persistence failure.
Exit 3: a persisted partial/failed scan; inspect provider_errors and coverage.

Evaluation uses UTC wall-clock time after provider/storage IO. Crossing next-open
before evaluation produces late_model_only in the forward namespace; crossing
while evaluating blocks publication so a retry can evaluate as late. Immutable
signals previously published retain their original timing. Transaction-side
publication-deadline enforcement is implemented in migration 004: PostgreSQL
checks its wall clock before a new forward insert and after all row writes.
An expired window rolls the entire transaction back with PT409. Already committed
identical runs can replay after the deadline. The deadline is the configured
next-session open, retained in the immutable run envelope. The source calendar
must still be verified; the database does not independently authenticate that
calendar's exchange hours. Migration 004 capability is now confirmed in the
fixture-mode development project. The development fixture guard still refuses
live provider execution. This CLI is not a claim that production scheduling is ready.

## Current evidence

Local tests cover wrong project, fixture/live mismatch, incomplete cross-section,
database mode checked before provider IO, partial exit status, delayed evaluation
and crossing the entry window before publication. The CLI help was executed.
No live CLI execution, official universe/calendar import or GitHub runner was
performed for this slice. No cron workflow is enabled.

## Migration 004 handoff

Generate the ignored development SQL file with:

    scanner/.venv/Scripts/python.exe supabase/scripts/prepare_dev_deadline_setup.py

Run data/dev-publication-deadline-vgmkpsestahkfahzdtae.sql once through the
development SQL Editor. It checks fixture mode, enabled dev owner, and revision
migration presence. Expected result: deadline_version=1, data_mode=fixture.
It does not modify existing scan/signal rows or change deployment mode.
The updated CLI refuses a live database without the capability RPC.
