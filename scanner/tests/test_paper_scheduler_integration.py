"""Scheduled publication/paper phase failures with explicit offline doubles."""
import json
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "supabase" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import scheduled_scanner_runner as runner  # noqa: E402

from idx_scanner.context import Universe  # noqa: E402
from idx_scanner.engine import ScanResult  # noqa: E402
from idx_scanner.persistence import PersistenceError  # noqa: E402
from idx_scanner.pipeline import PipelineResult  # noqa: E402
from idx_scanner.strategies import Ranking  # noqa: E402


@pytest.fixture
def scheduled(monkeypatch, calendar, tmp_path):
    clock = calendar.sessions[0].closes_at
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock if tz else clock.replace(tzinfo=None)
    events = []
    class ScanStore:
        def __init__(self, *args):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def require_live_schema(self):
            events.append("schema")
    class Runtime:
        def __init__(self, store, owner):
            events.append("owner")
        def initialize(self):
            events.append("activation")
    scan = ScanResult(calendar.sessions[0].day, "complete", 1, 1,
                      Ranking("complete", (), (), "fixture"), (), (), "fixture")
    receipt = {"run_id": "22222222-2222-4222-8222-222222222222", "replayed": False}
    def publication(*args, **kwargs):
        events.append("publication")
        return SimpleNamespace(pipeline=PipelineResult(scan, (), (), (), ()),
                               publication=receipt)
    def paper(*args):
        events.append("paper")
        return None, {"trades_count": 2, "closed_count": 0,
                      "persistence": "supabase", "runtime_revision": 1}
    universe = Universe(("TEST",), "fixture", calendar.sessions[0].day,
                        calendar.sessions[-1].day, "synthetic://test", "fixture")
    monkeypatch.setattr(runner, "datetime", Clock)
    monkeypatch.setattr(runner, "load_manual_context", lambda: (calendar, universe, ()))
    monkeypatch.setattr(runner, "load_requests", lambda *args: {})
    monkeypatch.setattr(runner, "SupabaseScanStore", ScanStore)
    monkeypatch.setattr(runner, "PaperRuntimeStore", Runtime)
    monkeypatch.setattr(runner, "run_once", publication)
    monkeypatch.setattr(runner, "complete_persisted_paper", paper)
    monkeypatch.setattr(runner, "SCHEDULED_DIR", tmp_path)
    monkeypatch.setattr(runner, "EVIDENCE_PATH", tmp_path / "evidence.json")
    monkeypatch.setenv("SUPABASE_URL", "https://fixture.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "offline-fixture-only")
    monkeypatch.setenv("APP_OWNER_USER_ID", "11111111-1111-4111-8111-111111111111")
    monkeypatch.setattr(runner, "process_paper_session", lambda *args: pytest.fail(
        "Live failure must never fall back to the local JSON book"))
    return events, scan, tmp_path / "evidence.json"


def test_activation_precedes_publication_and_successful_paper(scheduled, calendar):
    events, _, evidence = scheduled
    assert runner.run_scheduled_scanner(calendar.sessions[0].day, True) == 0
    assert events == ["schema", "owner", "activation", "publication", "paper"]
    report = json.loads(evidence.read_text())
    assert report["production_write"] and report["paper_persistence"] == "supabase"


def test_publication_success_paper_commit_failure_is_not_false_green(
    scheduled, calendar, monkeypatch,
):
    _, _, evidence = scheduled
    def failure(*args):
        raise PersistenceError("database_transport_failed")
    monkeypatch.setattr(runner, "complete_persisted_paper", failure)
    assert runner.run_scheduled_scanner(calendar.sessions[0].day, True) == 1
    report = json.loads(evidence.read_text())
    assert report["production_write"] and report["scanner_status"] == "published"
    assert report["paper_status"] == "failed"
    assert report["failure"] == "paper_commit_error: database_transport_failed"


def test_zero_scanner_coverage_still_advances_existing_paper(scheduled, calendar, monkeypatch):
    events, scan, evidence = scheduled
    failed = replace(scan, coverage_valid=0, status="failed")
    # The committed run may have no usable new signals; existing positions still need holds/exits.
    def zero(*args, **kwargs):
        events.append("publication")
        return SimpleNamespace(pipeline=PipelineResult(failed, (), (), (), ()),
                               publication={"run_id": "22222222-2222-4222-8222-222222222222"})
    monkeypatch.setattr(runner, "run_once", zero)
    assert runner.run_scheduled_scanner(calendar.sessions[0].day, True) == 1
    assert "paper" in events
    assert json.loads(evidence.read_text())["paper_status"] == "complete"


def test_paper_validation_failure_reports_current_failed_stage(
    scheduled, calendar, monkeypatch,
):
    _, _, evidence = scheduled
    evidence.write_text('{"status":"old-success"}')
    def failure(*args):
        raise ValueError("normalization_future_bars: provider payload must stay private")
    monkeypatch.setattr(runner, "complete_persisted_paper", failure)
    assert runner.run_scheduled_scanner(calendar.sessions[0].day, True) == 1
    report = json.loads(evidence.read_text())
    assert report["scanner_status"] == "published" and report["paper_status"] == "failed"
    assert report["failure"] == "paper_commit_error: validation_failed"
    assert "provider payload" not in evidence.read_text()
