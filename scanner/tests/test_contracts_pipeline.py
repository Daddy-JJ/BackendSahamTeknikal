import json
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from idx_scanner.config_io import load_calendar, load_universe
from idx_scanner.demo import demo_snapshot
from idx_scanner.fixtures import sample_market
from idx_scanner.models import ScanState, canonical_json
from idx_scanner.pipeline import collect_and_scan
from idx_scanner.providers import FetchRequest, ProviderError


def test_demo_matches_contract_is_reproducible_and_current():
    root = Path(__file__).resolve().parents[2]
    signal = json.loads((root / "contracts/signal.schema.json").read_text())
    schema = json.loads((root / "contracts/demo-snapshot.schema.json").read_text())
    registry = Registry().with_resource(signal["$id"], Resource.from_contents(signal))
    validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    current = canonical_json(demo_snapshot())
    payload = json.loads(current)
    validator.validate(payload)
    assert current == canonical_json(demo_snapshot())
    committed = json.loads(
        (root / "contracts/demo-snapshot.fixture.json").read_text(encoding="utf-8")
    )
    assert payload == committed
    for signal in payload["signals"]:
        assert signal["planned_entry_session"] > signal["session"]


def test_partial_provider_pipeline_does_not_fallback():
    series, calendar, universe = sample_market(620)
    target = calendar.sessions[619]
    calls = []

    class FakeProvider:
        def fetch(self, request):
            calls.append(request.ticker)
            if request.ticker == "DEMO-B":
                raise ProviderError("provider_rate_limited")
            return series[request.ticker]

    requests = {
        t: FetchRequest(t, t, calendar.sessions[0].day, target.day, True) for t in universe.tickers
    }
    result = collect_and_scan(
        FakeProvider(),
        requests,
        target.day,
        calendar,
        universe,
        target.closes_at + timedelta(hours=3),
        ScanState(),
    )
    assert len(calls) == 5
    assert result.provider_errors == (("DEMO-B", "provider_rate_limited"),)
    assert result.scan.coverage_valid == 4
    assert result.scan.ranking.status == "cross_section_incomplete"


def test_calendar_and_universe_import_require_provenance(tmp_path):
    calendar_path = tmp_path / "calendar.json"
    calendar_path.write_text(
        json.dumps(
            {"data_mode": "live", "version": "v1", "source": "synthetic://x", "sessions": []}
        )
    )
    with pytest.raises(ValueError, match="https"):
        load_calendar(calendar_path)
    metadata = {
        "data_mode": "fixture",
        "version": "fixture",
        "source": "synthetic://test",
        "effective_from": "2026-01-01",
        "effective_to": "2026-02-01",
    }
    meta_path = tmp_path / "universe.json"
    meta_path.write_text(json.dumps(metadata))
    csv_path = tmp_path / "universe.csv"
    csv_path.write_text("ticker\nDEMO-A\nDEMO-A\n")
    with pytest.raises(ValueError):
        load_universe(meta_path, csv_path)
    csv_path.write_text("ticker\nDEMO-A\n")
    imported = load_universe(meta_path, csv_path)
    assert imported.tickers == ("DEMO-A",)


def test_pipeline_blocks_bad_calendar_before_chargeable_fetch():
    from dataclasses import replace

    series, calendar, universe = sample_market(620)
    target = calendar.sessions[619]
    invalid = replace(calendar, sessions=calendar.sessions[:620])
    calls = []

    class Spy:
        def fetch(self, request):
            calls.append(request.ticker)
            return series[request.ticker]

    requests = {
        t: FetchRequest(t, t, calendar.sessions[0].day, target.day, True) for t in universe.tickers
    }
    with pytest.raises(ValueError, match="blocked_configuration"):
        collect_and_scan(
            Spy(), requests, target.day, invalid, universe, target.closes_at, ScanState()
        )
    assert not calls
