import json
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "supabase" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import scheduled_scanner_runner as runner  # noqa: E402

from idx_scanner.incremental_provider import IncrementalProvider  # noqa: E402
from idx_scanner.reviewed_backfill import BACKFILL_VERSION, ReviewedBackfillProvider  # noqa: E402

pytest_plugins = ("test_paper_scheduler_integration",)


def test_checked_in_paper_backfill_allowlist_contains_only_reviewed_records():
    records = runner.load_reviewed_paper_backfill()
    assert len(records) == 7
    assert all(r.session == date(2026, 10, 12) for r in records)


@pytest.mark.parametrize("payload", [
    {"version": BACKFILL_VERSION, "data_mode": "fixture", "records": []},
    {"version": "unreviewed", "data_mode": "live", "records": []},
    {"version": BACKFILL_VERSION, "data_mode": "live", "records": [], "extra": True},
])
def test_invalid_backfill_configuration_fails_closed(tmp_path, payload):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid_reviewed_backfill_manifest"):
        runner.load_reviewed_paper_backfill(path)


def test_missing_backfill_configuration_does_not_silently_disable_validation(tmp_path):
    with pytest.raises(OSError):
        runner.load_reviewed_paper_backfill(tmp_path / "missing.json")


def test_duplicate_json_keys_cannot_change_reviewed_configuration(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text('{"version":"unreviewed","version":"' + BACKFILL_VERSION
                    + '","data_mode":"live","records":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid_reviewed_backfill_manifest"):
        runner.load_reviewed_paper_backfill(path)


@pytest.mark.parametrize("paper_only", [False, True])
def test_scheduler_wraps_only_paper_provider_and_preserves_stage_boundaries(
    scheduled, calendar, monkeypatch, paper_only,
):
    captured = {}
    original_run = runner.run_once
    original_paper = runner.complete_persisted_paper
    def publication(*args, **kwargs):
        captured["scanner_provider"] = args[0]
        return original_run(*args, **kwargs)
    def paper(*args, **kwargs):
        captured["paper_provider"] = args[8]
        return original_paper(*args, **kwargs)
    monkeypatch.setattr(runner, "run_once", publication)
    monkeypatch.setattr(runner, "complete_persisted_paper", paper)
    assert runner.run_scheduled_scanner(calendar.sessions[0].day, True,
                                        paper_only=paper_only) == 0
    provider = captured["paper_provider"]
    assert isinstance(provider, ReviewedBackfillProvider)
    assert provider.records == runner.load_reviewed_paper_backfill()
    assert isinstance(provider.provider, IncrementalProvider)
    if paper_only:
        assert "scanner_provider" not in captured
    else:
        assert isinstance(captured["scanner_provider"], IncrementalProvider)
        assert not isinstance(captured["scanner_provider"], ReviewedBackfillProvider)


def test_invalid_manifest_stops_before_any_database_writer(scheduled, calendar, monkeypatch):
    events, _, evidence = scheduled
    def fail():
        raise ValueError("invalid_reviewed_backfill_manifest: PRIVATE-REFERENCE")
    monkeypatch.setattr(runner, "load_reviewed_paper_backfill", fail)
    assert runner.run_scheduled_scanner(calendar.sessions[0].day, True, paper_only=True) == 1
    assert events == []
    report = json.loads(evidence.read_text())
    assert not report["production_write"] and report["status"] == "failed"
    assert "PRIVATE-REFERENCE" not in evidence.read_text()
