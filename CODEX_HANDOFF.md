# Handoff Pengembangan untuk Codex

Versi: 0.2.0 • 2026-09-28

Production continuation (2026-10-02): user explicitly authorized backend
production deployment/smoke; do not request that authorization again.
`docs/PRODUCTION_READINESS.md` and IMPLEMENTATION_STATUS are current evidence.
Recovery capture/native actual restore/002–007 rehearsal/source counts passed;
latest USB copy explicitly waived, older USB verified. Production foundation
ACL reduced through guarded transaction at2026-10-02T05:16:25.481422Z; all10
clean001 fingerprints matched afterward. Production still001/history absent
until local operator runs hidden-password `deploy_production_prompt.py`.
CLI001 repair, exact dry-run002–007, application/readback and real JWT/HTTP/RLS/
concurrency remain gates. Original001/006 unchanged. GitHub Auth GET remained
disabled; no Auth changes, scheduler, frontend edits/deploy, commit or push.
Development007 remains active fixture; hosted SQL simulated-claim checks are
not real-JWT HTTP proof. See `docs/SIGNAL_ACTION_CONFLICT.md` and backup runbook.
Full-stack GO cannot precede backend production smoke and separately authorized
frontend Vercel smoke. No permanent synthetic production ledger fixtures.

## 1. Misi

Bangun IDX Night Scanner sesuai PRD/SOT/TECHNICAL_DOC. Pemilik menyetujui Supabase + GitHub + Vercel, scanner EOD KOMPAS100 memakai yfinance, empat setup MACD, Fractal Breakout, RS Breakout, Pullback Reclaim serta exit modular fixed RR/MA, serta jurnal/statistik. Paket ini berisi spesifikasi awal saja; jangan berasumsi akun, repository, migrasi, atau deployment sudah tersedia.

Read order: AGENTS.md → README.md → PRD.md → SOT.md → TECHNICAL_DOC.md → file ini. Jika repo existing berisi pekerjaan pengguna, audit read-only sebelum mengubah. Proyek ini terpisah dari KartuNamaDigital.

## 2. Prinsip eksekusi

- Kerjakan vertical slice kecil yang terbukti dahulu, kemudian perluas.
- Jangan menjadikan dashboard yang hanya berisi mock sebagai implementasi live yang selesai.
- Pekerjaan tanpa kredensial tetap dilanjutkan: scaffold, engine, fixtures, migrations, contracts, tests.
- Jelaskan kebutuhan akun/env yang benar-benar menghalangi langkah berikutnya tanpa meminta pengguna mengirim secret ke chat.
- Pertahankan scope empat setup dan dua mode exit modular MVP; default empat experiment fixed2R. Divergence/price action/AI lanjutan P1 tidak menghalangi MVP.
- Update status pekerjaan berdasarkan bukti aktual, termasuk test failures. Tidak mengarang backtest, harga, constituent list, deployment URL, atau commit SHA.
- Default rancangan di SOT boleh diimplementasikan; tampilkan dan versioning. Keputusan yang mengubah makna trading dicatat sebagai decision change, bukan perubahan tersembunyi.

## 3. Milestone 0 — Audit dan bootstrap

Tasks:

1. Periksa repo/status Git, instruksi lokal, dan file existing tanpa operasi destruktif.
2. Buat struktur monorepo TECHNICAL_DOC, scaffold Next.js/TypeScript + Python scanner.
3. Pin runtime/dependencies dan lockfiles, tambahkan lint/typecheck/test commands.
4. Buat `.env.example` placeholders, `.gitignore`, config schema, dan source attribution port fractal.
5. Buat fixture OHLCV synthetic kecil untuk edge cases dan fixture panjang deterministic untuk warm-up EMA; label di UI dev.
6. Siapkan contracts schema dan rencana migrasi; belum membutuhkan Supabase live.

Done: app lokal dapat dibuka dengan label fixture; scanner CLI dapat membaca fixture dan mengeluarkan hasil deterministic; tidak ada kredensial dalam repo.

## 4. Milestone 1 — Deterministic engine

Tasks:

- Implementasikan indikator SOT, MACD_EMA200_V1, FRACTAL_BREAKOUT_V1, RS_BREAKOUT_V1, PULLBACK_RECLAIM_V1. RS ranking memerlukan barrier cross-section lengkap.
- Implementasikan modul fixed_rr dan ma_close terpisah dari entry, config immutable, initial SL aktif, TP nullable, dan pending MA exit next open.
- Pastikan strategy engine tidak melakukan network call dan tidak mengakses AI.
- Implementasikan calendar/universe adapters, data validation, reason codes, version/config digest.
- Implementasikan lifecycle paper next-session entry dan exit EOD.
- Tulis meaningful tests di tabel berikut, termasuk referensi manual numerik, bukan hanya test yang meniru source implementation.

Done: semua test engine lulus, repeat run output identik, future-bars perturbation tidak mengubah sinyal sebelumnya.

## 5. Milestone 2 — Supabase + vertical slice live

Tasks:

1. Migrasi tabel inti, constraints, RLS, owner-only access, atomic journal RPC, audit log.
2. Buat isolated test users untuk membuktikan non-owner tidak dapat read/write data owner; jangan memasukkan user palsu ke production.
3. Implementasikan persistence adapter dan idempotent writes.
4. Konfigurasi Supabase melalui akses resmi yang disediakan. Simpan secret pada environment, bukan file committed.
5. Verifikasi source universe/calendars, lalu pilih 5–10 ticker nyata dari universe efektif untuk proof of connectivity.
6. Jalankan Python pada GitHub runner: fetch → validate → indicator → signal → database → web read.
7. Laporkan actual fetch outcomes/duration, missing symbols, dan potensi rate limit. Bila Yahoo menolak, bounded retry dan dokumentasikan; jangan mengganti sumber diam-diam.

Done: satu run live tersimpan dan dapat dilihat owner; rerun tidak menduplikasi data/sinyal; non-owner denial terbukti. Tanpa credential, status milestone blocked_config, bukan complete.

## 6. Milestone 3 — Frontend scanner dan operations

Tasks:

- Dashboard freshness/coverage/last run dan partial scan states.
- Scanner table mobile-friendly, strategy filters, detail/chart, available-at fractal.
- Reference close dan actual entry dibedakan jelas; tidak mengisi next open yang belum tersedia.
- Signal actions watchlist/planned/skipped tidak membuat actual fill.
- Operations page: run status/errors yang disanitasi, link Run workflow GitHub.
- Error/loading/empty/stale/insufficient states lengkap.

Done: owner dapat menjelaskan mengapa sinyal muncul dari snapshot yang sama dengan engine; no-data tidak terlihat sebagai no-signal; tidak ada service secret di browser bundle.

## 7. Milestone 4 — Journal dan analytics

Kelanjutan backend: baca [docs/ACTUAL_JOURNAL.md](docs/ACTUAL_JOURNAL.md) untuk
kontrak aktual migration 005, export closed cohort dan handoff SQL development.
Migration 005 sudah diterapkan ke development mode fixture, belum ke production.
Koreksi konflik revision 006 juga diterapkan di development. Laporan frontend
2026-10-01 mengonfirmasi owner-JWT HTTP412 dua-tab lulus tanpa extra note/revision.
Jangan menjalankan generator SQL hasilnya pada production; wrapper menolak mode
live. Smoke production dan frontend Vercel tetap gate. Bukti ada di status terbaru.

Persiapan production 2026-10-01: baca
[docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md) dan
[handoff frontend](docs/FRONTEND_DEPLOYMENT_HANDOFF.md). Production masih live
dengan fondasi001, tanpa migration history;002–007 belum diterapkan. Backup/
restore, Auth GitHub/HTTPS callback, rekonsiliasi001 dan smoke production masih
NO-GO. Jangan mengeksekusi repair/deploy sebelum instruksi **deploy production**.

Tasks:

- Actual draft, buy fills, finalize entry, partial sells, close, fee, stop changes, notes, corrections.
- Pisahkan paper dan actual data serta metrik.
- Tampilkan risk awal, planned RR, realized R, win rate, expectancy, PF, payoff, sample size.
- Paper ambiguous counts dan sensitivity; portfolio actual hanya menampilkan equity metrics jika cash ledger dan marks tersedia.
- Export CSV aman, filter cohort exit-date jelas, satu actual trade dengan multiple tags tidak menggandakan P&L.

Done: ledger dan stats cocok dengan contoh numerik SOT; duplikasi request fill tidak mengubah saldo dua kali; open/partial trades tidak masuk win-rate closed.

## 8. Milestone 5 — Schedule dan release pribadi

Tasks:

1. Aktifkan primary/recovery Actions, lock lease+heartbeat, retry/resume, dan manual dispatch.
2. Perluas scan ke seluruh anggota universe efektif. Terus update posisi ticker yang keluar indeks.
3. Supabase RLS, allowed origins, auth redirects, production DATA_MODE=live, billing cap dikonfigurasi dan diuji.
4. Deploy Vercel sesuai otorisasi dan akses pengguna; jangan mengaktifkan publikasi data pribadi.
5. Test partial provider failure, cron rerun, stale session, dan restore backup di dev.
6. Catat release commit/config/migration IDs, URL aktual, keterbatasan, serta procedure rollback non-destruktif.

Done: tidak ada secrets leak/duplicate fills, nightly dapat diaudit, scanner tetap berfungsi ketika AI off; backup restore terbukti. Schedule free tier tetap best effort, bukan SLA.

## 9. Test matrix wajib

| ID | Uji | Ekspektasi |
| --- | --- | --- |
| T01 | EMA/MACD sequence sederhana dihitung manual | Nilai sesuai definisi SOT, seed/warm-up eksplisit |
| T02 | Histogram sudah positif dua hari | Tidak menghasilkan crossover baru |
| T03 | MACD bullish tetapi close di bawah EMA200 | Tidak lolos MACD strategy |
| T04 | Pivot low membutuhkan dua right bars | Tidak tersedia sebelum close j+2 |
| T05 | Fractal highs [100,102,110,108,109] | Ceiling110 tersedia pada t5, bukan t2 |
| T06 | High/low ties pada fractal | >=/<= dipertahankan; null sampai pivot tersedia |
| T07 | Ceiling turun melewati harga | Tidak membuat false breakout jika prev close sudah di atas F baru |
| T08 | Wick-only breakout | No signal close-confirmed |
| T09 | Append/ubah future bars | Signal historis tidak berubah pada fixed input prefix |
| T10 | Signal Jumat, Senin libur fixture | Entry sesi kalender berikutnya, bukan hari kalender berikutnya |
| T11 | Next open <= SL / no floor / missing bar | Skip/hold reason sesuai SOT, bukan fill fiktif |
| T12 | Gap through SL dan gap above TP | Open fill loss vs TP conservative sesuai urutan SOT |
| T13 | SL dan TP tersentuh satu candle | Ambiguous flag, SL-first baseline, alternate tersimpan |
| T14 | Satu request scan/fill dikirim dua kali | Tidak double signal/trade/quantity |
| T15 | Partial provider failure | Run partial, denominator coverage benar |
| T16 | Provider revisi data/corporate action | Snapshot lama tidak ditulis ulang; reconciliation hold |
| T17 | Actual multiple entry fills + partial exits | Weighted basis/P&L/initial risk sesuai contoh SOT |
| T18 | SL diubah setelah entry | Initial risk dan historical realized R tetap |
| T19 | No trades/no losses/breakeven | null/undefined semantics dan denominator benar |
| T20 | Non-owner JWT, anon, spoofed trade ID | Akses ditolak di API dan DB |
| T21 | Late data/backfill setelah sesi entry mulai | Tidak masuk forward cohort dengan timestamp palsu |
| T22 | Dua strategy tags satu actual trade | Portfolio P&L dihitung sekali |
| T23 | AI timeout/invalid JSON/fabricated number | Core run sukses; komentar ditolak/fallback |
| T24 | Backup → restore dev | Ledger sample dan constraints/RLS terverifikasi |
| T25 | RS ranking tie, partial batch, insufficient history | Tie ticker ascending, coverage jelas; incomplete menahan RS, bukan rank batch |
| T26 | Breakout prior20 dan stop lima bar | Current high dikecualikan threshold; signal bar termasuk low/ATR stop |
| T27 | Pullback tiga sesi dan strict reclaim | Semua close prior3 > EMA50, satu <EMA20; prev<=EMA20, current>EMA20 dan prev high |
| T28 | Wilder ATR/SMA seed manual | ATR bukan rolling SMA TR; indeks dan data availability tepat |
| T29 | Fixed1.5 vs2 config dan switch settings | Target tepat; trade lama immutable; signal/fractal guard tidak reset |
| T30 | MA wick, equality, already below pada entry close | Wick/equality no exit; below menghasilkan pending next open |
| T31 | MA pending dan stop gap bersamaan | Satu fill open dengan stop gap reason; MA price bukan fill |
| T32 | MA no TP dan late exit discovery | planned_RR null; initial risk tetap; late tidak dianggap actionable forward |
| T33 | Exit eksperimen menyebabkan entry sample berbeda | Skip/holding/open dan common signal IDs ditampilkan; actual tidak double-count |

Gunakan pytest untuk engine, test runner TypeScript yang dipilih untuk web/API, dan integration SQL/RLS tests. Playwright smoke test hanya alur kritis login/scanner/journal; jangan menghabiskan waktu membuat tes kosmetik yang meniru implementasi.

## 10. Pengaturan live yang perlu diisi

| Item | Status awal | Tindakan |
| --- | --- | --- |
| GitHub repo URL/default branch | Belum tersedia | Buat/pilih repo privat melalui akun pengguna |
| Supabase project URL/key | Belum tersedia | Set env/Secrets dan migrasi setelah akses tersedia |
| Owner UUID | Belum tersedia | Buat akun, isi app_members secara terkontrol |
| Vercel project/domain | Belum tersedia | Link repo, root apps/web, env dan redirect |
| Constituents/calendar resmi | Belum diunduh untuk live | Verifikasi IDX, simpan provenance dan effective dates |
| Actual fee/modal | Belum dikonfirmasi | UI settings; paper default gross berlabel sampai diisi |
| AI provider/model/key | Opsional | Jangan menjadi blocker MVP |

## 11. Pelaporan per milestone

Laporkan: apa yang selesai; file utama yang berubah; command dan hasil test aktual; data_mode; bukti live bila ada; masalah tersisa; keputusan yang berubah; langkah berikutnya.

Tambahkan `IMPLEMENTATION_STATUS.md` ketika pengembangan dimulai dengan checklist milestone, tanggal, commit, migration, tests, dan blocker. Jangan menandai milestone selesai berdasarkan scaffold atau screenshot saja.

## 12. Prompt kelanjutan setelah MVP

> Audit hasil forward test keempat setup per exit policy/experiment berdasarkan versi/config yang sama. Implementasikan satu varian filter pada satu waktu tanpa menimpa baseline. Laporkan sample size, expectancy setelah biaya, ambiguity, dan perubahan coverage. Tambahkan AI commentary hanya setelah data, rule, dan statistik deterministik lulus pengujian.
