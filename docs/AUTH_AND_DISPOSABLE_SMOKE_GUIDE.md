# Owner login and disposable smoke target — 2026-10-02

No frontend edits or Vercel deployment were performed by this backend chat.
Production rollout is authorized; credential entry remains an operator action.
Do not paste credentials, OAuth callback codes or JWT into chat/logs/files.

## Production owner session

1. Finish guarded CLI001 reconciliation and002–007 before journal/API smoke.
   Review sanitized script output, actual history and schema/FK/RPC postflight.
2. In GitHub Settings → Developer settings → OAuth Apps, create a dedicated
   production OAuth app yourself. Callback:
   `https://hcjfxbynqzsaidlwvdfx.supabase.co/auth/v1/callback`.
   Homepage is the actual app origin; localhost3050 is acceptable for this
   preliminary local login test. This does not prove a Vercel deployment.
3. In the exact production Supabase project, Authentication → Sign In / Providers
   → GitHub, enter Client ID/Client Secret privately and enable the provider.
   The operator must enter and submit new credentials; do not send them to an agent.
4. For local owner login, permit the exact application redirect
   `http://localhost:3050/auth/callback`. Keep final Site URL/HTTPS callback tied
   to the verified Vercel origin when frontend deployment is separately authorized.
   The application callback differs from the GitHub provider callback above.
   Do not add broad production/preview wildcard redirects.
5. Ask the frontend chat to run its EXISTING local login/Auth-check against the
   production URL/public key, without UI changes, commit/push or Vercel deployment.
   Public key is retrieved privately from the production Dashboard; service-role
   keys remain backend-only. This backend chat does not modify frontend config.
6. Use the existing owner's GitHub account. Supabase issues the session JWT itself.
   Verified-email identity linking can preserve an existing user, but verify the
   resulting UUID against the existing enabled owner membership. Do not assume
   matching account names imply matching UUIDs, and do not promote a new account.
7. Report only: correct project, authenticated user/owner match boolean, enabled
   owner boolean, HTTP status/error codes, contract version and aggregate counts.
   Never copy a token from browser storage/network tools. Backend production
   owner read smoke is distinct from SQL claims and service-role preflight.

Without working OAuth credentials/login, this gate is BLOCKED. Enabling GitHub
alone is not an owner session or RLS proof. Outsider/disabled-owner writes must
use an explicitly approved safe target; never disable the sole production owner.

## Disposable target without a new paid/cloud project

An OFFLINE sandbox was prepared at
`backend/data/idx-smoke-local-20261002/supabase/`. CLI2.119.0 init completed;
project_id=`idx-smoke-local-20261002`, PostgreSQL major17, seed/analytics disabled,
all seven migration copies match the release manifest. No container was started,
Auth account created, migration applied, cloud project linked or production data
copied. This is preparation, not an available/tested target yet.

Start only this local sandbox. Suppress raw CLI output because startup/status
can display local API/JWT/service keys. Do not use a transcript or paste output.

```powershell
Set-Location C:\xampp\htdocs\SahamTeknikal\backend
$taskCli = "$env:LOCALAPPDATA\npm-cache\_npx\c34c3565ecb5471d\node_modules\@supabase\cli-windows-x64\bin\supabase.exe"
$taskSandbox = Join-Path (Get-Location) 'data/idx-smoke-local-20261002'
$taskNetwork = 'idx-smoke-loopback-20261002'
# Create a dedicated network; if the name already exists, review it first.
docker --context desktop-linux network create --driver bridge `
  --opt com.docker.network.bridge.host_binding_ipv4=127.0.0.1 $taskNetwork
if ($LASTEXITCODE -ne 0) { throw 'Network preparation failed; review before start' }
$taskOutput = & $taskCli start --workdir $taskSandbox --network-id $taskNetwork 2>&1
$taskExit = $LASTEXITCODE
Remove-Variable taskOutput
if ($taskExit -ne 0) { throw 'Disposable start failed; request sanitized diagnostics' }
'Disposable start completed; health and actual bindings still need verification'
```

Do not use `--ignore-health-check`, `--linked`, `db reset`, production DB URLs,
or production secrets. Before testing, inspect actual Docker port bindings and
health for containers belonging to this project. Require loopback-only API/DB
bindings; a successful start does not establish that. Check actual local CLI
history; start may already apply migrations. Apply only remaining local migrations
with `migration up --local --workdir $taskSandbox`, capturing/suppressing output.
Never repair local history to claim a migration that did not execute.

Then, on the fresh local target only:

- Verify007/schema/FK/RPC and zero Auth users/members/workload first.
- Set fixture mode on this sandbox only. Do not change production or shared dev.
- Create local test Auth accounts for ownerA, ownerB, outsider and disabled owner;
  explicitly grant memberships only for those disposable accounts. Local Auth
  issues their JWT on login; no manually signed JWT and no production identities.
- Test real Auth/PostgREST request replay/conflicts, HTTP412, ledger/analytics,
  CSV/cursor201 and two independent clients/connections. Compare final failed
  request counts/revisions/audit and cross-owner visibility. Financial calculations
  remain in backend RPCs. Keep QA data clearly fixture.
- Retain sanitized evidence of target, actual history, modes, HTTP codes, counts
  and independent sessions. Stop only this sandbox after tests; no destructive
  cleanup of shared projects or immutable production rows.

Local Auth/PostgREST evidence is local evidence, not production smoke. It can
exercise mutating contracts safely but cannot replace real production owner/
anon/RLS readiness. Production mutation lifecycle remains untested without
genuine owner-approved trade entries or another expressly approved isolation
strategy; do not manufacture permanent TEST trades to obtain a green gate.

## Hosted disposable alternative

If an available hosted project slot exists, the operator may create a dedicated
QA project and provide only its project ref. Do not silently upgrade, pause the
shared development project, clone production Auth/data, or reuse production keys.
Initialize the frozen schema, fixture mode and disposable users only on that
verified QA target. A hosted QA result is still not production evidence.

Sources checked for this guide:
- https://supabase.com/docs/guides/auth/social-login/auth-github
- https://supabase.com/docs/guides/auth/auth-identity-linking
- https://supabase.com/docs/guides/local-development/cli/getting-started
- Local pinned CLI `init --help`, `start --help`, `migration up --help`.
