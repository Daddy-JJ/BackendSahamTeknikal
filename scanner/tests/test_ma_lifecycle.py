from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D

import pytest

from idx_scanner.fixtures import sample_market
from idx_scanner.models import Bar, Costs, ExitConfig
from idx_scanner.paper import Experiment, create_plan, step


@pytest.mark.parametrize("ma_type", ["SMA", "EMA"])
@pytest.mark.parametrize("period", [5, 10, 20])
def test_full_ma_entry_day_pending_and_next_open(signal, ma_type, period):
    _, calendar, _ = sample_market(40)
    entry_session = calendar.sessions[30]
    signal = replace(
        signal,
        session=calendar.sessions[29].day,
        planned_entry_session=entry_session.day,
        published_at=calendar.sessions[29].closes_at,
    )
    experiment = Experiment(
        "ma",
        signal.candidate.strategy,
        ExitConfig("ma_close", None, ma_type, period),
        Costs(),
        calendar.sessions[29].opens_at,
    )
    history = tuple(Bar(s.day, 104, 105, 103, 104, 1000) for s in calendar.sessions[:30])
    candle = Bar(entry_session.day, 100, 104, 97, 103, 1000)
    plan = create_plan(signal, experiment, calendar)
    pending = step(
        plan,
        entry_session.day,
        candle,
        calendar,
        entry_session.closes_at,
        history=history + (candle,),
    )
    assert pending.target is None and pending.initial_risk == 5
    assert pending.pending_exit == calendar.sessions[31].day
    assert pending.actionable
    next_candle = Bar(calendar.sessions[31].day, 101, 103, 100, 102, 1000)
    closed = step(
        pending,
        next_candle.session,
        next_candle,
        calendar,
        calendar.sessions[31].closes_at,
        history=history + (candle, next_candle),
    )
    assert closed.state == "closed" and closed.realized_r == D(".2")
    assert closed.events[-1].price == 101
    assert closed.initial_risk == pending.initial_risk


def test_late_ma_discovery_is_model_only_and_suspension_waits(signal):
    _, calendar, _ = sample_market(40)
    session = calendar.sessions[30]
    signal = replace(
        signal,
        session=calendar.sessions[29].day,
        planned_entry_session=session.day,
        published_at=calendar.sessions[29].closes_at,
    )
    experiment = Experiment(
        "ma",
        signal.candidate.strategy,
        ExitConfig("ma_close", None, "SMA", 10),
        Costs(),
        calendar.sessions[29].opens_at,
    )
    history = tuple(Bar(s.day, 104, 105, 103, 104, 1000) for s in calendar.sessions[:30])
    candle = Bar(session.day, 100, 104, 97, 103, 1000)
    pending = step(
        create_plan(signal, experiment, calendar),
        session.day,
        candle,
        calendar,
        calendar.sessions[31].opens_at + timedelta(minutes=1),
        history=history + (candle,),
    )
    assert not pending.actionable and pending.events[-1].reason == "late_model_only"
    held = step(
        pending,
        calendar.sessions[31].day,
        None,
        calendar,
        calendar.sessions[31].closes_at,
        confirmed_untradable=True,
    )
    assert held.state == "open" and held.pending_exit == calendar.sessions[31].day


def test_unset_nonzero_fees_rejected():
    with pytest.raises(ValueError, match="Unset"):
        Costs(buy_bps=D(1))


def test_pending_exit_after_suspension_does_not_need_fabricated_ma_history(signal):
    _, calendar, _ = sample_market(40)
    session = calendar.sessions[30]
    signal = replace(
        signal,
        session=calendar.sessions[29].day,
        planned_entry_session=session.day,
        published_at=calendar.sessions[29].closes_at,
    )
    experiment = Experiment(
        "ma",
        signal.candidate.strategy,
        ExitConfig("ma_close", None, "SMA", 10),
        Costs(),
        calendar.sessions[29].opens_at,
    )
    history = tuple(Bar(s.day, 104, 105, 103, 104, 1000) for s in calendar.sessions[:30])
    candle = Bar(session.day, 100, 104, 97, 103, 1000)
    pending = step(
        create_plan(signal, experiment, calendar),
        session.day,
        candle,
        calendar,
        session.closes_at,
        history=history + (candle,),
    )
    assert pending.events[-1].ma_value is not None
    assert pending.events[-1].ma_period == 10
    held = step(
        pending,
        calendar.sessions[31].day,
        None,
        calendar,
        calendar.sessions[31].closes_at,
        confirmed_untradable=True,
    )
    next_candle = Bar(calendar.sessions[32].day, 101, 103, 100, 102, 1000)
    closed = step(held, next_candle.session, next_candle, calendar, calendar.sessions[32].closes_at)
    assert closed.state == "closed" and closed.events[-1].price == 101
    assert closed.events[-1].reason == "ma_breakdown"
