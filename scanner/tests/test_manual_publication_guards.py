"""Publisher guards use local doubles; never hosted deployment evidence."""

import importlib
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from idx_scanner.fixtures import sample_market
from idx_scanner.models import canonical_json
from idx_scanner.providers import FetchRequest


@pytest.fixture
def publisher(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "supabase/scripts"))
    return importlib.import_module("prepare_manual_publication")


def test_deadline_equality_and_preclose_fail(publisher):
    _, calendar, _ = sample_market(620)
    target = calendar.sessions[619].day
    publisher.window(calendar, target, calendar.get(target).closes_at)
    for now, code in ((calendar.get(target).closes_at - timedelta(seconds=1), "not_closed"),
                      (calendar.next(target).opens_at, "window_elapsed")):
        with pytest.raises(ValueError, match=code):
            publisher.window(calendar, target, now)


def test_plan_tamper_or_changed_inputs_rejected(publisher, tmp_path):
    path = tmp_path / "plan.json"
    plan = {"project_ref": publisher.REF, "run_digest": "approved", "counts": {"evaluated": 45}}
    path.write_text(json.dumps(plan))
    approved = publisher.sha(path)
    publisher.verify_plan(path, approved, plan)
    with pytest.raises(ValueError, match="inputs_changed"):
        publisher.verify_plan(path, approved, {**plan, "run_digest": "new"})
    path.write_text(json.dumps({**plan, "project_ref": "wrong"}))
    with pytest.raises(ValueError, match="checksum_mismatch"):
        publisher.verify_plan(path, approved, plan)


def test_complete_capture_digest_and_freshness_guard(publisher, tmp_path):
    series, calendar, _ = sample_market(620)
    target = calendar.sessions[619].day
    now = calendar.get(target).closes_at + timedelta(hours=1)
    original = next(iter(series.values()))
    live = replace(original, provider="yfinance", provider_symbol=original.ticker + ".JK",
                   fetched_at=now, provider_version="test-only")
    path = tmp_path / f"{live.ticker}.json"
    path.write_text(canonical_json(live), encoding="utf-8")
    requests = {live.ticker: FetchRequest(live.ticker, live.provider_symbol,
                                        live.bars[0].session, target, True)}
    raw, manifest = publisher.load_capture(tmp_path, requests, now)
    assert raw[live.ticker] == live
    assert manifest[0]["input_digest"] == live.input_digest
    with pytest.raises(ValueError, match="fetch_age"):
        publisher.load_capture(tmp_path, requests, now + timedelta(hours=24, seconds=1))
    with pytest.raises(ValueError, match="fetch_age"):
        publisher.load_capture(tmp_path, requests, now - timedelta(seconds=1))
    path.write_text(canonical_json(replace(live, bars=live.bars[:-1])), encoding="utf-8")
    with pytest.raises(ValueError, match="target_or_mapping"):
        publisher.load_capture(tmp_path, requests, now)


def test_unknown_files_or_missing_member_fail(publisher, tmp_path):
    (tmp_path / "unexpected.json").write_text("{}")
    with pytest.raises(ValueError, match="members_mismatch"):
        publisher.load_capture(tmp_path, {}, None)


@pytest.mark.parametrize("signals,ranking,counts", [
    ((object(),), "cross_section_incomplete",
     {"evaluated": 45, "corporate_action_hold": 25, "data_quality_hold": 30}),
    ((), "complete", {"evaluated": 45, "corporate_action_hold": 25, "data_quality_hold": 30}),
    ((), "cross_section_incomplete", {"evaluated": 100}),
])
def test_unreviewed_signals_quality_or_rs_fail(publisher, signals, ranking, counts):
    result = SimpleNamespace(signals=signals, ranking=SimpleNamespace(status=ranking),
                             items=[SimpleNamespace(status=s) for s, n in counts.items()
                                    for _ in range(n)])
    with pytest.raises(ValueError, match="new_review"):
        publisher.require_approved_result(result)


def test_wrong_project_or_missing_secret_cannot_open_database(publisher, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://wrong.supabase.co")
    monkeypatch.setattr(publisher, "BoundStore", lambda *a, **k: pytest.fail("DB must not open"))
    with pytest.raises(ValueError, match="target_mismatch"):
        publisher.execute({}, None, None, None, None, None, {})
    monkeypatch.setenv("SUPABASE_URL", f"https://{publisher.REF}.supabase.co")
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    with pytest.raises(ValueError, match="secret_missing"):
        publisher.execute({}, None, None, None, None, None, {})


def test_paged_readback_does_not_drop_201st_row(publisher):
    calls = []
    def request(method, table, params):
        calls.append((method, params["offset"]))
        start = int(params["offset"])
        return [{"id": i} for i in range(start, min(201, start + 200))]
    assert len(publisher.read_rows(SimpleNamespace(_request=request), "scan_run_items")) == 201
    assert calls == [("GET", "0"), ("GET", "200")]


@pytest.mark.parametrize("table,order", [
    ("actual_fill_corrections", "sequence.asc"),
    ("actual_journal_requests", "owner_id.asc,request_id.asc"),
    ("actual_trade_tags", "trade_id.asc,tag.asc"),
    ("scan_run_items", "run_id.asc,ticker.asc"),
    ("scan_run_signals", "run_id.asc,signal_id.asc"),
])
def test_composite_and_sequence_keys_use_schema_order(publisher, table, order):
    calls = []
    def request(method, requested_table, params):
        calls.append((requested_table, params["order"]))
        return []
    publisher.read_rows(SimpleNamespace(_request=request), table)
    assert calls == [(table, order)]


@pytest.mark.parametrize("change", ["none", "no_reviewers", "wrong_branch", "no_policy"])
def test_environment_without_required_approval_cannot_publish(publisher, change):
    guard = importlib.import_module("verify_publisher_environment")
    data = {"name": guard.ENVIRONMENT,
            "protection_rules": [{"type": "required_reviewers", "reviewers": [{"id": 1}]}],
            "deployment_branch_policy": {"protected_branches": False,
                                         "custom_branch_policies": True}}
    policies = [{"name": "main", "type": "branch"}]
    if change == "no_reviewers":
        data["protection_rules"] = []
    elif change == "wrong_branch":
        policies = [{"name": "*", "type": "branch"}]
    elif change == "no_policy":
        data["deployment_branch_policy"] = None
    if change == "none":
        guard.verify(data, policies)
    else:
        with pytest.raises(ValueError, match="protection_not_verified"):
            guard.verify(data, policies)


def test_before_write_hash_checkpoint_survives_ingest_failure(publisher, monkeypatch, tmp_path):
    class Store:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def require_live_schema(self):
            return None

        def load_state(self, **kwargs):
            return SimpleNamespace(signals=())

    monkeypatch.setattr(publisher, "ROOT", tmp_path)
    monkeypatch.setattr(publisher, "BoundStore", lambda *a, **k: Store())
    monkeypatch.setattr(publisher, "read_rows", lambda *a, **k: [
        {"id": "test-only-row", "private_body": "DO_NOT_PERSIST_RAW_ROW"}])
    monkeypatch.setattr(publisher, "window", lambda *a: None)
    monkeypatch.setenv("SUPABASE_URL", f"https://{publisher.REF}.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-only-not-a-credential")
    def fail_ingest(*args, **kwargs):
        assert (tmp_path / "data/manual-publication/latest-evidence.json").exists()
        raise RuntimeError("test-only-ingest-failure")
    monkeypatch.setattr(publisher, "run_once", fail_ingest)
    with pytest.raises(RuntimeError, match="ingest-failure"):
        publisher.execute({"target": "2026-10-02"}, None, None, None, None, None, {})
    text = (tmp_path / "data/manual-publication/latest-evidence.json").read_text()
    saved = json.loads(text)
    assert set(saved["before_journal_fingerprints"]) == set(publisher.LEDGER_ORDER)
    assert "DO_NOT_PERSIST_RAW_ROW" not in text
    assert saved["interrupted_execution_outcome"] == "unknown_until_get_reconciliation"
