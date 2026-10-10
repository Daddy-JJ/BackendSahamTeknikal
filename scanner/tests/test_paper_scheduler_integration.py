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
        def record_job(self, **kwargs):
            events.append((kwargs["phase"], kwargs["status"]))
    scan = ScanResult(calendar.sessions[0].day, "complete", 1, 1,
                      Ranking("complete", (), (), "fixture"), (), (), "fixture")
    receipt = {"run_id": "22222222-2222-4222-8222-222222222222", "replayed": False}
    def publication(*args, **kwargs):
        events.append("publication")
        return SimpleNamespace(pipeline=PipelineResult(scan, (), (), (), ()),
                               publication=receipt)
    def paper(*args, **kwargs):
        events.append("paper")
        return None, {"trades_count": 2, "closed_count": 0,
                      "persistence": "supabase", "runtime_revision": 1, "data_hold_count": 0}
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
    assert events[:3] == ["schema", "owner", "activation"]
    assert events.index("publication") < events.index("paper")
    assert ("job", "succeeded") in events
    report = json.loads(evidence.read_text())
    assert report["production_write"] and report["paper_persistence"] == "supabase"


def test_publication_success_paper_commit_failure_is_not_false_green(
    scheduled, calendar, monkeypatch,
):
    _, _, evidence = scheduled
    def failure(*args, **kwargs):
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
    def failure(*args, **kwargs):
        raise ValueError("normalization_future_bars: provider payload must stay private")
    monkeypatch.setattr(runner, "complete_persisted_paper", failure)
    assert runner.run_scheduled_scanner(calendar.sessions[0].day, True) == 1
    report = json.loads(evidence.read_text())
    assert report["scanner_status"] == "published" and report["paper_status"] == "failed"
    assert report["failure"] == "paper_commit_error: validation_failed"
    assert "provider payload" not in evidence.read_text()


def test_scanner_failure_recovers_only_committed_book_and_job_stays_failed(
    scheduled, calendar, monkeypatch,
):
    events, _, evidence = scheduled
    def failure(*args, **kwargs):
        events.append("publication")
        raise PersistenceError("database_transport_failed")
    calls = []
    def recovery(*args, **kwargs):
        calls.append((args[2], args[9], kwargs["attempted_tickers"]))
        events.append("paper")
        return None, {"persistence": "supabase", "runtime_revision": 2, "data_hold_count": 0}
    monkeypatch.setattr(runner, "run_once", failure)
    monkeypatch.setattr(runner, "complete_persisted_paper", recovery)
    assert runner.run_scheduled_scanner(calendar.sessions[0].day, True) == 1
    assert calls == [({}, None, ())]
    report = json.loads(evidence.read_text())
    assert report["scanner_status"] == "failed" and report["paper_status"] == "complete"
    assert ("publication", "failed") in events and ("paper", "succeeded") in events
    assert ("job", "failed") in events


def test_explicit_paper_only_does_not_publish_or_regenerate_signals(scheduled, calendar):
    events, _, evidence = scheduled
    assert runner.run_scheduled_scanner(calendar.sessions[0].day, True, paper_only=True) == 0
    assert "publication" not in events and "paper" in events
    assert json.loads(evidence.read_text())["scanner_status"] == "skipped"


def test_expired_publication_window_still_recovers_persisted_paper(
    scheduled, calendar, monkeypatch,
):
    events, _, evidence = scheduled
    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return calendar.sessions[2].closes_at
    monkeypatch.setattr(runner, "datetime", Later)
    assert runner.run_scheduled_scanner(calendar.sessions[0].day, True) == 0
    assert "publication" not in events and "paper" in events
    assert json.loads(evidence.read_text())["scanner_status"] == "skipped"


def test_health_write_failure_cannot_report_success(scheduled, calendar, monkeypatch):
    events, _, evidence = scheduled
    def failed_record(self, **kwargs):
        raise PersistenceError("database_transport_failed")
    monkeypatch.setattr(runner.PaperRuntimeStore, "record_job", failed_record)
    assert runner.run_scheduled_scanner(calendar.sessions[0].day, True) == 1
    assert "publication" not in events and "paper" not in events
    assert json.loads(evidence.read_text())["status"] == "failed"


def test_preflight_failure_replaces_old_success_without_private_error(
    scheduled, monkeypatch,
):
    events, _, evidence = scheduled
    evidence.write_text('{"status":"old-success"}')
    def invalid_context():
        raise ValueError("private configuration contents must never appear")
    monkeypatch.setattr(runner, "load_manual_context", invalid_context)
    assert runner.run_scheduled_scanner(execute_publication=True) == 1
    report = json.loads(evidence.read_text())
    assert report["status"] == "failed" and not report["production_write"]
    assert report["failure"] == "preflight_error: configuration_invalid"
    assert events == [] and "private configuration" not in evidence.read_text()
