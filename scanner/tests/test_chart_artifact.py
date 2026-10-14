"""Synthetic chart contracts: frozen inputs, recurrence and market calendar gaps."""

from dataclasses import replace
from datetime import date

import pytest

from idx_scanner.chart_artifact import (
    ChartReceipt,
    build_chart_artifact,
    cutoff_series,
    resolve_signal_receipt,
    source_scope,
)
from idx_scanner.fixtures import sample_market
from idx_scanner.indicators import calculate, sma
from idx_scanner.models import CorporateAction, canonical_json
from idx_scanner.untradable import VerifiedUntradable


@pytest.fixture
def market():
    sources, calendar, _ = sample_market(660)
    source = replace(next(iter(sources.values())), fetched_at=calendar.sessions[659].closes_at)
    receipt = ChartReceipt("11111111-1111-4111-8111-111111111111", "forward", "fixture",
                           source, source.fetched_at)
    return receipt, calendar


def signal_for(receipt, index=620):
    cutoff = receipt.series.bars[index].session
    return {"id": "a" * 64, "ticker": receipt.series.ticker, "session": str(cutoff),
            "input_digest": cutoff_series(receipt.series, cutoff).input_digest,
            "provider": "fixture", "price_basis": receipt.series.price_basis,
            "provider_version": receipt.series.provider_version, "data_mode": "fixture",
            "published_at": "2026-01-01T10:00:00+00:00", "source_revision": "b" * 40,
            "planned_entry_session": str(receipt.series.bars[index + 1].session),
            "candidate": {"reference_close": 1000, "stop": 925, "level": None}}


def test_snapshot_reconstructs_cutoff_digest_not_current_receipt(market):
    receipt, calendar = market
    signal = signal_for(receipt)
    original = resolve_signal_receipt((receipt,), signal)
    data = build_chart_artifact(original, calendar, observed_at=receipt.stored_at,
                                kind="signal", context_id=signal["id"], view="snapshot",
                                signal=signal)
    assert data["source"]["input_digest"] == receipt.series.input_digest
    assert data["source"]["resolved_input_digest"] == signal["input_digest"]
    assert data["sessions"][-1] == signal["session"]
    assert data["quality"]["freshness"] == "current"
    assert not any(m["kind"] == "entry_fill" for m in data["overlays"]["markers"])
    assert data["overlays"]["levels"][0]["starts_at"] > signal["session"]


def test_snapshot_never_falls_back_when_digest_cannot_be_proven(market):
    receipt, _ = market
    signal = {**signal_for(receipt), "input_digest": "f" * 64}
    with pytest.raises(ValueError, match="snapshot_unavailable"):
        resolve_signal_receipt((receipt,), signal)


def test_cutoff_uses_engine_action_and_issue_filtering(market):
    receipt, _ = market
    cutoff = receipt.series.bars[620].session
    source = replace(receipt.series, actions=(CorporateAction(cutoff, "dividend", "1"),
                     CorporateAction(receipt.series.bars[630].session, "split", "2")))
    cropped = cutoff_series(source, cutoff)
    assert len(cropped.bars) == 621
    assert len(cropped.actions) == 1
    assert source.bars == receipt.series.bars


def test_indicators_are_full_history_canonical_and_not_viewport_seeded(market):
    receipt, calendar = market
    data = build_chart_artifact(receipt, calendar, observed_at=receipt.stored_at)
    features = calculate(receipt.series.bars)
    assert data["indicators"]["ema200"]["points"][620]["value"] == features.ema200[620]
    assert data["indicators"]["macd"]["points"][620]["value"] == features.macd[620]
    assert data["indicators"]["sma10"]["points"][9]["value"] == sma(
        [b.close for b in receipt.series.bars], 10)[9]
    assert data["indicators"]["ema200"]["eligible_from"] == str(
        receipt.series.bars[599].session)


def test_missing_session_blocks_recurrence_without_fake_candle(market):
    receipt, calendar = market
    missing = receipt.series.bars[12].session
    receipt = replace(receipt, series=replace(receipt.series,
                      bars=receipt.series.bars[:12] + receipt.series.bars[13:]))
    data = build_chart_artifact(receipt, calendar, observed_at=receipt.stored_at)
    assert {"session": str(missing), "reason": "missing_bar"} in data["gaps"]
    assert not any(b["session"] == str(missing) for b in data["bars"])
    assert data["indicators"]["ema200"]["points"][13]["value"] is None
    assert data["quality"]["completeness"] == "partial"


def test_paper_recovery_provenance_is_preserved(market):
    receipt, _ = market
    source = replace(receipt.series, provenance=(canonical_json({
        "kind": "reviewed_historical_backfill_v1", "status": "recovered"}),))
    assert source_scope(replace(source, provider="yfinance"), "forward") == "paper_recovery"
    assert source_scope(source, "forward") == "fixture"


def test_artifact_identity_changes_when_source_or_overlay_changes(market):
    receipt, calendar = market
    data = build_chart_artifact(receipt, calendar, observed_at=receipt.stored_at)
    replay = build_chart_artifact(receipt, calendar, observed_at=receipt.stored_at)
    assert data == replay
    changed = replace(receipt, series=replace(receipt.series,
                      bars=receipt.series.bars[:-1]))
    assert build_chart_artifact(changed, calendar,
                                observed_at=receipt.stored_at)["revision"] != data["revision"]


def test_live_fixture_mismatch_and_unverified_calendar_rejected(market):
    receipt, calendar = market
    with pytest.raises(ValueError, match="chart_mode_mismatch"):
        build_chart_artifact(replace(receipt, data_mode="live"), calendar,
                             observed_at=receipt.stored_at)
    with pytest.raises(ValueError, match="calendar_unavailable"):
        build_chart_artifact(receipt, replace(calendar, sessions=calendar.sessions[10:]),
                             observed_at=receipt.stored_at)


def test_expired_calendar_unknown_and_future_candles_excluded(market):
    receipt, calendar = market
    at = calendar.sessions[600].closes_at
    data = build_chart_artifact(receipt, calendar, observed_at=at)
    assert data["sessions"][-1] == str(calendar.sessions[600].day)
    expired = replace(calendar, sessions=calendar.sessions[:601])
    later = build_chart_artifact(receipt, expired, observed_at=receipt.stored_at)
    assert later["quality"]["freshness"] == "unknown"
    assert later["quality"]["expected_session"] is None


def test_untradable_evidence_excludes_zero_bar_without_breaking_recurrence(market):
    receipt, calendar = market
    day = receipt.series.bars[12].session
    proof = VerifiedUntradable(receipt.series.ticker, day, "fixture", "synthetic://proof",
                              "a" * 64, calendar.sessions[13].closes_at)
    bars = tuple(replace(b, volume=0) if b.session == day else b for b in receipt.series.bars)
    source = replace(receipt, series=replace(receipt.series, bars=bars))
    data = build_chart_artifact(source, calendar, observed_at=receipt.stored_at, evidence=(proof,))
    assert {"session": str(day), "reason": "verified_untradable"} in data["gaps"]
    assert data["indicators"]["ema200"]["points"][13]["value"] is not None
    assert data["indicators"]["ema200"]["history_count"] == 659
    with pytest.raises(ValueError, match="untradable_evidence_conflicts_with_provider"):
        build_chart_artifact(receipt, calendar, observed_at=receipt.stored_at, evidence=(proof,))


def test_last_valid_market_session_and_stale_after_corporate_action_hold(market):
    receipt, calendar = market
    day = receipt.series.bars[650].session
    source = replace(receipt, series=replace(receipt.series,
                     actions=(CorporateAction(day, "split", "2"),)))
    data = build_chart_artifact(source, calendar, observed_at=receipt.stored_at)
    assert data["source"]["last_market_session"] == str(receipt.series.bars[649].session)
    assert data["quality"]["freshness"] == "stale"
    assert "corporate_action_hold" in data["quality"]["reasons"]


def test_no_false_number_or_duplicate_session_allowed(market):
    receipt, calendar = market
    broken = replace(receipt, series=replace(receipt.series,
                     bars=(receipt.series.bars[0], *receipt.series.bars)))
    with pytest.raises(ValueError, match="invalid_chart_sessions"):
        build_chart_artifact(broken, calendar, observed_at=receipt.stored_at)
    broken = replace(receipt, series=replace(receipt.series,
                     bars=(replace(receipt.series.bars[0], volume=True), *receipt.series.bars[1:])))
    with pytest.raises(ValueError, match="invalid_chart_volume"):
        build_chart_artifact(broken, calendar, observed_at=receipt.stored_at)


def test_unknown_actions_keep_candles_but_hold_indicators(market):
    receipt, calendar = market
    unknown = replace(receipt, series=replace(receipt.series, actions_complete=False))
    data = build_chart_artifact(unknown, calendar, observed_at=receipt.stored_at)
    assert data["bars"]
    assert data["quality"]["completeness"] == "partial"
    assert all(value["status"] == "unavailable" and not value["points"]
               for value in data["indicators"].values())


def test_older_zero_volume_matches_engine_recurrence_and_snapshot_ignores_later_proof(market):
    receipt, calendar = market
    day = receipt.series.bars[12].session
    bars = tuple(replace(bar, volume=0) if bar.session == day else bar
                 for bar in receipt.series.bars)
    source = replace(receipt, series=replace(receipt.series, bars=bars))
    signal = signal_for(source)
    proof = VerifiedUntradable(source.series.ticker, day, "fixture", "synthetic://proof",
                              "a" * 64, calendar.sessions[650].closes_at)
    snapshot = build_chart_artifact(source, calendar, observed_at=source.stored_at,
        kind="signal", context_id=signal["id"], view="snapshot", signal=signal, evidence=(proof,))
    assert not snapshot["gaps"]
    canonical = calculate(cutoff_series(source.series, date.fromisoformat(signal["session"])).bars)
    assert snapshot["indicators"]["ema200"]["points"][-1]["value"] == canonical.ema200[-1]
