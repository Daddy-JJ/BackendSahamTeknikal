"""Unit tests for v2 Technical Rules, Smart Money Scoring, Regime Detection, Contributors & Win Rate Evaluator."""

from datetime import date, timedelta

from idx_scanner.smart_money import (
    compute_ihsg_contributors,
    compute_smart_money_score,
    sector_to_slug,
)
from idx_scanner.technical_rules import (
    Bar,
    classify_ihsg_regime,
    classify_stock_regime,
    compute_pivot_points,
    detect_ticker_signals_history,
    evaluate_signal_outcomes,
    fractal_levels,
)


def _gen_bars(closes: list[float], start: date = date(2024, 1, 1), vol: float = 1_000_000) -> list[Bar]:
    bars: list[Bar] = []
    for i, c in enumerate(closes):
        d = (start + timedelta(days=i)).isoformat()
        bars.append(
            Bar(
                date=d,
                open=round(c * 0.99, 2),
                high=round(c * 1.02, 2),
                low=round(c * 0.98, 2),
                close=c,
                volume=vol,
                trade_value=c * vol,
                nbsa=50000,
            )
        )
    return bars


def test_fractal_levels_and_anti_lookahead():
    # Pivot at index 2 (high=110 >= 100,102,108,109 and low=94 <= 95,96,100,98) confirmed at t=5
    bars = [
        Bar("2026-01-01", 98, 100, 95, 99, 1000),
        Bar("2026-01-02", 99, 102, 96, 101, 1000),
        Bar("2026-01-03", 101, 110, 94, 105, 1000),
        Bar("2026-01-04", 105, 108, 100, 104, 1000),
        Bar("2026-01-05", 104, 109, 98, 106, 1000),
        Bar("2026-01-06", 106, 113, 102, 112, 1000),
    ]
    lvls = fractal_levels(bars)
    assert lvls[4][0] is None  # not confirmed before t=5
    upper5, lower5 = lvls[5]
    assert upper5 is not None
    assert upper5[1] == 110.0
    assert upper5[2] == "2026-01-03"  # pivot date
    assert upper5[3] == "2026-01-06"  # available session
    assert lower5 is not None and lower5[1] == 94.0

    sigs = detect_ticker_signals_history("TEST", bars)
    frac_sigs = [s for s in sigs if s["signal_type"] == "FRACTAL_BREAKOUT"]
    assert len(frac_sigs) == 1
    assert frac_sigs[0]["stop_loss"] == 94.0
    assert frac_sigs[0]["entry_price"] == 112.0


def test_macd_ema200_requires_600_bars_and_cross():
    short_bars = _gen_bars([100 + i * 0.1 for i in range(500)])
    assert [s for s in detect_ticker_signals_history("SHORT", short_bars) if s["signal_type"] == "MACD_EMA200"] == []

    # Create 620 bars with uptrend above EMA200, then slight dip and cross upward
    closes = [100 + i * 0.25 for i in range(605)]
    # Dip slightly so histogram goes <= 0, then jump up so histogram turns > 0
    closes.extend([245.0, 243.0, 241.0, 240.0, 239.0, 240.0, 248.0, 256.0, 265.0])
    bars = _gen_bars(closes)
    # Place explicit swing low pivot at index -7
    sigs = detect_ticker_signals_history("LONG", bars)
    macd_sigs = [s for s in sigs if s["signal_type"] == "MACD_EMA200"]
    assert len(macd_sigs) >= 1
    assert macd_sigs[-1]["rule_checklist"]["close_above_ema200"] is True
    assert macd_sigs[-1]["stop_loss"] < macd_sigs[-1]["entry_price"]


def test_smart_money_three_factor_scoring():
    # 3/3 Strong Confirmation
    s3 = compute_smart_money_score(
        confidence_pct=72.0,
        broksum_label="STRONG_ACCUMULATION",
        foreign_net_value=5_000_000_000,
        price_change_pct=3.5,
        smart_money_net=6_000_000_000,
    )
    assert s3["score"] == 3
    assert s3["label"] == "STRONG CONFIRMATION"

    # 2/3 Confirmed (confidence < 60%)
    s2 = compute_smart_money_score(
        confidence_pct=52.0,
        broksum_label="ACCUMULATION",
        foreign_net_value=2_000_000_000,
        price_change_pct=2.0,
        smart_money_net=2_500_000_000,
    )
    assert s2["score"] == 2
    assert s2["label"] == "CONFIRMED"

    # 1/3 Partial
    s1 = compute_smart_money_score(
        confidence_pct=65.0,
        broksum_label="ACCUMULATION",
        foreign_net_value=-1_000_000_000,
        price_change_pct=-1.0,
        smart_money_net=-500_000_000,
    )
    assert s1["score"] == 1
    assert s1["label"] == "PARTIAL"

    # 0/3 Not Confirmed
    s0 = compute_smart_money_score(
        confidence_pct=40.0,
        broksum_label="DISTRIBUTION",
        foreign_net_value=-5_000_000_000,
        price_change_pct=1.0,
        smart_money_net=-4_000_000_000,
    )
    assert s0["score"] == 0
    assert s0["label"] == "NOT CONFIRMED"


def test_regime_classification_stock_and_ihsg():
    assert classify_stock_regime(110, 105, 100, True, False) == ("MARKUP", "BUY")
    assert classify_stock_regime(90, 95, 100, False, True) == ("MARKDOWN", "SELL / AVOID")
    assert classify_stock_regime(102, 103, 99, False, False) == ("CONSOLIDATING", "TUNGGU BREAKOUT")

    assert classify_ihsg_regime(5400, 5350, 5300, 1, 420, 240) == "BULL"
    assert classify_ihsg_regime(5100, 5200, 5300, -1, 180, 450) == "BEAR"
    assert classify_ihsg_regime(5300, 5310, 5290, 1, 300, 300) == "NEUTRAL"


def test_win_rate_evaluator():
    # Entry=100, SL=95, TP1=107.5, TP2=110
    # Day 1 rises to 108 (TP1 hit, >100, low=98>95); Day 2 hits 111 (TP2 hit)
    future = [
        Bar("2026-10-02", 101, 108, 98, 106, 1000),
        Bar("2026-10-03", 106, 111, 104, 110, 1000),
    ]
    res = evaluate_signal_outcomes(100, 95, 107.5, 110, future)
    assert res["eval_tp1_status"] == "win"
    assert res["eval_tp2_status"] == "win"
    assert res["eval_up_5d_status"] == "pending"  # only 2 future bars available
    assert res["eval_up_10d_status"] == "pending"
    assert res["eval_up_latest_status"] == "win"

    # Ambiguous same-day SL + TP1
    amb = evaluate_signal_outcomes(
        100, 95, 107.5, 110, [Bar("2026-10-02", 100, 109, 94, 102, 1000)]
    )
    assert amb["eval_tp1_status"] == "ambiguous"
    assert amb["eval_up_latest_status"] == "loss"  # touched SL

    # Excluded when SL >= Entry
    exc = evaluate_signal_outcomes(100, 100, 107.5, 110, future)
    assert exc["eval_tp1_status"] == "excluded"


def test_pivots_and_contributors():
    piv = compute_pivot_points(Bar("2026-11-26", 5215, 5300, 5210, 5240, 100))
    assert piv["p"] == 5250.0
    assert piv["r1"] > piv["p"] > piv["s1"]

    snap = [
        {"ticker": "BBCA", "close": 6000, "previousClose": 5900, "changePercent": 1.69, "tradeValue": 8e11, "nbsa": 4e7},
        {"ticker": "GOTO", "close": 26, "previousClose": 27, "changePercent": -3.70, "tradeValue": 2.5e11, "nbsa": -2e9},
    ]
    master = {
        "BBCA": {"sector": "Financials", "market_cap": 7.4e14, "free_float_pct": 42.38},
        "GOTO": {"sector": "Technology", "market_cap": 3.0e13, "free_float_pct": 75.0},
    }
    contrib = compute_ihsg_contributors(snap, master, 5242.17)
    assert contrib["gainers"][0]["ticker"] == "BBCA"
    assert contrib["losers"][0]["ticker"] == "GOTO"
    assert sector_to_slug("Properties & Real Estate") == "properties-real-estate"


def test_only_three_core_strategies_emitted():
    # Volatile 650-bar sequence designed to trigger trends, flips, breakouts, and volume spikes
    closes = [100 + (i % 15) * 2.5 + i * 0.25 for i in range(650)]
    bars = _gen_bars(closes, vol=5_000_000)
    emitted = detect_ticker_signals_history("CORE", bars, min_signal_date="2024-01-01")
    allowed = {"FRACTAL_BREAKOUT", "MACD_EMA200", "G_ACC"}
    assert {s["signal_type"] for s in emitted}.issubset(allowed)
