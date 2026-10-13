"""Synthetic source continuity and seeded-history regression, no network."""
from dataclasses import replace
from datetime import UTC, datetime

import httpx
import pytest

from idx_scanner.context import quality, quality_diagnostics
from idx_scanner.fixtures import sample_market
from idx_scanner.incremental_provider import IncrementalProvider, persist_provider_captures
from idx_scanner.models import CorporateAction, canonical_json
from idx_scanner.persistence import SupabaseScanStore
from idx_scanner.providers import FetchRequest


@pytest.fixture
def source():
    market, calendar, _ = sample_market(651)
    full = replace(market["DEMO-A"], provider="yfinance", provider_symbol="DEMO-A.JK",
                   price_basis="yahoo_provider_ohlcv_auto_adjust_false_v1",
                   fetched_at=datetime.now(UTC))
    return full, calendar


class Store:
    def __init__(self, base):
        self.base = base
        self.saved = []

    def _request(self, method, table, params):
        assert method == "GET" and params["bar_count"] == "gte.600"
        return [{"id": "stored", "input_digest": self.base.input_digest}]

    def load_series(self, revision, **kwargs):
        assert kwargs["expected_input_digest"] == self.base.input_digest
        return self.base

    def ingest_series(self, value, **kwargs):
        self.saved.append(value)


class Provider:
    fetch_diagnostics = {}
    raw_recovery_captures = {}

    def __init__(self, full, mutate=None):
        self.full, self.mutate = full, mutate
        self.requests = []

    def fetch(self, request):
        self.requests.append(request)
        result = replace(self.full, bars=tuple(b for b in self.full.bars
                                              if request.start <= b.session <= request.end))
        return self.mutate(result) if self.mutate and len(self.requests) == 1 else result


def test_incremental_restores_full_indicator_seed_and_persists_overlap(source):
    full, calendar = source
    base = replace(full, bars=full.bars[:-1])
    store, provider = Store(base), Provider(full)
    wrapper = IncrementalProvider(provider, store, calendar)
    request = FetchRequest(full.ticker, full.provider_symbol, full.bars[0].session,
                           full.bars[-1].session, True)
    result = wrapper.fetch(request)
    assert result.bars == full.bars and quality(result, request.end, calendar) == "valid"
    assert provider.requests[0].start == base.bars[-10].session
    persist_provider_captures(wrapper, store, full.ticker, data_mode="live")
    assert len(store.saved[0].bars) == 11


@pytest.mark.parametrize("change", ["price", "action", "hole", "basis"])
def test_overlap_conflict_requires_full_reconstruction(source, change):
    full, calendar = source
    def mutate(result):
        if change == "price":
            return replace(result, bars=(replace(result.bars[0], close=result.bars[0].close + 1),)
                           + result.bars[1:])
        if change == "action":
            return replace(result, actions=(CorporateAction(result.bars[0].session, "split", "2"),))
        if change == "hole":
            return replace(result, bars=result.bars[1:])
        return replace(result, price_basis="unapproved_basis")
    provider = Provider(full, mutate)
    wrapper = IncrementalProvider(provider, Store(replace(full, bars=full.bars[:-1])), calendar)
    request = FetchRequest(full.ticker, full.provider_symbol, full.bars[0].session,
                           full.bars[-1].session, True)
    result = wrapper.fetch(request)
    assert len(provider.requests) == 2 and provider.requests[-1] == request
    assert result.input_digest == full.input_digest


def test_periodic_full_refresh_does_not_claim_overlap_catches_old_revisions(source):
    full, calendar = source
    base = replace(full, bars=full.bars[:-1], provenance=(canonical_json({
        "kind": "yahoo_persisted_incremental_v1",
        "full_refresh_session": full.bars[-12].session.isoformat(),
    }),))
    provider = Provider(full)
    request = FetchRequest(full.ticker, full.provider_symbol, full.bars[0].session,
                           full.bars[-1].session, True)
    assert IncrementalProvider(provider, Store(base), calendar).fetch(request) == full
    assert provider.requests == [request]


def test_missing_historical_session_diagnostic_points_to_actual_gap(source):
    full, calendar = source
    day = full.bars[-2].session
    broken = replace(full, bars=tuple(b for b in full.bars if b.session != day))
    assert quality(broken, full.bars[-1].session, calendar) == "history_gap"
    result = quality_diagnostics(broken, full.bars[-1].session, calendar)
    assert result["session"] == day.isoformat() and result["code"] == "missing_session"
    assert result["missing_fields"] == ["open", "high", "low", "close", "volume"]


def test_revision_lookup_uses_sql_revision_cutoff_as_integer_not_session(source):
    full, calendar = source
    requests = []

    def database(request):
        assert request.url.path == "/rest/v1/market_series_revisions"
        requests.append(request)
        # SQL002 defines bar_cutoff as bigint revision_seq, not a market date.
        cutoff = request.url.params.get("bar_cutoff")
        if cutoff is not None:
            try:
                int(cutoff.split(".", 1)[1])
            except ValueError:
                return httpx.Response(400, json={"code": "22P02"})
        return httpx.Response(200, json=[])

    request = FetchRequest(full.ticker, full.provider_symbol, full.bars[0].session,
                           full.bars[-1].session, True)
    with SupabaseScanStore("https://example.supabase.co", "test-key",
                           transport=httpx.MockTransport(database)) as store:
        assert IncrementalProvider(Provider(full), store, calendar).fetch(request) == full
    assert len(requests) == 1


def test_future_persisted_revision_cannot_seed_a_historical_target(source):
    full, calendar = source
    target = full.bars[-2].session
    provider = Provider(full)
    request = FetchRequest(full.ticker, full.provider_symbol, full.bars[0].session, target, True)
    result = IncrementalProvider(provider, Store(full), calendar).fetch(request)
    assert provider.requests == [request]
    assert result.bars == full.bars[:-1]
    assert result.bars[-1].session == target
    assert not any('yahoo_persisted_incremental_v1' in p for p in result.provenance)


def test_incremental_provider_base_skips_reviewed_backfill(source):
    full, calendar = source
    backfill_provenance = canonical_json({"kind": "reviewed_historical_backfill_v1"})
    base = replace(full, bars=full.bars[:-1], provenance=(backfill_provenance,))
    store, provider = Store(base), Provider(full)
    wrapper = IncrementalProvider(provider, store, calendar)
    request = FetchRequest(full.ticker, full.provider_symbol, full.bars[0].session,
                           full.bars[-1].session, True)
    result = wrapper.fetch(request)
    assert result.bars == full.bars
    # When base with reviewed backfill provenance is skipped, provider fetch is called
    # with full request directly
    assert provider.requests == [request]
