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
