"""Approved close-reference paper sizing, fill timing, and ledger regressions."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D

import pytest
from conftest import bar

from idx_scanner.context import Calendar, Session
from idx_scanner.models import Costs, ExitConfig
from idx_scanner.paper import (
    EXACT_SIZING_POLICY,
    Experiment,
    PaperBook,
    cash_fee,
    create_plan,
    paper_book_from_dict,
    paper_book_to_dict,
    size_lots,
    sized_profit,
    step,
    summarize_book,
)


@pytest.fixture
def close_calendar():
    # Synthetic explicit exchange sessions: Jan 5 is a holiday, weekends excluded.
    days = [date(2026, 1, 2)]
    for offset in range(4, 32):
        day = date(2026, 1, 2) + timedelta(days=offset)
        if day.weekday() < 5:
            days.append(day)
    return Calendar(
        tuple(Session(day, datetime(day.year, day.month, day.day, 2, tzinfo=UTC),
                      datetime(day.year, day.month, day.day, 9, tzinfo=UTC)) for day in days),
        "close-test-v1", "synthetic://close-calendar", "fixture",
    )


@pytest.fixture
def close_signal(signal, close_calendar):
    return replace(
        signal,
        candidate=replace(signal.candidate, stop=925, reference_close=1000),
        session=close_calendar.sessions[0].day,
        planned_entry_session=close_calendar.sessions[1].day,
        published_at=close_calendar.sessions[0].closes_at + timedelta(hours=3),
    )


@pytest.fixture
def close_experiment(close_calendar):
    return Experiment(
        "close-fixed-2r", "FRACTAL_BREAKOUT_V1", ExitConfig(),
        Costs(D(15), D(25), D(0), "verified"),
        close_calendar.sessions[0].opens_at,
        entry_model="signal_close", risk_budget_idr=D(1000000),
        model_version="close-signal-risk-v1",
    )


def test_fee_inclusive_cap_floors_lots_and_freezes_plan(
    close_signal, close_experiment, close_calendar,
):
    trade = create_plan(close_signal, close_experiment, close_calendar)
    assert trade.state == "pending_entry" and trade.entry is None
    assert trade.planned_entry_price == D(1000)
    assert (trade.lots, trade.quantity) == (126, 12600)
    assert trade.stop == D(925) and trade.target == D(1150)
    assert trade.initial_risk == D(945000)
    assert trade.entry_fee_idr == D("18900.00")
    assert trade.planned_stop_loss_idr == D("993037.50")
    loss_127, _, _ = sized_profit(D(1000), D(925), 12700, close_experiment.costs)
    assert -loss_127 == D("1000918.75") > close_experiment.risk_budget_idr


def test_fee_half_up_rounding_and_final_risk_recheck(close_experiment):
    assert cash_fee(D(90), D(25)) == D("0.23")
    # Raw risk of one lot is 10.375, but rounding the sell fee makes it 10.38.
    assert sized_profit(D(1), D("0.9"), 100, close_experiment.costs)[0] == D("-10.38")
    lots, quantity, loss, buy_fee = size_lots(
        D(1), D("0.9"), close_experiment.costs, D("10.375"),
    )
    assert (lots, quantity, loss, buy_fee) == (0, 0, D(0), D(0))
    assert size_lots(D(1), D("0.9"), close_experiment.costs, D("10.38"))[:3] == (
        1, 100, D("10.38"),
    )


def test_one_lot_over_budget_keeps_signal_as_skipped(
    close_signal, close_experiment, close_calendar,
):
    expensive = replace(close_signal, candidate=replace(
        close_signal.candidate, reference_close=1000000, stop=900000,
    ))
    trade = create_plan(expensive, close_experiment, close_calendar)
    assert trade.state == "skipped" and trade.reason == "skipped_budget"
    assert trade.quantity == 0 and trade.lots == 0
    assert trade.signal.id == close_signal.id and not trade.events


@pytest.mark.parametrize("reason", ["late_or_backtest_signal", "experiment_activated_too_late"])
def test_new_skipped_close_plan_retains_exact_policy(
    close_signal, close_experiment, close_calendar, reason,
):
    if reason == "late_or_backtest_signal":
        close_signal = replace(close_signal, cohort="backtest")
    else:
        close_experiment = replace(close_experiment,
            activated_at=close_calendar.get(close_signal.planned_entry_session).opens_at)
    trade = create_plan(close_signal, close_experiment, close_calendar)
    assert trade.state == "skipped" and trade.reason == reason
    assert trade.sizing_policy_version == EXACT_SIZING_POLICY


@pytest.mark.parametrize("entry,stop,budget", [
    (D(0), D(0), D(1)), (D(100), D(100), D(1)),
    (D(100), D(101), D(1)), (D("NaN"), D(90), D(1)),
    (D(100), D(90), D(0)), (D(100), D(90), D("Infinity")),
])
def test_sizing_invalid_inputs_rejected(close_experiment, entry, stop, budget):
    with pytest.raises(ValueError):
        size_lots(entry, stop, close_experiment.costs, budget)


def test_entry_uses_frozen_close_on_next_exchange_session(
    close_signal, close_experiment, close_calendar,
):
    plan = create_plan(close_signal, close_experiment, close_calendar)
    with pytest.raises(ValueError, match="chronological"):
        step(plan, close_signal.session, bar(close_signal.session, 1000, 1100, 950, 1050),
             close_calendar, close_calendar.sessions[0].closes_at)
    session = close_calendar.sessions[1]
    trade = step(plan, session.day, bar(session.day, 1050, 1100, 990, 1060),
                 close_calendar, session.closes_at)
    assert trade.state == "open" and trade.entry == D(1000)
    assert trade.initial_risk == plan.initial_risk and trade.stop == plan.stop
    assert trade.events[0].reason == "assumed_signal_close"
    assert trade.events[0].session == close_signal.planned_entry_session
    assert trade.events[0].price == D(1000)


@pytest.mark.parametrize("ohlc,exit_price,reason", [
    ((900, 1175, 890, 1000), D(900), "stop_gap"),
    ((1200, 1220, 900, 1000), D(1150), "target_gap_conservative"),
])
def test_entry_session_open_gap_resolves_before_intraday_range(
    close_signal, close_experiment, close_calendar, ohlc, exit_price, reason,
):
    plan = create_plan(close_signal, close_experiment, close_calendar)
    session = close_calendar.sessions[1]
    trade = step(plan, session.day, bar(session.day, *ohlc), close_calendar, session.closes_at)
    assert trade.state == "closed" and trade.entry == D(1000)
    assert trade.events[-1].price == exit_price and trade.events[-1].reason == reason
    assert trade.alternate_r is None
    assert trade.initial_risk == plan.initial_risk == D(945000)


def test_dual_hit_preserves_both_ledgers_and_is_excluded_from_closed(
    close_signal, close_experiment, close_calendar,
):
    book = PaperBook()
    plan = book.add(close_signal, close_experiment, close_calendar)
    session = close_calendar.sessions[1]
    trade = step(plan, session.day, bar(session.day, 1000, 1175, 900, 1020),
                 close_calendar, session.closes_at)
    assert trade.state == "ambiguous_review"
    assert trade.net_pnl == D("-993037.50")
    assert trade.alternate_net_pnl == D("1834875.00")
    assert trade.entry_fee_idr == D("18900.00")
    assert trade.exit_fee_idr == D("29137.50")
    assert trade.realized_r == trade.net_pnl / D(945000)
    assert trade.alternate_r == trade.alternate_net_pnl / D(945000)
    assert trade.events[-1].alternate_price == D(1150)
    assert step(trade, session.day, None, close_calendar, session.closes_at) == trade
    book.trades[trade.id] = trade
    summary = summarize_book(book)
    assert summary["closed_count"] == 0 and summary["ambiguous_count"] == 1
    assert summary["experiment_metrics"][close_experiment.id]["win_rate"] is None
    assert paper_book_from_dict(paper_book_to_dict(book)) == book


def test_entry_hold_replays_same_session_without_creating_a_second_entry(
    close_signal, close_experiment, close_calendar,
):
    plan = create_plan(close_signal, close_experiment, close_calendar)
    first, second = close_calendar.sessions[1:3]
    held = step(plan, first.day, None, close_calendar, first.closes_at)
    assert held.state == "data_hold" and held.last_session is None
    with pytest.raises(ValueError, match="chronological"):
        step(held, second.day, bar(second.day, 1000, 1050, 950, 1020),
             close_calendar, second.closes_at)
    trade = step(held, first.day, bar(first.day, 1000, 1050, 950, 1020),
                 close_calendar, second.closes_at)
    assert trade.entry == D(1000) and len(trade.events) == 1
    assert step(trade, first.day, None, close_calendar, second.closes_at) == trade


def test_future_bar_or_preclose_observation_cannot_enter(
    close_signal, close_experiment, close_calendar,
):
    plan = create_plan(close_signal, close_experiment, close_calendar)
    first, second = close_calendar.sessions[1:3]
    with pytest.raises(ValueError, match="not_closed"):
        step(plan, first.day, bar(first.day, 1000, 1050, 950, 1020),
             close_calendar, first.opens_at)
    with pytest.raises(ValueError, match="bar_session_mismatch"):
        step(plan, first.day, bar(second.day, 1000, 1050, 950, 1020),
             close_calendar, first.closes_at)


def test_model_activation_and_experiment_snapshot_are_immutable(
    close_signal, close_experiment, close_calendar,
):
    late = replace(close_experiment, activated_at=close_signal.published_at + timedelta(seconds=1))
    late_plan = create_plan(close_signal, late, close_calendar)
    assert late_plan.reason == "signal_before_model_activation"
    book = PaperBook()
    original = book.add(close_signal, close_experiment, close_calendar)
    assert book.add(close_signal, close_experiment, close_calendar) == original
    with pytest.raises(ValueError, match="immutable"):
        book.add(close_signal, replace(close_experiment, risk_budget_idr=D(500000)), close_calendar)
    sma = replace(close_experiment, id="close-sma10", exit=ExitConfig("ma_close", None, "SMA", 10))
    separate = book.add(close_signal, sma, close_calendar)
    assert separate.id != original.id and separate.target is None
    assert separate.initial_risk == original.initial_risk


@pytest.mark.parametrize("close,expected", [(1000, "open"), (990, "pending")])
def test_sma10_needs_confirmed_close_not_wick_or_equality(
    close_signal, close_experiment, close_calendar, close, expected,
):
    signal_session, entry_session = close_calendar.sessions[9:11]
    signal = replace(close_signal, session=signal_session.day,
                     published_at=signal_session.closes_at + timedelta(hours=3),
                     planned_entry_session=entry_session.day)
    experiment = replace(close_experiment, id="close-sma10",
                         exit=ExitConfig("ma_close", None, "SMA", 10))
    plan = create_plan(signal, experiment, close_calendar)
    history = tuple(bar(s.day, 1000, 1010, 940, 1000) for s in close_calendar.sessions[:10])
    current = bar(entry_session.day, 1000, 1010, 940, close)
    trade = step(plan, entry_session.day, current, close_calendar,
                 entry_session.closes_at, history=history + (current,))
    assert trade.initial_risk == D(945000) and trade.stop == D(925)
    if expected == "open":
        assert trade.pending_exit is None and trade.state == "open"
    else:
        next_session = close_calendar.sessions[11]
        assert trade.pending_exit == next_session.day
        assert trade.events[-1].kind == "pending_exit"
        assert trade.events[-1].ma_value == D(999)
        closed = step(trade, next_session.day, bar(next_session.day, 980, 1010, 970, 1000),
                      close_calendar, next_session.closes_at)
        assert closed.state == "closed" and closed.events[-1].price == D(980)
        assert closed.initial_risk == plan.initial_risk


def test_sma10_initial_stop_remains_intraday_protection(
    close_signal, close_experiment, close_calendar,
):
    experiment = replace(close_experiment, id="close-sma10",
                         exit=ExitConfig("ma_close", None, "SMA", 10))
    plan = create_plan(close_signal, experiment, close_calendar)
    session = close_calendar.sessions[1]
    closed = step(plan, session.day, bar(session.day, 1000, 1050, 920, 1030),
                  close_calendar, session.closes_at)
    assert closed.state == "closed" and closed.events[-1].reason == "stop"
    assert closed.events[-1].price == D(925) and closed.pending_exit is None


@pytest.mark.parametrize("mode", ["fixed_rr", "ma_close"])
def test_five_and_ten_session_checkpoints_never_auto_close(
    close_signal, close_experiment, close_calendar, mode,
):
    experiment = close_experiment if mode == "fixed_rr" else replace(
        close_experiment, id="close-sma10", exit=ExitConfig("ma_close", None, "SMA", 10),
    )
    trade = create_plan(close_signal, experiment, close_calendar)
    history = [bar(close_calendar.sessions[0].day, 1000, 1030, 950, 1000)]
    for session in close_calendar.sessions[1:11]:
        current = bar(session.day, 1000, 1030, 950, 1020)
        history.append(current)
        trade = step(trade, session.day, current, close_calendar, session.closes_at,
                     history=tuple(history))
        assert trade.state == "open" and trade.pending_exit is None
    assert len(trade.events) == 1 and trade.events[0].kind == "entry"
    assert trade.net_pnl is None and trade.initial_risk == D(945000)


def test_recovery_does_not_reenter_same_ambiguous_exit_session(
    close_signal, close_experiment, close_calendar,
):
    book = PaperBook()
    plan = book.add(close_signal, close_experiment, close_calendar)
    session = close_calendar.sessions[1]
    book.trades[plan.id] = step(
        plan, session.day, bar(session.day, 1000, 1175, 900, 1020),
        close_calendar, session.closes_at,
    )
    recovered_signal = replace(close_signal, id="missed-signal-same-entry-session")
    recovered = book.add(recovered_signal, close_experiment, close_calendar)
    assert recovered.state == "skipped" and recovered.reason == "position_at_session_start"


def test_budget_skip_survives_an_existing_position(
    close_signal, close_experiment, close_calendar,
):
    book = PaperBook({}, {})
    first = book.add(close_signal, close_experiment, close_calendar)
    assert first.state == "pending_entry"
    expensive = replace(close_signal, id="budget-overlap", candidate=replace(
        close_signal.candidate, reference_close=1000000, stop=900000,
    ))
    skipped = book.add(expensive, close_experiment, close_calendar)
    assert skipped.state == "skipped" and skipped.reason == "skipped_budget"
    assert skipped.quantity == 0 and skipped.lots == 0
