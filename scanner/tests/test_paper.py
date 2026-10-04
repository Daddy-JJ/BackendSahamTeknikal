from dataclasses import replace
from decimal import Decimal as D

import pytest
from conftest import bar

from idx_scanner.exits import evaluate_exit
from idx_scanner.metrics import summarize
from idx_scanner.models import Costs, ExitConfig, Series
from idx_scanner.paper import (
    Experiment,
    PaperBook,
    create_plan,
    paper_book_from_dict,
    paper_book_to_dict,
    step,
    step_paper_book,
    summarize_book,
)


@pytest.fixture
def experiment(calendar):
    return Experiment(
        "baseline", "FRACTAL_BREAKOUT_V1", ExitConfig(), Costs(), calendar.sessions[0].opens_at
    )


def test_next_exchange_session_entry_and_no_same_close(signal, experiment, calendar):
    plan = create_plan(signal, experiment, calendar)
    with pytest.raises(ValueError, match="chronological"):
        step(plan, signal.session, bar(signal.session), calendar, calendar.sessions[0].closes_at)
    entered = step(
        plan,
        calendar.sessions[1].day,
        bar(calendar.sessions[1].day),
        calendar,
        calendar.sessions[1].closes_at,
    )
    assert entered.entry == 100 and entered.target == 110 and entered.initial_risk == 5
    assert entered.events[0].session == calendar.sessions[1].day


def test_missing_entry_replay_and_invalid_open(signal, experiment, calendar):
    plan = create_plan(signal, experiment, calendar)
    day = calendar.sessions[1].day
    held = step(plan, day, None, calendar, calendar.sessions[1].closes_at)
    assert held.state == "data_hold" and held.entry is None
    with pytest.raises(ValueError, match="chronological"):
        step(
            held,
            calendar.sessions[2].day,
            bar(calendar.sessions[2].day),
            calendar,
            calendar.sessions[2].closes_at,
        )
    skipped = step(plan, day, bar(day, 95, 101, 94, 99), calendar, calendar.sessions[1].closes_at)
    assert skipped.reason == "skip_invalid_entry"
    expired = step(
        plan, day, None, calendar, calendar.sessions[1].closes_at, confirmed_untradable=True
    )
    assert expired.state == "expired"


@pytest.mark.parametrize(
    "ohlc,reason,price,alternate",
    [
        ((92, 96, 90, 94), "stop_gap", 92, None),
        ((112, 113, 109, 110), "target_gap_conservative", 110, None),
        ((102, 111, 94, 104), "ambiguous_both_hit", 95, 110),
        ((102, 108, 94, 104), "stop", 95, None),
        ((102, 111, 96, 104), "target", 110, None),
    ],
)
def test_gap_and_dual_hit_order(calendar, ohlc, reason, price, alternate):
    decision = evaluate_exit(bar(calendar.sessions[1].day, *ohlc), D(95), D(110), ExitConfig())
    assert (decision.reason, decision.price, decision.alternate_price) == (
        reason,
        D(price),
        D(alternate) if alternate else None,
    )


def test_entry_day_ambiguity_costs_and_idempotence(signal, experiment, calendar):
    plan = create_plan(signal, experiment, calendar)
    day = calendar.sessions[1].day
    candle = bar(day, 100, 111, 94, 104)
    closed = step(plan, day, candle, calendar, calendar.sessions[1].closes_at)
    assert closed.realized_r == -1 and closed.alternate_r == 2
    assert len(closed.events) == 2
    assert step(closed, day, candle, calendar, calendar.sessions[1].closes_at) == closed
    costs = Costs(D(10), D(20), D(5), "provisional")
    costly = create_plan(signal, replace(experiment, costs=costs), calendar)
    closed2 = step(
        costly, day, bar(day, 100, 111, 96, 104), calendar, calendar.sessions[1].closes_at
    )
    assert closed2.net_pnl == D("9.575")


def test_exit_config_immutable_and_explicit_new_experiment(signal, experiment, calendar):
    book = PaperBook()
    plan = book.add(signal, experiment, calendar)
    assert book.add(signal, experiment, calendar) == plan
    with pytest.raises(ValueError, match="immutable"):
        book.add(signal, replace(experiment, exit=ExitConfig(target_r=D("1.5"))), calendar)
    new = book.add(
        signal, replace(experiment, id="new", exit=ExitConfig(target_r=D("1.5"))), calendar
    )
    assert new.id != plan.id
    assert plan.experiment.exit.target_r == 2


def test_one_position_and_no_reentry_same_exit_day(signal, experiment, calendar):
    book = PaperBook()
    plan = book.add(signal, experiment, calendar)
    skipped = book.add(replace(signal, id="another"), experiment, calendar)
    assert skipped.reason == "position_at_session_start"
    day = calendar.sessions[1].day
    book.trades[plan.id] = step(
        plan, day, bar(day, 100, 111, 96, 104), calendar, calendar.sessions[1].closes_at
    )
    assert book.add(replace(signal, id="third"), experiment, calendar).state == "skipped"


@pytest.mark.parametrize(
    "low,close,kind",
    [(101, 103, "hold"), (101, 102, "hold"), (97, 101, "pending_ma"), (94, 103, "exit")],
)
def test_ma_wick_equality_strict_below_and_initial_stop(calendar, low, close, kind):
    config = ExitConfig("ma_close", None, "SMA", 10)
    decision = evaluate_exit(
        bar(calendar.sessions[1].day, 103, 104, low, close), D(95), None, config, ma=102
    )
    assert decision.kind == kind


def test_pending_ma_gap_priority_and_next_open_not_ma(calendar):
    config = ExitConfig("ma_close", None, "SMA", 10)
    normal = evaluate_exit(
        bar(calendar.sessions[2].day, 101, 104, 99, 103),
        D(95),
        None,
        config,
        ma=104,
        pending_ma=True,
    )
    assert normal.price == 101 and normal.reason == "ma_breakdown"
    gap = evaluate_exit(
        bar(calendar.sessions[2].day, 93, 104, 92, 103),
        D(95),
        None,
        config,
        ma=104,
        pending_ma=True,
    )
    assert gap.price == 93 and gap.reason == "stop_gap"


def test_late_signal_or_late_activation_not_forward(signal, experiment, calendar):
    assert (
        create_plan(replace(signal, cohort="late_model_only"), experiment, calendar).state
        == "skipped"
    )
    late = replace(experiment, activated_at=calendar.sessions[1].opens_at)
    assert create_plan(signal, late, calendar).reason == "experiment_activated_too_late"


@pytest.mark.parametrize(
    "config",
    [
        lambda: ExitConfig(target_r=D("NaN")),
        lambda: ExitConfig(target_r=D(0)),
        lambda: ExitConfig("ma_close", D(2), "SMA", 10),
        lambda: ExitConfig("ma_close", None, "SMA", 15),
    ],
)
def test_invalid_exit_config_rejected(config):
    with pytest.raises(ValueError):
        config()


def test_metrics_manual_reference_and_empty_semantics():
    m = summarize([D(2), D(-1), D(0), D(1)], open_count=2, ambiguous_count=1)
    assert m["win_rate"] == D(".5") and m["expectancy_r"] == D(".5")
    assert m["profit_factor"] == 3 and m["payoff_ratio"] == D("1.5")
    assert m["closed"] == 4 and m["open"] == 2 and m["breakeven"] == 1
    assert summarize([])["win_rate"] is None
    assert summarize([D(2)])["profit_factor"] is None
    assert summarize([D(-1)])["profit_factor"] == 0


def test_paper_book_serialization_roundtrip(signal, experiment, calendar):
    book = PaperBook()
    plan = book.add(signal, experiment, calendar)
    day = calendar.sessions[1].day
    closed = step(
        plan, day, bar(day, 100, 111, 96, 104), calendar, calendar.sessions[1].closes_at
    )
    book.trades[closed.id] = closed

    serialized = paper_book_to_dict(book)
    restored = paper_book_from_dict(serialized)

    assert restored.experiments == book.experiments
    assert len(restored.trades) == len(book.trades)
    trade = restored.trades[closed.id]
    assert trade.id == closed.id
    assert trade.state == "closed"
    assert trade.entry == D("100")
    assert trade.realized_r == closed.realized_r
    assert len(trade.events) == len(closed.events)
    assert trade.events[0].kind == "entry"
    assert trade.events[1].kind == "exit"


def test_step_paper_book_and_summarize(signal, experiment, calendar):
    book = PaperBook()
    plan = book.add(signal, experiment, calendar)

    day = calendar.sessions[1].day
    bars = (bar(day, 100, 111, 96, 104),)
    series_map = {
        signal.ticker: Series(
            signal.ticker,
            signal.ticker,
            "fixture",
            "test",
            bars,
            actions_complete=True,
        )
    }

    updated = step_paper_book(
        book, day, series_map, calendar, calendar.sessions[1].closes_at
    )
    assert plan.id in updated
    assert updated[plan.id].state == "closed"

    summary = summarize_book(book)
    assert summary["trades_count"] == 1
    assert summary["closed_count"] == 1
    assert summary["open_count"] == 0
    assert summary["metrics"]["closed"] == 1
    assert summary["metrics"]["win_rate"] == D("1")
    assert "experiment_metrics" in summary
    assert experiment.id in summary["experiment_metrics"]


def test_step_paper_book_holds_when_corporate_actions_unreconciled(signal, experiment, calendar):
    from idx_scanner.models import CorporateAction

    book = PaperBook()
    plan = book.add(signal, experiment, calendar)

    day = calendar.sessions[1].day
    bars = (bar(day, 100, 111, 96, 104),)
    # Add an unreconciled corporate action on the day
    action = CorporateAction(day, "dividend", "5.0")
    series_map = {
        signal.ticker: Series(
            signal.ticker,
            signal.ticker,
            "fixture",
            "test",
            bars,
            actions=(action,),
            actions_complete=True,
            reconciled_actions=(),  # Empty reconciled actions -> corporate_action_hold
        )
    }

    updated = step_paper_book(
        book, day, series_map, calendar, calendar.sessions[1].closes_at
    )
    assert plan.id in updated
    assert updated[plan.id].state == "data_hold"
    assert updated[plan.id].entry is None

    summary = summarize_book(book)
    assert summary["closed_count"] == 0
    assert summary["open_count"] == 1
    assert "experiment_metrics" in summary
    assert experiment.id in summary["experiment_metrics"]


