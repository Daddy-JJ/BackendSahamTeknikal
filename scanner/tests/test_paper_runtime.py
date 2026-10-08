"""Persistence restart and chronology tests; all market rows are explicit fixtures."""
import copy
from datetime import datetime

import httpx
import pytest
from conftest import bar

from idx_scanner.models import Series
from idx_scanner.paper_persistence import PaperRuntimeStore
from idx_scanner.paper_research import MODEL_VERSION
from idx_scanner.paper_runtime import process_persisted_paper_session
from idx_scanner.persistence import PersistenceError, SupabaseScanStore

OWNER = "11111111-1111-4111-8111-111111111111"


class PersistedFixtureStore:
    def __init__(self, state, signals):
        self.state, self.signals = state, signals
        self.owner_id = OWNER
        self.requests = {}
        self.fail_commit = False

    def load(self):
        return copy.deepcopy(self.state)

    def committed_signals(self, target, activation):
        return [s for s in self.signals if s.session <= target and s.published_at >= activation]

    def commit(self, *, revision, request_id, session, book, evaluations, source_run_id=None):
        if self.fail_commit:
            raise PersistenceError("database_transport_failed")
        if request_id in self.requests:
            return {"revision": self.requests[request_id], "replayed": True}
        assert revision == self.state["revision"]
        self.state.update(book=copy.deepcopy(book), evaluations=copy.deepcopy(evaluations),
                          revision=revision + 1)
        self.requests[request_id] = revision + 1
        return {"revision": revision + 1, "replayed": False}


def initial(calendar):
    return {"owner_id": OWNER, "data_mode": "fixture", "model_version": MODEL_VERSION,
            "activated_at": calendar.sessions[0].opens_at.isoformat(), "revision": 0,
            "book": {"trades": {}, "experiments": {}}, "evaluations": {}}


def market(signal, calendar, count):
    candles = [bar(s.day, 101, 114 if i == 1 else 104, 96, 103)
               for i, s in enumerate(calendar.sessions[:count])]
    return {signal.ticker: Series(signal.ticker, "TEST.JK", "fixture", "test", tuple(candles),
                                  actions_complete=True)}


def test_fresh_runner_restores_pending_trades_and_retry_no_duplicate(signal, calendar):
    persisted = initial(calendar)
    first = PersistedFixtureStore(persisted, [signal])
    book, summary = process_persisted_paper_session(
        first, signal.session, market(signal, calendar, 1), calendar,
        signal.published_at, mappings={signal.ticker: "TEST.JK"},
    )
    assert len(book.trades) == 2 and summary["evaluations_count"] == 1
    assert all(t.entry is None and t.planned_entry_price == 101 for t in book.trades.values())
    # Fresh process has no JSON file or Python book; only the persisted fixture survives.
    restored = PersistedFixtureStore(persisted, [signal])
    day = calendar.sessions[1]
    book, summary = process_persisted_paper_session(
        restored, day.day, market(signal, calendar, 2), calendar, day.closes_at,
    )
    fixed = next(t for t in book.trades.values() if t.experiment.exit.mode == "fixed_rr")
    ma = next(t for t in book.trades.values() if t.experiment.exit.mode == "ma_close")
    assert fixed.state == "closed" and fixed.entry == 101
    assert ma.state == "open" and len(persisted["evaluations"]) == 1
    before = copy.deepcopy(persisted)
    _, repeated = process_persisted_paper_session(
        restored, day.day, market(signal, calendar, 2), calendar, day.closes_at,
    )
    assert repeated["commit_replayed"] and persisted == before
    assert "metrics" not in summary and "strategy_metrics" not in summary


def test_missing_bar_holds_then_replays_original_entry_not_recovery(signal, calendar):
    store = PersistedFixtureStore(initial(calendar), [signal])
    process_persisted_paper_session(store, signal.session, market(signal, calendar, 1),
                                   calendar, signal.published_at)
    day = calendar.sessions[2]
    held, _ = process_persisted_paper_session(store, day.day, {}, calendar, day.closes_at)
    assert all(t.state == "data_hold" and t.entry is None for t in held.trades.values())
    recovered, _ = process_persisted_paper_session(store, day.day, market(signal, calendar, 3),
                                                calendar, day.closes_at)
    assert all(t.events[0].session == signal.planned_entry_session
               for t in recovered.trades.values())
    assert store.state["evaluations"][signal.id]["observed_sessions"] == 2


def test_failed_commit_does_not_advance_durable_state(signal, calendar):
    state = initial(calendar)
    store = PersistedFixtureStore(state, [signal])
    store.fail_commit = True
    with pytest.raises(PersistenceError, match="database_transport_failed"):
        process_persisted_paper_session(store, signal.session, market(signal, calendar, 1),
                                       calendar, signal.published_at)
    assert state["revision"] == 0 and state["book"]["trades"] == {}
    store.fail_commit = False
    book, _ = process_persisted_paper_session(store, signal.session, market(signal, calendar, 1),
                                            calendar, signal.published_at)
    assert len(book.trades) == 2


def test_adapter_rejects_incomplete_runtime_and_never_uses_local_state(calendar):
    payload = initial(calendar)
    def respond(request):
        assert request.url.path == "/rest/v1/rpc/load_paper_runtime_v1"
        return httpx.Response(200, json=payload)
    with SupabaseScanStore("http://127.0.0.1", "fixture-only-key", allow_local=True,
                           transport=httpx.MockTransport(respond)) as scan:
        store = PaperRuntimeStore(scan, OWNER, "fixture")
        assert datetime.fromisoformat(store.load()["activated_at"]).tzinfo is not None
        del payload["book"]
        with pytest.raises(PersistenceError, match="database_invalid_paper_runtime"):
            store.load()


def test_pre_activation_signals_are_not_repriced(signal, calendar):
    state = initial(calendar)
    state["activated_at"] = calendar.sessions[1].opens_at.isoformat()
    store = PersistedFixtureStore(state, [signal])
    book, summary = process_persisted_paper_session(
        store, calendar.sessions[1].day, market(signal, calendar, 2), calendar,
        calendar.sessions[1].closes_at,
    )
    assert book.trades == {} and summary["evaluations_count"] == 0
