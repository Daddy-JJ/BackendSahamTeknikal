"""Signal-only first-hit and observation horizons never mutate trade exits."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from conftest import bar

from idx_scanner.context import Calendar, Session
from idx_scanner.paper_research import (
    RESULT_KEYS,
    create_evaluation,
    evaluation_active,
    step_evaluation,
)


@pytest.fixture
def research_calendar():
    days = [date(2026, 1, 2)]
    for offset in range(4, 32):
        day = date(2026, 1, 2) + timedelta(days=offset)
        if day.weekday() < 5:
            days.append(day)
    return Calendar(
        tuple(Session(day, datetime(day.year, day.month, day.day, 2, tzinfo=UTC),
                      datetime(day.year, day.month, day.day, 9, tzinfo=UTC)) for day in days),
        "research-test-v1", "synthetic://research-calendar", "fixture",
    )


@pytest.fixture
def research_signal(signal, research_calendar):
    return replace(
        signal, candidate=replace(signal.candidate, stop=925, reference_close=1000),
        session=research_calendar.sessions[0].day,
        planned_entry_session=research_calendar.sessions[1].day,
        published_at=research_calendar.sessions[0].closes_at + timedelta(hours=3),
    )


def observe(record, calendar, index, *, o=1000, h=1040, low=950, c=1020):
    session = calendar.sessions[index]
    return step_evaluation(record, session.day, bar(session.day, o, h, low, c),
                           calendar, session.closes_at)


def test_evaluation_freezes_prices_and_is_independent_of_paper_experiments(research_signal):
    record = create_evaluation(research_signal, "TEST.JK")
    assert record["entry_price"] == "1000" and record["initial_stop"] == "925"
    assert record["target_1r"] == "1075" and record["target_2r"] == "1150"
    assert record["provider_symbol"] == "TEST.JK" and record["data_mode"] == "fixture"
    assert record["results"] == dict.fromkeys(RESULT_KEYS, "pending")
    assert record["observed_sessions"] == 0 and record["last_session"] is None
    assert "experiment_id" not in record and evaluation_active(record)


@pytest.mark.parametrize("cohort", ["backtest", "late_model_only"])
def test_historical_or_late_signal_is_not_forward_research(research_signal, cohort):
    with pytest.raises(ValueError, match="valid_forward"):
        create_evaluation(replace(research_signal, cohort=cohort))


def test_ineligible_signal_is_rejected(research_signal):
    with pytest.raises(ValueError, match="valid_forward"):
        create_evaluation(replace(research_signal, candidate=replace(
            research_signal.candidate, triggered=False,
        )))


def test_target_one_and_two_resolve_independently_while_horizons_continue(
    research_signal, research_calendar,
):
    original = create_evaluation(research_signal)
    first = observe(original, research_calendar, 1, h=1080)
    assert first["results"] == {
        "target_1r": "won", "target_2r": "pending", "net_5": "pending", "net_10": "pending",
    }
    second = observe(first, research_calendar, 2, h=1160)
    assert second["results"]["target_1r"] == second["results"]["target_2r"] == "won"
    assert second["results"]["net_5"] == second["results"]["net_10"] == "pending"
    for index in range(3, 11):
        second = observe(second, research_calendar, index)
    assert second["results"] == dict.fromkeys(RESULT_KEYS, "won")
    assert not evaluation_active(second)
    assert original["last_session"] is None and original["observed_sessions"] == 0
    assert original["results"] == dict.fromkeys(RESULT_KEYS, "pending")


@pytest.mark.parametrize("close,result", [(1000, "lost"), (1004, "lost"), (1005, "won")])
def test_five_session_net_checkpoint_includes_both_fees(
    research_signal, research_calendar, close, result,
):
    record = create_evaluation(research_signal)
    for index in range(1, 6):
        record = observe(record, research_calendar, index, c=close)
        if index < 5:
            assert record["results"]["net_5"] == "pending"
    assert record["observed_sessions"] == 5
    assert record["results"]["net_5"] == result
    assert record["results"]["net_10"] == "pending"
    # The 1R/2R observations are still pending; a horizon does not close them.
    assert record["results"]["target_1r"] == record["results"]["target_2r"] == "pending"
    assert evaluation_active(record)
    assert research_calendar.sessions[1].day == date(2026, 1, 6)
    assert date.fromisoformat(record["last_session"]) == research_calendar.sessions[5].day


def test_exact_net_break_even_is_not_a_win(research_signal, research_calendar):
    signal = replace(research_signal, candidate=replace(
        research_signal.candidate, reference_close=997.5,
    ))
    record = create_evaluation(signal)
    for index in range(1, 6):
        record = observe(record, research_calendar, index, o=1001.5, c=1001.5)
    assert record["results"]["net_5"] == "lost"


def test_ten_session_result_does_not_overwrite_five_session_checkpoint(
    research_signal, research_calendar,
):
    record = create_evaluation(research_signal)
    for index in range(1, 11):
        record = observe(record, research_calendar, index, c=1010 if index <= 5 else 1000)
    assert record["results"]["net_5"] == "won"
    assert record["results"]["net_10"] == "lost"
    assert record["observed_sessions"] == 10
    assert record["results"]["target_1r"] == "pending"
    assert evaluation_active(record)


def test_stop_touch_fails_horizons_and_only_unresolved_target(
    research_signal, research_calendar,
):
    first = observe(create_evaluation(research_signal), research_calendar, 1, h=1080)
    stopped = observe(first, research_calendar, 2, h=1040, low=925)
    assert stopped["results"] == {
        "target_1r": "won", "target_2r": "lost", "net_5": "lost", "net_10": "lost",
    }
    assert not evaluation_active(stopped)


@pytest.mark.parametrize("high,expected", [
    (1100, {"target_1r": "ambiguous", "target_2r": "lost"}),
    (1160, {"target_1r": "ambiguous", "target_2r": "ambiguous"}),
])
def test_daily_dual_hit_is_ambiguous_per_target(
    research_signal, research_calendar, high, expected,
):
    record = observe(create_evaluation(research_signal), research_calendar, 1, h=high, low=900)
    assert {key: record["results"][key] for key in expected} == expected
    assert record["results"]["net_5"] == record["results"]["net_10"] == "lost"
    assert not evaluation_active(record)


@pytest.mark.parametrize("opening,result", [(900, "lost"), (1200, "won")])
def test_open_orders_first_hit_before_daily_range(
    research_signal, research_calendar, opening, result,
):
    record = observe(create_evaluation(research_signal), research_calendar, 1,
                     o=opening, h=1250, low=890, c=1000)
    assert record["results"]["target_1r"] == record["results"]["target_2r"] == result
    assert record["results"]["net_5"] == record["results"]["net_10"] == "lost"


@pytest.mark.parametrize("invalid_kind", ["missing", "zero_volume", "unreconciled", "invalid"])
def test_data_hold_does_not_advance_and_recovery_preserves_completed_results(
    research_signal, research_calendar, invalid_kind,
):
    first = observe(create_evaluation(research_signal), research_calendar, 1, h=1080)
    session, next_session = research_calendar.sessions[2:4]
    candle = bar(session.day, 1000, 1040, 950, 1020)
    if invalid_kind == "missing":
        candle = None
    elif invalid_kind == "zero_volume":
        candle = replace(candle, volume=0)
    elif invalid_kind == "invalid":
        candle = replace(candle, high=900)
    held = step_evaluation(first, session.day, candle, research_calendar, session.closes_at,
                           data_valid=invalid_kind != "unreconciled")
    assert held["results"]["target_1r"] == "won"
    assert held["results"]["target_2r"] == "data_hold"
    assert held["results"]["net_5"] == held["results"]["net_10"] == "data_hold"
    assert held["observed_sessions"] == 1 and held["last_session"] == first["last_session"]
    assert len(held["input_digests"]) == 1 and evaluation_active(held)
    with pytest.raises(ValueError, match="chronological"):
        observe(held, research_calendar, 3)
    recovered = step_evaluation(held, session.day, bar(session.day, 1000, 1040, 950, 1020),
                               research_calendar, next_session.closes_at)
    assert recovered["observed_sessions"] == 2 and "hold_reason" not in recovered
    assert recovered["results"]["target_1r"] == "won"
    assert recovered["results"]["target_2r"] == "pending"


def test_replay_is_idempotent_and_retains_original_input_digest(research_signal, research_calendar):
    record = observe(create_evaluation(research_signal), research_calendar, 1)
    original = list(record["input_digests"])
    corrected_bar = observe(record, research_calendar, 1, h=1200, low=900)
    assert corrected_bar == record and corrected_bar["input_digests"] == original
    assert corrected_bar["results"] == dict.fromkeys(RESULT_KEYS, "pending")
    assert corrected_bar["observed_sessions"] == 1


def test_future_bar_or_preclose_observation_cannot_advance(research_signal, research_calendar):
    record = create_evaluation(research_signal)
    first, second = research_calendar.sessions[1:3]
    with pytest.raises(ValueError, match="not_closed"):
        step_evaluation(record, first.day, bar(first.day, 1000, 1040, 950, 1020),
                        research_calendar, first.opens_at)
    with pytest.raises(ValueError, match="bar_session_mismatch"):
        step_evaluation(record, first.day, bar(second.day, 1000, 1040, 950, 1020),
                        research_calendar, first.closes_at)
    with pytest.raises(ValueError, match="chronological"):
        observe(record, research_calendar, 2)
    assert record["observed_sessions"] == 0 and record["input_digests"] == []
