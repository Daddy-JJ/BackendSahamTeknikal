# Addendum keputusan implementasi — 2026-09-28

Instruksi eksplisit terbaru pemilik mendahului baseline enam dokumen awal.
Addendum ini mencatat perubahan tanpa mengganti dokumen sumber.

| Keputusan | Status |
| --- | --- |
| Frontend source frontend/, localhost port 3050, target Vercel | APPROVED |
| Backend source backend/, API/database target Supabase | APPROVED |
| Scanner Python tetap di GitHub Actions saat remote siap | APPROVED |
| GitHub dibuat/disiapkan pemilik setelah ready to deploy | APPROVED |
| Tambahkan EODHD selain yfinance; API key disediakan kemudian | APPROVED |
| Kerjakan milestone berurutan, prioritaskan M0/M1 dan core deterministik | APPROVED |

## Perubahan terhadap TECHNICAL_DOC / handoff

apps/web menjadi frontend. Scanner berada di backend/scanner.
Supabase migrations/tests/functions berada di backend/supabase.
Kontrak bersama di contracts. API bisnis menggunakan Supabase Data API/RPC dan
Edge Functions jika diperlukan; endpoint ringan Vercel pada baseline bukan
implementasi wajib yang sudah ada. Tidak ada deploy/provisioning pada M0/M1.
Owner-auth dan RLS live harus terbukti sebelum frontend menerima data pribadi.

## Tambahan kebijakan provider terhadap SOT bagian 4

yfinance tetap sumber default yang dipilih eksplisit. EODHD adalah adapter
alternatif yang diotorisasi, bukan automatic fallback. Setiap run/cross-section
memakai satu provider dan satu basis harga. Provider/basis menjadi bagian hash
konfigurasi dan identitas sinyal, sehingga hasil antarprovider tidak digabung.

Yahoo: auto_adjust=False, actions=True, back_adjust=False, repair=False.
EODHD: OHLC unadjusted, adjusted_close disimpan terpisah hanya untuk audit;
split/dividend diminta terpisah. Tidak memakai endpoint indikator EODHD untuk
angka resmi. Tidak menyamakan raw/adjusted semantics antarprovider.

Corporate action yang belum direkonsiliasi menahan sinyal baru. Akses API,
mapping IDX, kalender/constituent resmi, kuota/histori, dan parity antarprovider
belum diverifikasi live. Tidak membuka paid tier atau mengganti sumber diam-diam.

Empat strategi, seed/warm-up, next-open, fractal available-at, initial risk,
ambiguous fills, fixed RR/MA, dan definisi statistik SOT tetap berlaku.
MPL-2.0 dan © NielsG dipertahankan; aturan transaksi adalah tambahan proyek.
