# Supabase development — M2 local foundation

Migration: `migrations/202609290001_scan_foundation.sql`.
Belum diterapkan ke Supabase remote. Tidak ada akun owner atau market fixture
yang disisipkan migration. Mode database default **live**, fixture ditolak.

## Yang tersedia

- Membership owner, deployment mode, immutable scan runs/items/signals, run-to-signal links.
- Immutable engine snapshot, unique signal identity dan fractal guard lintas run.
- RPC publish_scan atomik: run + items + signals + audit dalam satu transaksi.
- RPC set_signal_action: watchlist/planned/skipped/none; tidak membuat fill.
- Owner JWT wajib untuk aksi; idempotency request + optimistic revision.
- RLS semua tabel; anon tidak punya grant, non-member tidak melihat market data,
  enabled owner boleh read, aksi pribadi hanya pemiliknya.
- Browser maupun service_role tidak memiliki direct DML pada tabel aplikasi.
  RPC publisher hanya service_role; fungsi SECURITY DEFINER memakai search_path kosong.
- Python SupabaseScanStore memakai REST RPC, bounded retry dan keyset pagination.
  Load state sampai target_session sebelum scan/replay; jangan memakai guard dari sesi masa depan.

## Tes lokal tanpa Docker atau cloud

PGlite dipakai hanya untuk test PostgreSQL, bukan database aplikasi atau pengganti Supabase.
Auth schema/uid/roles pada test disimulasikan. Database sementara berada di memori,
tidak mengubah instance PostgreSQL/Supabase pengguna.

Pastikan venv scanner terpasang lebih dahulu (lihat DEVELOPMENT.md).

```powershell
cd C:\xampp\htdocs\SahamTeknikal\backend\supabase
npm.cmd ci
npm.cmd test
```

Test mengeksekusi migration SQL asli dan payload fixture dari engine Python.
Mengukur denial anon/non-owner, owner read-only, isolation antar owner,
duplicate request, stale revision, rollback, immutable revision dan fractal guard.
PGlite hanya satu koneksi; uji race antar koneksi dan JWT/PostgREST tetap gate Supabase dev.

## Urutan yang masih harus dikerjakan

1. Metadata universe/calendar/instrument mapping resmi, revisioned OHLCV/actions,
   references ke revisi input dan policy rekonsiliasi corporate actions.
2. Immutable experiment/paper configuration, persistent paper trades/events.
3. Actual ledger/RPC: fills, finalize entry, corrections, stop events dan analytics.
4. Owner login frontend, read model live dan integrasi aksi RPC.
5. Apply pada Supabase development, tes owner/non-owner JWT, concurrent rerun,
   backup/restore dan runner GitHub ketika repository sudah disiapkan pengguna.

Snapshot di migration pertama menyimpan fitur/input digest, belum seluruh referensi
revisi bar yang diperlukan audit end-to-end. Jangan gunakan sebagai rilis live selesai.
Jangan mengubah deployment_settings ke fixture pada project production.
Tidak ada workflow, migration remote atau deployment yang diaktifkan.

Referensi implementasi:
- [Supabase RLS dan grants](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Supabase fungsi, search_path, dan execute grants](https://supabase.com/docs/guides/database/functions)
- [PGlite test runtime](https://pglite.dev/docs/)

## Production boundary and migration history

The owner applied migration `202609290001_scan_foundation.sql` through the SQL
Editor on project `hcjfxbynqzsaidlwvdfx`, branch `main (PROD)`, on 2026-09-29.
Read-only REST checks confirmed all nine tables, enabled owner membership,
`data_mode=live`, and denied anonymous table reads. Authenticated owner/non-owner
RLS and write-path behavior are **not yet verified remotely**. Do not rerun the
setup SQL or write fixture/test scans to this production project.

SQL Editor does not update Supabase CLI migration history. Before a future
`supabase db push` against production, inspect the applied schema/policies and
reconcile migration version `202609290001` using the official `migration repair`
workflow. Do not mark it applied on an unverified project.

## Isolated development project setup

The new development project has ref `vgmkpsestahkfahzdtae`. The ignored
`backend/.env.development` contains its URL and empty key/owner fields. Create
your own Auth user in that project and put **that project's UID** in
`APP_OWNER_USER_ID`; production's Auth UID is not copied across projects. The
SQL generator reads only the dev env and rejects the known production ref. It
does not need the development secret key.

```powershell
cd C:\xampp\htdocs\SahamTeknikal\backend
.\scanner\.venv\Scripts\python.exe supabase\scripts\prepare_dev_setup.py --project-ref vgmkpsestahkfahzdtae
```

Open the generated, Git-ignored
`backend/data/dev-supabase-setup-vgmkpsestahkfahzdtae.sql`. Confirm its project
ref, paste its entire contents into **the development project's** SQL Editor,
and run once. The transaction creates nine application tables and registers
the existing dev Auth user as owner. Its final SELECT should return
`owner_ready=true` and `data_mode=live`. Do not run it against production.
Afterward, put the development secret key in the ignored dev env file for
read/write integration checks; never put a key in a browser or Git.

### Development fixture RPC smoke

After verifying the development project only, set its
`public.deployment_settings.data_mode` to `fixture` in its SQL Editor. This
never applies to production. The script checks the exact development URL and
mode, defaults to a read-only dry run, and uses namespace `dev_smoke_m2`.

```powershell
cd C:\xampp\htdocs\SahamTeknikal\backend
.\scanner\.venv\Scripts\python.exe supabase\scripts\smoke_dev_fixture.py
.\scanner\.venv\Scripts\python.exe supabase\scripts\smoke_dev_fixture.py --execute
```

Verified on 2026-09-29: one labeled fixture run, five items, two signals and
one audit event; exact replay did not duplicate the run, persisted signals
reloaded, and a changed payload with the same run digest was rejected. The
fixture run is immutable and stays in the isolated development project.
Production remained live and had no dev_smoke_m2 run. The owner read path was
subsequently verified through the development app login. The owner action
RPC was also verified on the fixture as described below.

### Disposable non-owner RLS test

The development-only script creates a random `@example.invalid` Auth user
without sending email, signs it in, checks private reads and action denial,
then deletes it in a `finally` block. If cleanup is interrupted, the ignored
`backend/data/dev-rls-temp-user.json` marker prevents a duplicate test user
and identifies the user for manual recovery.

```powershell
cd C:\xampp\htdocs\SahamTeknikal\backend
.\scanner\.venv\Scripts\python.exe supabase\scripts\verify_dev_non_owner_rls.py --execute
```

Verified on 2026-09-29: real non-owner JWT saw no scan_runs, signals or
app_members rows; `set_signal_action` returned 42501, left no action residue,
and the temporary Auth user was deleted. Owner read access was later verified
through the app.

### Owner JWT/RLS read probe

The owner can run a read-only probe locally. By default it prompts for the
development project's Auth account email/password. With --access-token it
prompts for an existing Supabase Auth user access JWT for this same development
project. The token is checked against /auth/v1/user and the configured owner
UID before RLS reads. It cannot be a Supabase Dashboard Personal Access Token,
GitHub token, publishable key or secret key. Credentials remain in memory and
are not printed. Do not paste tokens or passwords into chat or shell arguments.
Dashboard GitHub login does not itself create a session for the app's Auth user.

```powershell
cd C:\xampp\htdocs\SahamTeknikal\backend
.\scanner\.venv\Scripts\python.exe supabase\scripts\verify_dev_owner_rls.py --check-config
.\scanner\.venv\Scripts\python.exe supabase\scripts\verify_dev_owner_rls.py --access-token
```

Use the command without --access-token for email/password login. A successful
run should report the owner membership, one `dev_smoke_m2`
fixture run and two signals visible through the publishable key plus the
owner's Auth JWT. This standalone probe remains optional: the app's GitHub
OAuth flow has now shown the same owner read path on localhost:3050/auth/check.
The user supplied a screenshot with the matching UID and one run/two signals;
read-only service queries independently matched those development counts.
The owner clicked the development-only fixture action button in the app.
The same request was replayed, and a separate read-only database check found
one watchlist action at revision 1, one idempotency request, one matching
audit event, and two unchanged fixture signals. No production write occurred.

### Market-series revision migration (local only)

Migration 202609290002_market_series_revisions.sql adds immutable,
owner-readable fetch receipts and changed-bar rows. The service-role-only
ingest_market_series RPC receives a normalized series. An exact replay
returns the same receipt ID; a changed bar with a new input digest creates
one new bar revision. A new fetch with unchanged bars adds no bar rows.
Duplicate session dates and digest reuse with changed content are rejected
transactionally. Receipt metadata retains provider actions and quality
issues, while provider_version is part of receipt identity; bar_cutoff records the revision high-water mark. Published signal
snapshots are never rewritten.

This migration passed local PGlite tests but has **not** been applied to
either remote project. Apply it to the isolated development project first,
then verify owner RLS and RPC behavior there before production rollout.
The local run_once orchestrator calls ingest_series for every fetched series
before publish; it is not connected to a CLI or GitHub runner yet. Zero-bar
provider results create a receipt without bar rows, preserving missing-data
status. Full-series reconstruction and production storage sizing remain to be
validated. The database trusts the service role for the supplied Python
input digest; its own snapshot_hash detects conflicting RPC replay but is
not a server-side recomputation of the engine digest. Service-role keys
remain in backend environment only, never browser code or Git.
