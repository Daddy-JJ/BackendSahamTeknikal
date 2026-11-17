# HISTORICAL / NOT AN ACTIVE TASK / NOT AUTHORIZATION

Archived 21 October 2026 during documentation-only handover cleanup.
Source: `docs/LOCAL_PROVIDER_PROBE.md` at backend `719bc8c7f4deff2f945a0825cc92f6685cf48661`.
Source SHA-256 (original bytes): `e18eabce4ee37e27c572713b685d1a8fd31d40634e2d280cd5d629f14ddba19d`.
Source dates and proof boundaries remain those stated in the body. Earlier pending,
NO-GO, approval and execution language is historical and authorizes no new action.
Superseded for navigation by [current document](../LOCAL_PROVIDER_PROBE.md)
and [dated status](../../IMPLEMENTATION_STATUS.md); archiving does not resolve gaps.
Only this wrapper and relative Markdown link rebasing alter the retained original.

---

# Yahoo local connectivity probe — 2026-09-29 WIB

Purpose: provider_probe_not_published_signal. Sumber yfinance 1.7.0, simbol BBCA.JK.
[Halaman simbol Yahoo](https://finance.yahoo.com/quote/BBCA.JK/) memverifikasi mapping,
bukan keanggotaan KOMPAS100 atau kualitas seluruh history.

Perintah yang dijalankan dari backend/scanner:

```powershell
.\.venv\Scripts\python.exe -m idx_scanner.cli fetch --provider yfinance --ticker BBCA --symbol BBCA.JK --mapping-verified --start 2023-09-01 --end 2026-09-28 --output ../data/yahoo-bbca-probe.json
```

Hasil aktual:
- 739 baris provider: 733 bar lengkap, 5 missing OHLCV, 1 incomplete OHLCV.
- Rentang bar lengkap: 2023-09-01 sampai 2026-09-25.
- Missing OHLCV: 2026-05-01, 2026-06-01, 2026-06-16, 2026-08-17, 2026-08-25.
- Incomplete: 2026-09-28, close tidak tersedia walaupun sebagian field ada.
- 8 corporate actions dikembalikan provider; belum direkonsiliasi.
- Input digest: 2689da0233f8282ae750d2b5117b1b74552ba4f64947c3814592d7b9f2c4e4e6.
- Output lokal backend/data/yahoo-bbca-probe.json diabaikan Git.

Probe awal gagal validasi. Adapter kemudian memisahkan bar lengkap dari audit
ProviderRowIssue; tidak mengisi harga dan tidak menghapus jejak field parsial.
Regresi missing/partial/future-prefix ditambahkan; probe ulang berhasil parsing.

Tanggal missing belum dinyatakan sebagai hari libur: kalender resmi belum diimpor.
Incomplete row menahan kalkulasi sinyal melalui quality gate. Corporate actions
yang belum direkonsiliasi juga menahan sinyal. Tidak ada sinyal live atau fill
yang diterbitkan dan dashboard tetap menggunakan fixture.

Ini bukti fetch satu ticker dari mesin lokal, bukan verifikasi runner GitHub,
seluruh universe, data tanpa revisi, atau kesamaan hasil Yahoo/EODHD.
EODHD baru teruji melalui mocked transport; menunggu EODHD_API_TOKEN backend.
