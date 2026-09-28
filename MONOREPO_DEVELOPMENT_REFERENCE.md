# Development lokal — IDX Night Scanner

Panduan implementasi saat ini. README.md dan lima dokumen awal tetap dipertahankan.
Perubahan keputusan terbaru: [DEVELOPMENT_ADDENDUM.md](DEVELOPMENT_ADDENDUM.md).
Bukti dan blocker: [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).

## Mulai di PowerShell

```powershell
cd C:\xampp\htdocs\SahamTeknikal
npm.cmd --prefix frontend run dev
```

Buka **http://localhost:3050**. Hentikan dengan Ctrl+C. Tidak perlu Apache atau
MySQL untuk frontend ini. Port 3050 dikunci pada script dev/start.

Jika belum terpasang:

```powershell
cd C:\xampp\htdocs\SahamTeknikal\frontend
npm.cmd ci
cd ..\backend\scanner
uv sync --locked
```

Runtime terkunci: Node 22.23.2, npm 12.0.2, Python 3.12.14.
Gunakan virtual environment, bukan alias Python Windows Store.

## Engine, fixture, dan tes

```powershell
cd C:\xampp\htdocs\SahamTeknikal\backend\scanner
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m idx_scanner.cli demo --output ../../frontend/src/generated/demo.json
```

CLI memutar ulang 60 sesi setelah warm-up 600 bar. Semua harga/kalender/universe
sintetis. Candle stress menguji gap besar; bukan kejadian pasar. Snapshot UI berasal
dari engine Python yang sama dengan pipeline provider. Tidak ada kalkulasi sinyal
atau metrik resmi di frontend.

```powershell
cd C:\xampp\htdocs\SahamTeknikal\frontend
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
```

Smoke test memakai Microsoft Edge lokal dan viewport desktop/mobile/tablet.
Build default menampilkan mode live belum dikonfigurasi, bukan fallback fixture.
Untuk preview build development: DATA_MODE=fixture dan ALLOW_FIXTURE_PREVIEW=true.
Jangan aktifkan flag preview pada production live.

## Apa yang dapat dicoba

Dashboard, candlestick sintetis, filter strategi/ticker, command menu Ctrl+K/Cmd+K,
detail alasan sinyal, watchlist sementara, paper journal, statistik fixture,
dan pratinjau status complete/partial/stale/missing/loading/error.

Jurnal actual tetap kosong. Watchlist hanya state sesi browser dan tidak membuat
actual fill. Tidak ada login owner, database, deployment, atau nightly job live.
Frontend source ada di frontend/; engine dan source Supabase di backend/.
GitHub disiapkan pemilik ketika ready to deploy.

Lihat [backend/README.md](backend/README.md) untuk batas provider dan engine.

## Database tests lokal

```powershell
cd C:\xampp\htdocs\SahamTeknikal\backend\supabase
npm.cmd ci
npm.cmd test
```

Tes memakai PostgreSQL PGlite dalam memori dengan auth simulasi. Tidak perlu Docker
untuk tes ini dan tidak menyentuh Supabase remote. Migration + owner-only RLS +
atomic scan RPC tersedia; jurnal actual dan live integration belum selesai.
Lihat [backend/supabase/README.md](backend/supabase/README.md).

Yahoo sudah berhasil fetch satu ticker lokal, dengan missing/partial rows tetap
dicatat. Detail dan batas bukti ada di [probe lokal](docs/LOCAL_PROVIDER_PROBE.md).
UI tetap fixture. EODHD menunggu token pada environment backend.
