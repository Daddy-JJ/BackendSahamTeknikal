"""Synthetic official-evidence fixtures; no production suspension is invented."""

import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D

import pytest
from conftest import bar
from test_paper_runtime import PersistedFixtureStore

from idx_scanner.context import quality
from idx_scanner.fixtures import sample_market
from idx_scanner.models import Costs, Series
from idx_scanner.paper import (
    EXACT_SIZING_POLICY,
    LEGACY_SIZING_POLICY,
    PaperBook,
    cash_fee,
    paper_book_from_dict,
    paper_book_to_dict,
    size_lots,
)
from idx_scanner.paper_research import create_evaluation, step_evaluation
from idx_scanner.paper_runtime import advance_runtime, process_persisted_paper_session
from idx_scanner.untradable import VerifiedUntradable, load_untradable_evidence


@pytest.fixture
def lifecycle(signal):
    _, calendar, _ = sample_market(24)
    signal_day, entry_day = calendar.sessions[9:11]
    signal = replace(signal, session=signal_day.day, planned_entry_session=entry_day.day,
                     published_at=signal_day.closes_at,
                     candidate=replace(signal.candidate, reference_close=100, stop=90))
    source = Series(signal.ticker, "TEST.JK", "fixture", "test", tuple(
        bar(s.day, 100, 102, 95, 100) for s in calendar.sessions[:24]
    ))
    return calendar, signal, source


def proof(signal, session):
    return VerifiedUntradable(signal.ticker, session.day, "fixture",
                             "synthetic://reviewed-suspension", "a" * 64, session.closes_at)


def initial_state(calendar):
    return {"owner_id": "11111111-1111-4111-8111-111111111111", "data_mode": "fixture",
            "model_version": "close-signal-risk-v1",
            "activated_at": calendar.sessions[0].opens_at.isoformat(), "revision": 0,
            "book": {"trades": {}, "experiments": {}}, "evaluations": {}}


def source_until(source, session, *, missing=(), closes=None):
    return replace(source, bars=tuple(replace(b, close=closes[b.session])
        if closes and b.session in closes else b for b in source.bars
        if b.session <= session and b.session not in missing))


def test_verified_entry_suspension_expires_and_excludes_without_fill(lifecycle):
    calendar, signal, source = lifecycle
    suspended = calendar.sessions[10]
    evidence = (proof(signal, suspended),)
    market = {signal.ticker: source_until(source, suspended.day, missing=(suspended.day,))}
    store = PersistedFixtureStore(initial_state(calendar), [signal])
    book, _ = process_persisted_paper_session(
        store, suspended.day, market, calendar, suspended.closes_at,
        mappings={signal.ticker: "TEST.JK"}, untradable_evidence=evidence,
    )
    assert all(t.state == "expired" and t.entry is None and t.reason == "expired_untradable"
               for t in book.trades.values())
    assert all(t.events[-1].session == suspended.day and t.events[-1].kind == "entry_expired"
               and t.events[-1].untradable_evidence["document_sha256"] == "a" * 64
               for t in book.trades.values())
    record = store.state["evaluations"][signal.id]
    assert record["observed_sessions"] == 0 and record["last_session"] is None
    assert set(record["results"].values()) == {"excluded"}
    assert set(record["exclusion_reasons"].values()) == {"official_untradable_entry"}
    snapshot = paper_book_to_dict(book)
    replay, _ = process_persisted_paper_session(
        store, suspended.day, market, calendar, suspended.closes_at,
        untradable_evidence=evidence,
    )
    assert paper_book_to_dict(replay) == snapshot
    assert paper_book_from_dict(snapshot) == book


@pytest.mark.parametrize("zero_placeholder", [False, True])
@pytest.mark.parametrize("pending_ma", [False, True])
def test_suspension_history_recovery_through_persisted_runtime(
    lifecycle, zero_placeholder, pending_ma,
):
    calendar, signal, source = lifecycle
    entry, suspended, resumed = calendar.sessions[10:13]
    missing = () if zero_placeholder else (suspended.day,)
    source = source_until(source, resumed.day, missing=missing,
                          closes={entry.day: 99 if pending_ma else 100,
                                  resumed.day: 100 if pending_ma else 99})
    if zero_placeholder:
        source = replace(source, bars=tuple(replace(b, volume=0) if b.session == suspended.day
                                           else b for b in source.bars))
    assert quality(source, resumed.day, calendar) != "valid"  # Scanner/RS stays unchanged.
    store = PersistedFixtureStore(initial_state(calendar), [signal])
    book, _ = process_persisted_paper_session(
        store, resumed.day, {signal.ticker: source}, calendar, resumed.closes_at,
        untradable_evidence=(proof(signal, suspended),),
    )
    ma = next(t for t in book.trades.values() if t.experiment.exit.mode == "ma_close")
    assert ma.events[0].session == entry.day and ma.entry == D(100)
    assert any(e.kind == "untradable" and e.session == suspended.day for e in ma.events)
    if pending_ma:
        assert ma.state == "closed" and ma.events[-1].session == resumed.day
        assert ma.events[-1].reason == "ma_breakdown" and ma.events[-1].price == 100
    else:
        assert ma.state == "open" and ma.pending_exit == calendar.sessions[13].day
        assert ma.events[-1].ma_value == D("99.9")
    evaluation = store.state["evaluations"][signal.id]
    assert evaluation["observed_sessions"] == 3
    assert [x["session"] for x in evaluation["input_digests"]] == [
        entry.day.isoformat(), suspended.day.isoformat(), resumed.day.isoformat()
    ]
    assert ma.initial_risk == ma.quantity * D(10)


def test_unknown_missing_or_not_yet_verified_stays_held(lifecycle):
    calendar, signal, source = lifecycle
    entry = calendar.sessions[10]
    source = source_until(source, entry.day, missing=(entry.day,))
    late_proof = replace(proof(signal, entry), verified_at=entry.closes_at + timedelta(hours=1))
    for evidence in ((), (late_proof,)):
        book, records = advance_runtime(
            PaperBook(), {}, [signal], calendar.sessions[0].opens_at,
            entry.day, {signal.ticker: source}, calendar, entry.closes_at, {},
            untradable_evidence=evidence,
        )
        assert all(t.state == "data_hold" and not t.events for t in book.trades.values())
        assert set(records[signal.id]["results"].values()) == {"data_hold"}


def test_restart_restores_frozen_suspension_without_local_configuration(lifecycle):
    calendar, signal, source = lifecycle
    entry, suspended, resumed = calendar.sessions[10:13]
    store = PersistedFixtureStore(initial_state(calendar), [signal])
    partial = source_until(source, suspended.day, missing=(suspended.day,))
    process_persisted_paper_session(
        store, suspended.day, {signal.ticker: partial}, calendar, suspended.closes_at,
        untradable_evidence=(proof(signal, suspended),),
    )
    fresh = PersistedFixtureStore(store.state, [signal])
    recovered, _ = process_persisted_paper_session(
        fresh, resumed.day,
        {signal.ticker: source_until(source, resumed.day, missing=(suspended.day,),
                                     closes={resumed.day: 99})},
        calendar, resumed.closes_at,  # No operator evidence file at restart.
    )
    assert all(t.entry == 100 and t.events[0].session == entry.day
               and t.last_session == resumed.day for t in recovered.trades.values())
    assert fresh.state["evaluations"][signal.id]["observed_sessions"] == 3
    conflicting = replace(proof(signal, suspended), document_sha256="b" * 64)
    with pytest.raises(ValueError, match="conflicting_untradable_evidence"):
        process_persisted_paper_session(
            fresh, resumed.day, {}, calendar, resumed.closes_at,
            untradable_evidence=(conflicting,),
        )
    malformed = fresh.state["evaluations"][signal.id]["untradable_evidence"][0]
    malformed["verified_at"] = (resumed.closes_at + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="invalid_frozen_untradable_evidence"):
        process_persisted_paper_session(fresh, resumed.day, {}, calendar, resumed.closes_at)


def test_conflicting_trading_bar_or_wrong_evidence_mode_fails_before_commit(lifecycle):
    calendar, signal, source = lifecycle
    entry = calendar.sessions[10]
    for evidence in ((proof(signal, entry),), (replace(
        proof(signal, entry), data_mode="live", source_url="https://www.idx.co.id/suspension.pdf"
    ),)):
        store = PersistedFixtureStore(initial_state(calendar), [signal])
        with pytest.raises(ValueError, match="untradable"):
            process_persisted_paper_session(
                store, entry.day, {signal.ticker: source_until(source, entry.day)}, calendar,
                entry.closes_at, untradable_evidence=evidence,
            )
        assert store.state["revision"] == 0 and not store.state["book"]["trades"]


def test_suspended_horizon_excludes_exact_checkpoint_without_shifting(lifecycle):
    calendar, signal, _ = lifecycle
    record = create_evaluation(signal)
    for offset in range(6):
        session = calendar.sessions[10 + offset]
        record = step_evaluation(
            record, session.day, None if offset == 4 else bar(session.day, 100, 102, 95, 101),
            calendar, session.closes_at,
            untradable_evidence=proof(signal, session) if offset == 4 else None,
        )
    assert record["observed_sessions"] == 6
    assert record["results"]["net_5"] == "excluded"
    assert record["exclusion_reasons"]["net_5"] == "official_untradable_horizon"
    assert record["results"]["net_10"] == "pending"
    assert record["results"]["target_1r"] == record["results"]["target_2r"] == "pending"


def test_strict_evidence_loader_and_empty_live_config(tmp_path, lifecycle):
    calendar, signal, _ = lifecycle
    evidence = proof(signal, calendar.sessions[10]).audit()
    evidence = {k: v for k, v in evidence.items() if k not in ("version", "data_mode", "digest")}
    path = tmp_path / "reviewed.json"
    payload = {"version": "verified_untradable_v1", "data_mode": "fixture",
               "records": [evidence]}
    path.write_text(json.dumps(payload))
    assert len(load_untradable_evidence(path, "fixture")) == 1
    for records in ([evidence, evidence], [{**evidence, "source_url": "https://example.com"}],
                    [{**evidence, "document_sha256": "not-reviewed"}],
                    [{**evidence, "verified_at": "2026-01-01T00:00:00"}]):
        path.write_text(json.dumps({**payload, "records": records}))
        with pytest.raises(ValueError, match="invalid_untradable_evidence_file"):
            load_untradable_evidence(path, "fixture")
    path.write_text(json.dumps({"version": "verified_untradable_v1", "data_mode": "live",
                                "records": []}))
    assert load_untradable_evidence(path, "live") == ()
    with pytest.raises(ValueError):
        load_untradable_evidence(path, "fixture")


def test_exact_new_plan_cap_preserves_legacy_snapshot_policy(lifecycle):
    costs = Costs(D(15), D(25), D(0), "verified")
    entry, stop = D(10000), D("15.03759399496240601503759398")
    exact = 100 * (entry - stop) + cash_fee(100 * entry, D(15)) + cash_fee(100 * stop, D(25))
    assert exact > D(1000000)
    assert size_lots(entry, stop, costs)[0] == 0
    assert size_lots(entry, stop, costs, sizing_policy_version=LEGACY_SIZING_POLICY)[0] == 1
    calendar, signal, source = lifecycle
    book, _ = advance_runtime(PaperBook(), {}, [signal], calendar.sessions[0].opens_at,
                              signal.session, {signal.ticker: source_until(source, signal.session)},
                              calendar, signal.published_at, {})
    snapshot = paper_book_to_dict(book)
    assert all(t["sizing_policy_version"] == EXACT_SIZING_POLICY
               for t in snapshot["trades"].values())
    for t in snapshot["trades"].values():
        del t["sizing_policy_version"]
    old = paper_book_from_dict(snapshot)
    assert all(t.sizing_policy_version == LEGACY_SIZING_POLICY for t in old.trades.values())
    assert paper_book_to_dict(old) == snapshot  # No historical config/event mutation.


def test_evaluation_only_data_hold_remains_visible_in_runtime_summary(lifecycle):
    calendar, signal, source = lifecycle
    entry, missing = calendar.sessions[10:12]
    # Fixed exits at the target gap; MA exits next open. Independent horizons
    # remain active after both exits and must still report a missing session.
    store = PersistedFixtureStore(initial_state(calendar), [signal])
    source = source_until(source, entry.day)
    source = replace(source, bars=tuple(
        bar(b.session, 121, 122, 95, 99) if b.session == entry.day else b for b in source.bars
    ))
    book, _ = process_persisted_paper_session(
        store, entry.day, {signal.ticker: source}, calendar, entry.closes_at,
    )
    # The MA exits next open; all research targets won, horizons still pending.
    resumed = replace(source, bars=source.bars + (bar(missing.day, 100, 102, 95, 100),))
    process_persisted_paper_session(
        store, missing.day, {signal.ticker: resumed}, calendar, missing.closes_at,
    )
    later = calendar.sessions[12]
    book, summary = process_persisted_paper_session(
        store, later.day, {signal.ticker: resumed}, calendar, later.closes_at,
    )
    assert all(t.state == "closed" for t in book.trades.values())
    assert summary["trades_data_hold_count"] == 0
    assert summary["evaluations_data_hold_count"] == summary["data_hold_count"] == 1
