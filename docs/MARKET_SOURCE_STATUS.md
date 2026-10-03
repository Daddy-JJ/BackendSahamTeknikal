# Authoritative market source review - 2026-09-29

## Latest full-universe result — 2026-10-02

100 Yahoo identity mappings and100 actual fetches passed through2026-10-02.
Known2024–2026 calendar source dates and current execution timing are assembled
in config/live; historical dates do not claim execution hours. Monthly counts
match237/236/239. KPEI2024 primary attachment cites BEI and was visually reviewed;
owner original KOMPAS100 workbook provenance remains explicit. Current captured
data holds all100 tickers for zero-volume rows;78 also have unreconciled actions.
No raw audit bars were removed or corporate actions marked reconciled.
One production forward/live diagnostic exists with quality failed0/100,100 holds
and0 signals. Manual GitHub five-symbol IO passed; full GitHub publication and
quality readiness remain open. See SCANNER_LIVE_READINESS.md and evidence files.

## Verified baseline document

IDX announcement Peng-00171/BEI.POP/09-2025, dated 23 September 2025,
Kalender Libur Bursa Tahun 2026, downloaded from IDXCarbon's public host:
https://www.idxcarbon.co.id/document/share/158/0a901391-a0ad-4ca5-930e-2788cb7eb27f

Local ignored evidence: data/sources/idx-calendar-2026.pdf.
SHA-256: 5273a6f5724a5ac7f17027bdfcc8205ff8491e8299a6c0230347c59332e25324

All three pages were text-extracted; page 2's Indonesian calendar table was
rendered and visually inspected. There are 22 weekday holidays. Monthly trading
counts match [20,18,17,21,16,20,23,19,22,22,21,20], total 239.
Only the facts/metadata are committed in config/reference/idx-holidays-2026-source.json.
This is deliberately not a runnable Calendar config.

The public announcement page exposed an internal-host download URL. That private
host was not contacted; the same document path was fetched on the already-known
public idxcarbon.co.id host and returned an actual PDF.

## Remaining source gates

- Reconcile any subsequent amendments to the 2026 baseline.
- 2025 baseline and one official amendment are now transcribed in a reference file; original PDFs, checksums, visual review, later amendments, and 2024 calendar remain pending.
- Verify historical regular-equity open/close rules and their effective dates.
- The owner supplied the BEI KOMPAS100 July 2026 major-evaluation workbook and pasted its full roster. All 100 IDX ticker codes are transcribed in config/reference/kompas100-2026-08-transcribed.csv with period metadata in config/reference/kompas100-2026-08-source.json. Original workbook checksum/sheet review and provider mappings remain pending.
- Verify provider symbols against the selected provider; EODHD key remains pending.

A BEI 2025 amendment is available at:
https://www.idxcarbon.co.id/document/share/143/cf878b0d-87c1-45e2-98a5-4c54d6efc8c2
It adds 18 August 2025. This is evidence that amendments must be merged; no
2025 runtime calendar is claimed complete from this single reference.
Official index/holiday landing pages failed to open through the web tool during
this review. Missing documents do not justify weekday-only or invented configs.

No live provider scan or live database publication was performed.

## Additional official 2025 source review - 2026-09-29

IDXCarbon-hosted text extraction confirms baseline announcement Peng-00213/BEI.POP/10-2024 dated 2024-10-16 lists 237 trading days. The official amendment Peng-00149/BEI.POP/08-2025 dated 2025-08-08 adds 2025-08-18 as a market holiday. The listed weekday closures therefore reconcile to 236 trading days after this known amendment. Source dates and closure list are recorded in config/reference/idx-holidays-2025-source.json.

Sources:
- https://www.idxcarbon.co.id/document/share/109/e11c312a-95d6-4525-b71a-f70377cc7777
- https://www.idxcarbon.co.id/document/share/143/cf878b0d-87c1-45e2-98a5-4c54d6efc8c2

This is an official-source transcription, not a runtime calendar. The original PDFs have not yet been downloaded, hashed, and visually checked locally; subsequent amendments and historical session hours remain open. The full KOMPAS100 table is now recorded from the owner-provided official attachment transcription, not from media. Its source checksum and workbook sheet-level review remain pending. No provider scan or production write was performed.


## Official KOMPAS100 roster supplied by owner - 2026-09-29

The project owner supplied the workbook named "4. Lamp Peng-00148-BEI POP - KOMPAS100 - Jul 2026 Mayor.xlsx" and pasted its 100 IDX ticker codes. The stated effective period is 2026-08-03 through 2027-01-29 inclusive; the half-open interval for the loader is [2026-08-03, 2027-01-30). The transcribed list has 100 rows and 100 unique codes.

Reference files:
- config/reference/kompas100-2026-08-transcribed.csv
- config/reference/kompas100-2026-08-source.json

This remains a non-runtime source reference. Local workspace execution could not open the workbook, so its binary checksum, sheet structure and exact publication date are unverified. No provider symbol mapping or live scan is implied.

## Latest verified source continuation — 2026-10-02

Original workbook found under data/sources: SHA51b988ab5af2953e40603eb2884883120f2b727887ad014dc496a8c9cb0f4eb5; sheet1 C10:C109 matches all100 transcribed tickers and header confirms2026-07-27 publication and2026-08-03–2027-01-29 constituents. This supersedes the earlier missing-workbook statement. 2025 PDFs downloaded/hashed; five live Yahoo issuer mappings/fetches succeeded. Complete runtime calendar/history,95 mappings and actual GitHub runner remain open. See SCANNER_LIVE_READINESS.md.
