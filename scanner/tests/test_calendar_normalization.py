"""Only source-backed non-trading rows may leave the indicator series."""

import json
from dataclasses import replace
from datetime import timedelta

import pytest

from idx_scanner.context import quality
from idx_scanner.fixtures import sample_market
from idx_scanner.models import Bar, ProviderRowIssue, ScanState
from idx_scanner.normalization import normalize_closed_sessions
from idx_scanner.persistence import market_series_envelope, series_from_revision
from idx_scanner.providers import FetchRequest
from idx_scanner.runner import run_once


def market():
    values, calendar, universe = sample_market(620)
    raw = values["DEMO-A"]
    closed = raw.bars[3].session + timedelta(days=1)  # Explicit SYNTHETIC closure.
    calendar = replace(calendar, closed_days=(closed,))
    bar = Bar(closed, 100, 100, 100, 100, 0)
    raw = replace(raw, bars=tuple(sorted(raw.bars + (bar,), key=lambda b: b.session)))
    return raw, calendar, universe, calendar.sessions[619]


def revision(series):
    from datetime import UTC, datetime

    series = replace(series, fetched_at=datetime(2026, 1, 1, tzinfo=UTC))
    record = market_series_envelope(series, namespace="test", data_mode="fixture")["p_record"]
    return series_from_revision(record), record


def test_explicit_closed_flat_row_excluded_with_lossless_parent_audit():
    raw, calendar, _, target = market()
    assert quality(raw, target.day, calendar) == "data_quality_hold"
    derived = normalize_closed_sessions(raw, calendar, target.day)
    assert quality(derived, target.day, calendar) == "valid"
    assert len(raw.bars) == 621 and len(derived.bars) == 620
    audit = json.loads(derived.provenance[-1])
    assert audit["source_input_digest"] == raw.input_digest
    assert audit["calendar_version"] == calendar.version
    excluded = audit["excluded_bars"][0]
    assert excluded["volume"] == 0 and excluded["session"] == calendar.closed_days[0].isoformat()
    assert derived.input_digest != raw.input_digest
    assert normalize_closed_sessions(derived, calendar, target.day) is derived
    assert derived.price_basis == raw.price_basis
    assert derived.actions == raw.actions


@pytest.mark.parametrize("volume,high", [(1, 100), (0, 101)])
def test_suspicious_closed_day_rows_are_not_silently_discarded(volume, high):
    raw, calendar, _, target = market()
    raw = replace(
        raw,
        bars=tuple(
            replace(b, volume=volume, high=high) if b.session in calendar.closed_days else b
            for b in raw.bars
        ),
    )
    assert normalize_closed_sessions(raw, calendar, target.day) is raw
    assert quality(raw, target.day, calendar) != "valid"


def test_unknown_closure_is_not_inferred_from_a_weekend_or_provider_gap():
    raw, calendar, _, target = market()
    assert normalize_closed_sessions(raw, replace(calendar, closed_days=()), target.day) is raw


def test_zero_volume_on_an_open_session_remains_a_hold():
    raw, calendar, _, target = market()
    raw = replace(
        raw, bars=tuple(replace(b, volume=0) if b.session == target.day else b for b in raw.bars)
    )
    derived = normalize_closed_sessions(raw, calendar, target.day)
    assert derived.bars[-1].volume == 0
    assert quality(derived, target.day, calendar) == "data_quality_hold"


def test_closed_missing_rows_are_audited_but_open_missing_and_incomplete_are_retained():
    raw, calendar, _, target = market()
    closed = calendar.closed_days[0]
    raw = replace(
        raw,
        provider_missing_sessions=(closed, target.day),
        provider_row_issues=(
            ProviderRowIssue(
                closed,
                "missing_ohlcv",
                (
                    ("open", None),
                    ("high", None),
                    ("low", None),
                    ("close", None),
                    ("volume", 0),
                ),
            ),
            ProviderRowIssue(closed, "incomplete_ohlcv", (("close", None),)),
            ProviderRowIssue(target.day, "missing_ohlcv", (("volume", 0),)),
        ),
    )
    derived = normalize_closed_sessions(raw, calendar, target.day)
    assert derived.provider_missing_sessions == (target.day,)
    assert len(derived.provider_row_issues) == 2
    assert quality(derived, target.day, calendar) == "data_quality_hold"
    assert json.loads(derived.provenance[-1])["excluded_missing_sessions"] == [closed.isoformat()]


def test_historical_date_only_missing_issue_is_not_ignored():
    raw, calendar, _, target = market()
    derived = normalize_closed_sessions(raw, calendar, target.day)
    historical = derived.bars[0].session
    calendar = replace(
        calendar,
        historical_days=tuple(s.day for s in calendar.sessions[:619]),
        sessions=calendar.sessions[619:],
    )
    assert (
        quality(replace(derived, provider_missing_sessions=(historical,)), target.day, calendar)
        == "missing_session"
    )


def test_future_bars_and_mixed_fixture_live_cannot_be_normalized():
    raw, calendar, _, target = market()
    with pytest.raises(ValueError, match="future_bars"):
        normalize_closed_sessions(raw, calendar, raw.bars[-2].session)
    with pytest.raises(ValueError, match="mixed_fixture_live"):
        normalize_closed_sessions(replace(raw, provider="yfinance"), calendar, target.day)


def test_closures_cannot_overlap_real_sessions_or_be_duplicated():
    _, calendar, _, target = market()
    with pytest.raises(ValueError, match="Explicit closed days"):
        replace(calendar, closed_days=(target.day,))
    with pytest.raises(ValueError, match="Explicit closed days"):
        replace(calendar, closed_days=calendar.closed_days * 2)


def test_persistence_roundtrip_retains_derived_audit_and_legacy_raw_payload():
    raw, calendar, _, target = market()
    legacy, record = revision(raw)
    assert "provenance" not in record["snapshot"]
    assert "provenance" not in json.loads(record["metadata_source"])
    assert legacy.input_digest == raw.input_digest
    derived = normalize_closed_sessions(legacy, calendar, target.day)
    restored, record = revision(derived)
    assert restored == derived
    record["metadata_source"] = record["metadata_source"].replace(
        "explicit_exchange_closed_day_not_a_trading_bar", "tampered"
    )
    with pytest.raises(ValueError, match="digest_mismatch"):
        series_from_revision(record)


@pytest.mark.parametrize("fail_derived", [False, True])
def test_runner_verifies_raw_then_derived_before_publication(fail_derived):
    raw, calendar, universe, target = market()
    universe = replace(universe, tickers=(raw.ticker,))
    calls = []
    stored = {}

    class Provider:
        def fetch(self, request):
            return raw

    class Store:
        def load_state(self, **kwargs):
            return ScanState()

        def ingest_series(self, series, **kwargs):
            calls.append(("ingest", bool(series.provenance)))
            if fail_derived and series.provenance:
                raise RuntimeError("derived_ingest_failed")
            stored[series.input_digest] = series
            return {"revision_id": series.input_digest}

        def load_series(self, revision_id, **kwargs):
            calls.append(("verify", bool(stored[revision_id].provenance)))
            assert kwargs["expected_input_digest"] == revision_id
            return stored[revision_id]

        def publish(self, result, **kwargs):
            calls.append(("publish", result.coverage_valid))
            return {"run_id": "test-only", "replayed": False}

    requests = {
        raw.ticker: FetchRequest(raw.ticker, raw.ticker, raw.bars[0].session, target.day, True)
    }
    args = (Provider(), Store(), requests, target.day, calendar, universe, target.closes_at)
    if fail_derived:
        with pytest.raises(RuntimeError, match="derived_ingest_failed"):
            run_once(*args)
        assert calls == [("ingest", False), ("verify", False), ("ingest", True)]
    else:
        result = run_once(*args)
        assert calls == [
            ("ingest", False),
            ("verify", False),
            ("ingest", True),
            ("verify", True),
            ("publish", 1),
        ]
        assert result.pipeline.fetched_series == (raw,)
        assert result.pipeline.prepared_series[0].provenance


def test_historical_zero_volume_suspension_does_not_hold_active_current_session():
    raw, calendar, _, target = market()
    # Normalize closed days so only historical open day zero-volume remains
    derived = normalize_closed_sessions(raw, calendar, target.day)
    assert quality(derived, target.day, calendar) == "valid"
    # Inject a zero-volume suspension bar 100 days in the past on an open day
    historical_idx = max(0, len(derived.bars) - 100)
    past_session = derived.bars[historical_idx].session
    bars_with_past_suspension = tuple(
        replace(b, volume=0) if b.session == past_session else b for b in derived.bars
    )
    series_with_past_suspension = replace(derived, bars=bars_with_past_suspension)
    # The active current session has volume > 0, so it remains valid
    assert series_with_past_suspension.bars[-1].volume > 0
    assert quality(series_with_past_suspension, target.day, calendar) == "valid"
