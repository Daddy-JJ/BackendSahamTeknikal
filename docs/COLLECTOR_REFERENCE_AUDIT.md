# Read-only Yahoo collector study - 2026-10-03

## Result

The owner-supplied collector at
`D:\Saham2026\AntiGravity-Dashboard-IDX\collector` is useful as a direct Yahoo
Chart API reference and for long-history retrieval. The actual comparison did
not resolve the current scanner's quality/corporate-action holds. Its source
files were not changed; SHA256 of all five collector Python files matched before
and after the study. The collector's main sync, shared DB setup, company seeding,
fundamentals, news, foreign-flow and broker ingestion were never executed.

## Source behavior reviewed

- `yahoo.py`: HTTPX async client, Chart v8 JSON, browser-style request headers,
  bounded retry/backoff on HTTP429. `fetch_chart` requests range/interval and
  `includePrePost=false` without an explicit events parameter.
- `daily_sync.py`: price sync asks for `5y`/`1d`. Four sampled established
  tickers had more than 600 converted rows, while COIN remained below 600.
- `chart_to_daily_rows`: rows with close=null are skipped; volume=null is
  converted to zero. Those semantics hide the distinction between incomplete
  data, unknown volume and observed zero volume required by SOT.
- Daily storage skips existing company/date rows instead of preserving new
  provider revisions. This cannot replace the scanner's immutable raw/derived
  revision model or update corrected historical observations by itself.
- Conversion uses UTC calendar date. No UTC/WIB date mismatch was observed in
  these daily responses, but a scanner adapter should retain an explicit exchange
  timezone check rather than generalize from this sample.

The pinned local yfinance source also requests the same Chart v8 endpoint and
adds dividend/split event parameters. Its primary repository documents the
implementation in [history.py](https://github.com/ranaroussi/yfinance/blob/main/yfinance/scrapers/history.py).
Switching transport does not establish an independent market-data source.

## Actual read-only comparison

Eight HTTP GET requests completed with HTTP200 on 2026-10-03 around 00:05 WIB:
five exact collector-style requests (5y/1d), one fixed-date AMMN diagnostic, and
two fixed-date AMMN/BBCA requests with event metadata. Only OHLCV and technical
audit metadata were examined; no financial-statement endpoints were requested.
Raw responses are ignored local artifacts in `data/collector-study-20261003/`.

| Ticker | Converted 5y rows | First date | Latest complete date | Common dates versus prior capture | Differing OHLCV rows |
| --- | ---: | --- | --- | ---: | ---: |
| AMMN | 775 | 2023-07-07 | 2026-10-01 | 654 | 0 |
| BBCA | 1202 | 2021-10-04 | 2026-10-01 | 654 | 0 |
| BRPT | 1203 | 2021-10-04 | 2026-10-01 | 655 | 0 |
| BUMI | 1203 | 2021-10-04 | 2026-10-01 | 655 | 0 |
| COIN | 302 | 2025-07-09 | 2026-10-01 | 302 | 0 |

These are converted provider row counts, not counts certified as continuous
valid exchange sessions. They include 4-5 known closed-day volume-zero rows.
All five response conversions skipped 5-6 close-null rows. In these samples,
none of the rows with a present close had a missing volume, so the converter's
missing-volume-to-zero behavior was identified statically rather than observed
as a new live defect.

AMMN retained exactly the three known zero-volume open-session rows:
2024-01-15, 2024-03-25 and 2024-03-26. COIN retained all seven:
2025-07-17, 2025-07-22, 2025-07-23, 2025-08-26 through 2025-08-29.
The collector therefore did not repair the sampled problematic Yahoo bars.

All five range responses lacked a complete 2026-10-02 close. Fixed-window
AMMN and BBCA requests also returned the target day's open/high/low/volume
with close=null. Adding dividend/split event parameters did not complete that
close. This is the observed response at the study time, not a claim that the
previous immutable 2026-10-02 capture was incomplete or should be rewritten.
Do not fill the missing close from regularMarketPrice or previous_close.

The exact collector-style responses had no event metadata. The BBCA diagnostic
with an explicit events parameter returned seven dividends. Missing event data
in the collector response cannot prove there were no corporate actions or clear
the scanner's 59 action holds. Primary-source approval remains required.

## Decision and safe reuse

Retain the current provider and production runs. The study did not create a new
scan, signal, trade, schema change, fallback or schedule. No engine code was
changed. Independent collector transport can be retained as a diagnostics tool,
with raw response hashes and a fixed target window; HTTP429 backoff is useful.
Adoption into scanner execution would need the existing explicit calendar,
identity, null-data, action provenance and immutable-revision contracts.

Scanner quality remains NO-GO: 30 data-quality holds, 59 corporate-action holds,
RS incomplete and full GitHub publication pending. The longer 5y request can
help established ticker warm-up, but cannot create pre-IPO COIN history or
resolve suspension/zero-volume classification. Financial statements remain
outside the requested scanner scope.
