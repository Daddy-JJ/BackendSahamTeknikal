# Synthetic fixtures only

Deterministic long OHLCV fixture: ../scanner/src/idx_scanner/fixtures.py.
Small timing/gap/ambiguity fixtures: ../scanner/tests.
Explicit file import examples: ../config/fixture-calendar.json and
../config/fixture-universe.json + CSV.

All tickers beginning DEMO- are synthetic, not IDX instruments or constituents.
Weekday fixture calendar is not an exchange calendar. Do not promote these
fixtures into a live database. Regenerate frontend snapshot through the Python CLI.
