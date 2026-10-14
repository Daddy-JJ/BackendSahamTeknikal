"""Cloud artifact writer mock transport; no private data or provider requests."""

import json
from dataclasses import asdict, replace
from datetime import timedelta

import httpx
import pytest

from idx_scanner.chart_artifact import ChartReceipt, cutoff_series
from idx_scanner.chart_runtime import ChartArtifactStore, build_context_records, run_chart_job
from idx_scanner.fixtures import sample_market
from idx_scanner.models import canonical_json
from idx_scanner.persistence import PersistenceError, SupabaseScanStore, market_series_envelope

OWNER = "22222222-2222-4222-8222-222222222222"


def inputs():
    sources, calendar, _ = sample_market(660)
    series = replace(next(iter(sources.values())), fetched_at=calendar.sessions[659].closes_at)
    receipt = ChartReceipt("11111111-1111-4111-8111-111111111111", "forward", "fixture",
                           series, series.fetched_at)
    source_record = market_series_envelope(series, namespace="forward", data_mode="fixture")[
        "p_record"]
    revision = {**source_record, "id": receipt.series_id,
                "stored_at": series.fetched_at.isoformat()}
    raw = {"revision_id": receipt.series_id, **source_record}
    day = series.bars[620].session
    signal = {"id": "a" * 64, "ticker": series.ticker, "session": str(day),
              "input_digest": cutoff_series(series, day).input_digest,
              "provider": "fixture", "price_basis": series.price_basis,
              "provider_version": series.provider_version, "data_mode": "fixture",
              "planned_entry_session": str(series.bars[621].session),
              "candidate": {"reference_close": "1000", "stop": "925", "level": None}}
    paper = {"id": "paper-legacy-text", "signal": signal, "planned_entry_price": "1000",
             "target": "1150", "experiment": {"id": "fixed2r"}, "events": []}
    bundle = {"owner_id": OWNER, "data_mode": "fixture", "ticker": series.ticker,
              "calendar": json.loads(canonical_json(asdict(calendar))),
              "market_revisions": [revision], "signals": [{"id": signal["id"],
              "snapshot": signal}], "paper_trades": [{"id": paper["id"], "details": paper}],
              "paper_events": [], "actual_trades": [], "actual_fills": [], "actual_stops": [],
              "evaluations": []}
    return receipt, calendar, bundle, raw


def test_all_contexts_generated_and_repeat_has_identical_revision():
    receipt, calendar, bundle, _ = inputs()
    at = receipt.stored_at
    records, errors = build_context_records(bundle, (receipt,), calendar, observed_at=at)
    assert not errors
    assert len(records) == 5
    assert {(r["context_kind"], r["view"]) for r in records} == {
        ("latest", "followup"), ("signal", "snapshot"), ("signal", "followup"),
        ("paper", "snapshot"), ("paper", "followup")}
    again, _ = build_context_records(bundle, (receipt,), calendar, observed_at=at)
    assert records == again


def test_missing_historical_proof_explicit_context_error_but_latest_survives():
    receipt, calendar, bundle, _ = inputs()
    broken = {**bundle, "signals": [{"id": "a" * 64, "snapshot": {
        **bundle["signals"][0]["snapshot"], "input_digest": "f" * 64}}], "paper_trades": []}
    records, errors = build_context_records(broken, (receipt,), calendar,
                                            observed_at=receipt.stored_at)
    assert len(records) == 1
    assert errors == [{"context_kind": "signal", "code": "snapshot_unavailable"}]


def test_cloud_rpc_owner_mode_validation_and_idempotent_writer():
    receipt, _, bundle, raw = inputs()
    writes = []
    def handle(request):
        path = request.url.path
        body = json.loads(request.content)
        if path.endswith("prune_ticker_chart_cursors_v1"):
            assert body == {"p_limit": 10000}
            return httpx.Response(200, json={"deleted": 2, "has_more": False})
        if path.endswith("load_ticker_chart_inputs_v1"):
            if body["p_ticker"] is None:
                return httpx.Response(200, json={"owner_id": OWNER, "data_mode": "fixture",
                                                 "tickers": [receipt.series.ticker],
                                                 "calendar": bundle["calendar"]})
            return httpx.Response(200, json=bundle)
        if path.endswith("read_market_series"):
            return httpx.Response(200, json=raw)
        if path.endswith("persist_ticker_chart_artifact_v1"):
            writes.append(body["p_record"])
            return httpx.Response(200, json={"revision": body["p_record"]["revision"],
                                             "replayed": len(writes) > 5})
        pytest.fail("unexpected provider or economic request")
    with SupabaseScanStore("https://test.supabase.co", "synthetic-key",
                           transport=httpx.MockTransport(handle), sleep=lambda _: None) as base:
        store = ChartArtifactStore(base, OWNER, "fixture")
        first = run_chart_job(store, observed_at=receipt.stored_at, execute=True)
        second = run_chart_job(store, observed_at=receipt.stored_at, execute=True)
    assert first["written"] == second["written"] == 5
    assert writes[:5] == writes[5:]
    assert first["status"] == "ready"
    assert first["cursor_maintenance"] == {"deleted": 2, "has_more": False, "batches": 1}


def test_dry_run_no_writes_and_wrong_owner_rejected():
    receipt, _, bundle, raw = inputs()
    def handle(request):
        if request.url.path.endswith("prune_ticker_chart_cursors_v1"):
            pytest.fail("dry run deleted cursor metadata")
        if request.url.path.endswith("persist_ticker_chart_artifact_v1"):
            pytest.fail("dry run wrote artifact")
        if request.url.path.endswith("read_market_series"):
            return httpx.Response(200, json=raw)
        body = json.loads(request.content)
        return httpx.Response(200, json=bundle if body["p_ticker"] else {
            "owner_id": OWNER, "data_mode": "fixture", "tickers": [receipt.series.ticker],
            "calendar": bundle["calendar"]})
    with SupabaseScanStore("https://test.supabase.co", "synthetic-key",
                           transport=httpx.MockTransport(handle)) as base:
        store = ChartArtifactStore(base, OWNER, "fixture")
        assert run_chart_job(store, observed_at=receipt.stored_at)["written"] == 0
        with pytest.raises(PersistenceError, match="chart_owner_mode_mismatch"):
            ChartArtifactStore(base, "33333333-3333-4333-8333-333333333333", "fixture").load()


def test_writer_failure_is_reported_separately_without_economic_commit():
    receipt, _, bundle, raw = inputs()
    def handle(request):
        if request.url.path.endswith("prune_ticker_chart_cursors_v1"):
            return httpx.Response(200, json={"deleted": 0, "has_more": False})
        if request.url.path.endswith("persist_ticker_chart_artifact_v1"):
            return httpx.Response(403, json={"private": "never log this"})
        if request.url.path.endswith("read_market_series"):
            return httpx.Response(200, json=raw)
        body = json.loads(request.content)
        return httpx.Response(200, json=bundle if body["p_ticker"] else {
            "owner_id": OWNER, "data_mode": "fixture", "tickers": [receipt.series.ticker],
            "calendar": bundle["calendar"]})
    with SupabaseScanStore("https://test.supabase.co", "synthetic-key",
                           transport=httpx.MockTransport(handle)) as base:
        result = run_chart_job(ChartArtifactStore(base, OWNER, "fixture"),
                                observed_at=receipt.stored_at, execute=True)
    assert result["status"] == "failed"
    assert result["failures"][0]["code"] == "database_forbidden"
    assert "private" not in str(result)


def test_cursor_cleanup_bounded_and_malformed_receipt_fails_closed():
    calls = []
    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"deleted": 10000, "has_more": True})
    with SupabaseScanStore("https://test.supabase.co", "synthetic-key",
                           transport=httpx.MockTransport(handle)) as base:
        result = ChartArtifactStore(base, OWNER, "fixture").prune_cursors()
    assert result == {"deleted": 200000, "has_more": True, "batches": 20}
    assert calls == [{"p_limit": 10000}] * 20
    with SupabaseScanStore("https://test.supabase.co", "synthetic-key",
                           transport=httpx.MockTransport(lambda _: httpx.Response(
                               200, json={"deleted": True, "has_more": False}))) as base:
        with pytest.raises(PersistenceError, match="chart_invalid_cleanup_receipt"):
            ChartArtifactStore(base, OWNER, "fixture").prune_cursors()


def test_new_invalid_receipt_selects_previous_valid_with_explicit_stale_warning():
    receipt, calendar, bundle, _ = inputs()
    bad = replace(receipt, series_id="33333333-3333-4333-8333-333333333333",
                  stored_at=receipt.stored_at + timedelta(seconds=1),
                  series=replace(receipt.series, bars=receipt.series.bars[:12]
                                 + receipt.series.bars[13:]))
    records, errors = build_context_records(bundle, (receipt, bad), calendar,
                                            observed_at=receipt.stored_at)
    assert not errors
    data = records[0]["data"]
    assert data["source"]["series_id"] == receipt.series_id
    assert data["quality"]["freshness"] == "stale"
    assert "newer_receipt_unusable" in data["quality"]["warnings"]
    snapshot = next(r for r in records if r["context_kind"] == "signal" and r["view"] == "snapshot")
    assert snapshot["data"]["quality"]["freshness"] == "current"


def test_snapshot_survives_broken_followup_observation():
    receipt, calendar, bundle, _ = inputs()
    # Fixture backtest provenance can resolve its frozen context but cannot supply latest.
    records, errors = build_context_records(bundle, (replace(receipt, namespace="backtest"),),
                                            calendar, observed_at=receipt.stored_at)
    assert {error["code"] for error in errors} == {"chart_source_unavailable"}
    snapshots = [r for r in records if r["view"] == "snapshot"]
    assert len(snapshots) == 2


def test_legacy_without_provenance_does_not_block_latest_or_valid_contexts():
    receipt, calendar, bundle, _ = inputs()
    bundle = {**bundle, "paper_trades": [*bundle["paper_trades"],
                                       {"id": "legacy-text", "details": {}}]}
    records, errors = build_context_records(bundle, (receipt,), calendar,
                                            observed_at=receipt.stored_at)
    assert len(records) == 5
    assert errors == [{"context_kind": "paper", "code": "snapshot_unavailable"}]


def test_bounded_hourly_rotation_covers_departed_tickers_without_writes(monkeypatch):
    receipt, calendar, bundle, _ = inputs()
    catalog = [f"T{index:03}" for index in range(123)]
    visited = []
    class Store:
        data_mode = "fixture"
        def load(self, ticker=None):
            if ticker is None:
                return {"tickers": catalog}
            visited.append(ticker)
            return {**bundle, "ticker": ticker}
        def receipts(self, *args, **kwargs):
            return ()
        def persist(self, record):
            pytest.fail("dry run mutated chart")
    monkeypatch.setattr("idx_scanner.chart_runtime.build_context_records",
                        lambda *args, **kwargs: ([], []))
    store = Store()
    first = run_chart_job(store, observed_at=receipt.stored_at)
    first_symbols = visited[:]
    visited.clear()
    replay = run_chart_job(store, observed_at=receipt.stored_at)
    assert visited == first_symbols
    visited.clear()
    second = run_chart_job(store, observed_at=receipt.stored_at + timedelta(hours=1))
    assert len(set(first_symbols + visited)) == 123
    assert first["total_tickers"] == replay["total_tickers"] == second["total_tickers"] == 123
    assert first["deferred_tickers"] == second["deferred_tickers"] == 23
    visited.clear()
    selected = run_chart_job(store, observed_at=receipt.stored_at, ticker="T122")
    assert visited == ["T122"]
    assert selected["total_tickers"] == selected["tickers"] == 1
