# Scanner and paper recovery contract — SQL012

User approved P1–P8 on 2026-10-13. This adds operational contracts without changing fees, risk, prices, trading rules, actual ledger/CSV or historical signal/trade identities.

## Source recovery

Yahoo remains the source, with daily unadjusted OHLCV and `repair=False`. The existing provider may use bounded `period=1d` / `period=5d` captures only for an exact verified closed session. Every known overlapping OHLCV value, symbol, basis, granularity and price-affecting action must agree. Original invalid captures, short captures, closed prefixes and the accepted revision are retained separately. Fetch time and retry count do not change input identity. Missing historical bars and conflicting captures remain holds.

The runtime reads verified persisted history with a ten-session overlap. Conflicts/actions/history gaps require full reconstruction; a controlled full refresh also runs every ten sessions or with `SCANNER_FORCE_FULL_REFRESH=true`. Tracked-book recovery has a separate provider budget (100 requests / 300 seconds, at most20 tickers per attempt), excludes already-current/future-entry objects, prioritizes the oldest unresolved session and rotates ties using the server lease sequence. It never expands the scanner RS comparison set.

`ScanItem.diagnostics` is additive: `{contract_version:1,code,session,missing_fields,recovery_status}`. Absence/null remains legacy-compatible. Missing Close is distinct from absent history, invalid data, provider transport failure and genuine no signal.

## Lease and outcomes

Service-only `claim_paper_runtime_lease_v1(owner,mode,job,session)`, `heartbeat_paper_runtime_lease_v1(owner,mode,job)` and `release_paper_runtime_lease_v1(owner,mode,job)` return version1 operational receipts. Claim returns `acquired`, expiry and a stable-per-job recovery sequence. The runner heartbeats every60seconds; a lease expires after10minutes.

`commit_paper_session_with_lease_v1` uses the original eight named commit arguments plus `p_job_id`. `publish_scan_with_lease_v1(p_run,p_signals,p_owner_id,p_job_id)` uses the original publication envelope. Both lock and validate the matching unexpired lease in the same transaction as the canonical mutation. Legacy writers retain compatibility while no lease/watchdog is active; they cannot bypass active fencing. Canonical cores are private and unavailable to API roles. Existing revision CAS, request idempotency and publication deadline checks remain in force.

A successful held-state commit is not a completed economic session: a required closed-session hold records `paper_data_hold`, terminal failure and nonzero workflow exit. Future pending entry is a valid wait. Failed publication and successful paper processing remain separate stages.

## Owner reporting

The existing version1 health/read RPCs add `attempt_session`, `last_fully_resolved_session`, `earliest_unresolved_session`, trade/evaluation and filled/unfilled hold counts, `scope=all_experiments_and_evaluations`, stage statuses and the latest job's run/source metadata. `processed_session` retains its legacy persisted-attempt meaning. A expired lease exposes `runtime_stalled=true`, `operational_failure_code=heartbeat_stalled` and overdue/held state without inventing a terminal job event.

Detail adds `trade.processing` with version1, persisted entry processing time, last processed session and earliest unresolved session. `events[].recorded_at` comes from the database event creation time, independently from economic session and observation time. Missing historical metadata remains null. Frontend validates these relations and formats canonical values; it performs no financial recalculation.

## Cloud watchdog and credentials

Supabase Cron runs the privileged tick every20minutes. Its default is disabled. It waits2h15 after the verified exchange close, respects active runtime/queued dispatch leases, a30minute cooldown, four additional dispatches per session, permanent configuration failures and rate-limit backoff. Publication is allowed only inside the forward window; delayed jobs use paper-only recovery. The dispatcher fixes repository, workflow and ref to the backend's `scheduled-scanner.yml` on `main`.

`pg_net` sends only a short-lived one-use UUID ticket to `idx-paper-watchdog`. The Edge function atomically consumes the service-only ticket, dispatches GitHub and records the safe outcome. GitHub HTTP204 is acceptance, not job completion. Client roles cannot create/consume tickets, invoke the privileged tick or read private lease/configuration records. Safe owner receipts contain no secret or request header.

The GitHub PAT stays exclusively in the Edge Function secret `GITHUB_WATCHDOG_DISPATCH_TOKEN`, scoped to this repository with Actions write. It is never decrypted into the `pg_net` queue. Supabase warns that queued request headers can be read by database roles and project grants/RLS cannot reliably restrict that queue: [official constraint](https://supabase.com/docs/guides/troubleshooting/database-roles-can-read-request-headers-queued-by-pg_net-ad6357).

The ignored `.env.production-operator.local` is a provisioning input only. `SUPABASE_DB_PASSWORD` is for backup/migration, and `SUPABASE_ACCESS_TOKEN` is for management deployment. Neither is copied into Edge runtime. GitHub Actions uses its separately configured Supabase/owner secrets; Vercel uses its own public/server environment. Production requires no laptop REST service or local file.

Activation follows backup → full isolated restore/rehearsal → SQL012 → compatible runtime/frontend → verified Edge secret/ticket/security → Cron enable → catch-up/retry. Rollback disables the watchdog and unschedules only `idx-paper-watchdog-v1`, preserving all receipts and financial history. A provider outage remains visible; one successful recovery does not prove later-session stability.
