"""
Unit tests for Broker Flow & Bandarmology Logic Module.
Tests calculations for Bandar Average Cost, Quadrant Classification,
Counterparty Quality, and Trade Plan Synthesis.
"""

from idx_scanner.broker_flow import (
    calculate_bandar_average_cost,
    calculate_bandar_gap_pct,
    classify_market_quadrant,
    analyze_counterparty,
    synthesize_trade_plan,
)


def test_calculate_bandar_average_cost_weighted():
    buyers = [
        {"code": "BK", "buyVolume": 2000, "buyValue": 68000000.0},  # avg 340
        {"code": "AK", "buyVolume": 1000, "buyValue": 35000000.0},  # avg 350
    ]
    # Total value = 103,000,000
    # Total shares = (2000 + 1000) * 100 = 300,000
    # Expected avg = 103,000,000 / 300,000 = 343.33
    avg = calculate_bandar_average_cost(buyers)
    assert avg == 343.33


def test_calculate_bandar_gap_pct():
    gap_profit = calculate_bandar_gap_pct(close_price=350.0, bandar_avg_cost=340.0)
    assert gap_profit == 2.94

    gap_discount = calculate_bandar_gap_pct(close_price=3000.0, bandar_avg_cost=3060.0)
    assert gap_discount == -1.96

    assert calculate_bandar_gap_pct(100.0, 0.0) == 0.0


def test_classify_market_quadrant():
    assert classify_market_quadrant(2.5, 50000000.0) == "markup_akumulasi"
    assert classify_market_quadrant(1.2, -30000000.0) == "markup_distribusi"
    assert classify_market_quadrant(-3.5, 80000000.0) == "markdown_akumulasi"
    assert classify_market_quadrant(-4.0, -100000000.0) == "markdown_distribusi"
    assert classify_market_quadrant(0.0, 1000.0) == "markup_akumulasi"


def test_analyze_counterparty():
    buyers = [{"code": "BK"}, {"code": "KZ"}]
    sellers = [{"code": "YP"}, {"code": "XL"}]
    res = analyze_counterparty(buyers, sellers)
    assert res["quality"] == "GRADE_A_ACCUMULATION"
    assert "BK" in res["smart_buyers"]
    assert "YP" in res["retail_sellers"]

    # Inverted: retail buys from smart money
    trap_res = analyze_counterparty([{"code": "YP"}], [{"code": "BK"}])
    assert trap_res["quality"] == "DISTRIBUTION_TRAP"


def test_synthesize_trade_plan():
    # Markdown distribusi -> Hard Avoid
    plan_dd = synthesize_trade_plan("markdown_distribusi", 5550.0, 5570.0)
    assert plan_dd["action"] == "HARD AVOID"

    # Markup distribusi -> Bull trap warning
    plan_md = synthesize_trade_plan("markup_distribusi", 3200.0, 3180.0)
    assert "AVOID" in plan_md["action"]

    # Markdown akumulasi -> Swing buy serapan
    plan_da = synthesize_trade_plan("markdown_akumulasi", 3080.0, 3060.0)
    assert "SWING BUY" in plan_da["action"]
    assert "1 : 2.8" in plan_da["rr_ratio"]

    # Markup akumulasi -> Buy on pullback
    plan_ma = synthesize_trade_plan("markup_akumulasi", 344.0, 340.0, foreign_streak=4)
    assert "BUY ON PULLBACK" in plan_ma["action"]
    assert "1 : 3.0" in plan_ma["rr_ratio"]
    assert "rentetan beli asing 4 sesi" in plan_ma["note"]
