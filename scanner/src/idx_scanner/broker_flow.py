"""
Broker Flow & Bandarmology Logic Module for IDX Stock Trading.
Implements quantitative calculations for smart money tracking:
- Bandar Average Cost
- Bandar Gap Percentage (Distance to Cost)
- Market Flow Quadrant Classification
- Counterparty Quality Check
- Actionable Trade Plan Generation
"""

from typing import Any, Dict, List, Optional


def calculate_bandar_average_cost(buyers: List[Dict[str, Any]]) -> float:
    """
    Calculate volume-weighted average buy price of top accumulators.
    Handles both direct buyAvgPrice or buyValue / (buyVolume * 100).
    """
    if not buyers:
        return 0.0

    total_value = 0.0
    total_volume_shares = 0

    for b in buyers:
        val = float(b.get("buyValue") or b.get("buy_value") or 0.0)
        vol = int(b.get("buyVolume") or b.get("buy_volume") or 0)
        avg_price = float(b.get("buyAvgPrice") or b.get("buy_avg_price") or 0.0)

        if val > 0 and vol > 0:
            total_value += val
            total_volume_shares += vol * 100
        elif avg_price > 0 and vol > 0:
            total_value += avg_price * vol * 100
            total_volume_shares += vol * 100

    if total_volume_shares > 0:
        return round(total_value / total_volume_shares, 2)

    # Fallback to simple average of provided average prices
    prices = [float(b.get("buyAvgPrice") or b.get("buy_avg_price") or 0.0) for b in buyers]
    valid_prices = [p for p in prices if p > 0]
    return round(sum(valid_prices) / len(valid_prices), 2) if valid_prices else 0.0


def calculate_bandar_gap_pct(close_price: float, bandar_avg_cost: float) -> float:
    """
    Calculate the percentage distance of current close price from bandar average cost.
    Positive: Bandar is floating in profit.
    Negative: Current price is below bandar cost (discount zone).
    """
    if bandar_avg_cost <= 0:
        return 0.0
    return round(((close_price - bandar_avg_cost) / bandar_avg_cost) * 100.0, 2)


def classify_market_quadrant(price_change_pct: float, flow_net_value: float) -> str:
    """
    Classify into 4 Wyckoff-Smart Money quadrants:
    - [MA] markup_akumulasi (Price >= 0, Flow > 0)
    - [MD] markup_distribusi (Price >= 0, Flow <= 0) - Bull trap
    - [DA] markdown_akumulasi (Price < 0, Flow > 0) - Absorption / Serapan
    - [DD] markdown_distribusi (Price < 0, Flow <= 0) - Bear distribution / Avoid
    """
    if price_change_pct >= 0:
        return "markup_akumulasi" if flow_net_value > 0 else "markup_distribusi"
    else:
        return "markdown_akumulasi" if flow_net_value > 0 else "markdown_distribusi"


FOREIGN_BROKER_CODES = {"BK", "KZ", "AK", "RX", "ZP", "YU", "CS"}
DANANTARA_GOV_BROKER_CODES = {"CC", "NI", "BB", "AZ", "LG"}
RETAIL_BROKER_CODES = {"XL", "XC", "YP", "PD", "SQ", "KK"}
SMART_MONEY_BROKER_CODES = FOREIGN_BROKER_CODES.union(DANANTARA_GOV_BROKER_CODES)


def calculate_counterparty_purity_index(
    smart_money_buy_val: float,
    retail_sell_val: float,
) -> float:
    """
    Calculates the counterparty purity percentage.
    High percentage indicates smart money is absorbing retail panic selling.
    """
    if smart_money_buy_val <= 0:
        return 0.0
    return round(min(smart_money_buy_val, max(0.0, retail_sell_val)) / smart_money_buy_val * 100.0, 2)


def evaluate_bandar_action_verdict(
    flow_net_value: float,
    gap_pct: float,
    is_retail_net_buyer: bool = False,
    quadrant: str = "markup_akumulasi",
) -> Dict[str, Any]:
    """
    Evaluates actionable stock decision:
    - SWEET_SPOT_BUY: Flow > 0, gap_pct in [-2.0%, +3.5%], retail not trap buyer
    - WEAKNESS_ABSORPTION: Flow > 0, gap_pct < -2.0% (markdown absorption)
    - CHASING_RISK: Flow > 0, gap_pct > +8.0%
    - BULL_TRAP_AVOID: Flow <= 0, retail net buying
    - HEAVY_DISTRIBUTION: Flow <= 0, markdown distribution
    """
    if flow_net_value <= 0:
        if is_retail_net_buyer:
            return {
                "verdict": "BULL TRAP / AVOID",
                "grade": "Grade D",
                "description": "Ritel menampung jualan smart money (exit liquidity). Hindari mengejar harga.",
                "action": "AVOID / SELL ON STRENGTH",
            }
        return {
            "verdict": "HEAVY DISTRIBUTION",
            "grade": "Grade F",
            "description": "Tekanan jual smart money konsisten dan belum ada pivot serapan.",
            "action": "HARD AVOID",
        }

    # Flow is positive
    if gap_pct < -2.0:
        return {
            "verdict": "ACCUMULATE DIP",
            "grade": "Grade B+",
            "description": f"Weakness absorption: harga berada di area diskon ({gap_pct}%) di bawah modal bandar.",
            "action": "SWING BUY / ACCUMULATE",
        }

    if gap_pct <= 3.5:
        return {
            "verdict": "SWEET SPOT BUY",
            "grade": "Grade A",
            "description": f"Golden entry zone: harga sangat dekat dengan modal bandar (+{gap_pct}%). Risk/reward optimal.",
            "action": "BUY ON PULLBACK / BREAKOUT",
        }

    if gap_pct > 8.0:
        return {
            "verdict": "CHASING RISK / WAIT RETEST",
            "grade": "Grade C",
            "description": f"Overheated: harga telah terbang +{gap_pct}% di atas modal bandar. Tunggu pullback.",
            "action": "WAIT FOR PULLBACK",
        }

    return {
        "verdict": "BUY ON PULLBACK",
        "grade": "Grade B",
        "description": f"Akumulasi terkonfirmasi, gap +{gap_pct}% dari modal bandar. Beli saat koreksi wajar.",
        "action": "BUY ON PULLBACK",
    }


def calculate_horizon_momentum(
    flow_2d: float,
    flow_5d: float,
    flow_10d: float,
) -> Dict[str, Any]:
    """
    Determines if smart money accumulation is accelerating or fading.
    """
    rate_2d = flow_2d / 2.0
    rate_10d = flow_10d / 10.0
    acc_rate = rate_2d - rate_10d
    is_accelerating = acc_rate > 0

    return {
        "acc_rate": round(acc_rate, 2),
        "is_accelerating": is_accelerating,
        "status": "ACCELERATING_INFLOW" if is_accelerating else "FADING_OR_STABLE",
    }


def analyze_counterparty(top_buyers: List[Dict[str, Any]], top_sellers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze counterparty purity:
    Grade A: Smart Money (Foreign/Gov) buying from retail sellers.
    Danger: Retail buying from institutional distributors.
    """
    buyer_codes = {b.get("code") or b.get("broker") for b in top_buyers if (b.get("code") or b.get("broker"))}
    seller_codes = {s.get("code") or s.get("broker") for s in top_sellers if (s.get("code") or s.get("broker"))}

    smart_buyers = buyer_codes.intersection(SMART_MONEY_BROKER_CODES)
    retail_sellers = seller_codes.intersection(RETAIL_BROKER_CODES)
    retail_buyers = buyer_codes.intersection(RETAIL_BROKER_CODES)
    smart_sellers = seller_codes.intersection(SMART_MONEY_BROKER_CODES)

    if smart_buyers and retail_sellers:
        quality = "GRADE_A_ACCUMULATION"
        description = f"Smart money ({', '.join(smart_buyers)}) menyerap buangan ritel ({', '.join(retail_sellers)})"
    elif smart_sellers and retail_buyers:
        quality = "DISTRIBUTION_TRAP"
        description = f"Smart money ({', '.join(smart_sellers)}) mendistribusikan barang ke ritel ({', '.join(retail_buyers)})"
    elif smart_buyers:
        quality = "INSTITUTIONAL_INTEREST"
        description = f"Didorong akumulasi institusi ({', '.join(smart_buyers)})"
    else:
        quality = "NEUTRAL_MIXED"
        description = "Pertukaran volume campuran antar pelaku pasar"

    return {
        "quality": quality,
        "description": description,
        "smart_buyers": list(smart_buyers),
        "retail_sellers": list(retail_sellers),
    }


def synthesize_trade_plan(
    quadrant: str,
    close_price: float,
    bandar_avg_cost: float,
    foreign_streak: int = 1,
) -> Dict[str, Any]:
    """
    Generate an actionable, disciplined stock trade plan.
    Enforces risk/reward >= 1:2.5 whenever actionable.
    """
    if close_price <= 0:
        return {
            "action": "AVOID",
            "entry_zone": "-",
            "stop_loss": "-",
            "target_price": "-",
            "rr_ratio": "-",
            "note": "Harga tidak valid.",
        }

    cost = bandar_avg_cost if bandar_avg_cost > 0 else close_price

    if quadrant == "markdown_distribusi":
        return {
            "action": "HARD AVOID",
            "entry_zone": "Dilarang Entry",
            "stop_loss": "-",
            "target_price": "Tunggu konfirmasi reversal di support",
            "rr_ratio": "-",
            "note": "Distribusi smart money masih berlangsung (tekanan jual tinggi).",
        }

    if quadrant == "markup_distribusi":
        return {
            "action": "AVOID / SELL ON STRENGTH",
            "entry_zone": "Jangan mengejar harga (Bull Trap)",
            "stop_loss": f"{int(round(close_price * 0.97))}",
            "target_price": "Segera amankan profit bila sudah pegang",
            "rr_ratio": "-",
            "note": "Kenaikan harga tidak didukung smart money (potensi jebakan ritel).",
        }

    if quadrant == "markdown_akumulasi":
        # Serapan diam-diam saat harga turun: area entry tepat di sekitar cost bandar
        entry_low = int(round(cost * 0.98))
        entry_high = int(round(max(cost, close_price)))
        sl_price = int(round(cost * 0.95))  # 5% risk below bandar cost
        risk = entry_high - sl_price
        tp_price = int(round(entry_high + (risk * 2.8)))  # 1 : 2.8 RR
        rr = "1 : 2.8"

        return {
            "action": "SWING BUY / ACCUMULATE",
            "entry_zone": f"{entry_low} - {entry_high}",
            "stop_loss": f"{sl_price} (Risk ~5.0%)",
            "target_price": f"{tp_price} (Reward ~14.0%)",
            "rr_ratio": rr,
            "note": f"Weakness absorption terdeteksi. Smart money menampung di harga modal ~{int(round(cost))}.",
        }

    # quadrant == "markup_akumulasi"
    # Momentum breakout / pull-back
    entry_low = int(round(max(cost, close_price * 0.98)))
    entry_high = int(round(close_price * 1.01))
    sl_price = int(round(min(cost * 0.96, close_price * 0.95)))
    risk = max(1, entry_high - sl_price)
    tp_price = int(round(entry_high + (risk * 3.0)))
    rr = "1 : 3.0"

    streak_note = f" dengan rentetan beli asing {foreign_streak} sesi" if foreign_streak > 1 else ""

    return {
        "action": "BUY ON PULLBACK / BREAKOUT",
        "entry_zone": f"{entry_low} - {entry_high}",
        "stop_loss": f"{sl_price} (Risk ~4.5%)",
        "target_price": f"{tp_price} (Reward ~13.5%)",
        "rr_ratio": rr,
        "note": f"Markup akumulasi valid{streak_note}. Smart money mengawal tren naik.",
    }
