"""Bounded revision growth: no source truncation, provider IO, or economic writes."""

import importlib
import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from test_chart_runtime import OWNER, inputs

from idx_scanner.chart_runtime import ChartArtifactStore, run_chart_job
from idx_scanner.persistence import PersistenceError, SupabaseScanStore


@pytest.mark.parametrize("count", [129, 131])
def test_default_receipt_budget_accepts_all_persisted_revisions(count):
    receipt, _, bundle, raw = inputs()
    rows = [{**bundle["market_revisions"][0], "id": str(UUID(int=i + 1))}
            for i in range(count)]
    reads = []
    def handle(request):
        assert request.url.path.endswith("rpc/read_market_series")
        identity = json.loads(request.content)["p_revision_id"]
        reads.append(identity)
        return httpx.Response(200, json={**raw, "revision_id": identity})
    with SupabaseScanStore("https://test.supabase.co", "synthetic-key",
                           transport=httpx.MockTransport(handle)) as base:
        receipts = ChartArtifactStore(base, OWNER, "fixture").receipts(rows, receipt.series.ticker)
    assert reads == [row["id"] for row in rows]
    assert [r.series_id for r in receipts] == reads
    assert all(r.series.input_digest == receipt.series.input_digest for r in receipts)


def test_default_and_explicit_receipt_limits_fail_before_any_rpc():
    class NeverRequest:
        def _request(self, *args, **kwargs):
            pytest.fail("over-budget revision list must fail before reading or writing")
    store = ChartArtifactStore(NeverRequest(), OWNER, "fixture")
    with pytest.raises(PersistenceError, match="chart_revision_budget_exhausted"):
        store.receipts([{}] * 257, "ADRO")
    with pytest.raises(PersistenceError, match="chart_revision_budget_exhausted"):
        store.receipts([{}] * 129, "ADRO", maximum=128)


def test_job_default_increases_bound_without_changing_explicit_override(monkeypatch):
    receipt, _, bundle, _ = inputs()
    budgets = []
    class Store:
        data_mode = "fixture"
        def load(self, ticker=None):
            return bundle if ticker else {"tickers": [receipt.series.ticker]}
        def receipts(self, rows, ticker, *, maximum):
            budgets.append(maximum)
            return (receipt,)
    monkeypatch.setattr("idx_scanner.chart_runtime.build_context_records",
                        lambda *args, **kwargs: ([], []))
    assert run_chart_job(Store(), observed_at=receipt.stored_at)["status"] == "ready"
    run_chart_job(Store(), observed_at=receipt.stored_at, max_revisions=131)
    assert budgets == [256, 131]
    for invalid in (0, 501):
        with pytest.raises(ValueError, match="invalid_chart_job_budget"):
            run_chart_job(Store(), observed_at=receipt.stored_at, max_revisions=invalid)


def test_cli_uses_shared_default_and_preserves_explicit_override(monkeypatch, capsys):
    scripts = Path(__file__).resolve().parents[2] / "supabase/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    runner = importlib.import_module("chart_artifact_runner")
    for name, value in (("SUPABASE_URL", "https://test.supabase.co"),
                        ("SUPABASE_SECRET_KEY", "synthetic-key"), ("APP_OWNER_USER_ID", OWNER)):
        monkeypatch.setenv(name, value)
    budgets = []
    def run(store, **kwargs):
        budgets.append(kwargs["max_revisions"])
        return {"status": "ready"}
    monkeypatch.setattr(runner, "run_chart_job", run)
    assert runner.main([]) == 0
    assert runner.main(["--max-revisions", "131"]) == 0
    assert budgets == [256, 131]
    assert "synthetic-key" not in capsys.readouterr().out
