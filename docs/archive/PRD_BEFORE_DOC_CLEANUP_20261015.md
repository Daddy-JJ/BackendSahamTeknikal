# Product Requirements Document — IDX Night Scanner

## Approved journal/dashboard update ? 2026-10-08

The current paper model is `close-signal-risk-v1`: create a persistent next-session plan as soon as a valid forward signal is published, with fill price fixed at the signal close. Freeze initial SL, configuration and quantity at planning. Risk is capped at Rp1,000,000 including buy 0.15% and estimated SL-sale 0.25% fees, rounded per fill to Rp0.01 HALF_UP; lot sizing rounds down. Fixed 2R and confirmed-close SMA10 are independent experiments. Historical next-open cohorts are preserved separately.

`/analytics` presents Paper, Aktual and Evaluasi Sinyal with summary ? monetary closed-P&L curve ? strategy/method matrix ? source details. Paper defaults to Fixed 2R and offers SMA10 separately. Closed net win rate includes its denominator, expectancy is IDR, drawdown starts from zero IDR, and R uses immutable initial price risk. Actual reporting reads the existing ledger and recorded actual fees. `/journal?tab=paper` shows pending/open/closed/skipped/expired/data hold/ambiguous states and links to `/journal/paper/[id]` audit details.

Journal filters select exit periods for closed cohorts; unresolved positions are separately labelled, without pretending they exited inside that period. Research filters select signal dates. Its four columns are 1R before SL, 2R before SL, net-positive without SL through five sessions, and through ten sessions. Each cell exposes assessed/wins, waiting, ambiguity, held data and reasoned exclusions; zero assessed rates are null. These checkpoints never auto-close a trade. Evaluation continues independently of both paper exit policies and includes valid signals whose paper plan was skipped.

All new views display data time/coverage, loading, empty, backend-not-ready and error states. RPC failure cannot become an empty-success result or fixture data. Only matrix tables use horizontal scrolling on narrow screens. Statistics drill down to their actual contributing trades/signals. Local acceptance uses synthetic fixtures explicitly; hosted authentication, RLS and rollout remain separately verified gates.

Versi: 0.2.0 • 2026-09-28 • Status: initial implementation baseline

## 1. Masalah dan tujuan

Pemilik membutuhkan shortlist saham berdasarkan aturan teknikal yang bisa diaudit, tanpa memeriksa seluruh chart secara manual setiap malam. Daftar sinyal perlu terhubung dengan pencatatan hasil supaya kualitas strategi dan disiplin eksekusi dapat diukur secara terpisah.

Produk harus menjawab:

1. Saham anggota KOMPAS100 mana yang memenuhi aturan hari ini?
2. Mengapa sinyal muncul, level mana yang digunakan, dan data tanggal berapa?
3. Bagaimana hasil semua sinyal yang disimulasikan secara konsisten?
4. Bagaimana hasil transaksi aktual yang dipilih pengguna?
5. Apakah filter/versi strategi baru meningkatkan expectancy setelah biaya?

## 2. Pengguna dan positioning

- Satu pemilik pada MVP, aplikasi privat berbahasa Indonesia dengan istilah trading umum.
- Penggunaan pribadi, conservative swing, long-only, EOD daily.
- Scanner adalah alat penelitian dan jurnal; tidak mengeksekusi transaksi broker.
- Skor setup, jika ditambahkan kemudian, bukan probabilitas menang.
- Data broker/foreign flow, orderbook, absorption, dan OFI tidak tersedia dari OHLCV dan tidak boleh diklaim oleh produk ini.

## 3. Stack dan batas produk

| Komponen | Pilihan |
| --- | --- |
| Webapp | Next.js + TypeScript, hosting Vercel Hobby |
| Database/API/Auth | Supabase PostgreSQL + Data API + Auth |
| Batch scanner | Python + yfinance, GitHub Actions pada repo privat |
| Data market | EOD Yahoo Finance melalui yfinance |
| Universe | KOMPAS100 dari publikasi resmi BEI, disimpan per periode berlaku |
| AI | Gemini atau provider adapter lain; default nonaktif |

Supabase/GitHub/Vercel merupakan pilihan yang telah disepakati pengguna. Framework, auth flow, waktu cron, dan parameter operasional adalah default rancangan; lihat SOT bagian keputusan.

## 4. Scope rilis

### P0 — MVP wajib

- Login khusus pemilik dan proteksi semua data finansial pribadi.
- Universe KOMPAS100 berversi, import CSV tervalidasi dengan sumber dan tanggal efektif.
- Kalender hari bursa; jangan hanya menyaring Sabtu/Minggu.
- Initial load histori dan pembaruan EOD incremental dengan validasi data.
- Empat setup berbeda: MACD Crossover + EMA200, Fractal Breakout Base, Relative Strength Breakout, Trend Pullback Reclaim.
- Exit modular fixed_rr (default2, contoh1.5) atau ma_close (SMA default/EMA opsi; periode5/10/20); initial SL tetap di semua mode. Tidak ada time exit.
- Empat baseline fixed2R aktif; alternatif exit sebagai experiment terpisah yang dipilih pengguna, tidak mengubah trade lama.
- Scan harian, status lengkap/parsial/gagal, rerun manual, pencegahan duplikasi.
- Chart candlestick, volume, EMA20/50/200, MACD, MA exit pilihan, ceiling/floor, dan penanda kapan level tersedia.
- Detail sinyal, rencana next-session entry, SL, TP indikatif, dan jarak risiko.
- Paper forward test otomatis berbasis EOD, termasuk kasus SL/TP satu candle yang ambigu.
- Jurnal aktual manual, multiple fills/partial exits, fee, perubahan SL, catatan, tag setup.
- Statistik per strategi, versi, periode, dan mode; paper dan aktual tidak dicampur.
- Export CSV jurnal/statistik dan backup yang dapat dipulihkan.
- Riwayat input/aturan sinyal yang dapat diaudit; data live dibedakan dari fixture.

### P1 — Setelah baseline stabil

- AI commentary dengan evidence IDs dan validasi output.
- Divergence, double bottom, CHoCH/BOS setelah definisi formal disetujui.
- Filter eksperimen MACD/EMA/volume untuk fractal sebagai versi terpisah.
- Backtest historis, dengan label universe historis atau current-constituent bias.
- Import transaksi broker setelah format contoh disediakan.
- Simulasi portfolio dengan modal terbatas, ranking kandidat, dan batas risiko agregat.

### Di luar scope awal

- Auto-buy/sell broker, market order otomatis, short selling, leverage.
- Real-time feed atau notifikasi SL intraday yang dijamin.
- Semua saham IHSG, sistem berlangganan publik, pembayaran/multi-tenant komersial.
- Reimplementasi proyek KartuNamaDigital, hosting melalui Sites, atau migrasi repository lain.

## 5. Alur pengguna

### A. Review malam

1. Login dan lihat tanggal sesi, waktu scan terakhir, universe efektif, dan kelengkapan data.
2. Buka daftar sinyal; filter berdasarkan strategi dan tanggal.
3. Buka chart dan panel alasan: kondisi yang lulus, level, tanggal konfirmasi, serta source timestamp.
4. Tandai Watchlist / Planned / Skipped dengan alasan opsional.
5. Rencana malam memakai close sebagai referensi, bukan harga fill besok.

### B. Transaksi aktual

1. Dari sinyal, buat draft trade; belum masuk statistik transaksi closed.
2. Isi pembelian aktual: tanggal/waktu, harga, jumlah saham, fee, initial SL.
3. Isi penjualan/partial exit dan alasan; ukuran awal serta risiko awal tetap terlacak.
4. Setelah semua saham terjual, trade menjadi closed dan masuk metrik win rate.
5. Koreksi data melalui revisi/audit; jangan menimpa riwayat tanpa jejak.

### C. Evaluasi strategi

1. Pilih paper atau actual, entry strategy version, exit policy/parameters, experiment, dan periode.
2. Lihat jumlah signal, executed/skipped/pending/ambiguous, closed/open, win rate, payoff, expectancy, PF.
3. Buka trades pembentuk statistik dan baca asumsi fee/fill.
4. Bandingkan versi pada periode/universe/biaya yang sama.

## 6. Halaman dan informasi wajib

| Halaman | Konten |
| --- | --- |
| Dashboard | Last successful scan, data coverage, jumlah signal, posisi aktual, ringkasan statistik |
| Scanner | Ticker, strategi/versi, tanggal sinyal, close referensi, level pemicu, SL kandidat, freshness |
| Signal detail | Chart, rule checklist, available-at, input snapshot, planned versus actual |
| Paper journal | Lifecycle, simulasi entry/exit, biaya, realized R, ambiguity flag |
| Actual journal | Fills, initial SL/risk, notes, tags, review, P&L |
| Analytics | Closed-trade metrics, sample size, open positions, comparison, definisi perhitungan |
| Settings/Operations | Universe, kalender, biaya, risk, scan runs, export, AI toggle |

Desain mobile-first. Status warna selalu disertai teks. Angka IDR memakai format Indonesia. Tanggal sesi memakai Asia/Jakarta; timestamp audit disimpan UTC. P/L negatif tidak boleh hanya disampaikan melalui warna.

## 7. Perilaku penting

- No signal berbeda dengan data missing/stale/insufficient.
- Partial scan menampilkan denominator anggota universe dan ticker gagal; tidak dipublikasikan sebagai full coverage.
- Data synthetic/fixture hanya untuk dev/test, berlabel jelas dan tidak masuk statistik live.
- Hanya candle yang sudah selesai digunakan untuk sinyal.
- AI gagal tidak menggagalkan scanning/journal/statistik.
- Satu actual trade dapat memiliki beberapa tag strategi tanpa menggandakan portfolio P&L.
- Paper MVP adalah trade-level forward test; bukan simulasi kemampuan membeli seluruh sinyal sekaligus.
- Sinyal historis yang berubah akibat revisi provider diberi versi; jangan menghapus hasil lama.

## 8. Acceptance criteria

| ID | Kriteria |
| --- | --- |
| AC-01 | Tanpa login atau bukan owner, data pribadi dan endpoint write tidak dapat diakses |
| AC-02 | Dari fixture yang sama dan config sama, sinyal serta statistik selalu sama |
| AC-03 | MACD bullish crossover dievaluasi setelah close; entry paper paling cepat sesi berikutnya |
| AC-04 | Fractal menggunakan indeks asli t-3 dan level available-at t; offset visual tidak menjadi input |
| AC-05 | Satu scan diulang tidak menggandakan signal/trade/fill |
| AC-06 | Ticker stale/missing tidak dianggap gagal rule dan tidak membuka paper trade baru |
| AC-07 | Win rate memakai closed trades net fee, breakeven terpisah, open trades tidak dihitung sebagai loss |
| AC-08 | SL/TP tercapai pada satu daily candle ditandai ambiguous dan asumsi hasil ditampilkan |
| AC-09 | Initial risk tersimpan immutable; perubahan SL tidak mengubah denominator realized R |
| AC-10 | Corporate action/revisi harga tidak mengubah nominal actual fill tanpa tindakan audit |
| AC-11 | Secret scanner/provider tidak ada di bundle browser atau repository |
| AC-12 | Owner dapat mengidentifikasi last successful run, failed symbols, dan menjalankan retry dengan aman |
| AC-13 | Universe dan kalender live memiliki sumber/tanggal; fixture bukan fallback tersembunyi |
| AC-14 | Vertical slice live 5–10 ticker berhasil pada GitHub runner sebelum rollout universe penuh |
| AC-15 | Export jurnal dan restore backup telah diuji pada database dev terpisah |
| AC-16 | RS ranking top20% return60, prior20 high, dan pullback reclaim sesuai SOT; cross-section parsial menahan RS |
| AC-17 | Mengubah exit menghasilkan konfigurasi baru; signal tidak diduplikasi dan trade/plan lama tetap memakai snapshot |
| AC-18 | MA close breakdown mengisi next open, bukan harga MA; wick/equality tidak memicu, initial SL tetap aktif |
| AC-19 | TP/planned RR ma_close null; semua statistik dipisah per exit config dan melaporkan perbedaan entry sample |

## 9. Ukuran keberhasilan produk

Keberhasilan teknis dinilai dari reproducibility, coverage transparan, tidak ada duplicate fill, akses data terlindungi, dan journal akurat. Profit strategi bukan acceptance gate perangkat lunak.

Tampilkan observasi operasional: durasi job, data coverage, kegagalan per ticker, database size, Actions minutes, egress, dan pemakaian AI. Jangan menjanjikan SLA atau waktu tepat pada free tier.

## 10. Dependensi yang belum tersedia

- Akun/project Supabase, GitHub repo, dan Vercel project belum ditetapkan dalam paket ini.
- Latest KOMPAS100 constituents dan kalender BEI harus diperoleh dari sumber resmi.
- Fee broker/modal/risk aktual belum dikonfirmasi; actual metrics tidak boleh memakai fee fiktif.
- Validasi akses Yahoo dari cloud runner belum dilakukan.
- Nama produk/domain final dan provider/model AI belum dipilih.

Ketiadaan kredensial tidak menghambat pembuatan kode, migrasi, fixture, dan test lokal. Jangan meminta secret dalam chat.
