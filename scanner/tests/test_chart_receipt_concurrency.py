"""Parallel read-only chart sources preserve order, budgets and atomic projection."""

import threading
import time
from uuid import UUID

import pytest
from test_chart_runtime import OWNER, inputs

from idx_scanner.chart_runtime import ChartArtifactStore, run_chart_job
from idx_scanner.persistence import PersistenceError


def test_receipt_reads_are_bounded_parallel_and_return_source_order(monkeypatch):
    receipt, _, bundle, raw = inputs()
    ids = [str(UUID(int=i + 1)) for i in range(8)]
    rows = [{**bundle["market_revisions"][0], "id": key} for key in ids]
    lock = threading.Lock()
    active, peak = 0, 0
    requested, completed = [], []
    class Base:
        def _request(self, method, path, *, json):
            nonlocal active, peak
            assert method == "POST" and path == "rpc/read_market_series"
            identity = json["p_revision_id"]
            with lock:
                active += 1
                peak = max(peak, active)
                requested.append(identity)
            try:
                # Early sources deliberately complete after later sources.
                time.sleep(0.02 * (4 - ids.index(identity) % 4))
                with lock:
                    completed.append(identity)
                return {**raw, "revision_id": identity}
            finally:
                with lock:
                    active -= 1
    monkeypatch.setattr("idx_scanner.chart_runtime.series_from_revision",
                        lambda _: receipt.series)
    result = ChartArtifactStore(Base(), OWNER, "fixture").receipts(rows, receipt.series.ticker)
    assert peak == 4 and active == 0
    assert len(requested) == len(ids) and set(requested) == set(ids)
    assert completed != ids
    assert [r.series_id for r in result] == ids
    assert all(r.series is receipt.series for r in result)


def test_one_bad_receipt_prevents_any_artifact_build_or_write(monkeypatch):
    receipt, _, bundle, raw = inputs()
    rows = [{**bundle["market_revisions"][0], "id": str(UUID(int=i + 1))} for i in range(8)]
    reads = []
    class Base:
        def _request(self, method, path, *, json):
            if path == "rpc/prune_ticker_chart_cursors_v1":
                return {"deleted": 0, "has_more": False}
            if path == "rpc/load_ticker_chart_inputs_v1":
                return {**bundle, "market_revisions": rows} if json["p_ticker"] else {
                    "owner_id": OWNER, "data_mode": "fixture", "tickers": [receipt.series.ticker]}
            assert path == "rpc/read_market_series", "unexpected write or economic request"
            identity = json["p_revision_id"]
            reads.append(identity)
            return {**raw, "revision_id": identity,
                    "input_digest": "invalid" if identity == rows[1]["id"] else raw["input_digest"]}
    monkeypatch.setattr("idx_scanner.chart_runtime.series_from_revision",
                        lambda _: receipt.series)
    monkeypatch.setattr("idx_scanner.chart_runtime.build_context_records",
                        lambda *args, **kwargs: pytest.fail("partial source set projected"))
    result = run_chart_job(ChartArtifactStore(Base(), OWNER, "fixture"),
                            observed_at=receipt.stored_at, execute=True)
    assert result["status"] == "failed" and result["written"] == result["prepared"] == 0
    assert result["failures"] == [{"ticker": receipt.series.ticker,
                                   "code": "chart_invalid_market_revision"}]
    assert len(reads) == len(set(reads)) <= len(rows)


def test_empty_receipts_make_no_requests():
    class Base:
        def _request(self, *args, **kwargs):
            pytest.fail("empty sources requested")
    assert ChartArtifactStore(Base(), OWNER, "fixture").receipts([], "ADRO") == ()


def test_all_source_modes_are_validated_before_dispatch():
    receipt, _, bundle, _ = inputs()
    valid = bundle["market_revisions"][0]
    class Base:
        def _request(self, *args, **kwargs):
            pytest.fail("source read before all modes were checked")
    store = ChartArtifactStore(Base(), OWNER, "fixture")
    for invalid in ({**valid, "data_mode": "live"}, {**valid, "ticker": "WRONG"}, None):
        with pytest.raises(PersistenceError, match="chart_market_mode_mismatch"):
            store.receipts([valid, invalid], receipt.series.ticker)


def test_failed_receipt_cancels_queued_reads_and_waits_for_inflight(monkeypatch):
    receipt, _, bundle, raw = inputs()
    rows = [{**bundle["market_revisions"][0], "id": str(UUID(int=i + 1))} for i in range(20)]
    requested, completed = [], []
    class Base:
        def _request(self, method, path, *, json):
            assert path == "rpc/read_market_series"
            identity = json["p_revision_id"]
            requested.append(identity)
            if identity == rows[0]["id"]:
                return {**raw, "revision_id": identity, "input_digest": "invalid"}
            time.sleep(0.1)
            completed.append(identity)
            return {**raw, "revision_id": identity}
    monkeypatch.setattr("idx_scanner.chart_runtime.series_from_revision",
                        lambda _: receipt.series)
    with pytest.raises(PersistenceError, match="chart_invalid_market_revision"):
        ChartArtifactStore(Base(), OWNER, "fixture").receipts(rows, receipt.series.ticker)
    assert 1 <= len(requested) < len(rows)
    assert set(completed) == set(requested) - {rows[0]["id"]}
