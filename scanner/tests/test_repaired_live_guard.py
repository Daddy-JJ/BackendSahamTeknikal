"""Operator guard tests use doubles; not hosted market or database evidence."""

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def helper(monkeypatch, tmp_path):
    scripts = Path(__file__).resolve().parents[2] / "supabase/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "repaired_guard_test", scripts / "publish_repaired_live_run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(module, "local_env", lambda *_: pytest.fail("unexpected secret read"))
    monkeypatch.setattr(module, "ObservedStore", lambda *_: pytest.fail("unexpected database IO"))
    return module


def test_corrupted_review_aborts_before_credentials_or_database(helper, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["test", "--execute"])

    def reject():
        raise ValueError("capture_checksum_mismatch")

    monkeypatch.setattr(helper, "prepare", reject)
    assert helper.main() == 1
    report = json.loads((helper.ROOT / "data/repaired-live-run-20261002.json").read_text())
    assert report["production_write_attempted"] is False


def test_expired_capture_aborts_before_quality_evaluation(helper, monkeypatch):
    now = datetime.now(UTC)
    calendar = SimpleNamespace(
        data_mode="live", next=lambda _: SimpleNamespace(opens_at=now - timedelta(seconds=1))
    )
    monkeypatch.setattr(
        helper,
        "prepare",
        lambda: (calendar, SimpleNamespace(data_mode="live"), (), {"X": None}, {}, {}),
    )
    monkeypatch.setattr(helper, "load_requests", lambda *_: {"X": None})
    with pytest.raises(ValueError, match="window_elapsed"):
        helper.reviewed_preflight(now)


@pytest.mark.parametrize("signals", [(), ("unexpected-signal",)])
def test_changed_quality_or_signal_scope_requires_new_review(helper, monkeypatch, signals):
    now = datetime.now(UTC)
    calendar = SimpleNamespace(
        data_mode="live", next=lambda _: SimpleNamespace(opens_at=now + timedelta(days=1))
    )
    statuses = ["valid"] * 11 + ["corporate_action_hold"] * 59 + ["data_quality_hold"] * 30
    if not signals:
        statuses[0] = "valid-new-status"
    values = {str(i): status for i, status in enumerate(statuses)}
    monkeypatch.setattr(
        helper,
        "prepare",
        lambda: (calendar, SimpleNamespace(data_mode="live"), (), values, {}, values),
    )
    monkeypatch.setattr(helper, "load_requests", lambda *_: values)
    monkeypatch.setattr(helper, "quality", lambda status, *_: status)
    monkeypatch.setattr(
        helper,
        "scan",
        lambda *_: SimpleNamespace(
            signals=signals, ranking=SimpleNamespace(status="cross_section_incomplete")
        ),
    )
    with pytest.raises(ValueError, match="partial_zero_signal"):
        helper.reviewed_preflight(now)
