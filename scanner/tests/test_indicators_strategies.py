from dataclasses import replace
from datetime import date, timedelta

import pytest

from idx_scanner.fractal import levels
from idx_scanner.indicators import Features, atr, calculate, ema, sma
from idx_scanner.models import Bar, EntryConfig
from idx_scanner.strategies import Ranking, evaluate, rank_returns, swing_stop


def bars_from_highs(highs):
    return tuple(
        Bar(date(2026, 1, 1) + timedelta(days=i), 95, h, 90, 95, 100) for i, h in enumerate(highs)
    )


def test_ema_macd_seed_against_manual_numeric_reference():
    assert ema([10, 12, 14], 3) == (10, 11, 12.5)
    bars = tuple(
        Bar(date(2026, 1, 1) + timedelta(days=i), c, c + 1, c - 1, c, 1)
        for i, c in enumerate([100, 110, 110])
    )
    f = calculate(bars)
    # At t1 EMA12=101.538461538..., EMA26=100.740740740...
    assert f.macd[1] == pytest.approx(0.7977207977207854)
    assert f.signal[1] == pytest.approx(0.1595441595441571)
    assert f.histogram[1] == pytest.approx(0.6381766381766283)


def test_sma_and_wilder_atr_manual_seed():
    assert sma([1, 2, 3, 9], 3) == (None, None, 2, 14 / 3)
    bars = tuple(Bar(date(2026, 1, 1) + timedelta(days=i), 10, 11, 9, 10, 1) for i in range(15))
    bars = bars[:-1] + (replace(bars[-1], high=15, low=5),)
    result = atr(bars)
    assert result[:13] == (None,) * 13
    assert result[13] == 2
    assert result[14] == pytest.approx(36 / 14)  # Wilder, not rolling TR average in later steps.
    further = bars + (replace(bars[-1], session=date(2026, 1, 16), high=11, low=9),)
    assert atr(further)[15] == pytest.approx((13 * (36 / 14) + 2) / 14)


def test_fractal_available_at_t5_not_pivot_t2_and_ties():
    bars = bars_from_highs([100, 102, 110, 108, 109, 140])
    result = levels(bars)
    assert all(upper is None for upper, _ in result[:5])
    upper = result[5][0]
    assert upper.price == 110
    assert upper.pivot_date == bars[2].session
    assert upper.available_session == bars[5].session
    assert (
        levels(bars_from_highs([110] * 7))[-1][0].id != levels(bars_from_highs([110] * 6))[-1][0].id
    )


def test_fractal_current_candle_cannot_confirm_pivot():
    bars = bars_from_highs([100, 102, 110, 108, 109, 140])
    assert levels(bars)[-1] == levels(bars[:-1] + (replace(bars[-1], high=9999),))[-1]


def test_false_breakout_when_level_falls_and_wick_only():
    bars = bars_from_highs([100, 102, 110, 108, 115, 118])
    # Independent trigger example uses an available F=110, prev=115, current=116.
    # A high >= close is necessary; inject the level evaluator boundary separately below.
    from idx_scanner.strategies import _candidate

    c = _candidate(
        "FRACTAL_BREAKOUT_V1",
        116,
        90,
        {"previous_close_at_or_below_level": 115 <= 110, "close_above_level": 116 > 110},
    )
    assert not c.triggered
    bars = bars_from_highs([100, 102, 110, 108, 109, 113])
    bars = bars[:-1] + (replace(bars[-1], close=109),)
    candidates = evaluate("TEST", bars, calculate(bars), Ranking("complete", (), (), "x"))
    assert not candidates[0].triggered


def test_pivot_requires_right_bars_and_latest_stop_is_not_replaced():
    bars = tuple(
        Bar(date(2026, 1, 1) + timedelta(days=i), 100, 120, low, 110, 1)
        for i, low in enumerate([95, 94, 90, 92, 93, 89])
    )
    assert swing_stop(bars[:4], EntryConfig()) is None
    assert swing_stop(bars[:5], EntryConfig()) == 90
    assert swing_stop(bars, EntryConfig()) == 90  # t5 low is unconfirmed.


def controlled_history():
    bars = tuple(
        Bar(date(2024, 1, 1) + timedelta(days=i), 100, 105, 90, 102, 1) for i in range(600)
    )
    f = Features(
        (100.0,) * 600,
        (95.0,) * 600,
        (80.0,) * 600,
        (0.0,) * 600,
        (0.0,) * 600,
        (0.0,) * 598 + (-0.2, 0.1),
        (4.0,) * 600,
    )
    return bars, f


@pytest.mark.parametrize(
    "previous,current,close,expected",
    [
        (-0.2, 0.1, 105, True),
        (0.1, 0.2, 105, False),
        (-0.2, 0.1, 79, False),
        (0, 0.1, 105, True),
        (-0.1, 0, 105, False),
    ],
)
def test_macd_conditions(previous, current, close, expected):
    bars, f = controlled_history()
    bars = bars[:-1] + (replace(bars[-1], close=close, high=max(105, close)),)
    f = replace(f, histogram=f.histogram[:-2] + (previous, current))
    found = {c.strategy: c for c in evaluate("TEST", bars, f, Ranking("complete", (), (), "x"))}
    assert found["MACD_EMA200_V1"].triggered is expected


def test_rs_ranking_ties_and_incomplete_cross_section():
    r = rank_returns(
        {"B": 0.2, "A": 0.2, "C": 0.1, "D": 0, "E": -0.1}, ("B", "A", "C", "D", "E"), (), "x"
    )
    assert r.top == {"A"}
    assert rank_returns({"A": 0.9}, ("A", "B"), (), "x").status == "cross_section_incomplete"
    assert rank_returns({"A": 0.9}, ("A", "B"), ("B",), "x").status == "complete"


def test_rs_prior20_excludes_current_and_five_bar_stop_includes_current():
    bars, f = controlled_history()
    bars = bars[:-1] + (replace(bars[-1], close=110, high=999, low=88),)
    r = Ranking("complete", (("TEST", 0.5),), (), "x")
    found = {c.strategy: c for c in evaluate("TEST", bars, f, r)}
    candidate = found["RS_BREAKOUT_V1"]
    assert candidate.triggered and candidate.level == 105
    assert candidate.stop == 87


def test_pullback_exact_three_prior_sessions_and_strict_reclaim():
    bars, f = controlled_history()
    bars = bars[:-2] + (
        replace(bars[-2], close=99, high=103),
        replace(bars[-1], close=106, high=110, low=92),
    )
    found = {c.strategy: c for c in evaluate("TEST", bars, f, Ranking("complete", (), (), "x"))}
    assert found["PULLBACK_RECLAIM_V1"].triggered
    assert found["PULLBACK_RECLAIM_V1"].stop == 89
    for close in (100, 103):
        modified = bars[:-1] + (replace(bars[-1], close=close),)
        assert not {
            c.strategy: c for c in evaluate("TEST", modified, f, Ranking("complete", (), (), "x"))
        }["PULLBACK_RECLAIM_V1"].triggered
    modified = bars[:-3] + (replace(bars[-3], close=94),) + bars[-2:]
    assert not {
        c.strategy: c for c in evaluate("TEST", modified, f, Ranking("complete", (), (), "x"))
    }["PULLBACK_RECLAIM_V1"].triggered


def test_prefix_indicators_and_fractals_unchanged_when_future_perturbed():
    bars, _ = controlled_history()
    future = bars + (replace(bars[-1], session=date(2030, 1, 1), close=200, high=999),)
    for name in Features.__dataclass_fields__:
        assert getattr(calculate(future), name)[:600] == getattr(calculate(bars), name)
    assert levels(future)[:600] == levels(bars)


@pytest.mark.parametrize("values,period", [([float("nan")], 3), ([1], 0), ([1], True)])
def test_invalid_indicator_inputs(values, period):
    with pytest.raises(ValueError):
        ema(values, period)
