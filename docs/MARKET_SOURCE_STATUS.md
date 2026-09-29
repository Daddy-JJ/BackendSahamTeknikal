# Authoritative market source review - 2026-09-29

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
- Obtain and verify 2024/2025 calendars and amendments, needed for 600 bars.
- Verify historical regular-equity open/close rules and their effective dates.
- Obtain the full effective KOMPAS100 constituent attachment. News references
  Peng-00148/BEI.POP/07-2026, attachment 4, but the original full attachment has
  not yet been verified. No news-derived ticker list has been imported.
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

This is an official-source transcription, not a runtime calendar. The original PDFs have not yet been downloaded, hashed, and visually checked locally; subsequent amendments and historical session hours remain open. The same primary-source search did not locate the full KOMPAS100 attachment 4. Media extracts are not being used as universe data. No provider scan or production write was performed.
