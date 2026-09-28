# Panduan Agen Coding — IDX Night Scanner

## Baca sebelum mengubah kode

README.md, PRD.md, SOT.md, TECHNICAL_DOC.md, CODEX_HANDOFF.md. Aturan trading canonical ada di SOT.md. Instruksi eksplisit terbaru pengguna diutamakan; konflik material didokumentasikan. DEFAULT dalam SOT boleh diimplementasikan tanpa meminta konfirmasi berulang.

## Scope dan stack

- Proyek pribadi baru, terpisah dari KartuNamaDigital dan repository lain.
- Vercel untuk Next.js/TypeScript; Supabase PostgreSQL/Auth/API; GitHub Actions untuk scanner Python/yfinance.
- MVP: KOMPAS100 EOD daily, MACD_EMA200_V1 + FRACTAL_BREAKOUT_V1 + RS_BREAKOUT_V1 + PULLBACK_RECLAIM_V1, exit modular fixed_rr/ma_close, paper journal, actual journal, statistik.
- AI opsional dan nonblocking. Tidak ada auto-order broker atau janji win rate.

## Invariants

1. Jangan mengarang market data, anggota indeks, broker fees, test results, atau deployment success.
2. Fixture hanya dev/test, diberi label; production live tidak boleh fallback ke mock.
3. Rule engine deterministik; AI tidak menghitung sinyal maupun metrik resmi.
4. Fractal level available-at berbeda dengan pivot date; jangan gunakan offset=-3 sebagai data trading.
5. Next-open belum diketahui malam sinyal. Tidak ada same-close fill default.
6. Data stale/missing berbeda dari no signal. Partial coverage selalu terlihat.
7. Paper dan actual terpisah. Initial risk tidak berubah karena stop digeser.
8. Daily SL/TP dual hit harus ditandai ambiguous, bukan dianggap urutan pasti.
9. Signal/trade/fill idempotent, audit dan data/config version dipertahankan.
10. Entry rules dan exit policy terpisah; config trade immutable; MA exit close-confirmed → next open, SL awal tetap. RS ranking memakai cross-section lengkap.
11. RLS owner-only diuji; service-role/AI keys tidak boleh masuk browser/log/repo.

## Cara kerja

- Audit repository dan git status sebelum edit. Jangan reset/drop/truncate DB, force-push, overwrite .env, atau merusak pekerjaan pengguna.
- Kerjakan milestone berurutan. Tanpa credentials, lanjutkan pekerjaan lokal yang memungkinkan dan laporkan langkah live yang belum bisa dilakukan.
- Jalankan test yang menguji risiko nyata: signal timing, lookahead, fill ambiguity, monetary ledger, RLS, idempotency.
- Pin dependency/runtime dan verifikasi dokumentasi resmi untuk versi/API yang digunakan.
- Tidak mengganti rule, sumber data, hosting, atau membuka paid tier secara diam-diam.
- Pertahankan atribusi © NielsG dan MPL-2.0 pada port Fractal Channel; tandai aturan transaksi sebagai tambahan proyek.
- Update IMPLEMENTATION_STATUS.md saat mulai implementasi dan setelah milestone, berdasarkan bukti.
- Remote provisioning/deploy mengikuti otorisasi dan akses pengguna. Paket dokumen bukan bukti bahwa resource remote sudah ada.
- Jangan menaruh secret ke chat. Beri daftar nama env dan lokasi konfigurasi saja.

## Definition of done

Kode, migrasi, kontrak, meaningful tests, dan docs konsisten; fixture/live jelas; smoke test sesuai milestone; output mencatat keterbatasan; tidak ada klaim implementasi yang belum diuji. Lihat CODEX_HANDOFF untuk gates rinci.
