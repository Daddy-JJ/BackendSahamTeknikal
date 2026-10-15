# Development decisions index

[SOT](SOT.md) is the synchronized trading-policy snapshot. [TECHNICAL_DOC](TECHNICAL_DOC.md)
contains the architecture map; [DEVELOPMENT](DEVELOPMENT.md) contains commands.

- frontend and backend are independent repositories; run backend Git here.
- Cloud runtime secrets are provisioned separately from local operator env files.
- Provider selection is explicit; EODHD is not an automatic Yahoo fallback.
- Versioned paper entry/fee/exit and approved dividend handling follow SOT.

[Original28September addendum](docs/archive/DEVELOPMENT_ADDENDUM_BEFORE_DOC_CLEANUP_20261015.md)
is historical; early next-open/setup status does not override the current versioned model.
