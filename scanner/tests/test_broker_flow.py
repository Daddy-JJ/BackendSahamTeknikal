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
    calculate_counterparty_purity_index,
    evaluate_bandar_action_verdict,
    calculate_horizon_momentum,
    FOREIGN_BROKER_CODES,
    DANANTARA_GOV_BROKER_CODES,
    RETAIL_BROKER_CODES,
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

    # Also handles netValue / netVolume from get_broksum_ticker_brokers
    net_buyers = [
        {"code": "BK", "netVolume": 2000, "netValue": 68000000.0},
        {"code": "AK", "netVolume": 1000, "netValue": 35000000.0},
    ]
    assert calculate_bandar_average_cost(net_buyers) == 343.33


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


def test_broker_taxonomy_and_danantara():
    assert "BK" in FOREIGN_BROKER_CODES
    assert "KZ" in FOREIGN_BROKER_CODES
    assert "CC" in DANANTARA_GOV_BROKER_CODES
    assert "NI" in DANANTARA_GOV_BROKER_CODES  # BNI Sekuritas is Danantara/Gov
    assert "XL" in RETAIL_BROKER_CODES  # Stockbit
    assert "XC" in RETAIL_BROKER_CODES  # Ajaib
    assert "YP" in RETAIL_BROKER_CODES  # Mirae


def test_calculate_counterparty_purity_index():
    # 80B bought by smart money, 60B sold by retail -> 75%
    purity = calculate_counterparty_purity_index(80_000_000_000.0, 60_000_000_000.0)
    assert purity == 75.0

    # Over 100% capped
    purity_full = calculate_counterparty_purity_index(50_000_000_000.0, 80_000_000_000.0)
    assert purity_full == 100.0

    # Zero smart money buy -> 0%
    assert calculate_counterparty_purity_index(0.0, 10_000_000.0) == 0.0


def test_evaluate_bandar_action_verdict():
    # Sweet spot entry: positive flow, gap +1.0%
    verdict_sweet = evaluate_bandar_action_verdict(50_000_000_000.0, 1.0)
    assert verdict_sweet["verdict"] == "SWEET SPOT BUY"
    assert verdict_sweet["grade"] == "Grade A"

    # Weakness absorption: positive flow, gap -2.5%
    verdict_dip = evaluate_bandar_action_verdict(80_000_000_000.0, -2.5)
    assert verdict_dip["verdict"] == "ACCUMULATE DIP"
    assert verdict_dip["grade"] == "Grade B+"

    # Chasing risk: positive flow, gap +12.0%
    verdict_chase = evaluate_bandar_action_verdict(30_000_000_000.0, 12.0)
    assert "CHASING RISK" in verdict_chase["verdict"]
    assert verdict_chase["grade"] == "Grade C"

    # Bull trap: negative flow, retail net buyer
    verdict_trap = evaluate_bandar_action_verdict(-40_000_000_000.0, 0.5, is_retail_net_buyer=True)
    assert "BULL TRAP" in verdict_trap["verdict"]
    assert verdict_trap["grade"] == "Grade D"

    # Heavy distribution
    verdict_dist = evaluate_bandar_action_verdict(-100_000_000_000.0, -4.0, is_retail_net_buyer=False)
    assert verdict_dist["verdict"] == "HEAVY DISTRIBUTION"
    assert verdict_dist["grade"] == "Grade F"


def test_calculate_horizon_momentum():
    # Flow 2D is 40B (rate 20B/day), Flow 10D is 100B (rate 10B/day) -> accelerating
    mom_acc = calculate_horizon_momentum(40_000_000_000.0, 70_000_000_000.0, 100_000_000_000.0)
    assert mom_acc["is_accelerating"] is True
    assert mom_acc["status"] == "ACCELERATING_INFLOW"
    assert mom_acc["acc_rate"] == 10_000_000_000.0

    # Flow 2D is -10B, Flow 10D is 50B -> fading
    mom_fade = calculate_horizon_momentum(-10_000_000_000.0, 10_000_000_000.0, 50_000_000_000.0)
    assert mom_fade["is_accelerating"] is False
    assert mom_fade["status"] == "FADING_OR_STABLE"


def test_resolve_horizon_start_dates_and_paths(tmp_path):
    from pathlib import Path
    from idx_scanner.daily_broker_flow_sync import (
        resolve_horizon_start_dates,
        resolve_snapshot_output_paths,
    )

    avail = [
        "2026-11-11", "2026-11-12", "2026-11-13",
        "2026-11-16", "2026-11-17", "2026-11-18",
        "2026-11-19", "2026-11-20", "2026-11-23", "2026-11-24",
    ]
    starts = resolve_horizon_start_dates(avail, "2026-11-24")
    assert starts == {"2D": "2026-11-23", "5D": "2026-11-18", "10D": "2026-11-11"}

    # Simulated standalone BackendSahamTeknikal checkout (no sibling frontend dir)
    fake_backend = tmp_path / "BackendSahamTeknikal"
    fake_mod = fake_backend / "scanner" / "src" / "idx_scanner" / "daily_broker_flow_sync.py"
    fake_mod.parent.mkdir(parents=True)
    fake_mod.touch()
    b_path, f_path = resolve_snapshot_output_paths(fake_mod)
    assert b_path == fake_backend.resolve() / "data" / "broker_flow_snapshot_latest.json"
    assert f_path is None

    # Simulated monorepo with sibling frontend dir
    (tmp_path / "frontend").mkdir()
    b_path2, f_path2 = resolve_snapshot_output_paths(fake_mod)
    assert f_path2 == (tmp_path / "frontend" / "src" / "data" / "broker_flow_snapshot_latest.json").resolve()


def test_build_ticker_detail_record_and_sync_pipeline(tmp_path):
    from idx_scanner.daily_broker_flow_sync import (
        build_ticker_detail_record,
        sync_daily_broker_flow,
    )

    detail = build_ticker_detail_record(
        ticker="MBMA",
        horizon="5D",
        horizon_label="5 Hari",
        date_range="2026-11-23 s/d 2026-11-27",
        close_price=360.0,
        change_pct=4.5,
        net_value=60_000_000_000.0,
        net_volume_lots=1_500_000,
        bandar_cost=345.0,
        top_buyers=[{"code": "BK", "name": "JPM", "investor_group": "FOREIGN", "net_value": 80_000_000_000.0, "avg_price": 345.0}],
        top_sellers=[{"code": "YP", "name": "Mirae", "investor_group": "LOCAL", "net_value": -20_000_000_000.0, "avg_price": 350.0}],
        why_insight="Lead BK",
    )
    assert detail["concentration_pct"] == 80.0
    assert "BK" in detail["counterparty_note"]
    assert "YP" in detail["counterparty_note"]

    class FakeMcpClient:
        async def call_tool(self, http_client, tool_name, arguments, timeout=25.0):
            if tool_name == "get_broksum_availability":
                return {"dates": [{"date": "2026-11-26"}, {"date": "2026-11-27"}]}
            if tool_name == "get_broksum_market_ranking":
                if arguments.get("side") == "accumulation":
                    return {
                        "records": [
                            {
                                "ticker": "ASII",
                                "close": 5750,
                                "changePercent": 2.0,
                                "foreignNetValue": 120_000_000_000,
                                "governmentNetValue": 10_000_000_000,
                                "topBuyerNetValueTopN": 150_000_000_000,
                                "topSellerNetValueTopN": 40_000_000_000,
                                "topNetBuyer": {"code": "AK"},
                                "bandarSignal": {"score": 45},
                            }
                        ]
                    }
                return {
                    "records": [
                        {
                            "ticker": "ASII",
                            "close": 5750,
                            "changePercent": 2.0,
                            "foreignNetValue": 120_000_000_000,
                            "topSellerNetValueTopN": 40_000_000_000,
                            "topNetSeller": {"code": "BK"},
                        },
                        {
                            "ticker": "BBRI",
                            "close": 3070,
                            "changePercent": -1.5,
                            "foreignNetValue": -250_000_000_000,
                            "topSellerNetValueTopN": 300_000_000_000,
                            "topNetSeller": {"code": "ZP"},
                        },
                    ]
                }
            if tool_name == "get_broksum_market_quadrant":
                return {
                    "totalTickers": 2,
                    "summary": {
                        "markup_akumulasi": 1,
                        "markup_distribusi": 0,
                        "markdown_akumulasi": 0,
                        "markdown_distribusi": 1,
                    },
                    "records": [
                        {"ticker": "ASII", "close": 5750, "changePercent": 2.0, "quadrant": "markup_akumulasi", "smartMoneyNet": 130_000_000_000, "turnoverValue": 500_000_000_000},
                        {"ticker": "BBRI", "close": 3070, "changePercent": -1.5, "quadrant": "markdown_distribusi", "smartMoneyNet": -250_000_000_000, "turnoverValue": 600_000_000_000},
                    ],
                }
            if tool_name == "get_market_snapshot":
                return {
                    "records": [
                        {"ticker": "ASII", "close": 5750, "changePercent": 2.0, "volume": 10000, "tradeValue": 500_000_000_000},
                        {"ticker": "BBRI", "close": 3070, "changePercent": -1.5, "volume": 20000, "tradeValue": 600_000_000_000},
                    ]
                }
            if tool_name == "get_broksum_ticker_brokers":
                ticker = arguments["ticker"]
                if ticker == "BBRI":
                    if arguments.get("sort") == "net_value_asc":
                        return {"records": [{"code": "ZP", "netSide": "SELL", "netValue": -300_000_000_000, "netVolume": -970000, "sellAvgPrice": 3080}]}
                    return {"records": [{"code": "XL", "netSide": "BUY", "netValue": 50_000_000_000, "netVolume": 160000, "buyAvgPrice": 3070}]}
                if arguments.get("sort") == "net_value_asc":
                    return {"records": [{"code": "BK", "netSide": "SELL", "netValue": -40_000_000_000, "netVolume": -70000, "sellAvgPrice": 5740}]}
                return {"records": [{"code": "AK", "netSide": "BUY", "netValue": 150_000_000_000, "netVolume": 260000, "buyAvgPrice": 5730}]}
            if tool_name == "get_broksum_signal":
                if arguments["ticker"] == "BBRI":
                    return {"label": "STRONG_DISTRIBUTION", "score": -40, "components": {"brokerConcentration": 31.2}, "summary": {"foreignNetValue": -250_000_000_000}}
                return {"label": "STRONG_ACCUMULATION", "score": 52, "components": {"brokerConcentration": 28.5}, "summary": {"foreignNetValue": 120_000_000_000}}
            return {}

    res = sync_daily_broker_flow(
        tickers=["ASII", "BBRI"],
        client=FakeMcpClient(),
        output_dir=tmp_path,
    )
    assert res["market_summary"]["smart_money_net"] == -120_000_000_000
    acc_tickers = {x["ticker"] for x in res["top_accumulations"]}
    dist_tickers = {x["ticker"] for x in res["top_distributions"]}
    assert acc_tickers.isdisjoint(dist_tickers)
    assert "smart_money_net" in res["top_accumulations"][0]
    assert "smart_money_net" in res["top_distributions"][0]
    assert res["ticker_horizons"]["BBRI"]["5D"]["quadrant"] == "markdown_distribusi"
    assert res["ticker_horizons"]["BBRI"]["5D"]["concentration_pct"] == 31.2
    assert (tmp_path / "broker_flow_snapshot_latest.json").exists()


