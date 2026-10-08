"""Out-of-universe paper monitoring against explicit offline persisted fixtures."""
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from test_paper_runtime import PersistedFixtureStore, initial, market

from idx_scanner.persistence import PersistenceError
from idx_scanner.providers import FetchRequest, ProviderError

SCRIPTS = Path(__file__).resolve().parents[2] / "supabase" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from paper_runtime_runner import complete_persisted_paper  # noqa: E402


class SnapshotStore:
    def __init__(self, source, original_digest):
        self.source = source
        self.original_digest = original_digest
        self.ingested = []
        self.lookups = []

    def _request(self, method, table, *, params):
        assert method == "GET" and table == "market_series_revisions"
        self.lookups.append(params)
        assert params["input_digest"] == "eq." + self.original_digest
        return [{"id": "original", "input_digest": self.original_digest}]

    def ingest_series(self, source, *, data_mode):
        assert data_mode == "fixture"
        self.ingested.append(source)
        return {"revision_id": "tracked"}

    def load_series(self, revision, *, data_mode, expected_input_digest):
        assert data_mode == "fixture"
        assert expected_input_digest == (self.original_digest if revision == "original"
                                         else self.source.input_digest)
        return self.source


class OutsideProvider:
    def __init__(self, source, fail=False):
        self.source, self.fail = source, fail
        self.requests = []

    def fetch(self, request):
        self.requests.append(request)
        assert request.symbol == "EXPLICIT_OLD.JK" and request.mapping_verified
        if self.fail:
            raise ProviderError("provider_unavailable")
        return self.source


@pytest.mark.parametrize("fail", [False, True])
def test_recovered_signal_outside_universe_uses_original_verified_mapping(
    signal, calendar, fail,
):
    target = calendar.sessions[1]
    source = replace(market(signal, calendar, 2)[signal.ticker],
                     provider_symbol="EXPLICIT_OLD.JK")
    store = PersistedFixtureStore(initial(calendar), [signal])
    store.data_mode = "fixture"
    snapshots = SnapshotStore(source, signal.input_digest)
    provider = OutsideProvider(source, fail)
    # The scanner comparison set is separate and must never gain the old ticker.
    requests = {"CURRENT": FetchRequest("CURRENT", "CURRENT.JK", signal.session,
                                         target.day, True)}
    prepared = {}
    book, summary = complete_persisted_paper(
        snapshots, store, prepared, requests, target.day, calendar, (), target.closes_at,
        provider, "22222222-2222-4222-8222-222222222222",
    )
    assert list(requests) == ["CURRENT"] and prepared == {}
    assert len(provider.requests) == 1 and len(snapshots.lookups) == 1
    assert len(book.trades) == 2 and len(store.state["evaluations"]) == 1
    if fail:
        assert summary["provider_errors"] == [{"ticker": signal.ticker,
                                                "code": "provider_unavailable"}]
        assert all(t.state == "data_hold" for t in book.trades.values())
    else:
        assert summary["provider_errors"] == []
        assert all(t.entry == 101 for t in book.trades.values())
        assert len(snapshots.ingested) == 2


def test_unverified_historical_mapping_fails_instead_of_guessing(signal, calendar):
    class MissingOriginal(SnapshotStore):
        def _request(self, *args, **kwargs):
            return []
    source = market(signal, calendar, 2)[signal.ticker]
    store = PersistedFixtureStore(initial(calendar), [signal])
    store.data_mode = "fixture"
    provider = OutsideProvider(source)
    with pytest.raises(PersistenceError, match="paper_original_mapping_unavailable"):
        complete_persisted_paper(
            MissingOriginal(source, signal.input_digest), store, {}, {},
            calendar.sessions[1].day, calendar, (), calendar.sessions[1].closes_at,
            provider, None,
        )
    assert provider.requests == [] and store.state["revision"] == 0
