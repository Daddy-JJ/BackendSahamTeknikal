# Backend-to-frontend handoff

Updated 2026-10-15 from recorded release evidence, not a fresh production check.
Backend chart capability is released through migration 016; frontend Production is recorded deployed.
See [current status](../IMPLEMENTATION_STATUS.md) for exact SHAs, deployment and remaining limits.
Historical preparation/NO-GO prompts remain in [handoff history](archive/FRONTEND_DEPLOYMENT_HANDOFF_BEFORE_DOC_CLEANUP_20261015.md);
they do not instruct a new agent to repeat migrations, turn off scheduling or recreate completed work.

## Current task

Scanner detail relayout stages 1-4 is frontend-only. Use the frontend active plan and existing
canonical contracts. No backend/schema/provider/financial-rule change is needed for layout.

## Integration boundaries

- Frontend repository root is the Vercel build root, not `apps/web`.
- Production public alias: `https://sahamteknikal.vercel.app`.
- Frontend environment: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`,
  `DATA_MODE=live`, `ALLOW_FIXTURE_PREVIEW=false` or unset. Preview uses its explicitly labelled
  development/fixture scope. Public URL/key must belong to the intended project.
- Privileged service, database, provider, OAuth and watchdog tokens stay backend/cloud-side;
  never expose them through `NEXT_PUBLIC`, browser bundles, logs or chat.
- Scanner service adapter uses `SUPABASE_SECRET_KEY`; `APP_OWNER_USER_ID` identifies the existing
  enabled owner. Do not auto-promote a new login. Local operator env files are not cloud runtime env.
- App callback is `/auth/callback` on the allowed application origin; provider callback belongs
  to Supabase Auth. Derive callback from the actual origin, keep dev/prod redirects separate.
  Do not change Auth settings merely because a dated archived prompt requested setup.

## Preserve consumer contracts

- Read selected scanner run/items/signal membership together; preserve run query/filter/page/detail
  URL semantics. An old publication is not fresh-provider health; held coverage remains explicit.
- Financial calculations, indicators and official statistics stay canonical backend outputs.
- Actual journal: `apply_actual_journal(text,uuid,jsonb,uuid)`, expected revision in payload,
  persistent UUID idempotency for identical retry; stale revision is PT412/HTTP412.
- Correction embedding remains `actual_fill_corrections!actual_fill_corrections_fill_id_fkey`,
  sequence descending and latest correction limit 1.
- Actual export keeps `actual-journal-export-v1`, closed status, `p_exit_snapshot`, limit 200 and
  identical filters while following `next_after` as `p_after` until `has_more=false`.
  Keep writes quiet for this legacy no-snapshot-token export; do not invent another CSV contract.
- New reporting/chart contracts live in [contracts](../contracts/); use matching versions/checksums
  from each independent repo. Strict parsing must expose failures rather than return empty fixtures.

## Release verification

For a new authorized release, use [readiness](PRODUCTION_READINESS.md). Deploy backend capability
first only when needed, then the compatible frontend; verify exact SHA and public alias separately
from authenticated owner browser, genuine outsider JWT and immutable-to-alias asset-byte comparison.
Test login/navigation/refresh/back, filters, journal/reporting/export, accessibility/mobile and
error states appropriate to the change. Do not create QA financial trades in production or claim
local/SQL tests as authenticated hosted proof. Owner-browser and real outsider JWT remain unverified
at the current chart evidence cutoff; full backup/populated restore were release-specific waived.
