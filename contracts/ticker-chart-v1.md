# Ticker chart v1 — kontrak implementasi

Tanggal: 2026-10-14 WIB. Status: spesifikasi Tahap 1; **belum ada RPC/route ini di produksi**.
Pemilik kontrak: backend; konsumen: frontend. Rencana dan acceptance matrix:
[CHART_V1_IMPLEMENTATION_PLAN](../docs/CHART_V1_IMPLEMENTATION_PLAN.md).
Aturan trading tetap mengikuti [SOT](../SOT.md); kontrak ini hanya menambah pembacaan/visualisasi.

## 1. Batas arsitektur

- RPC baru: `read_ticker_chart_v1(p_request jsonb)`; satu respons JSON berversi.
- HTTP baru: `GET /api/chart/[ticker]` di Next.js, menerjemahkan query ke RPC melalui session owner.
- Halaman baru: `/chart/[ticker]`; komponen yang sama dipakai panel Scanner dan detail jurnal.
- Tidak ada provider request, perhitungan indikator, dispatch job, atau penulisan ekonomi pada GET/RPC chart.
- Python membuat artifact indikator immutable dari riwayat canonical; Supabase melayani reader.
- Perhitungan artifact dijalankan sebagai pekerjaan cloud opsional setelah pekerjaan ekonomi selesai,
  dengan status/log sendiri. Kegagalan artifact tidak mengubah keberhasilan publikasi/paper atau menutup hold.
- Reader memakai auth/RLS yang ada, bukan service-role browser atau reader publik baru.
- Artifact lama boleh dibuat oleh job cloud terbatas yang hanya menulis artifact chart, bukan sinyal/fill.

## 2. Request

Query HTTP dan key `p_request` sama kecuali ticker berasal dari route HTTP. Unknown key ditolak.

| Field | Tipe / default | Aturan |
| --- | --- | --- |
| `ticker` | string | Pola existing `^[A-Z0-9_-]{1,20}$`; mapping sumber harus terverifikasi; tidak dibatasi universe saat ini |
| `context` | `latest`, `signal`, `paper`, `actual`; default `latest` | Konteks menentukan sumber dan overlay |
| `context_id` | string, opsional | Wajib untuk signal/paper/actual; dilarang untuk latest; ikuti ID existing, jangan paksa semua menjadi UUID |
| `view` | `snapshot` atau `followup` | signal default snapshot; latest/paper/actual default followup; latest hanya followup |
| `timeframe` | literal `1d`, default `1d` | Tidak menerima intraday, weekly, monthly |
| `from`, `to` | tanggal ISO, opsional | Inklusif; tanggal valid, from <= to; backend menentukan batas sesi tertutup |
| `limit` | integer, default 250, min 1, max 500 | Jumlah slot sesi bursa per halaman, termasuk slot gap; bukan bar buatan |
| `cursor` | opaque string, opsional, max 2048 karakter | Untuk halaman lebih lama; tidak boleh digabung dengan from/to |

`data_mode`, owner, provider, namespace, source revision, harga, level, dan indikator tidak boleh dipilih
oleh caller. Mode berasal dari konfigurasi server; produksi live menolak fixture. Tidak menerima arbitrary
SQL/filter/symbol-provider/URL. ID ditentukan server dari tabel sumber dan divalidasi terhadap ticker/mode/owner.
Invalid kombinasi ditolak, bukan diam-diam diganti latest. Context milik pihak lain tidak dibocorkan.

ID signal mengikuti lowercase SHA256 (64 hex), actual trade UUID, paper mengikuti ID text existing
(nonkosong, maksimum 256 karakter untuk batas request). Jangan menolak legacy paper hanya karena bukan
64 hex; jika provenance cohort lama tidak mendukung chart, return SNAPSHOT_UNAVAILABLE secara eksplisit.

Jika `to` tidak diberikan: latest/followup memakai sesi tertutup terakhir dari kalender backend; snapshot
memakai sesi sinyal. `to` melewati cutoff snapshot atau sesi tertutup menghasilkan INVALID_REQUEST.
Jika from tidak diberikan: ambil jendela terakhir sebanyak limit slot yang berakhir di to. Jika from/to
meliputi lebih dari limit: kembalikan halaman terakhir dan cursor untuk bagian sebelumnya. Kalender persisted
yang terverifikasi wajib mencakup jendela; bila tidak tersedia, return DATA_UNAVAILABLE dengan alasan
calendar_unavailable. Jangan mengarang sessions/gaps dari hari Senin–Jumat. freshness unknown digunakan
ketika jendela historis terverifikasi tetapi kalender belum dapat membuktikan expected session terkini.
Dalam kasus itu latest/followup tanpa to berakhir di sesi terakhir yang sudah terverifikasi, expected_session
null dan warning calendar_current_unknown; from/to eksplisit di luar kalender tetap ditolak.

## 3. Konteks dan waktu

| Konteks | Input chart | Overlay |
| --- | --- | --- |
| latest/followup | Revisi persisted yang lolos kualitas/provenance untuk ticker dan mode | Tidak mengambil semua transaksi pengguna secara otomatis |
| signal/snapshot | Revisi asli dari digest sinyal, dibatasi sesi sinyal | Sinyal dan level yang sudah tersedia saat itu; tidak ada actual/paper fill masa depan |
| signal/followup | Revisi observasi yang layak; input sinyal asli tetap direferensikan terpisah | Sinyal asal dengan label perkembangan setelah sinyal |
| paper/snapshot | Snapshot sumber sinyal trade | Rencana yang memang sudah diketahui pada sesi sinyal; bukan event eksekusi kemudian |
| paper/followup | Revisi observasi yang layak untuk source scope trade | Rencana frozen dan event jurnal paper, tidak disimpulkan dari candle |
| actual/followup | Revisi observasi yang layak untuk ticker | Fill/stop dari ledger aktual; trade manual tanpa signal_id didukung |

actual/snapshot tidak didukung V1: tampilkan tautan terpisah ke snapshot signal terkait bila ada.
Followup tidak menggabungkan diam-diam bar berbagai provider/basis. Return revisi observasi yang dipilih
beserta sumber sinyal asli. Bila basis overlay dan candle tidak kompatibel, candle boleh tampil tetapi
garis/marker harga terkait ditahan dengan alasan; angka ledger tetap dapat dibaca di panel detail.
Jangan mereskala entry/SL/fill agar tampak cocok. Event tanpa bukti basis yang memadai juga ditahan.
Revisi khusus paper recovery tidak boleh dipilih latest/scanner; artifact mempertahankan scope tersebut.

Resolusi frozen snapshot adalah pekerjaan backend nyata: signal menyimpan input_digest/provider/basis/version,
bukan foreign key langsung ke market revision. Engine dapat memotong bars/actions/issues ke cutoff sebelum
digest dihitung. Resolver harus membuktikan hasil rekonstruksi+cutoff cocok dengan digest sinyal, atau return
SNAPSHOT_UNAVAILABLE; tidak boleh fallback ke histori saat ini. Bedakan `source.series_id` (UUID market)
dari `context.engine_source_revision` (Git SHA engine). Source receipt digest dan resolved cutoff digest
dapat berbeda dan wajib ditampilkan sebagai field berbeda.

`fetched_at`/`stored_at` bukan waktu harga terakhir. Freshness dibandingkan dengan kalender backend dan
`last_market_session`. Untuk snapshot, expected_session selalu cutoff historis yang terverifikasi;
snapshot lengkap tidak disebut stale hanya karena bukan sesi hari ini. Followup/latest memakai expected
session terakhir yang tertutup, bukan sekadar to filter, agar tanggal lama tidak menyembunyikan data stale.
Revisi lebih lama yang dipakai akibat capture baru gagal diberi stale/partial,
bukan diam-diam dilabeli current. Tidak ada klaim tick real-time.

## 4. Envelope dan tipe payload

Success: `{ contract_version: "ticker-chart-v1", success: true, data: ChartData, error: null }`.
Failure: `{ contract_version: "ticker-chart-v1", success: false, data: null,
error: { code, message, request_id, retryable } }`.
Field wajib harus ada; nullable hanya bila ditulis nullable. Frontend parser ketat dan memeriksa relasi,
bukan hanya type cast. Unknown field ditolak dalam versi ini; penambahan kontrak harus dikoordinasikan.

`ChartData`:

| Field | Isi wajib |
| --- | --- |
| `ticker`, `data_mode`, `timeframe`, `exchange`, `timezone`, `currency`, `volume_unit` | Ticker; live/fixture; `1d`; `XIDX`; `Asia/Jakarta`; `IDR`; `shares` |
| `context` | `{ kind, id: string|null, view, signal_session: date|null, snapshot_cutoff: date|null, model_version: string|null, experiment: string|null, engine_source_revision: string|null }` |
| `revision` | Opaque immutable chart revision; mengikat sumber, context/event revision dan versi indikator selama pagination |
| `source` | `{ series_id, input_digest, resolved_input_digest, resolved_cutoff, provider, provider_version, price_basis, scope, fetched_at, stored_at, history_start, last_market_session }` |
| `signal_source` | Source reference dengan field sama, atau null jika tidak memiliki sumber sinyal |
| `quality` | `{ completeness, freshness, expected_session: date|null, reasons: string[], warnings: string[] }` |
| `sessions` | Array sesi exchange di jendela, unik ascending; batas <= limit |
| `bars` | Array `{ session, open, high, low, close, volume }`; subset sessions, unik ascending |
| `gaps` | Array `{ session, reason }`; komplemen bars di sessions, tidak mencakup libur bursa |
| `indicators` | Object dengan tepat key sma10, ema200, macd, macd_signal, macd_histogram; bentuk Indicator di bawah |
| `overlays` | `{ status, reason: string|null, levels: Level[], markers: Marker[], has_more: boolean, next_cursor: string|null }` |
| `pagination` | `{ window_from, window_to, returned_slots, limit, has_more, next_cursor: string|null }` |

Enum: completeness=`complete|partial`; freshness=`current|stale|unknown`.
Scope source=`forward|paper_recovery|fixture`; backend memetakan namespace/metadata existing tanpa membuang
provenance. API tidak mengekspos credential atau metadata provider mentah. `series_id` memakai UUID existing,
digest memakai format existing. Semua date adalah YYYY-MM-DD, instant ISO8601 ber-offset UTC.
`input_digest` adalah digest receipt asli; `resolved_input_digest` adalah digest input setelah cutoff
(`resolved_cutoff`, date) dan harus sama dengan digest sinyal pada signal_source. `last_market_session`
adalah sesi valid terakhir dari input resolved, bukan metadata run terbaru.
price_basis wajib membawa label exact existing, antara lain `yahoo_provider_ohlcv_auto_adjust_false_v1`
dan `eodhd_unadjusted_ohlc_v1`; jangan ganti dengan label generik raw atau adjusted_close.
Reason code adalah string nonkosong <=128 karakter; message/warning <=512, maksimum 20 alasan/peringatan.

Harga OHLC/level/marker berupa decimal string tanpa separator ribuan/exponent; volume integer decimal
string >=0. Indicator memakai JSON number finite atau null, sesuai konvensi contracts existing.
Validate low <= open/close <= high, harga positif, sesi unik, relasi counts/cursor, dan tipe yang tidak
menerima bool sebagai angka. Nol volume tidak otomatis valid: keputusan kualitas tetap canonical.
Konversi decimal ke number hanya di adapter render; label uang memakai nilai canonical, bukan hitung ulang
risiko/P&L. Nilai yang tidak dapat direpresentasikan aman ditolak sebagai CONTRACT_ERROR.

Indicator: `{ status: "ready"|"unavailable", reason: string|null, definition_version,
artifact_digest: string|null, history_count: integer, eligible_from: date|null, points: [{ session, value: number|null }] }`.
Ready: satu point per sessions, gap/undefined warm-up bernilai null. Unavailable: points kosong,
reason wajib. Artifact hilang tidak menggagalkan candle valid. Tidak menghasilkan indikator fiktif.
EMA/MACD memakai calculate() canonical dari awal riwayat, lalu crop; SOT minimal 600 bar untuk readiness
strategi MACD/EMA200. Nilai recurrence sebelum 600 boleh terlihat dengan label insufficient_history; ini
bukan sinyal layak. eligible_from menandai eligibility histori saja, bukan konfirmasi strategi/RS.
SMA10 memakai sma() canonical: sembilan point pertama null, lalu minimal 10 bar pada urutan histori canonical
setelah verified-untradable exclusions, sama seperti paper engine (bukan sepuluh tanggal bursa berturut-turut).
Sesi verified-untradable tidak memiliki candle sintetis, dicatat gaps reason=verified_untradable dan tidak
otomatis merusak continuity indikator jika engine memang mengecualikannya. Jangan mengecualikan missing bar
yang belum terbukti untradable. Tidak reseed dari
halaman/viewport. Gap yang membuat continuity tidak sah menahan point selanjutnya sampai ada rekonstruksi
canonical yang valid; tidak meneruskan indikator melewati gap secara diam-diam.

Level: `{ id, kind, price, starts_at, ends_at: date|null, available_session,
origin_session: date|null, source_id, status }`.
kind=`planned_entry|initial_stop|current_stop|target|fractal`; status=`planned|effective|ended`.
starts_at >= available_session; berhenti sesuai event backend. Snapshot tidak memuat perubahan stop masa depan.
Fractal hanya dari level canonical yang sudah tersedia; tidak menghitung pivot/garis fractal baru di UI.
Level dimasukkan bila interval starts_at..ends_at overlap dengan window, termasuk level aktif yang dimulai
sebelum window_from. starts_at boleh di masa depan untuk rencana yang sudah diketahui pada cutoff snapshot:
kembalikan level planned tersebut sebagai pengecualian overlap dan tampilkan di ringkasan rencana saja,
bukan candle/fill masa depan. Semua level tetap mensyaratkan available_session <= cutoff konteks.

Marker: `{ id, kind, session, available_session, price: decimal|null, source_id, status }`.
kind=`signal|entry_fill|ma_exit_trigger|exit_fill|ambiguous`; status=`confirmed|simulated|ambiguous`.
Actual partial fills tetap event terpisah, bukan harga rata-rata rekaan. Jika beberapa event pada satu hari,
stack/list tanpa mengarang urutan intraday. MA trigger pada close berbeda dari fill next-open. Paper fill
close-sinyal dapat di luar candle entry; tetap tampil dengan label simulasi. Pending bukan entry_fill.
Target Fixed 2R berasal dari trade; SMA10 tidak diberi fixed TP. Ambigu tidak divisualkan sebagai TP-first/SL-first.
Marker disaring session di dalam window dan available_session <= cutoff konteks. Followup cutoff adalah
sesi closed yang digunakan respons; snapshot cutoff adalah sesi sinyal. Event tidak diasumsikan diketahui
pada snapshot hanya karena memiliki session historis; gunakan availability/event revision canonical.

Overlay status=`ready|partial|unavailable`; reason wajib jika tidak ready. Payload awal maksimal 500
gabungan level+marker dalam window (urut available_session lalu id); tidak boleh dipotong tanpa has_more.
Untuk konteks actual dengan lebih banyak fills, cursor overlay mengambil halaman overlay berikutnya melalui
RPC/HTTP yang sama: cursor menyimpan kind=overlays; bars/sessions/gaps kosong, indikator unavailable dengan
reason=overlay_page, pagination returned_slots=0, dan source/revision sama. Frontend hanya append overlays.
Cursor bar kind=bars mengembalikan data jendela lebih lama berikut overlay jendela itu.

## 5. Pagination, caching dan security

- Cursor server-issued terikat owner/mode/ticker/context/view/revision/window/limit/kind. Revalidate auth pada
  setiap halaman; cursor bukan credential. Payload cursor tidak boleh mengizinkan caller memilih revisi bebas.
- Halaman kedua tidak pindah ke revisi baru ketika job EOD selesai. Refresh eksplisit memulai revision baru.
  Missing/expired backing revision menghasilkan REVISION_UNAVAILABLE, tidak latest fallback.
- No shared public cache. HTTP `Cache-Control: private, no-store`; cache memori frontend hanya session tab,
  keyed context+mode+revision dan dibuang ketika logout/owner berubah. Tidak menyimpan jurnal di localStorage.
- Server/RPC memvalidasi bounds sebelum query. Terapkan batas 60 chart reads/menit/owner (burst 10), melalui
  limiter server/cloud yang sama untuk jalur langsung maupun HTTP; jangan mengandalkan memori satu instance
  Vercel. Tahap 2 harus membuktikan limiter bersama atau melaporkan gate belum terpenuhi.
- Authenticated hanya EXECUTE reader/SELECT melalui RLS; writer artifact hanya service role. SECURITY DEFINER
  jika diperlukan harus memeriksa owner aktif/mode, fixed search_path dan grants minimum. Uji direct RPC bypass.
- Market revisions memakai membership app-owner aktif existing; paper/actual juga wajib owner_id=auth.uid().
  Pencatatan limiter dibolehkan sebagai metadata keamanan, tidak menyentuh data pasar atau ledger.
- Logging hanya request_id, kode, durasi, counts/revision tersanitasi; jangan log token atau raw private fills.

## 6. Error dan degradasi

| HTTP / code | Perilaku UI |
| --- | --- |
| 400 INVALID_REQUEST | Pesan filter/konteks invalid; jangan ganti ticker/context |
| 401 UNAUTHENTICATED | Login dengan return URL internal yang tervalidasi |
| 403 FORBIDDEN | Akun tidak memiliki akses; tanpa informasi data owner |
| 404 NOT_FOUND | Ticker/context tidak tersedia; foreign context sama seperti tidak ditemukan |
| 409 REVISION_UNAVAILABLE | Minta refresh; jangan gabungkan halaman beda revisi |
| 409 SNAPSHOT_UNAVAILABLE | Snapshot historis tidak dapat dibuktikan; jangan ganti ke latest |
| 429 RATE_LIMITED | Retry-After; tombol coba lagi, tanpa retry storm |
| 503 BACKEND_NOT_READY | Capability chart belum tersedia; halaman asal tetap berfungsi |
| 503 DATA_UNAVAILABLE | Tidak ada sumber layak; tampil alasan aman, bukan grafik kosong sukses |
| 502 CONTRACT_ERROR / UPSTREAM_ERROR | Payload invalid/RPC gagal; tampil error, bukan fixture |
| 500 INTERNAL_ERROR | Pesan aman + request_id; detail hanya log server |

Partial valid bars menghasilkan success dengan quality partial dan gaps. Tidak ada candle nol, interpolasi,
carry-forward close, atau offset tanggal untuk menutup lubang. Hari nonbursa bukan missing bar. Corporate-action
hold dan harga lintas basis tidak diperbaiki oleh chart. Data tertahan tetap tertahan di scanner/jurnal.

## 7. Implementer checklist

- [ ] Buat schema/strict parser dan fixture kontrak positif/negatif di kedua repo (Tahap 2/3).
- [ ] Pin artifact ke input_digest + full-history/indicator version + scope/mode; writer idempotent.
- [ ] Simpan snapshot event/level revision agar pagination stabil saat ledger berubah; append-only artifact,
  tidak menyalin ulang seluruh ledger ke browser atau mengubah event asli.
- [ ] Uji contract dan seluruh invariant C01–C18 pada rencana sebelum integrasi live.
- [ ] Tandai capability ready hanya ketika reader+writer artifacts+RLS tersedia; jangan infer dari frontend build.

## Referensi implementasi

- `backend/supabase/migrations/202609290002_market_series_revisions.sql`
- `backend/supabase/migrations/202609290003_market_series_reconstruction.sql`
- `backend/scanner/src/idx_scanner/indicators.py`, `models.py`, `persistence.py`
- `frontend/src/components/scanner-terminal.tsx`, `src/lib/scanner-server.ts`
- [Dokumentasi library](https://tradingview.github.io/lightweight-charts/docs): renderer browser,
  TypeScript, dan kewajiban notice/link TradingView. Seri harga tetap disediakan aplikasi.
