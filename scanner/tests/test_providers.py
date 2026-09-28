from datetime import date

import httpx
import pandas as pd
import pytest

from idx_scanner.providers import (
    EODHDProvider,
    FetchRequest,
    ProviderError,
    YFinanceProvider,
    make_provider,
)


@pytest.fixture
def request_spec():
    return FetchRequest("TEST", "TEST.EX", date(2026, 1, 2), date(2026, 1, 6), True)


def test_yahoo_explicit_parameters_and_inclusive_end(request_spec):
    seen = {}

    def loader(symbol, **kwargs):
        seen.update(kwargs)
        return pd.DataFrame(
            {
                "Open": [100],
                "High": [110],
                "Low": [90],
                "Close": [105],
                "Volume": [1000],
                "Adj Close": [50],
                "Dividends": [0],
                "Stock Splits": [0],
            },
            index=pd.to_datetime(["2026-01-02"]),
        )

    series = YFinanceProvider(loader, lambda _: None).fetch(request_spec)
    assert seen["end"] == "2026-01-07"
    assert seen["auto_adjust"] is False and seen["actions"] is True
    assert seen["repair"] is False and seen["keepna"] is True
    assert series.bars[0].close == 105 and series.bars[0].adjusted_close == 50


def test_eodhd_three_endpoints_and_unadjusted_close(request_spec):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        assert request.url.params["to"] == "2026-01-06"
        if "/eod/" in request.url.path:
            assert request.url.params["period"] == "d"
            return httpx.Response(
                200,
                json=[
                    {
                        "date": "2026-01-02",
                        "open": 100,
                        "high": 110,
                        "low": 90,
                        "close": 105,
                        "adjusted_close": 50,
                        "volume": 1000,
                    }
                ],
            )
        return httpx.Response(200, json=[])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = EODHDProvider("test-secret", client, lambda _: None)
        result = provider.fetch(request_spec)
        assert "test-secret" not in repr(provider)
    assert len(paths) == 3 and result.bars[0].close == 105
    assert result.price_basis == "eodhd_unadjusted_ohlc_v1"


@pytest.mark.parametrize(
    "status,code,retries",
    [
        (401, "provider_auth_or_entitlement_denied", 1),
        (403, "provider_auth_or_entitlement_denied", 1),
        (404, "provider_symbol_not_found", 1),
        (429, "provider_rate_limited", 3),
        (500, "provider_unavailable", 3),
    ],
)
def test_eodhd_bounded_retry_and_sanitized_error(request_spec, status, code, retries):
    attempts = []

    def handler(request):
        attempts.append(1)
        return httpx.Response(status, text="secret-in-provider-body")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as error:
            EODHDProvider("secret-token", client, lambda _: None).fetch(request_spec)
    assert str(error.value) == code and len(attempts) == retries
    assert "secret" not in str(error.value)


def test_transport_timeout_is_sanitized(request_spec):
    def handler(request):
        raise httpx.ReadTimeout("url contains api_token=secret", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError, match="provider_unavailable") as error:
            EODHDProvider("secret", client, lambda _: None).fetch(request_spec)
    assert error.value.__suppress_context__


@pytest.mark.parametrize(
    "payload",
    [
        {"error": "bad"},
        [{"date": "2026-01-02", "open": 100, "high": 1, "low": 90, "close": 105, "volume": 1000}],
    ],
)
def test_malformed_payload_rejected(request_spec, payload):
    def handler(request):
        return httpx.Response(200, json=payload if "/eod/" in request.url.path else [])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError, match="invalid_provider_payload"):
            EODHDProvider("secret", client, lambda _: None).fetch(request_spec)


def test_no_key_no_fallback(monkeypatch):
    monkeypatch.delenv("EODHD_API_TOKEN", raising=False)
    with httpx.Client() as client:
        with pytest.raises(ProviderError, match="credentials_missing"):
            make_provider("eodhd", client)
    with pytest.raises(ValueError, match="no automatic fallback"):
        make_provider("auto")


def test_mapping_must_be_explicit_and_verified():
    with pytest.raises(ValueError):
        FetchRequest("TEST", "TEST.EX", date(2026, 1, 1), date(2026, 2, 1), False)
    with pytest.raises(ValueError):
        FetchRequest("TEST", "TEST.EX?api_token=evil", date(2026, 1, 1), date(2026, 2, 1), True)


def test_yahoo_empty_rows_preserved_as_gaps_not_fabricated_bars(request_spec):
    from idx_scanner.models import canonical_json

    def loader(symbol, **kwargs):
        return pd.DataFrame(
            {
                "Open": [100, float("nan")],
                "High": [110, float("nan")],
                "Low": [90, float("nan")],
                "Close": [105, float("nan")],
                "Volume": [1000, 0],
                "Adj Close": [100, float("nan")],
                "Dividends": [0, 0],
                "Stock Splits": [0, 0],
            },
            index=pd.to_datetime(["2026-01-02", "2026-01-06"]),
        )

    series = YFinanceProvider(loader, lambda _: None).fetch(request_spec)
    assert len(series.bars) == 1
    assert series.provider_missing_sessions == (date(2026, 1, 6),)
    assert "NaN" not in canonical_json(series)


def test_missing_row_is_only_excluded_when_explicit_calendar_is_closed(calendar):
    from dataclasses import replace

    from idx_scanner.context import quality
    from idx_scanner.models import Bar, Series

    candles = tuple(Bar(s.day, 100, 110, 90, 105, 100) for s in calendar.sessions[:2])
    series = Series(
        "TEST", "TEST", "fixture", "test", candles, provider_missing_sessions=(date(2026, 1, 5),)
    )
    assert quality(series, date(2026, 1, 6), calendar) == "valid"
    assert (
        quality(
            replace(series, provider_missing_sessions=(date(2026, 1, 2),)),
            date(2026, 1, 6),
            calendar,
        )
        == "missing_session"
    )


def test_partial_daily_bar_is_audited_and_holds_scan(request_spec, calendar):
    from idx_scanner.context import quality
    from idx_scanner.models import canonical_json

    def loader(symbol, **kwargs):
        return pd.DataFrame(
            {
                "Open": [100, 100],
                "High": [110, 110],
                "Low": [90, 90],
                "Close": [105, float("nan")],
                "Volume": [1000, 1200],
                "Adj Close": [100, float("nan")],
                "Dividends": [0, 0],
                "Stock Splits": [0, 0],
            },
            index=pd.to_datetime(["2026-01-02", "2026-01-06"]),
        )

    series = YFinanceProvider(loader, lambda _: None).fetch(request_spec)
    assert len(series.bars) == 1
    assert series.provider_row_issues[0].code == "incomplete_ohlcv"
    assert dict(series.provider_row_issues[0].observed_values)["close"] is None
    assert dict(series.provider_row_issues[0].observed_values)["volume"] == 1200
    assert quality(series, date(2026, 1, 6), calendar) == "data_quality_hold"
    assert "NaN" not in canonical_json(series)
