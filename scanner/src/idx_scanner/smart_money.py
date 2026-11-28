"""
Smart Money Scoring (3 Factors) & IHSG Contributors / Draggers Calculator.

Smart Money 3 Factors:
1. Broker Accumulation: confidence >= 60% AND accumulation bias
2. Foreign Inflow: net foreign > 0
3. Bandarmology Alignment: broker trend aligns with price trend

Score Mapping:
  3/3 -> STRONG CONFIRMATION
  2/3 -> CONFIRMED
  1/3 -> PARTIAL
  0/3 -> NOT CONFIRMED
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def sector_to_slug(sector_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", sector_name.lower().strip()).strip("-")
    return slug or "other"


def compute_smart_money_score(
    *,
    confidence_pct: Optional[float],
    broksum_label: Optional[str],
    accumulation_share_pct: Optional[float] = None,
    distribution_share_pct: Optional[float] = None,
    foreign_net_value: Optional[float] = None,
    price_change_pct: float = 0.0,
    smart_money_net: float = 0.0,
    bandar_value: Optional[float] = None,
    bandar_value_ma10: Optional[float] = None,
    close_price: float = 0.0,
    bandar_avg_cost: Optional[float] = None,
) -> Dict[str, Any]:
    """Compute exact 3-factor Smart Money Confirmation Score (0/3 .. 3/3)."""
    conf = float(confidence_pct or 0.0)
    lbl = str(broksum_label or "").upper()
    acc_pct = float(accumulation_share_pct or 0.0)
    dist_pct = float(distribution_share_pct or 0.0)

    is_acc_bias = "ACCUMULATION" in lbl or (
        smart_money_net > 0 and acc_pct >= dist_pct and "DISTRIBUTION" not in lbl
    )
    factor_broker_acc = conf >= 60.0 and is_acc_bias

    f_net = float(foreign_net_value or 0.0)
    factor_foreign_inflow = f_net > 0.0

    b_val = float(bandar_value if bandar_value is not None else smart_money_net)
    # Alignment: price up accompanied by net accumulation, or rising bandar accumulation trend above MA10
    same_direction_up = price_change_pct > 0 and (smart_money_net > 0 or b_val > 0)
    ma_trend_up = (
        bandar_value_ma10 is not None
        and b_val > 0
        and b_val >= float(bandar_value_ma10)
        and (bandar_avg_cost is None or bandar_avg_cost <= 0 or close_price >= float(bandar_avg_cost) * 0.985)
    )
    factor_alignment = same_direction_up or ma_trend_up

    score = int(factor_broker_acc) + int(factor_foreign_inflow) + int(factor_alignment)
    labels = {
        3: "STRONG CONFIRMATION",
        2: "CONFIRMED",
        1: "PARTIAL",
        0: "NOT CONFIRMED",
    }

    return {
        "score": score,
        "label": labels[score],
        "factors": {
            "broker_accumulation": {
                "passed": factor_broker_acc,
                "confidence_pct": round(conf, 2),
                "label": lbl or "UNKNOWN",
                "rule": "confidence >= 60% dan dominan akumulasi",
            },
            "foreign_inflow": {
                "passed": factor_foreign_inflow,
                "foreign_net": round(f_net),
                "rule": "net foreign > 0",
            },
            "bandarmology_alignment": {
                "passed": factor_alignment,
                "price_change_pct": round(price_change_pct, 2),
                "smart_money_net": round(smart_money_net),
                "bandar_value": round(b_val),
                "rule": "trend broker searah kenaikan harga / di atas modal bandar",
            },
        },
    }


def compute_ihsg_contributors(
    snapshot_records: List[Dict[str, Any]],
    master_by_ticker: Dict[str, Dict[str, Any]],
    ihsg_prev_close: float,
    top_n: int = 15,
) -> Dict[str, Any]:
    """
    Estimate top IHSG index point contributors (Penopang) and draggers (Pemberat)
    using Free-Float Adjusted Market Cap weights when free_float_pct is available,
    falling back to raw market_cap for constituents missing free_float.
    """
    weighted_rows: List[Dict[str, Any]] = []
    total_ff_weight = 0.0

    for rec in snapshot_records:
        ticker = str(rec.get("ticker") or "").upper().strip()
        if not ticker or ticker == "IHSG":
            continue
        chg_pct = rec.get("changePercent")
        close = rec.get("close")
        prev_c = rec.get("previousClose")
        if chg_pct is None or close is None:
            continue
        chg_val = float(chg_pct)
        close_val = float(close)
        prev_val = float(prev_c) if prev_c else (close_val / (1.0 + chg_val / 100.0) if chg_val != -100.0 else close_val)
        meta = master_by_ticker.get(ticker) or {}
        mcap = float(meta.get("market_cap") or 0.0)
        ff_pct = meta.get("free_float_pct")
        if mcap <= 0:
            continue
        ff_ratio = (float(ff_pct) / 100.0) if ff_pct is not None and float(ff_pct) > 0 else 0.50
        # Previous day estimated free-float mcap weight
        prev_ff_mcap = (mcap * ff_ratio) / (1.0 + chg_val / 100.0) if prev_val > 0 and chg_val != -100.0 else (mcap * ff_ratio)
        total_ff_weight += prev_ff_mcap
        weighted_rows.append({
            "ticker": ticker,
            "sector": meta.get("sector") or "Other",
            "close": close_val,
            "change_pct": round(chg_val, 2),
            "trade_value": float(rec.get("tradeValue") or 0.0),
            "market_cap": mcap,
            "free_float_pct": float(ff_pct) if ff_pct is not None else None,
            "prev_ff_mcap": prev_ff_mcap,
            "nbsa": float(rec.get("nbsa") or 0.0),
        })

    if total_ff_weight <= 0 or ihsg_prev_close <= 0:
        return {"gainers": [], "losers": [], "methodology": "Estimasi Free-Float Market Cap Weight"}

    for row in weighted_rows:
        weight_share = row["prev_ff_mcap"] / total_ff_weight
        est_points = ihsg_prev_close * weight_share * (row["change_pct"] / 100.0)
        row["weight_pct"] = round(weight_share * 100.0, 3)
        row["index_points"] = round(est_points, 2)
        del row["prev_ff_mcap"]

    gainers = sorted(
        [r for r in weighted_rows if r["index_points"] > 0],
        key=lambda r: r["index_points"],
        reverse=True,
    )[:top_n]
    losers = sorted(
        [r for r in weighted_rows if r["index_points"] < 0],
        key=lambda r: r["index_points"],
    )[:top_n]

    return {
        "gainers": gainers,
        "losers": losers,
        "methodology": "Estimasi kontribusi poin menggunakan bobot Market Cap × Free Float (%) dari Max Trade MCP terhadap IHSG sesi sebelumnya.",
        "constituents_weighted": len(weighted_rows),
    }
