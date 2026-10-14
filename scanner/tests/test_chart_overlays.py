from dataclasses import replace

from idx_scanner.chart_artifact import ChartReceipt, build_chart_artifact, cutoff_series
from idx_scanner.fixtures import sample_market
from idx_scanner.indicators import sma
from idx_scanner.models import ExitConfig, digest


def setup_context():
    series, calendar, _ = sample_market(660)
    source = replace(next(iter(series.values())), fetched_at=calendar.sessions[659].closes_at)
    receipt = ChartReceipt("11111111-1111-4111-8111-111111111111", "forward", "fixture",
                           source, source.fetched_at)
    day, entry = source.bars[620].session, source.bars[621].session
    signal = {"id": "a" * 64, "session": str(day), "published_at": str(
        calendar.sessions[620].closes_at.isoformat()), "planned_entry_session": str(entry),
        "source_revision": "b" * 40, "input_digest": cutoff_series(source, day).input_digest,
        "candidate": {"reference_close": "1000", "stop": "925", "level": "980",
                      "available_session": str(day), "pivot_date": str(source.bars[618].session)}}
    paper = {"id": "p", "experiment": {"id": "fixed2r", "model_version": "close-signal-risk-v1"},
             "planned_entry_price": "1000", "stop": "925", "target": "1150", "events": []}
    return receipt, calendar, signal, paper


def test_pending_has_plan_but_no_fill_and_fractal_availability():
    receipt, calendar, signal, paper = setup_context()
    data = build_chart_artifact(receipt, calendar, observed_at=receipt.stored_at,
        kind="paper", context_id="p", signal=signal, signal_receipt=receipt, paper=paper)
    overlay = data["overlays"]
    assert {p["kind"] for p in overlay["levels"]} == {
        "planned_entry", "initial_stop", "target", "fractal"}
    assert not any(p["kind"] == "entry_fill" for p in overlay["markers"])
    fractal = next(p for p in overlay["levels"] if p["kind"] == "fractal")
    assert fractal["starts_at"] == signal["session"]
    assert fractal["origin_session"] < fractal["available_session"]


def test_ma_trigger_and_next_open_fill_separate_and_no_sma_target():
    receipt, calendar, signal, paper = setup_context()
    policy = ExitConfig(mode="ma_close", target_r=None, ma_type="SMA", period=10)
    ma = sma([b.close for b in receipt.series.bars[:624]], 10)[-1]
    paper = {**paper, "target": None, "experiment": {"id": "ma10", "exit": {
        "mode": "ma_close", "ma_type": "SMA", "period": 10, "version": "v1"}}, "events": [
        {"kind": "entry", "session": signal["planned_entry_session"], "price": "1000",
         "reason": "assumed_signal_close", "input_digest": digest(receipt.series.bars[621]),
         "observed_at": calendar.sessions[621].closes_at.isoformat()},
        {"kind": "pending_exit", "session": str(receipt.series.bars[623].session), "price": None,
         "reason": "ma_close_below", "input_digest": digest((receipt.series.bars[623], ma, policy)),
         "ma_value": "1001",
         "ma_type": "SMA", "ma_period": 10,
         "observed_at": calendar.sessions[623].closes_at.isoformat()},
        {"kind": "exit", "session": str(receipt.series.bars[624].session), "price": "990",
         "reason": "ma_next_open", "input_digest": digest(receipt.series.bars[624]),
         "observed_at": calendar.sessions[624].closes_at.isoformat()}]}
    data = build_chart_artifact(receipt, calendar, observed_at=receipt.stored_at,
        kind="paper", context_id="p", signal=signal, signal_receipt=receipt, paper=paper)
    assert not any(p["kind"] == "target" for p in data["overlays"]["levels"])
    assert {p["kind"] for p in data["overlays"]["markers"]} >= {
        "entry_fill", "ma_exit_trigger", "exit_fill"}
    snapshot = build_chart_artifact(receipt, calendar, observed_at=receipt.stored_at,
        kind="paper", context_id="p", view="snapshot", signal=signal, paper=paper)
    assert {p["kind"] for p in snapshot["overlays"]["markers"]} == {"signal"}


def test_ambiguous_event_does_not_become_normal_exit():
    receipt, calendar, signal, paper = setup_context()
    paper = {**paper, "events": [{"kind": "exit", "session": signal["planned_entry_session"],
        "price": "925", "alternate_price": "1150", "input_digest": digest(receipt.series.bars[621]),
        "reason": "ambiguous", "observed_at": calendar.sessions[621].closes_at.isoformat()}]}
    data = build_chart_artifact(receipt, calendar, observed_at=receipt.stored_at,
        kind="paper", context_id="p", signal=signal, signal_receipt=receipt, paper=paper)
    event = data["overlays"]["markers"][-1]
    assert event["kind"] == "ambiguous"
    assert event["price"] is None


def test_unknown_or_changed_basis_holds_price_overlays():
    receipt, calendar, signal, _ = setup_context()
    data = build_chart_artifact(receipt, calendar, observed_at=receipt.stored_at,
        kind="actual", context_id="x", actual={"id": "x"}, fills=[{"price_idr": "1000"}])
    assert data["overlays"]["reason"] == "actual_price_basis_unverified"
    assert data["overlays"]["markers"] == []
    other = replace(receipt, series=replace(receipt.series, price_basis="other"))
    data = build_chart_artifact(other, calendar, observed_at=receipt.stored_at,
        kind="signal", context_id=signal["id"], signal=signal, signal_receipt=receipt)
    assert data["overlays"]["reason"] == "overlay_price_basis_mismatch"


def test_actual_partial_fills_keep_ids_prices_and_correction_availability():
    receipt, calendar, _, _ = setup_context()
    actual = {"id": "trade", "price_basis": receipt.series.price_basis, "initial_stop": "900",
              "created_at": calendar.sessions[620].closes_at.isoformat()}
    fills = [{"id": "first-buy", "side": "buy", "price_idr": "1000",
              "filled_at": calendar.sessions[621].opens_at.isoformat(),
              "created_at": calendar.sessions[621].closes_at.isoformat()},
             {"id": "second-buy", "side": "buy", "price_idr": "1010",
              "filled_at": calendar.sessions[621].opens_at.isoformat(),
              "created_at": calendar.sessions[621].closes_at.isoformat()}]
    stops = [{"id": "stop1", "new_stop": "910", "occurred_at":
              calendar.sessions[622].closes_at.isoformat()},
             {"id": "stop2", "new_stop": "920", "occurred_at":
              calendar.sessions[623].closes_at.isoformat()}]
    data = build_chart_artifact(receipt, calendar, observed_at=receipt.stored_at,
        kind="actual", context_id="trade", actual=actual, fills=fills, stops=stops)
    assert [m["price"] for m in data["overlays"]["markers"]] == ["1000", "1010"]
    assert stops[0].get("ends_at") is None
    level = next(item for item in data["overlays"]["levels"] if item["id"] == "stop1")
    assert level["ends_at"] == str(receipt.series.bars[623].session)
    assert level["status"] == "ended"


def test_late_event_unavailable_in_earlier_followup_and_unknown_event_digest_held():
    receipt, calendar, signal, paper = setup_context()
    paper = {**paper, "events": [{"kind": "entry", "session": signal["planned_entry_session"],
        "price": "1000", "reason": "assumed_signal_close", "input_digest": "c" * 64,
        "observed_at": calendar.sessions[650].closes_at.isoformat()}]}
    early = build_chart_artifact(receipt, calendar,
        observed_at=calendar.sessions[630].closes_at, kind="paper", context_id="p",
        signal=signal, signal_receipt=receipt, paper=paper)
    assert {m["kind"] for m in early["overlays"]["markers"]} == {"signal"}
    later = build_chart_artifact(receipt, calendar, observed_at=receipt.stored_at,
        kind="paper", context_id="p", signal=signal, signal_receipt=receipt, paper=paper)
    assert later["overlays"]["reason"] == "event_basis_unverified"


def test_actual_stop_intervals_follow_occurrence_time_not_same_day_uuid_order():
    receipt, calendar, _, _ = setup_context()
    actual = {"id": "trade", "price_basis": receipt.series.price_basis, "initial_stop": "900",
              "created_at": calendar.sessions[620].closes_at.isoformat()}
    day = receipt.series.bars[622].session
    next_day = receipt.series.bars[623].session
    stops = [{"id": "z", "new_stop": "910", "occurred_at": f"{day}T09:00:00+07:00"},
             {"id": "a", "new_stop": "920", "occurred_at": f"{day}T10:00:00+07:00"},
             {"id": "next", "new_stop": "930", "occurred_at": f"{next_day}T09:00:00+07:00"}]
    data = build_chart_artifact(receipt, calendar, observed_at=receipt.stored_at,
        kind="actual", context_id="trade", actual=actual, stops=stops)
    levels = {level["id"]: level for level in data["overlays"]["levels"]}
    assert levels["z"]["ends_at"] == str(day)
    assert levels["a"]["ends_at"] == str(next_day)


def test_actual_corrected_fill_price_not_exposed_before_correction_known():
    receipt, calendar, _, _ = setup_context()
    actual = {"id": "trade", "price_basis": receipt.series.price_basis, "initial_stop": "900",
              "created_at": calendar.sessions[620].closes_at.isoformat()}
    fill = {"id": "corrected", "side": "buy", "price_idr": "1001",
            "filled_at": calendar.sessions[621].opens_at.isoformat(),
            "created_at": calendar.sessions[621].closes_at.isoformat(),
            "correction_created_at": calendar.sessions[650].closes_at.isoformat()}
    data = build_chart_artifact(receipt, calendar, observed_at=calendar.sessions[630].closes_at,
        kind="actual", context_id="trade", actual=actual, fills=(fill,))
    assert data["overlays"]["markers"] == []
