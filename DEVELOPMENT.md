# Backend local development

Backend repository meliputi scanner Python, provider yfinance/EODHD, schema kontrak, migrasi Supabase, serta tes database. Runtime hanya hidup sesuai scheduler/runner yang kelak diatur; migration tidak otomatis mendeploy scanner.

## Python engine

Di Windows PowerShell:

```powershell
cd scanner
uv sync --locked
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m idx_scanner.cli demo --output ..\contracts\demo-snapshot.fixture.json
```

Gunakan Python 3.12.14. fixtures/, kalender fixture-*, dan snapshot demo adalah data sintetis. Jangan mengubah fixture menjadi fallback saat provider gagal.

## Supabase migration/RLS lokal

Pastikan venv Python sudah terpasang karena test membuat snapshot synthetic melalui engine. Node.js 22.23.2 dan npm 12.0.2 diperlukan untuk test PGlite.

```powershell
cd supabase
npm.cmd ci
npm.cmd test
```

PGlite adalah PostgreSQL sementara di memori. Simulasi role/JWT menguji SQL migration dan kontrol akses secara lokal; hasilnya bukan koneksi Supabase live. Jangan menjalankan migration ke project pengguna tanpa memastikan URL project development secara eksplisit.

## Environment

Salin .env.example menjadi .env lokal bila memakai adapter/provider. Isi secret di environment lokal atau secret store tepercaya saja. Jangan commit file .env. SUPABASE_SECRET_KEY hanya backend/runner; EODHD key juga backend saja. Supabase URL dan frontend publishable key berada di repository frontend.

Probe provider tidak menerbitkan sinyal. EODHD meminta EODHD_API_TOKEN. Mapping ticker wajib Anda verifikasi. Action corporate yang belum direkonsiliasi menahan sinyal.

## Batas implementasi saat ini

Empat entry rules, indikator, exit paper, provider adapter, Supabase scan RPC dan snapshot/reload adapter tersedia secara lokal. Owner Auth/RLS sudah dibuktikan di development. Penyimpanan dan rekonstruksi revisi market tersedia secara lokal; migrasi 002-003 dan smoke test revisi sudah berhasil di Supabase development. Scheduler scan live, kalender/universe resmi, paper persistence, actual ledger, dan integrasi live masih dalam pengembangan. Lihat IMPLEMENTATION_STATUS.md dan docs/LOCAL_PROVIDER_PROBE.md untuk bukti terkini.

Panduan migrasi revisi development dan smoke test: docs/MARKET_REVISIONS.md.
