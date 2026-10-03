"""Known trading dates do not imply historical execution times."""

import json
from dataclasses import replace
from datetime import timedelta

import pytest

from idx_scanner.config_io import load_calendar
from idx_scanner.context import quality
from idx_scanner.engine import scan
from idx_scanner.fixtures import sample_market
from idx_scanner.models import ScanState, canonical_json


def test_date_only_warmup_preserves_results_without_inventing_timing():
    series, calendar, universe = sample_market(620)
    target = calendar.sessions[619]
    split = replace(
        calendar,
        historical_days=tuple(s.day for s in calendar.sessions[:619]),
        sessions=calendar.sessions[619:],
    )
    observed = target.closes_at + timedelta(hours=3)
    assert quality(series["DEMO-A"], target.day, split) == "valid"
    assert canonical_json(scan(series, target.day, split, universe, observed, ScanState())) == (
        canonical_json(scan(series, target.day, calendar, universe, observed, ScanState()))
    )
    with pytest.raises(ValueError, match="session unknown"):
        split.get(split.historical_days[-1])
    with pytest.raises(ValueError, match="session unknown"):
        scan(series, split.historical_days[-1], split, universe, observed, ScanState())


def test_unknown_history_start_and_overlapping_dates_are_rejected():
    _, calendar, _ = sample_market(620)
    split = replace(calendar, historical_days=(), sessions=calendar.sessions[619:])
    with pytest.raises(ValueError, match="history start session unknown"):
        split.between(calendar.sessions[0].day, calendar.sessions[619].day)
    with pytest.raises(ValueError, match="must precede"):
        replace(split, historical_days=(split.sessions[0].day,))
    with pytest.raises(ValueError, match="must precede"):
        replace(split, historical_days=(calendar.sessions[1].day, calendar.sessions[0].day))


def test_loader_keeps_date_only_history_explicit(tmp_path):
    _, calendar, _ = sample_market(620)
    target = calendar.sessions[619]
    path = tmp_path / "calendar.json"
    path.write_text(
        json.dumps(
            {
                "data_mode": "fixture",
                "version": "date-only-v1",
                "source": "synthetic://test",
                "historical_days": [calendar.sessions[0].day.isoformat()],
                "sessions": [
                    {
                        "day": target.day.isoformat(),
                        "opens_at": target.opens_at.isoformat(),
                        "closes_at": target.closes_at.isoformat(),
                    }
                ],
            }
        )
    )
    loaded = load_calendar(path)
    assert loaded.historical_days == (calendar.sessions[0].day,)
    assert loaded.get(target.day).opens_at == target.opens_at
    with pytest.raises(ValueError, match="session unknown"):
        loaded.get(loaded.historical_days[0])
