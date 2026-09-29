# Manual scanner command (M2)

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
verify that a publication is official. Effective KOMPAS100 membership, all
historical exchange sessions, next session, and provider mappings must first
be reviewed against authoritative publications. No live config is supplied
or implied by the synthetic fixture files in this repository.

## Explicit execution

Set SUPABASE_URL and SUPABASE_SECRET_KEY in the process environment using your
local secret handling. For EODHD also set EODHD_API_TOKEN. Never pass keys as
command arguments or store them in a committed config.

Only add --execute after reviewing the preflight and destination.
The SUPABASE_URL must exactly match https://<project-ref>.supabase.co.
Before contacting a provider the command requires database live mode and
revision-schema columns. The current dev database is fixture, so this command
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
publication-deadline enforcement during an in-flight network call/retry is still
a release gate; this CLI is not a claim that production scheduling is ready.

## Current evidence

Local tests cover wrong project, fixture/live mismatch, incomplete cross-section,
database mode checked before provider IO, partial exit status, delayed evaluation
and crossing the entry window before publication. The CLI help was executed.
No live CLI execution, official universe/calendar import or GitHub runner was
performed for this slice. No cron workflow is enabled.
