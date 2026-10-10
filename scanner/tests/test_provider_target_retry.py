"""Fresh-provider retries never turn incomplete target candles into valid prices."""

from datetime import date

import pandas as pd
import pytest

from idx_scanner.models import canonical_json
from idx_scanner.providers import FetchRequest, ProviderError, YFinanceProvider


def frame(close=105, volume=1000, *, day="2026-01-06", actions=True):
    columns = {"Open": [100], "High": [110], "Low": [90], "Close": [close], "Volume": [volume]}
    if actions:
        columns.update({"Dividends": [0], "Stock Splits": [0]})
    return pd.DataFrame(columns, index=pd.to_datetime([day]))


@pytest.fixture
def request_spec():
    return FetchRequest("TEST", "TEST.JK", date(2026, 1, 2), date(2026, 1, 6), True)


def loader_for(receipts):
    calls = []
    def loader(*args, **kwargs):
        calls.append(kwargs)
        result = receipts[len(calls) - 1]
        if isinstance(result, Exception):
            raise result
        return result
    return loader, calls


def test_nonempty_missing_close_retries_fresh_then_preserves_final_identity(request_spec):
    loader, calls = loader_for([frame(float("nan")), frame()])
    sleeps = []
    provider = YFinanceProvider(loader, sleeps.append)
    result = provider.fetch(request_spec)
    assert len(calls) == 2 and len(sleeps) == 1
    assert not result.provider_row_issues and result.bars[-1].close == 105
    attempts = provider.fetch_diagnostics["TEST"]
    assert [d["status"] for d in attempts] == ["target_bar_incomplete", "valid_target_received"]
    assert attempts[0]["input_digest"] != attempts[1]["input_digest"]
    assert attempts[1]["input_digest"] == result.input_digest
    stable = YFinanceProvider(lambda *a, **k: frame(), lambda _: None).fetch(request_spec)
    assert stable.input_digest == result.input_digest
    assert all(d["fetched_at"] and d["attempt"] for d in attempts)


def test_all_incomplete_attempts_keep_last_invalid_row_and_diagnostics(request_spec):
    loader, calls = loader_for([frame(float("nan"), v) for v in (1000, 2000, 3000)])
    provider = YFinanceProvider(loader, lambda _: None)
    result = provider.fetch(request_spec)
    assert len(calls) == 3 and not result.bars
    assert dict(result.provider_row_issues[0].observed_values)["volume"] == 3000
    assert dict(result.provider_row_issues[0].observed_values)["close"] is None
    assert len(provider.fetch_diagnostics["TEST"]) == 3
    assert "NaN" not in canonical_json(result)


def test_incomplete_then_transport_exhaustion_does_not_reuse_earlier_capture(request_spec):
    loader, calls = loader_for([frame(float("nan")), RuntimeError("private-provider-token"), None])
    provider = YFinanceProvider(loader, lambda _: None)
    with pytest.raises(ProviderError, match="provider_empty_or_unavailable"):
        provider.fetch(request_spec)
    assert len(calls) == 3
    assert [d["status"] for d in provider.fetch_diagnostics["TEST"]] == [
        "target_bar_incomplete", "transport_error", "provider_empty"
    ]
    assert "private" not in str(provider.fetch_diagnostics)


@pytest.mark.parametrize("receipt", [frame(day="2026-01-02"), frame(volume=0)])
def test_stale_or_zero_volume_is_not_incomplete_target_retry(request_spec, receipt):
    loader, calls = loader_for([receipt])
    provider = YFinanceProvider(loader, lambda _: None)
    result = provider.fetch(request_spec)
    assert len(calls) == 1
    assert provider.fetch_diagnostics["TEST"][0]["retryable"] is False
    assert result.bars  # Scanner quality still decides stale/zero-volume hold.


def test_unknown_action_metadata_is_not_retried_or_approved(request_spec):
    loader, calls = loader_for([frame(actions=False)])
    provider = YFinanceProvider(loader, lambda _: None)
    with pytest.raises(ProviderError, match="corporate_actions_unknown"):
        provider.fetch(request_spec)
    assert len(calls) == 1
    assert provider.fetch_diagnostics["TEST"][0]["status"] == "corporate_actions_unknown"
