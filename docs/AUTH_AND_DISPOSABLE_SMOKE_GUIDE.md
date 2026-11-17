# Owner login and disposable smoke guide

Reusable isolation/security procedure; reviewed 21 October 2026 without execution.
[Status](../IMPLEMENTATION_STATUS.md) owns dated schema/release and proof limits.
[Original guide](archive/AUTH_AND_DISPOSABLE_SMOKE_GUIDE_BEFORE_HANDOVER_CLEANUP_20261021.md)
retains local smoke results, startup failure/binding correction and earlier setup.
Old rollout approval is historical; it is not permission to create Auth users,
change production settings, start containers or write permanent QA financial rows.

## Production owner session

Verify intended project/ref/mode, schema history/capabilities and existing enabled
owner before a scoped smoke. Already-applied migrations are not setup work to repeat.
For an authorized Auth configuration change, the operator privately creates/uses the
dedicated OAuth app and submits Client ID/secret in the intended Supabase provider.
Provider callback is `https://<project-ref>.supabase.co/auth/v1/callback`;
application callback is `/auth/callback` on the exact allowed app origin.
Keep development/production origins separate, no broad preview wildcard redirects.
Enabling GitHub is not an Auth session or owner-RLS proof.

Use the existing owner's actual app login. Auth issues the JWT; verify returned UID
against existing enabled membership. Verified-email linking/account names do not
authorize promotion or imply UUID equality. Dashboard login is not the app session.
Do not extract/copy browser tokens, accept service-key owner impersonation or sign
manual JWTs. Use protected prompts/environment; never passwords/JWT/callback codes
in chat, shell arguments, transcripts, screenshots, logs, files or Git.

Report only correct-project/owner-match/enabled booleans, safe HTTP/error codes,
contract versions and aggregate counts. Owner browser, SQL-role, service preflight
and real owner/outsider JWT prove distinct boundaries. Do not disable the sole
production owner or create/promote an account to manufacture a denial test.
A credential/login failure stays blocked for that boundary while safe work continues.

Development-only read probes exist in `supabase/scripts/verify_dev_owner_rls.py`
(`--check-config`, optional protected `--access-token` prompt) and
`verify_dev_non_owner_rls.py` (account creation requires explicit execute/isolation).
Verify their allowlisted development URL and exact source before any use.
A disposable cleanup marker prevents duplicate accounts after interruption; recover
that target explicitly instead of creating more users or deleting unrelated ones.

## Disposable local target

Use only a verified isolated sandbox under ignored `data/` with its own project ID,
fixture mode, intended frozen schema, empty starting Auth/workload and local secrets.
Never link it to cloud, clone production Auth/data, reuse production secrets, reset
shared development, silently upgrade a service or pause another project for a slot.

The historical CLI startup accepted a custom bridge default yet exposed ports on all
interfaces. Require inspection of actual Docker port bindings and health before
creating accounts/trades, including after every restart: API/DB must bind loopback
only. A successful start/network setting is insufficient. Stop the exact unsafe
sandbox before fixture identities/workload; preserve data/volumes unless cleanup
is explicitly authorized. The archived cache-specific CLI path is not portable.

Suppress raw start/status output because it can contain local keys; keep it in
memory without transcripts. Use a trusted pinned CLI, no `--ignore-health-check`,
`--linked`, production URLs/secrets or broad `db reset`. Check actual local migration
history: startup may already apply SQL. Apply only remaining verified local versions;
never repair history to claim an unexecuted migration.

After readiness, scoped tests may create disposable ownerA/ownerB/outsider/disabled
accounts and grant only their intended memberships. Auth logins supply real local
JWTs. Test row isolation, anon/direct DML denial, replay/changed payload/stale PT412,
ledger corrections/fees/analytics/CSV, cursor 200+1 and independent clients/sessions.
Compare revisions/receipts/audit and failed-request residue. Financial math stays
in canonical RPC. Label every local fixture. Stop only this sandbox after testing.
Nonempty owner data matters: denial on an empty table is narrower than row isolation.

## Hosted alternative and evidence limits

An operator may provision a dedicated hosted QA target only when authorized, then
provide its ref and privately provision secrets. Do not buy/upgrade/repurpose shared
projects silently. Verify target/mode/schema/users before setup. Hosted QA remains
QA evidence; local disposable Auth/HTTP remains local evidence.

Production mutation lifecycle/error/concurrency needs genuine owner-approved activity
to retain or a separately approved isolation design. Never seed immutable permanent
TEST trades just to close a gate. SQL rollback fixtures can test database contracts
without becoming real JWT/HTTP/browser proof. A one-page real CSV does not prove
>200-row HTTP pagination. Record skips, owner waivers and unavailable tests honestly;
an archived waiver belongs only to its original release/source.

<!-- Compatibility anchors for consolidated historical sections. Original content is in archive/AUTH_AND_DISPOSABLE_SMOKE_GUIDE_BEFORE_HANDOVER_CLEANUP_20261021.md. -->
<a id="owner-login-and-disposable-smoke-target--2026-10-02"></a>
<a id="latest-execution-evidence"></a>
<a id="disposable-target-without-a-new-paidcloud-project"></a>
<a id="hosted-disposable-alternative"></a>
