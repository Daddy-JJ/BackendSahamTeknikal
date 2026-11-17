# HISTORICAL / NOT AN ACTIVE TASK / NOT AUTHORIZATION

Archived 21 October 2026. Source: `DEVELOPMENT_ADDENDUM.md` at backend `719bc8c7f4deff2f945a0825cc92f6685cf48661`.
Source SHA-256 (original bytes): `516e86b576bdb0c64e713d9165699c542a65b2849c7d163746ac50483c145fff`.
Only wrapper and relative Markdown link rebasing alter the retained original.
Current [architecture](../../TECHNICAL_DOC.md), [development](../../DEVELOPMENT.md), [status](../../IMPLEMENTATION_STATUS.md).

---

# Development decisions index

[SOT](../../SOT.md) is the synchronized trading-policy snapshot. [TECHNICAL_DOC](../../TECHNICAL_DOC.md)
contains the architecture map; [DEVELOPMENT](../../DEVELOPMENT.md) contains commands.

- frontend and backend are independent repositories; run backend Git here.
- Cloud runtime secrets are provisioned separately from local operator env files.
- Provider selection is explicit; EODHD is not an automatic Yahoo fallback.
- Versioned paper entry/fee/exit and approved dividend handling follow SOT.

[Original28September addendum](DEVELOPMENT_ADDENDUM_BEFORE_DOC_CLEANUP_20261015.md)
is historical; early next-open/setup status does not override the current versioned model.
