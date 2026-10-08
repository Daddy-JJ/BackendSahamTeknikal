# Source of Truth — IDX Night Scanner

Versi dokumen: 0.3.0 • 2026-10-08 • Bahasa produk: Indonesia

Dokumen ini menentukan perilaku yang akan dikodekan. Status ACCEPTED hanya untuk keputusan eksplisit pengguna; DEFAULT adalah default rancangan yang boleh diimplementasikan dan harus terlihat dalam konfigurasi. Perubahan default yang memengaruhi hasil trading wajib menaikkan versi, tidak berlaku retroaktif.

## 1. Register keputusan

| ID | Keputusan | Status |
| --- | --- | --- |
| D-01 | Supabase + GitHub + Vercel; sasaran memakai free tier | ACCEPTED |
| D-02 | Yahoo Finance melalui yfinance, EOD, scan malam | ACCEPTED |
| D-03 | Universe KOMPAS100, tidak seluruh saham IHSG | ACCEPTED |
| D-04 | Strategi MACD dari video dan Fractal Breakout dari script pengguna | ACCEPTED |
| D-05 | Journal, win rate, serta reward/risk harus tercatat | ACCEPTED |
| D-06 | AI dapat memakai Gemini atau provider lain, tidak wajib | ACCEPTED |
| D-07 | Empat setup: MACD + EMA200, Fractal Breakout, Relative Strength Breakout, Trend Pullback Reclaim | ACCEPTED tambahan dua setup; parameter numerik baru DEFAULT |
| D-08 | Single owner, personal, long-only, daily | DEFAULT |
| D-09 | Cron primary 20.17 WIB, recovery 22.17 WIB; cek hari bursa | DEFAULT |
| D-10 | Paper close-signal-risk-v1: entry sesi berikutnya pada harga close sinyal yang dibekukan | ACCEPTED 2026-10-08 |
| D-11 | Exit modular: fixed RR dapat diubah, atau breakdown MA5/10/20; SL awal tetap | ACCEPTED pilihan exit; default fixed 2R dan detail simulasi DEFAULT |
| D-12 | Paper risiko maksimal Rp1.000.000 termasuk fee beli 0,15% dan jual di SL 0,25%; lot 100 saham dibulatkan turun; slippage nol. Actual risk tetap milik ledger pengguna | ACCEPTED 2026-10-08 |
| D-13 | AI default off; tidak menghitung sinyal/harga/hasil transaksi | DEFAULT |
| D-14 | MACD swing low: pivot 2-left/2-right, lookback 60 sesi | DEFAULT formalization, tidak dinyatakan numerik dalam video |
| D-15 | Fractal SL: floor terakhir saat sinyal, tanpa buffer | DEFAULT tambahan; bukan dari script asli |
| D-16 | Tidak ada filter EMA slope, volume, MACD pada fractal base | DEFAULT, baseline murni |

| D-17 | Model baru mengaktifkan Fixed 2R dan SMA10 sebagai eksperimen terpisah per strategi sejak aktivasi | ACCEPTED 2026-10-08; parameter lain memerlukan eksperimen baru |
| D-18 | Tidak ada time exit 15 sesi; tidak ada partial TP, auto-breakeven, atau pergantian exit mid-trade pada paper baseline | DEFAULT mengikuti fokus exit terbaru pengguna |

## 2. Provenance sumber strategi

- Video pengguna: https://www.youtube.com/watch?v=YJNXXNCJasA, judul “3 Metode Terbaik MACD yang Saya Gunakan”.
- Transkrip pengguna dibaca 2026-09-28: `youtube-video (1).txt`.
- 03:14–06:08: EMA200 + MACD crossover; entry next candle; SL swing; RR 1:2; risk 1%.
- 06:08–07:54: divergence dan konfirmasi histogram melewati nol.
- 07:55–10:43: double bottom entry sebelum neckline, CHoCH, dan BOS dengan MACD.
- Fractal: Pine Script Fractal Channel / FracChan_v2 © NielsG, diberikan langsung pengguna. Header MPL-2.0 dipertahankan pada port yang berasal dari script; dokumentasikan provenance. Script menggambar level, bukan strategi entry/exit lengkap.
- Tidak ada bukti backtest atau win rate empiris yang disediakan. Jangan mengubah klaim video menjadi statistik produk.

## 3. Waktu dan data yang tersedia

- `session_date` adalah tanggal sesi BEI dalam Asia/Jakarta, bukan tanggal UTC atau tanggal pengambilan data.
- `fetched_at`, `created_at`, `published_at` adalah UTC timestamptz.
- Sinyal daily baru diterbitkan setelah sesi selesai dan candle tanggal target tersedia/valid.
- Pemrosesan nightly pada sesi t hanya memakai bar sampai t. Simulated entry paling cepat sesi BEI t+1.
- `t+1` berarti sesi bursa berikutnya menurut kalender, bukan besok kalender.
- Tidak membuat bar baru dengan forward-fill pada hari libur, suspension, atau data hilang.
- Stock suspended/missing dibedakan dari market holiday; missing bukan bukti no trading atau no signal.
- Calendar unknown/universe unknown → run blocked_configuration, tidak menebak.
- Scanning historis adalah backtest, bukan forward test. Late recovery data setelah sesi entry dimulai berlabel late/backfill dan tidak boleh membuat sinyal seolah tersedia malam sebelumnya.

## 4. Kebijakan OHLCV dan revisi

- Provider: Yahoo Finance via versi yfinance yang dipin; interval=1d; parameter `auto_adjust=False` dan `actions=True` dibuat eksplisit. Jangan bergantung default library.
- Istilah penyimpanan: `provider_ohlcv`, bukan jaminan raw exchange tape. Harga Yahoo dapat sudah memiliki penyesuaian split dari sumber; verifikasi perilakunya, jangan melakukan adjustment dua kali.
- Indikator dihitung dari OHLC pada basis provider yang sama. Jangan mencampur adjusted close dengan open/high/low basis lain. Adj Close boleh disimpan terpisah untuk audit, tidak digunakan oleh baseline.
- Dividen tidak di-back-adjust oleh engine baseline. Portfolio actual dapat mencatat dividen sebagai cash event terpisah; bukan trading win otomatis.
- Initial fetch: sekitar 3 tahun kalender; minimal 600 bar valid kontinu untuk eligibility MACD. IPO dengan histori kurang → insufficient_history. Fractal minimal 6 bar dengan ceiling/floor tersedia.
- Incremental fetch overlap 10 sesi sebagai default; corporate action memicu reconciliation histori lebih luas dan recomputation pada versi data baru.
- Validasi: finite, harga positif; low <= min(open,close) <= max(open,close) <= high; volume >= 0; tidak ada duplicate session; symbol mapping tepat; kalender/data freshness.
- Volume nol, candle tidak lengkap, atau anomaly → data_quality_hold untuk entry baru sampai diklarifikasi; jangan menghapus data audit.
- Gap histori yang tak terjelaskan menghalangi signal eligibility. Tidak mengisi harga hilang secara sintetis.
- Corporate action belum direkonsiliasi → hold sinyal baru dan paper trade terkait; actual ledger tetap memakai transaksi asli. Split memerlukan event penyesuaian quantity/basis terdokumentasi, bukan mengedit fill lama.
- Simpan bar revision/input digest serta snapshot fitur saat signal dibuat. Provider revisions tidak menulis ulang sinyal atau paper fill yang sudah published. Re-evaluation menjadi run/version terpisah dengan alasan.
- Full history refresh terkontrol dibutuhkan untuk mendeteksi revisi yang lebih tua daripada overlap. Jangan mengklaim overlap 10 sesi mendeteksi semua revisi.

## 5. Universe

- Ticker mapping IDX ke Yahoo, contoh format `BBCA` → `BBCA.JK`; verifikasi masing-masing symbol, jangan hanya mengandalkan suffix.
- Keanggotaan menyimpan `effective_from` inclusive dan `effective_to` exclusive, URL sumber, tanggal publikasi, checksum/import ID.
- Universe tanggal t dipilih berdasarkan periode efektif; file terbaru belum tentu sudah berlaku.
- Universe scan baru mengikuti keanggotaan t. Posisi terbuka tetap dipantau walau ticker keluar indeks.
- Backtest tanpa historical constituents berlabel `CURRENT_CONSTITUENTS_ONLY`; jangan disebut backtest KOMPAS100 historis yang bebas bias.
- Tidak menyertakan daftar anggota palsu. Fixture kecil diberi label synthetic/test.

## 6. Indikator MACD

Baseline `indicator_definition=v1`:

```text
alpha(n) = 2 / (n + 1)
EMA_n[0] = close[0]
EMA_n[t] = alpha(n)*close[t] + (1-alpha(n))*EMA_n[t-1]
MACD[t] = EMA12[t] - EMA26[t]
Signal[0] = MACD[0]
Signal[t] = (2/10)*MACD[t] + (8/10)*Signal[t-1]
Histogram[t] = MACD[t] - Signal[t]
```

EMA200 memakai recurrence yang sama. Float64 untuk indikator; monetary ledger menggunakan decimal. Tidak membulatkan indikator sebelum rule evaluation. Warm-up minimal 600 bar; hasil dekat nol ditampilkan dengan presisi cukup. Tidak menjanjikan persis sama dengan TradingView jika seed/history/feed berbeda; parity check membandingkan basis dan history yang sama, melaporkan toleransi/error.

Histogram cross ke atas nol adalah signal-line crossover yang sama; jangan menjadikannya dua konfirmasi independen. MACD line cross nol adalah kondisi berbeda.

## 7. Strategi `MACD_EMA200_V1`

Config minimal: `timeframe=1d`, `min_history=600`, `pivot_left=2`, `pivot_right=2`, `swing_lookback=60`, `entry_mode=next_session_open`.

### Trigger

```text
valid_data(t)
AND close[t] > EMA200[t]
AND Histogram[t-1] <= 0
AND Histogram[t] > 0
```

### Initial stop

Pivot low pada bar j valid bila low[j] <= low[j-2], low[j-1], low[j+1], low[j+2]. Pivot diketahui setelah close j+2. Untuk signal t pilih j paling baru dalam rentang t-60 sampai t-2 yang memenuhi rule; jika ties, j terbaru. SL = low[j], tanpa buffer untuk baseline. Tidak mencari swing lain bila pivot terbaru tidak valid terhadap close; tandai stop_invalid.

- Tidak ada pivot → sinyal teknikal dapat dicatat, tetapi `execution_eligible=false`, alasan `missing_stop`.
- SL >= close[t] → stop_invalid. Validasi diulang terhadap actual/simulated entry.
- Close > EMA200 tanpa syarat slope. Tidak mensyaratkan MACD line > 0 atau minimum volume.
- Default tidak mensyaratkan breakout swing high atau masa histogram merah singkat; itu eksperimen terpisah.
- Contoh momentum bullish dominan di video dicatat sebagai penjelasan, bukan filter kuantitatif yang dikarang.

## 8. Strategi `FRACTAL_BREAKOUT_V1`

### Port persis perhitungan level (daily/current timeframe)

```text
up[t] = high[t-3] >= high[t-4]
        AND high[t-3] >= high[t-5]
        AND high[t-2] <= high[t-3]
        AND high[t-1] <= high[t-3]

down[t] = low[t-3] <= low[t-4]
          AND low[t-3] <= low[t-5]
          AND low[t-2] >= low[t-3]
          AND low[t-1] >= low[t-3]

ceiling[t] = high[t-3] if up[t] else ceiling[t-1]
floor[t]   = low[t-3]  if down[t] else floor[t-1]
```

Initial ceiling/floor = null. Loop mulai saat t >= 5. Bar t tidak ikut mengonfirmasi pivot, sehingga ceiling[t]/floor[t] sudah dapat diketahui pada awal sesi t dari data sampai t-1. Simpan pivot_date=t-3, available_session=t. Jangan memajukan ketersediaan menjadi pivot_date.

Jika up/down true bersama, keduanya diperbarui. Equality diperbolehkan, bukan diganti strict >/<. Pivot baru memiliki ID baru walaupun nilainya sama.

`offset=-3` dari plot asli hanya untuk visual; tidak diterapkan ke seri perhitungan, sinyal, maupun backtest. UI default menggambar level dari available_session, bukan backplot. Multi-timeframe dikecualikan dari MVP.

### Trigger buy

Definisikan F = ceiling[t], level terbaru yang aktif di awal sesi t:

```text
valid_data(t)
AND F is not null
AND close[t] > F
AND close[t-1] <= F
AND upper_fractal_id has no previous emitted signal in this strategy version
```

Bandingkan kedua close terhadap F yang sama. Ini mencegah sinyal palsu yang hanya disebabkan garis baru turun melewati harga yang sudah berada di atasnya. Ini definisi breakout rancangan, bukan kode transaksi asli dari script.

- Wick/high di atas F, tetapi close <= F → no signal.
- Gap open di atas F dan close tetap di atas → dapat memenuhi trigger; bukan simulasi buy-stop.
- Fractal terdekat = fractal atas terbaru menurut waktu, bukan level numerik terdekat dari semua pivot lama.
- Satu emitted signal per upper_fractal_id per strategy version; skipped signal tetap mengonsumsi ID pada baseline. Re-entry adalah versi eksperimen.
- Initial SL = floor[t] dari snapshot signal; jika null atau >= close[t], execution_eligible=false. Jangan pilih floor alternatif secara diam-diam.
- Tidak mensyaratkan EMA200, MACD, RVOL, atau buffer breakout. Filter tersebut menjadi versi tersendiri.

### Source attribution

Port source: `Fractal Channel`, shorttitle `FracChan_v2`, © NielsG, Pine v1, MPL-2.0 https://mozilla.org/MPL/2.0/. Pertahankan header provenance/lisensi dalam file port. Rumus up/down, persistence level, dan equality berasal dari snippet pengguna; aturan trading dan tampilan tanpa backplot adalah tambahan produk ini.

## 8A. Strategi `RS_BREAKOUT_V1`

Setup riset yang disetujui sebagai tambahan, bukan berasal dari video MACD/script NielsG. Semua angka berikut hipotesis awal, belum terbukti profitable pada KOMPAS100.

- Daily, long-only, minimal 600 bar valid untuk EMA; definisi EMA bagian 6 dipakai juga untuk EMA20/50.
- Pada sesi t: `close[t] > EMA50[t] > EMA200[t]`.
- Relative strength berarti ranking return saham dalam universe, bukan indikator RSI: `return60 = close[t]/close[t-60]-1` pada basis provider yang sama.
- Ranking dilakukan descending atas seluruh anggota efektif t dengan histori return60 valid, sebelum filter trend/entry. Tie dipecahkan ticker ascending. Top `ceil(0.20*N)` eligible constituents. Simpan N, rank, return, cutoff, universe dan input digest seluruh cross-section; ticker yang tidak punya histori dikecualikan dan ditampilkan jumlahnya.
- Jika anggota yang seharusnya eligible memiliki data stale/missing/unresolved corporate action, ranking sesi itu `cross_section_incomplete`: tahan publikasi RS baru sampai lengkap. Jangan diam-diam menobatkan top20% dari batch parsial. Strategi lain dapat tetap publish.
- Trigger: `close[t] > max(high[t-20:t])`, slice mengecualikan t, tepat 20 sesi sebelum t. Equality bukan breakout. Setiap qualifying close adalah signal harian; aturan satu posisi aktif/experiment mencegah pyramiding.
- Initial SL: `min(low[t-4:t+1]) - 0.25*ATR14[t]`, yaitu lima bar termasuk sinyal.
- Entry next-session open; SL dibekukan pada snapshot; exit menggunakan modul pilihan bagian 9. Stop nonpositive atau >= reference close → execution ineligible; validasi ulang terhadap entry.
- Tidak ada filter volume, slope, IHSG regime, atau gap cap tersembunyi.

## 8B. Strategi `PULLBACK_RECLAIM_V1`

Setup riset kedua, daily/long-only, minimal 600 bar. Kondisi pada close sesi t:

```text
close[t] > EMA50[t] > EMA200[t]
AND exists j in {t-3,t-2,t-1}: close[j] < EMA20[j]
AND for all j in {t-3,t-2,t-1}: close[j] > EMA50[j]
AND close[t-1] <= EMA20[t-1]
AND close[t] > EMA20[t]
AND close[t] > high[t-1]
```

Initial SL = `min(low[t-3:t+1]) - 0.25*ATR14[t]`, empat bar termasuk sinyal. Entry next-session open, stop snapshot dan validasi sama dengan RS. Tidak membutuhkan ranking RS, volume, atau MACD.

### ATR dan MA tambahan

TR[0]=high[0]-low[0]; TR[t]=max(high[t]-low[t], abs(high[t]-close[t-1]), abs(low[t]-close[t-1])). ATR14 pertama pada indeks13 = mean(TR[0:14]); berikutnya `(13*ATRprev+TR)/14` (Wilder). Seed/history disimpan; jangan memakai SMA rolling TR sebagai ATR diam-diam. ATR signal t boleh memakai bar t karena keputusan setelah close.

SMA_n[t] = rata-rata close dari t-n+1 sampai t. EMA memakai recurrence bagian 6. Default exit MA memakai SMA; type dan period selalu tampil. Contoh stop/target paper menggunakan harga kontinu teoretis; actual quantity/fraksi harga mengikuti verifikasi BEI pada implementasi, bukan dianggap pasti executable.

## 9. Entry dan exit paper baseline

Paper model close-signal-risk-v1 adalah evaluasi trade-level dengan quantity lot hipotetis dan batas risiko per trade, tanpa modal agregat. Model lama next-open/unit saham tetap historis dan tidak direprice atau dicampur dengan model baru. Tidak boleh dilabeli portfolio return yang dapat direplikasi.

Harga E=close hari sinyal dibekukan saat pending plan dibuat; fill diasumsikan pada E di sesi entry berikutnya. Dengan S=initial SL dan fee beli/jual 15/25 bps, lots=floor(1000000 / (100*((E-S)+0.0015*E+0.0025*S))). Fee per fill dan net P&L dikuantisasi ke Rp0,01 HALF_UP; sesudah pembulatan, kurangi lot bila planned loss melebihi budget. Quantity=100*lots; lots nol menghasilkan skipped_budget. Simpan initial_price_risk_idr=Q*(E-S) dan planned_stop_loss_idr=Q*(E-S)+fee_buy(Q*E)+fee_sell(Q*S) secara terpisah. Slippage nol. Realized R tetap net P&L / initial price risk, bukan risk termasuk fee.

### Eligibility dan lifecycle

Signal: detected → published (atau excluded/late/data_hold).
Plan: pending_entry → open → closed; alternatif skipped/expired/data_hold/ambiguous_review.

- Sinyal dipublikasikan sebelum sesi entry dimulai agar masuk forward cohort. Timestamp asli tetap disimpan.
- Entry hanya pada next exchange session yang dijadwalkan; tidak membawa order ke sesi lain tanpa aturan baru.
- Untuk missing data, tahan di data_hold. Jangan menyimpulkan expired atau terisi dari ketidakadaan bar. Setelah bukti tersedia, evaluasi sesi yang seharusnya; tidak memindahkan entry ke hari recovery.
- Bila ada bukti saham tidak diperdagangkan pada sesi entry (mis. suspension resmi), plan expired_untradable.
- Satu open paper trade per ticker per entry strategy version per experiment (exit/config yang dibekukan). Sinyal baru selama open tetap dicatat dengan skip reason. Tidak re-entry pada tanggal trade lama exit; eligibility memakai posisi pada awal sesi.
- Paper fill close-sinyal adalah asumsi referensi harga yang dipilih pengguna, tidak menyatakan transaksi broker atau harga open berikutnya. Harga open/OHLC sesi entry hanya dipakai untuk evaluasi exit.
- Entry E = close sinyal yang dibekukan; S = SL snapshot; jika E <= S atau E tidak valid, skip_invalid_entry. Tidak mengganti S atau E untuk memaksakan trade.
- Initial price risk R0 = E-S, selalu >0. Exit policy dipilih dan dibekukan sebelum entry: fixed_rr atau ma_close. Default fixed_rr dengan target_r=2. Tidak ada time stop; posisi akhir sampel tetap open.
- Default chasing/gap cap disabled; tampilkan gap%. Penambahan cap harus berversi, bukan filter tersembunyi.

### Kontrak exit modular

Pisahkan `entry_strategy_version` dari `exit_policy_version` dan `experiment_id`. Sinyal teknikal diterbitkan sekali, lalu dapat dipakai beberapa paper experiment. Mengubah target RR tidak membuat sinyal fractal baru atau mereset guard pivot. Config per trade immutable; setting baru hanya untuk plan baru. Actual discretionary override boleh dicatat dengan alasan/audit, bukan mengubah hasil baseline.

| Mode | Parameter | Aturan |
| --- | --- | --- |
| fixed_rr | target_r positif finite; default2, preset1.5/2 | T=E+target_r*(E-S); initial SL tetap, tidak ada MA exit |
| ma_close | ma_type SMA default / EMA opsional; period5/10/20, default10 | Tidak ada fixed TP; exit signal saat close[t] < MA_n[t], market exit pada next-session open; initial SL tetap |

`ma_close` memakai kondisi strict below, bukan wajib crossover dari atas. Ini menghindari trade yang telanjur di bawah MA tidak pernah exit karena tidak ada cross baru. Mulai evaluasi pada close hari entry; bila sudah di bawah MA, jadwalkan exit sesi berikutnya. Close sama MA atau wick-only breakdown tidak memicu. Tidak ada syarat trade sudah untung: nama “let profit run” tidak menjamin exit profit. planned_RR/TP untuk ma_close = null; realized_R tetap dapat dihitung dari initial risk.

Tidak mengubah mode otomatis setelah +1R/+2R. Hybrid fixed TP sebagian, aktivasi MA setelah profit threshold, auto-breakeven, dan ratcheting price stop bukan bagian baseline.

### Evaluasi exit EOD — fixed_rr

T=E+target_r*(E-S). Pada setiap sesi mulai sesi entry, cek open dahulu:

1. Open <= S → assumed stop fill pada open (gap loss dapat melebihi -1R).
2. Open >= T → assumed take-profit fill pada T (konservatif, tanpa positive gap improvement).
3. Jika open di antara S dan T: low <= S dan high >= T → ambiguous_both_hit; baseline SL-first; simpan juga alternate TP-first.
4. Hanya low <= S → exit S. Hanya high >= T → exit T. Tidak ada → tetap open.

Pada sesi entry, fill referensi E tetap close sinyal; evaluasi open yang teramati terlebih dahulu, kemudian high/low untuk SL/TP dengan aturan ambigu yang sama. Bar OHLC tidak dapat membuktikan urutan intraday. Data invalid/corporate-action hold menghentikan auto-evaluation ticker itu, bukan menutup posisi paksa.

### Evaluasi exit EOD — ma_close

1. Posisi dari sesi sebelumnya: jika open <= initial SL, exit open dengan stop gap reason. Jika ada pending MA exit dari sesi sebelumnya dan open > SL, exit open dengan ma_breakdown reason. Bila keduanya bertemu, satu fill saja (stop gap mengambil reason).
2. Jika belum keluar: low <= initial SL → simulated exit SL; tidak memerlukan close di bawah MA. Stop tidak pernah dilonggarkan mengikuti MA.
3. Jika masih open setelah evaluasi stop: close < MA → append pending exit untuk sesi berikutnya; simpan MA value/type/period, close, signal session, publication timestamp, dan versi data.
4. Entry-day reference-close buy diikuti pemeriksaan open/stop, lalu close/MA. Tidak membeli dan menjual pada open yang sama berdasarkan close yang belum diketahui.
5. Missing next-session bar → data_hold, bukan fill pada tanggal recovery. Jika ada bukti resmi saham tidak dapat diperdagangkan, pending market exit tetap menunggu sesi pertama yang benar-benar tradable; bedakan dari expiry entry order. Daily bar open adalah asumsi fill, bukan jaminan transaksi saat terkunci batas harga.
6. MA value pada close t hanya memberi exit t+1. Tidak menggunakan harga MA sebagai fill, tidak mengklaim stop intraday real-time. Jika exit signal baru ditemukan setelah open eksekusi yang semestinya, tandai late/model-only dan keluarkan dari actionable forward cohort; jangan backdate.

Publikasi exit dari data tepat waktu dicatat sebelum open eksekusi; sinyal malam hanya instruksi rencana, tidak mengirim order broker. Semua exit actual membutuhkan fill aktual pengguna.

### Biaya dan friksi

- `fee_buy_bps`, `fee_sell_bps`, `slippage_bps` adalah konfigurasi wajib berstatus verified/provisional/unset.
- Untuk prototype test gunakan 0 secara eksplisit dengan label `GROSS / ZERO-COST ASSUMPTION`; bukan net result live.
- Implementasi baseline: simulated fill memakai E/S/T/open aturan di atas; slippage adalah biaya tambahan bps dari notional masing-masing fill, tidak dihitung dua kali melalui pergeseran harga.
- `gross_pnl = q*(exit-entry)`; `cost = q*entry*(buy_fee+buy_slip)/10000 + q*exit*(sell_fee+sell_slip)/10000`; `net_pnl=gross_pnl-cost`.
- Hasil gap/ambiguous tidak diberi tag net verified hanya karena tersedia angka.

## 10. Actual journal

- Trade dibuat sebagai draft, actual open hanya setelah buy fill pengguna/import valid.
- Fills immutable secara bisnis: corrections memakai revision/audit. Fee aktual dalam IDR per fill; estimasi diberi label. Jangan menambahkan fee model di atas fee aktual yang sudah diisi.
- Baseline multiple buy fills boleh dalam entry batch yang belum difinalisasi, sebelum sell pertama, dengan initial SL sama. `finalize-entry` mengunci batch dan initial risk; sell pertama wajib didahului finalisasi (boleh otomatis dalam transaksi RPC yang sama). Buy tambahan setelah finalisasi menjadi trade baru; tidak ada scale-in tersembunyi.
- `initial_risk_idr = sum(q_buy * (price_buy - initial_SL))`, harus > 0; setiap buy fill harus di atas initial SL. Sebelum entry batch difinalisasi, risk tampil sebagai provisional. Sesudah finalisasi, risk immutable kecuali koreksi input yang eksplisit dan diaudit. Risiko ini price risk sebelum biaya, dijelaskan di UI.
- `net_pnl` memakai total actual cash received - total cash spent - fee. Closed jika posisi quantity nol; oversell ditolak.
- Saat partial exit, remaining cost basis memakai weighted average. P&L terealisasi tampil, trade belum dihitung closed win/loss.
- `realized_R = closed_trade_net_pnl / initial_risk_idr`. Menggeser SL tidak mengubah initial risk.
- Budget risiko usulan = modal trading × risk_pct; quantity dibulatkan turun menurut lot/fraksi BEI yang diverifikasi. Risk budget bukan jaminan batas loss saat gap.
- Primary strategy wajib satu; secondary tags boleh banyak. Actual strategy metrics memakai primary attribution; tag overlap tampil sebagai analisis terpisah. Portfolio menghitung setiap trade satu kali.
- Dividend/cash deposit/withdrawal dicatat terpisah, tidak otomatis menjadi trading P&L. Actual equity harus memisahkan cash flow eksternal dari return.

## 11. Statistik

- Cohort closed metrics memakai exit session dalam filter tanggal, entry strategy version, exit policy version/parameters, experiment, mode, cost model, dan universe policy yang jelas. Open count ditampilkan terpisah.
- Win: net P&L > 0; loss < 0; breakeven = 0 setelah pembulatan monetary policy. `win_rate = wins / all_closed`, termasuk breakeven pada denominator.
- `planned_RR=(T-E)/(E-S)` untuk fixed_rr sebelum biaya; ma_close=null/“open target”. TP 2R gross tidak menjamin realized R = 2.
- `payoff_ratio=mean(net positive P&L)/abs(mean(net negative P&L))`, sertakan basis IDR; tampilkan juga R payoff untuk paper normalisasi.
- `expectancy_R=mean(realized_R)` seluruh closed trades, termasuk breakeven.
- `profit_factor=sum(net positive P&L)/abs(sum(net negative P&L))` pada cohort/basis sama.
- No closed → null, bukan 0% win rate. No loss → PF/payoff undefined/infinite sesuai konteks; tampilkan “belum ada loss”, bukan angka palsu. No wins dengan losses → PF 0.
- Model paper baru: kurva utama cumulative closed net P&L IDR dan drawdown dari puncak dengan titik awal nol. Kurva R tetap opsional; bukan persentase portfolio, equity marked-to-market, atau CAGR.
- Model paper baru default expectancy/payoff/profit factor berbasis net IDR untuk quantity hasil sizing. Model legacy unit-risk tetap basis R. Actual memakai IDR dengan opsi R; model dan mode tidak dicampur.
- Actual equity drawdown memakai EOD marked-to-market plus cash, disesuaikan arus dana. Sebelum capital/cash ledger tersedia, jangan menampilkan portfolio drawdown%; closed-P&L drawdown boleh dengan label tepat.
- EOD equity tidak merepresentasikan intraday max drawdown. Stale marks diberi flag.
- Model baru mengecualikan ambiguous_review dan late/model-only dari statistik utama dengan count dan alasan terlihat. Sensitivitas SL-first dan TP-first dihitung terpisah dengan denominator known+ambiguous yang jelas. Legacy baseline tidak direwrite.
- Semua statistik menampilkan sample size; confidence/probability kemenangan tidak diproduksi oleh AI.

### Perbandingan eksperimen

Model close-signal-risk-v1 memiliki delapan eksperimen: empat setup × Fixed2R/SMA10. Aktivasi persisten terjadi sebelum publikasi pertama model ini; hanya sinyal forward published_at >= activated_at yang masuk. Statistik satu exit family per tampilan (default Fixed2R), tanpa penjumlahan kedua eksperimen. Exit lain memerlukan versi/aktivasi baru. Jangan otomatis mencari kombinasi terbaik lalu menyebutnya terbukti.

Bandingkan biaya, periode, data, dan universe yang sama; laporkan closed/open, durasi holding, skip counts, expectancy R net dan drawdown cumulative realized R. Batas satu posisi per experiment berarti exit lebih lama dapat mengubah kesempatan entry berikutnya. Laporkan overlap signal IDs dan perbedaan sampel; perbandingan bukan otomatis paired. Analisis paired tambahan memakai common entry IDs, menampilkan trade yang belum closed di masing-masing mode tanpa membuangnya secara diam-diam.

Trade saham sama/hari sama lintas setup/exit saling berkaitan; bukan observasi independen dan tidak boleh dijumlah menjadi total profit portfolio. Regime IHSG dan MFE/MAE dapat menjadi analisis tambahan, bukan filter entry baru tanpa versi. MFE/MAE dari daily exit bar tidak dapat memisahkan gerakan sebelum/sesudah fill; tandai ambiguity.

## 12. Immutability dan versi

Setiap signal menyimpan strategy_id/version, config_hash, indicator_version, universe_version, data_snapshot_id/input_digest, session_date, available_at, published_at, rule outcomes, level origin dates, dan processing commit SHA.

Key idempotensi signal = `(strategy_version, config_hash, universe_version, ticker, session_date)`; fractal punya unique guard tambahan `(strategy_version, config_hash, upper_fractal_id)` untuk forward baseline. Backtest dipisahkan oleh experiment_id.

Signal config_hash hanya mencakup entry/indicator/universe policy; exit policy dan cost model disimpan dalam experiment immutable beserta activated_at. Paper trade menyimpan snapshot exit policy, bukan membaca setting terbaru tiap malam. Pending plan lama tidak berubah ketika setting diperbarui; cancel/recreate perlu event audit.

Parameter baru → versi/experiment baru. Jangan menggabungkan MACD base dan filter EMA-slope dalam satu seri hasil. Rerun data sama bukan experiment baru; reproduksi deterministik menggunakan snapshot lama.

## 13. Contoh uji numerik (synthetic, bukan data saham)

1. MACD close=105, EMA200=100, H_prev=-0.2, H=0.1, pivot SL=98 → trigger valid. H_prev=0.1/H=0.2 → bukan crossover baru.
2. Fractal highs sesi 0..4 = [100,102,110,108,109]. Pada sesi 5 ceiling=110, pivot sesi 2, tersedia sesi 5. Sesi 5 tidak ikut validasi pivot.
3. F=110, prev close=109, current close=112 → signal. Current high=113, close=109 → no signal.
4. Garis lama 120, garis baru F=110, prev close=115, current close=116 → no breakout; harga sudah di atas F sebelumnya.
5. E=100, S=95, T=110, q=1, tanpa biaya: exit110 → +2R; exit95 → -1R; gap open92 → -1.6R.
6. E=100, S=95, T=110, subsequent O=102/H=111/L=94/C=104 → ambiguous: baseline -1R, alternate +2R, sebelum biaya.
7. Empat closed R=[2,-1,0,1], tanpa biaya → win rate50%, expectancy0.5R, R-based PF3, R payoff1.5.
8. Actual: beli100 saham@100 dan100@102, initialSL95 → risk1.200; jual100@105 dan100@108 → grossP&L1.100. Jika total fee100 → net1.000, realizedR0.833333. Partial exit pertama belum closed.

9. Fixed1.5R: E100/S95 → TP107.5, gross+1.5R sebelum biaya/fraksi harga. Tidak mengubah risk awal.
10. MA exit: E100/S95, low97, close103<SMA10=104 → pending; next open101 → gross+0.2R, bukan exit104. Jika next open93 → exit93 satu kali, gross-1.4R.
11. MA wick: low101<MA102 tetapi close103>MA102 dan SL95 tidak kena → tetap open. Close102=MA102 juga tetap open.
12. RS lima-bar low minimum90, ATR14=4 → initialSL89; pullback empat-bar low minimum92, ATR14=4 → initialSL91.

## 14. Backlog / keputusan terbuka

- Nama/domain, owner identity, fee/modal sebenarnya, provider AI, universe/calendar live.
- Divergence: pivot association, tolerance, expiry; price action: double-bottom tolerance, BOS/CHoCH definition. Jangan mengimplementasikannya sebagai fitur “selesai” dari intuisi saja.
- Buffer tambahan di luar definisi RS/Pullback, liquidity filters, gap cap, time stop, portfolio risk cap, re-entry, broker order validity memerlukan versi tambahan.
- Kriteria halal/pajak/kesesuaian investasi tidak diasumsikan oleh sistem.
- Batas layanan/free tier dapat berubah; diverifikasi ulang saat provisioning, bukan menjadi konstanta bisnis.

## Evaluasi sinyal close-signal-risk-v1 (disetujui 2026-10-08)

Satu observasi per sinyal forward valid sejak aktivasi, tidak digandakan per eksperimen exit; sinyal skipped_budget/position tetap dianalisis. Target 1R/2R memakai jarak harga entry-SL dan first-hit independen sampai target/SL; dual-hit tanpa urutan diketahui adalah ambiguous. Horizon 5/10 adalah checkpoint riset, BUKAN auto-close atau time exit. Sesi entry adalah sesi ke-1. Sukses horizon: tidak ada sentuhan SL sampai N dan close_N*0.9975-entry*1.0015 > 0 secara teoritis per saham. SL tersentuh berarti gagal; data hilang menahan observasi untuk replay, bukan menggeser tanggal. Setiap sel menampilkan dinilai/wins/pending/ambiguous/data_hold/excluded dan alasan. Periode riset berdasarkan signal_session; periode statistik trade closed berdasarkan exit session Asia/Jakarta. SMA10 memicu hanya pada confirmed daily close < SMA10; equality/wick bukan trigger, initial technical SL tetap aktif; eksekusi MA pada next-open.
