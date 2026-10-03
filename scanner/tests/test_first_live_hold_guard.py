"""A hold-only operator helper must never turn into a signal publisher."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def helper(monkeypatch, tmp_path):
    scripts = Path(__file__).resolve().parents[2] / "supabase/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "first_live_hold_guard_under_test", scripts / "publish_first_live_hold_run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(module, "local_env", lambda *_: pytest.fail("unexpected secret read"))
    monkeypatch.setattr(module, "ObservedStore", lambda *_: pytest.fail("unexpected database IO"))
    return module


def test_corrupted_capture_fails_before_credentials_or_database(helper, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["smoke", "--execute"])
    monkeypatch.setattr(helper, "load_calendar", lambda *_: SimpleNamespace(data_mode="live"))
    monkeypatch.setattr(helper, "load_universe", lambda *_: SimpleNamespace(data_mode="live"))
    monkeypatch.setattr(helper, "load_requests", lambda *_: {})

    def reject_capture():
        raise ValueError("capture_checksum_mismatch")

    monkeypatch.setattr(helper, "captured_series", reject_capture)
    assert helper.main() == 1
    report = json.loads((helper.ROOT / "data/first-live-hold-run-20261002.json").read_text())
    assert report["production_write_attempted"] is False


def test_nonzero_eligibility_cannot_publish_even_with_execute(helper, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["smoke", "--execute"])
    session = SimpleNamespace(day=helper.TARGET, opens_at=helper.datetime.now(helper.UTC))
    calendar = SimpleNamespace(data_mode="live", version="test", next=lambda _: session)
    universe = SimpleNamespace(data_mode="live", version="test", tickers=("TEST",))
    monkeypatch.setattr(helper, "load_calendar", lambda *_: calendar)
    monkeypatch.setattr(helper, "load_universe", lambda *_: universe)
    monkeypatch.setattr(helper, "load_requests", lambda *_: {"TEST": None})
    monkeypatch.setattr(helper, "captured_series", lambda: {"TEST": None})
    monkeypatch.setattr(
        helper,
        "scan",
        lambda *_: SimpleNamespace(
            status="complete",
            coverage_valid=1,
            coverage_total=1,
            signals=(),
            items=(),
        ),
    )
    assert helper.main() == 1
    report = json.loads((helper.ROOT / "data/first-live-hold-run-20261002.json").read_text())
    assert report["stage"] == "offline_configuration"
    assert report["production_write_attempted"] is False
