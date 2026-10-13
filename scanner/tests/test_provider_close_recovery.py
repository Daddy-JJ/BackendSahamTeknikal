"""Synthetic incident fixtures, never production data or publisher calls.

Oct12 ADRO daily OHLV/Close are transcribed from the audited source capture;
the surrounding sessions and loader are explicit test-only inputs.
"""

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from idx_scanner.context import Calendar, Session, quality, quality_diagnostics
from idx_scanner.engine import scan
from idx_scanner.models import ScanState, canonical_json
from idx_scanner.providers import FetchRequest, ProviderError, YFinanceProvider

DAYS = (date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 12), date(2026, 10, 13))
PRIOR = [(DAYS[0], 2550, 2600, 2500, 2550, 1000),
         (DAYS[1], 2540, 2600, 2510, 2580, 19314700)]
COMPLETE = (DAYS[2], 2580, 2590, 2490, 2490, 51348000)


def frame(rows, **attrs):
    values = [row[1:] for row in rows]
    result = pd.DataFrame(values, columns=["Open", "High", "Low", "Close", "Volume"],
                          index=pd.to_datetime([row[0].isoformat() for row in rows]))
    result["Adj Close"] = result["Close"]
    result["Dividends"] = 0.0
    result["Stock Splits"] = 0.0
    result.attrs.update(attrs)
    return result


@pytest.fixture
def live_calendar():
    return Calendar(tuple(Session(day, datetime(day.year, day.month, day.day, 1, 58, tzinfo=UTC),
                                  datetime(day.year, day.month, day.day, 9, 15, tzinfo=UTC))
                          for day in DAYS), "synthetic-incident-v1", "synthetic://incident", "live")


@pytest.fixture
def request_spec():
    return FetchRequest("ADRO", "ADRO.JK", DAYS[0], DAYS[2], True)


def recovering_provider(live_calendar, missing=float("nan"), short=None, **options):
    calls = []
    bad = frame([*PRIOR, (*COMPLETE[:4], missing, COMPLETE[5])])
    def loader(symbol, **kwargs):
        assert symbol == "ADRO.JK"
        assert kwargs["interval"] == "1d" and kwargs["actions"] is True
        assert not any(kwargs[key] for key in ("auto_adjust", "back_adjust", "repair", "rounding"))
        assert kwargs["keepna"] is True
        calls.append(kwargs)
        if "period" in kwargs:
            assert "start" not in kwargs and "end" not in kwargs
            value = short[kwargs["period"]] if isinstance(short, dict) else short
            return (value if value is not None else frame([COMPLETE])).copy()
        return bad.copy()
    options.setdefault("clock", lambda: live_calendar.get(DAYS[2]).closes_at + timedelta(hours=1))
    options.setdefault("calendar", live_calendar)
    options.setdefault("request_interval_seconds", 0)
    return YFinanceProvider(loader, lambda _: None, **options), calls


@pytest.mark.parametrize("missing", [None, float("nan"), pd.NA])
def test_missing_close_uses_exact_closed_daily_bar_and_retains_original(
    live_calendar, request_spec, missing,
):
    provider, calls = recovering_provider(live_calendar, missing)
    result = provider.fetch(request_spec)
    assert len(calls) == 4 and calls[-1]["period"] == "1d"
    assert quality(result, DAYS[2], live_calendar) == "valid"
    assert result.bars[-1].close == 2490 and result.bars[-1].volume == 51348000
    original, daily = provider.raw_recovery_captures["ADRO"]
    assert dict(original.provider_row_issues[0].observed_values)["close"] is None
    assert daily.bars[-1] == result.bars[-1]
    assert original.bars == result.bars[:-1] and original.provider_row_issues
    assert result.price_basis == original.price_basis == daily.price_basis
    metadata = json.loads(result.provenance[-1])
    assert metadata["original_input_digest"] == original.input_digest
    assert metadata["recovery_input_digest"] == daily.input_digest
    assert metadata["replaced_sessions"] == ["2026-10-12"]
    assert "fetched_at" not in metadata and "attempt" not in metadata
    assert quality_diagnostics(result, DAYS[2], live_calendar) == {
        "contract_version": 1, "code": "valid", "session": "2026-10-12",
        "missing_fields": [], "recovery_status": "recovered",
    }
    assert "NaN" not in canonical_json(result)


@pytest.mark.parametrize("mode", ["no_calendar", "fixture_calendar", "before_close", "naive_clock"])
def test_recovery_requires_verified_live_closed_session(live_calendar, request_spec, mode):
    options = {}
    if mode == "no_calendar":
        options["calendar"] = None
    elif mode == "fixture_calendar":
        options["calendar"] = replace(live_calendar, data_mode="fixture")
    elif mode == "before_close":
        options["clock"] = lambda: live_calendar.get(DAYS[2]).closes_at - timedelta(seconds=1)
    else:
        options["clock"] = lambda: datetime(2026, 10, 13)
    provider, calls = recovering_provider(live_calendar, **options)
    result = provider.fetch(request_spec)
    assert len(calls) == 3 and result.provider_row_issues
    assert not result.provenance


@pytest.mark.parametrize("changed", [(2585, 2590, 2490, 2490, 51348000),
                                   (2580, 2595, 2490, 2490, 51348000),
                                   (2580, 2590, 2480, 2490, 51348000),
                                   (2580, 2590, 2490, 2490, 51348001)])
def test_original_nonmissing_ohlv_must_match_exactly(live_calendar, request_spec, changed):
    provider, calls = recovering_provider(live_calendar, short=frame([(DAYS[2], *changed)]))
    result = provider.fetch(request_spec)
    assert len(calls) == 5 and result.provider_row_issues and not result.provenance
    assert provider.fetch_diagnostics["ADRO"][-1]["status"] == "recovery_overlap_conflict"
    assert len(provider.raw_recovery_captures["ADRO"]) == 2


def test_wrong_session_cannot_shift_missing_bar_or_use_metadata_price(live_calendar, request_spec):
    short = frame([(DAYS[1], *COMPLETE[1:])], regularMarketPrice=2490)
    provider, _ = recovering_provider(live_calendar, short=short)
    result = provider.fetch(request_spec)
    assert result.provider_row_issues[0].session == DAYS[2] and not result.provenance
    assert provider.fetch_diagnostics["ADRO"][-1]["status"] == "recovery_wrong_session"


@pytest.mark.parametrize("attrs", [{"price_basis": "dividend_adjusted"},
                                  {"dataGranularity": "1m"}, {"provider_symbol": "INDY.JK"},
                                  {"currency": "USD"}, {"exchangeTimezoneName": "UTC"}])
def test_basis_granularity_mapping_and_market_metadata_conflicts_hold(
    live_calendar, request_spec, attrs,
):
    provider, _ = recovering_provider(live_calendar, short=frame([COMPLETE], **attrs))
    result = provider.fetch(request_spec)
    assert result.provider_row_issues and not result.provenance
    assert provider.fetch_diagnostics["ADRO"][-1]["status"] == (
        "recovery_basis_or_granularity_mismatch")


@pytest.mark.parametrize("kind", ["split", "missing_actions", "invalid_close", "missing_close"])
def test_missing_actions_or_unusable_daily_bar_cannot_recover(live_calendar, request_spec, kind):
    short = frame([COMPLETE])
    if kind == "split":
        short["Stock Splits"] = 2
    elif kind == "missing_actions":
        short = short.drop(columns=["Dividends"])
    elif kind == "invalid_close":
        short["Close"] = 9999
    else:
        short["Close"] = pd.NA
    provider, _ = recovering_provider(live_calendar, short=short)
    result = provider.fetch(request_spec)
    assert result.provider_row_issues and not result.provenance


def test_cash_dividend_metadata_does_not_change_unadjusted_ohlc(live_calendar, request_spec):
    short = frame([COMPLETE])
    short["Dividends"] = 123
    provider, _ = recovering_provider(live_calendar, short=short)
    result = provider.fetch(request_spec)
    assert quality(result, DAYS[2], live_calendar) == "valid"
    assert result.bars[-1].close == 2490 and result.actions == ()
    assert json.loads(result.provenance[-1])["cash_dividend_metadata_disagreement"] is True


def test_period5d_can_repair_yesterday_without_borrowing_current_session(
    live_calendar, request_spec,
):
    future = (DAYS[3], 8000, 9999, 7000, 9000, 1000)
    short = {"1d": frame([future]), "5d": frame([PRIOR[1], COMPLETE, future])}
    provider, calls = recovering_provider(live_calendar, short=short)
    result = provider.fetch(request_spec)
    assert len(calls) == 5 and calls[-1]["period"] == "5d"
    assert quality(result, DAYS[2], live_calendar) == "valid"
    assert all(bar.session <= DAYS[2] for bar in result.bars)
    assert any(any(bar.session == DAYS[3] for bar in capture.bars)
               for capture in provider.raw_recovery_captures["ADRO"])
    # Future price/action changes cannot affect the derived target data identity.
    changed = frame([PRIOR[1], COMPLETE, (DAYS[3], 1, 10, 1, 2, 99999)])
    changed.loc[pd.Timestamp(DAYS[3]), "Stock Splits"] = 7
    other, _ = recovering_provider(live_calendar, short={"1d": frame([future]), "5d": changed})
    assert other.fetch(request_spec).input_digest == result.input_digest


def test_all_complete_historical_overlap_fields_must_match(live_calendar, request_spec):
    future = (DAYS[3], 8000, 9999, 7000, 9000, 1000)
    wrong_prior = (DAYS[1], 2540, 2600, 2510, 2585, 19314700)
    provider, _ = recovering_provider(live_calendar, short={
        "1d": frame([future]), "5d": frame([wrong_prior, COMPLETE, future])})
    result = provider.fetch(request_spec)
    assert result.provider_row_issues and not result.provenance
    assert provider.fetch_diagnostics["ADRO"][-1]["status"] == "recovery_overlap_conflict"


def test_history_incomplete_is_distinct_and_repaired_without_rewriting_target(
    live_calendar, request_spec,
):
    calls = []
    bad = frame([PRIOR[0], (*PRIOR[1][:4], None, PRIOR[1][5]), COMPLETE])
    def loader(*args, **kwargs):
        calls.append(kwargs)
        return (frame([PRIOR[1], COMPLETE]) if kwargs.get("period") == "5d" else
                frame([COMPLETE]) if "period" in kwargs else bad)
    provider = YFinanceProvider(loader, lambda _: None, calendar=live_calendar,
                                clock=lambda: live_calendar.get(DAYS[2]).closes_at,
                                request_interval_seconds=0)
    result = provider.fetch(request_spec)
    assert len(calls) == 5 and quality(result, DAYS[2], live_calendar) == "valid"
    assert provider.fetch_diagnostics["ADRO"][0]["status"] == "history_bar_incomplete"
    assert result.bars[-1].close == COMPLETE[4] and result.bars[1].close == PRIOR[1][4]


def test_retry_times_do_not_change_recovered_content_identity(live_calendar, request_spec):
    first, _ = recovering_provider(live_calendar)
    second, _ = recovering_provider(live_calendar,
        clock=lambda: live_calendar.get(DAYS[2]).closes_at + timedelta(days=1))
    a, b = first.fetch(request_spec), second.fetch(request_spec)
    assert a.input_digest == b.input_digest and a.bars == b.bars and a.provenance == b.provenance
    assert first.fetch_diagnostics["ADRO"][-1]["fetched_at"] != (
        second.fetch_diagnostics["ADRO"][-1]["fetched_at"])


def test_request_budget_exhaustion_preserves_hold_without_more_network(live_calendar, request_spec):
    provider, calls = recovering_provider(live_calendar, max_requests=3)
    result = provider.fetch(request_spec)
    assert len(calls) == 3 and result.provider_row_issues and not result.provenance
    assert provider.fetch_diagnostics["ADRO"][-1]["status"] == "provider_request_budget_exhausted"


def test_elapsed_budget_and_interticker_pacing_are_shared(live_calendar, request_spec):
    ticks = [0.0]
    calls, sleeps = [], []
    def loader(*args, **kwargs):
        calls.append(kwargs)
        return frame([*PRIOR, COMPLETE])
    provider = YFinanceProvider(loader, sleeps.append, calendar=live_calendar,
        monotonic=lambda: ticks[0], max_elapsed_seconds=2, request_interval_seconds=0.2)
    provider.fetch(request_spec)
    provider.fetch(request_spec)
    assert sleeps == [0.2] and len(calls) == 2
    ticks[0] = 2
    with pytest.raises(ProviderError, match="provider_request_budget_exhausted"):
        provider.fetch(request_spec)
    assert len(calls) == 2


def test_canonical_scanner_diagnostics_remain_safe_and_legacy_optional(
    live_calendar, request_spec,
):
    from idx_scanner.context import Universe
    from idx_scanner.engine import ScanItem
    provider, _ = recovering_provider(live_calendar, calendar=None)
    source = provider.fetch(request_spec)
    universe = Universe(("ADRO",), "synthetic-v1", DAYS[0], DAYS[-1], "synthetic://test", "live")
    result = scan({"ADRO": source}, DAYS[2], live_calendar, universe,
                  live_calendar.get(DAYS[2]).closes_at, ScanState(), source_revision="fixture")
    assert result.status == "failed" and result.coverage_valid == 0 and not result.signals
    assert result.items[0].diagnostics == {"contract_version": 1, "code": "missing_close",
        "session": "2026-10-12", "missing_fields": ["close"], "recovery_status": "unresolved"}
    assert ScanItem("ADRO", "missing", ()).diagnostics is None
    assert "NaN" not in canonical_json(result)
