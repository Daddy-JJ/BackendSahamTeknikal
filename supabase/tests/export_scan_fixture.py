"""Synthetic engine output for SQL tests only. No network or credentials."""
import json
from datetime import timedelta

from idx_scanner.engine import scan
from idx_scanner.fixtures import sample_market
from idx_scanner.models import ScanState
from idx_scanner.persistence import scan_envelope

series, calendar, universe = sample_market(620)
session = calendar.sessions[619]
result = scan(series, session.day, calendar, universe,
              session.closes_at + timedelta(hours=3), ScanState())
print(json.dumps(scan_envelope(result, "forward", "fixture")))
