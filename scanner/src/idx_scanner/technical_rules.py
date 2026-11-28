"""
Quantitative Technical Rules, Indicators, Regime Classifier & Win Rate Evaluator.

Implements deterministic, auditable daily EOD rules:
1. FRACTAL_BREAKOUT  (FracChan_v2 port — 5-bar fractal channel, anti-lookahead available_session=t)
2. MACD_EMA200       (EMA200 trend filter + MACD histogram <=0 -> >0 + 60-bar pivot low SL)
3. G_ACC             (Low-base / discount accumulation detected + volume/price expansion)
4. Regime Detection  (MARKUP / CONSOLIDATING / MARKDOWN + IHSG BULL / NEUTRAL / BEAR).
5. Historical Win Rate Evaluator (TP1 before SL, TP2 before SL, Up without SL 5D / 10D / Latest).
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_value: float = 0.0
    nbsa: float = 0.0

    def valid(self) -> bool:
        vals = (self.open, self.high, self.low, self.close, self.volume)
        return (
            all(isfinite(v) for v in vals)
            and self.open > 0
            and self.high > 0
            and self.low > 0
            and self.close > 0
            and self.volume >= 0
            and self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high
        )


def round_idx_tick(price: float, direction: str = "nearest") -> float:
    """Round price to IDX equity tick step."""
    if price <= 0 or not isfinite(price):
        return 0.0
    if price < 200:
        step = 1
    elif price < 500:
        step = 2
    elif price < 2000:
        step = 5
    elif price < 5000:
        step = 10
    else:
        step = 25

    if direction == "down":
        return float(max(step, int(price // step) * step))
    if direction == "up":
        import math

        return float(int(math.ceil(price / step)) * step)
    return float(max(step, round(price / step) * step))


def ema_series(values: Sequence[float], period: int) -> List[float]:
    """Recurrence EMA matching SOT indicator_definition=v1 (float64, no rounding)."""
    if not values:
        return []
    alpha = 2.0 / (period + 1)
    out = [float(values[0])]
    for val in values[1:]:
        out.append(alpha * float(val) + (1.0 - alpha) * out[-1])
    return out


def sma_series(values: Sequence[Optional[float]], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for i in range(len(values)):
        if i < period - 1:
            out.append(None)
            continue
        window = values[i - period + 1 : i + 1]
        if any(v is None for v in window):
            out.append(None)
        else:
            out.append(sum(float(v) for v in window if v is not None) / period)
    return out


def macd_series(
    closes: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> Tuple[List[float], List[float], List[float]]:
    if not closes:
        return [], [], []
    ema_fast = ema_series(closes, fast)
    ema_slow = ema_series(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow, strict=True)]
    signal_line = ema_series(macd_line, signal)
    histogram = [m - sig for m, sig in zip(macd_line, signal_line, strict=True)]
    return macd_line, signal_line, histogram


def atr_series(bars: Sequence[Bar], period: int = 14) -> List[Optional[float]]:
    if not bars:
        return []
    tr: List[float] = []
    for i, b in enumerate(bars):
        if i == 0:
            tr.append(b.high - b.low)
        else:
            prev_c = bars[i - 1].close
            tr.append(max(b.high - b.low, abs(b.high - prev_c), abs(b.low - prev_c)))
    out: List[Optional[float]] = [None] * len(bars)
    if len(bars) >= period:
        cur = sum(tr[:period]) / period
        out[period - 1] = cur
        for i in range(period, len(bars)):
            cur = ((period - 1) * cur + tr[i]) / period
            out[i] = cur
    return out


def rsi_series(closes: Sequence[float], period: int = 14) -> List[Optional[float]]:
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    if n <= period:
        return out
    gains = [max(0.0, closes[i] - closes[i - 1]) for i in range(1, n)]
    losses = [max(0.0, closes[i - 1] - closes[i]) for i in range(1, n)]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    for i in range(period, len(gains)):
        avg_gain = ((period - 1) * avg_gain + gains[i]) / period
        avg_loss = ((period - 1) * avg_loss + losses[i]) / period
        if avg_loss == 0:
            out[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i + 1] = 100.0 - (100.0 / (1.0 + rs))
    return out


def supertrend_series(
    bars: Sequence[Bar], period: int = 10, multiplier: float = 3.0
) -> List[Dict[str, Any]]:
    atr_vals = atr_series(bars, period)
    out: List[Dict[str, Any]] = []
    prev_upper = 0.0
    prev_lower = 0.0
    prev_st = 0.0
    prev_dir = 1
    initialized = False

    for i, b in enumerate(bars):
        a = atr_vals[i]
        if a is None:
            out.append({"date": b.date, "value": None, "direction": 0})
            continue
        hl2 = (b.high + b.low) / 2.0
        basic_upper = hl2 + multiplier * a
        basic_lower = hl2 - multiplier * a
        if not initialized:
            prev_upper = basic_upper
            prev_lower = basic_lower
            prev_dir = 1 if b.close >= basic_lower else -1
            prev_st = basic_lower if prev_dir == 1 else basic_upper
            initialized = True
            out.append({"date": b.date, "value": round(prev_st, 2), "direction": prev_dir})
            continue

        prev_c = bars[i - 1].close
        final_upper = basic_upper if (basic_upper < prev_upper or prev_c > prev_upper) else prev_upper
        final_lower = basic_lower if (basic_lower > prev_lower or prev_c < prev_lower) else prev_lower

        if prev_st == prev_upper:
            if b.close > final_upper:
                cur_dir, cur_st = 1, final_lower
            else:
                cur_dir, cur_st = -1, final_upper
        else:
            if b.close < final_lower:
                cur_dir, cur_st = -1, final_upper
            else:
                cur_dir, cur_st = 1, final_lower

        prev_upper, prev_lower, prev_dir, prev_st = final_upper, final_lower, cur_dir, cur_st
        out.append({"date": b.date, "value": round(cur_st, 2), "direction": cur_dir})
    return out


def compute_pivot_points(prev_bar: Bar) -> Dict[str, float]:
    """Classic floor pivot points calculated from prior session H/L/C."""
    h, low, c = prev_bar.high, prev_bar.low, prev_bar.close
    p = (h + low + c) / 3.0
    r1 = 2.0 * p - low
    s1 = 2.0 * p - h
    r2 = p + (h - low)
    s2 = p - (h - low)
    r3 = h + 2.0 * (p - low)
    s3 = low - 2.0 * (h - p)
    return {
        "p": round(p, 2),
        "r1": round(r1, 2),
        "r2": round(r2, 2),
        "r3": round(r3, 2),
        "s1": round(s1, 2),
        "s2": round(s2, 2),
        "s3": round(s3, 2),
    }


def fractal_levels(
    bars: Sequence[Bar],
) -> List[Tuple[Optional[Tuple[str, float, str, str]], Optional[Tuple[str, float, str, str]]]]:
    """
    Port of FracChan_v2 (© NielsG, MPL-2.0) + SOT available_session = session[t].
    Each non-null element is (id, price, pivot_date, available_date).
    """
    ceiling: Optional[Tuple[str, float, str, str]] = None
    floor: Optional[Tuple[str, float, str, str]] = None
    out: List[Tuple[Optional[Tuple[str, float, str, str]], Optional[Tuple[str, float, str, str]]]] = []

    for t, bar in enumerate(bars):
        if t >= 5:
            pivot = bars[t - 3]
            others = (bars[t - 5], bars[t - 4], bars[t - 2], bars[t - 1])
            if all(pivot.high >= o.high for o in others):
                fid = sha256(f"upper|{pivot.date}|{bar.date}".encode()).hexdigest()[:24]
                ceiling = (fid, pivot.high, pivot.date, bar.date)
            if all(pivot.low <= o.low for o in others):
                fid = sha256(f"lower|{pivot.date}|{bar.date}".encode()).hexdigest()[:24]
                floor = (fid, pivot.low, pivot.date, bar.date)
        out.append((ceiling, floor))
    return out


def swing_low_stop(bars: Sequence[Bar], idx: int, lookback: int = 60) -> Optional[float]:
    """Pivot low at j in [max(2, idx - lookback) .. idx - 2] with 2-left / 2-right check."""
    start = max(2, idx - lookback)
    for j in range(idx - 2, start - 1, -1):
        if all(bars[j].low <= bars[k].low for k in (j - 2, j - 1, j + 1, j + 2)):
            return bars[j].low
    return None


def classify_stock_regime(
    close: float,
    ema21: Optional[float],
    ema50: Optional[float],
    has_accumulation: bool,
    has_distribution: bool,
) -> Tuple[str, str]:
    """
    Stock Regime Detection:
    - MARKUP: close > EMA21 and close > EMA50, trend naik & akumulasi terdeteksi -> BUY
    - MARKDOWN: close < EMA21 and close < EMA50, trend turun & distribusi terdeteksi -> SELL / AVOID
    - CONSOLIDATING: sideways di antara EMA / belum searah -> TUNGGU BREAKOUT
    """
    if ema21 is None or ema50 is None or close <= 0:
        return "CONSOLIDATING", "TUNGGU BREAKOUT"

    above_both = close > ema21 and close > ema50
    below_both = close < ema21 and close < ema50
    uptrend_stack = ema21 >= ema50 * 0.995
    downtrend_stack = ema21 <= ema50 * 1.005

    if above_both and uptrend_stack and has_accumulation and not has_distribution:
        return "MARKUP", "BUY"
    if below_both and downtrend_stack and has_distribution:
        return "MARKDOWN", "SELL / AVOID"
    if above_both and has_accumulation:
        return "MARKUP", "BUY"
    if below_both and not has_accumulation:
        return "MARKDOWN", "SELL / AVOID"
    return "CONSOLIDATING", "TUNGGU BREAKOUT"


def classify_ihsg_regime(
    close: float,
    ema21: Optional[float],
    ema50: Optional[float],
    supertrend_dir: int,
    gainers: int,
    losers: int,
) -> str:
    """Market-level IHSG regime: BULL / NEUTRAL / BEAR."""
    if ema21 is None or ema50 is None:
        return "NEUTRAL"
    breadth_ratio = gainers / max(1, losers)
    if close > ema21 and close > ema50 and supertrend_dir == 1 and breadth_ratio >= 1.05:
        return "BULL"
    if close < ema21 and close < ema50 and supertrend_dir == -1 and breadth_ratio <= 0.95:
        return "BEAR"
    return "NEUTRAL"


def evaluate_signal_outcomes(
    entry_price: float,
    stop_loss: Optional[float],
    tp1: Optional[float],
    tp2: Optional[float],
    future_bars: Sequence[Bar],
) -> Dict[str, str]:
    """
    Evaluate historical forward outcomes starting on t+1 (day after signal):
    - tp1 / tp2: win if TP touched before SL; same-day SL + TP = ambiguous; SL >= entry or TP <= entry = excluded.
    - up_5d / up_10d: requires full N bars; win if max(high) > entry AND min(low) > SL across all N bars.
    - up_latest: requires >= 1 bar; win if max(high) > entry AND min(low) > SL across all bars so far.
    """
    if (
        stop_loss is None
        or tp1 is None
        or tp2 is None
        or stop_loss <= 0
        or not (stop_loss < entry_price < tp1 <= tp2)
    ):
        return {
            "eval_tp1_status": "excluded",
            "eval_tp2_status": "excluded",
            "eval_up_5d_status": "excluded",
            "eval_up_10d_status": "excluded",
            "eval_up_latest_status": "excluded",
        }

    def eval_target(target: float) -> str:
        for b in future_bars:
            if not b.valid():
                return "excluded"
            hit_sl = b.low <= stop_loss
            hit_tp = b.high >= target
            if hit_sl and hit_tp:
                return "ambiguous"
            if hit_sl:
                return "loss"
            if hit_tp:
                return "win"
        return "pending"

    def eval_up_window(n_days: Optional[int]) -> str:
        if n_days is not None:
            if len(future_bars) < n_days:
                return "pending"
            window = future_bars[:n_days]
        else:
            if len(future_bars) == 0:
                return "pending"
            window = future_bars

        if any(not b.valid() for b in window):
            return "excluded"
        sl_touched = any(b.low <= stop_loss for b in window)
        if sl_touched:
            return "loss"
        went_up = any(b.high > entry_price for b in window)
        if went_up:
            return "win"
        return "loss" if n_days is not None else "pending"

    return {
        "eval_tp1_status": eval_target(tp1),
        "eval_tp2_status": eval_target(tp2),
        "eval_up_5d_status": eval_up_window(5),
        "eval_up_10d_status": eval_up_window(10),
        "eval_up_latest_status": eval_up_window(None),
    }


def detect_ticker_signals_history(
    ticker: str,
    bars: Sequence[Bar],
    broksum_by_date: Optional[Dict[str, Dict[str, Any]]] = None,
    min_signal_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Scan chronological EOD bars for one ticker and emit signals for:
    - FRACTAL_BREAKOUT
    - MACD_EMA200
    - G_ACC
    """
    n = len(bars)
    if n < 6:
        return []

    closes = [b.close for b in bars]
    volumes = [b.volume for b in bars]
    ema21 = ema_series(closes, 21)
    ema50 = ema_series(closes, 50)
    ema200 = ema_series(closes, 200)
    _, _, hist = macd_series(closes, 12, 26, 9)
    atr14 = atr_series(bars, 14)
    rsi14 = rsi_series(closes, 14)
    st = supertrend_series(bars, 10, 3.0)
    vol_sma20 = sma_series(volumes, 20)
    fracs = fractal_levels(bars)

    emitted_fractal_ids: set[str] = set()
    signals: List[Dict[str, Any]] = []

    gamma_ref: Optional[float] = None

    broksum_map = broksum_by_date or {}

    for t in range(5, n):
        b = bars[t]
        prev = bars[t - 1]
        if not b.valid() or not prev.valid():
            continue

        dir_now = int(st[t]["direction"])
        old_dir = int(st[t - 1]["direction"]) if t > 0 else dir_now
        if dir_now == -1:
            gamma_ref = None

        # Pre-check date filter only for emitting (state must always warm up chronologically)
        emit_allowed = min_signal_date is None or b.date >= min_signal_date
        a14_t = atr14[t]
        v20_t = vol_sma20[t]
        rsi_t = rsi14[t]
        bs = broksum_map.get(b.date) or {}

        # Derive flow hint for G_ACC & regime (broksum preferred, fallback nbsa if pre-broksum)
        brok_label = str(bs.get("label") or "").upper()
        smart_net = float(bs.get("smart_money_net") or 0.0)
        bandar_cost = float(bs.get("bandar_avg_cost") or 0.0)
        gap_cost_pct = ((b.close - bandar_cost) / bandar_cost * 100.0) if bandar_cost > 0 else None

        acc_detected = (
            "ACCUMULATION" in brok_label
            or smart_net > 0
            or (not bs and b.nbsa > 0 and b.close >= b.open)
        )
        dist_detected = "DISTRIBUTION" in brok_label or smart_net < 0

        regime, regime_action = classify_stock_regime(
            b.close, ema21[t], ema50[t], acc_detected, dist_detected
        )

        # ------------------------------------------------------------------
        # RULE 1: FRACTAL_BREAKOUT (SOT FRACTAL_BREAKOUT_V1)
        # ------------------------------------------------------------------
        upper, lower = fracs[t]
        if upper is not None:
            fid, f_price, piv_date, avail_date = upper
            if prev.close <= f_price and b.close > f_price and fid not in emitted_fractal_ids:
                emitted_fractal_ids.add(fid)
                sl = lower[1] if lower is not None else None
                if emit_allowed and sl is not None and 0 < sl < b.close:
                    risk = b.close - sl
                    tp1 = round_idx_tick(b.close + 1.5 * risk)
                    tp2 = round_idx_tick(b.close + 2.0 * risk)
                    signals.append({
                        "date": b.date,
                        "ticker": ticker,
                        "signal_type": "FRACTAL_BREAKOUT",
                        "entry_price": b.close,
                        "stop_loss": sl,
                        "tp1": tp1,
                        "tp2": tp2,
                        "rr_tp1": round((tp1 - b.close) / risk, 2),
                        "rr_tp2": round((tp2 - b.close) / risk, 2),
                        "regime": regime,
                        "regime_action": regime_action,
                        "rule_checklist": {
                            "ceiling_price": f_price,
                            "ceiling_pivot_date": piv_date,
                            "ceiling_available_date": avail_date,
                            "prev_close_lte_ceiling": True,
                            "close_gt_ceiling": True,
                            "floor_sl": sl,
                        },
                        "notes": f"Close {b.close:g} menembus Fractal Ceiling {f_price:g} (pivot {piv_date}). SL di Floor {sl:g}.",
                        "_bar_index": t,
                    })

        # ------------------------------------------------------------------
        # RULE 2: MACD_EMA200 (SOT MACD_EMA200_V1 — requires min 600 bars)
        # ------------------------------------------------------------------
        if t >= 599 and b.close > ema200[t] and hist[t - 1] <= 0.0 < hist[t]:
            sl = swing_low_stop(bars, t, lookback=60)
            if emit_allowed and sl is not None and 0 < sl < b.close:
                risk = b.close - sl
                tp1 = round_idx_tick(b.close + 1.5 * risk)
                tp2 = round_idx_tick(b.close + 2.0 * risk)
                signals.append({
                    "date": b.date,
                    "ticker": ticker,
                    "signal_type": "MACD_EMA200",
                    "entry_price": b.close,
                    "stop_loss": sl,
                    "tp1": tp1,
                    "tp2": tp2,
                    "rr_tp1": round((tp1 - b.close) / risk, 2),
                    "rr_tp2": round((tp2 - b.close) / risk, 2),
                    "regime": regime,
                    "regime_action": regime_action,
                    "rule_checklist": {
                        "min_history_600": True,
                        "close_above_ema200": True,
                        "ema200": round(ema200[t], 2),
                        "histogram_prev": round(hist[t - 1], 4),
                        "histogram_now": round(hist[t], 4),
                        "swing_low_sl": sl,
                    },
                    "notes": f"Close {b.close:g} > EMA200 ({ema200[t]:.1f}) & MACD Histogram cross positif ({hist[t - 1]:.2f} -> {hist[t]:.2f}).",
                    "_bar_index": t,
                })

        # ------------------------------------------------------------------
        # RULE 3: G_ACC / G ACCUMULATION (Low-Base Accumulation + Continuation)
        # ------------------------------------------------------------------
        if t >= 199 and v20_t and v20_t > 0 and rsi_t is not None and a14_t and a14_t > 0:
            range_150 = bars[max(0, t - 149) : t + 1]
            hh150 = max(x.high for x in range_150)
            ll150 = min(x.low for x in range_150)
            range_span = max(1e-9, hh150 - ll150)
            pos_150 = (b.close - ll150) / range_span

            body = abs(b.close - b.open)
            span = b.high - b.low
            upper_wick = b.high - b.close
            green = b.close > b.open
            vol_expand = b.volume > v20_t * 1.2
            rsi_ok = rsi_t > 50.0
            flip_up = dir_now == 1 and old_dir == -1
            premium = b.close >= (hh150 + ll150) / 2.0
            candle_ok = green and body > span * 0.4 and upper_wick < body

            beta = flip_up and rsi_ok and premium and vol_expand and candle_ok
            gamma = (
                b.close > ema200[t]
                and b.close > ema50[t]
                and vol_expand
                and dir_now == 1
                and body > span * 0.5
                and upper_wick < body * 0.4
                and rsi_ok
                and rsi_t < 90.0
                and not beta
            )

            # G_ACC: Akumulasi terdeteksi & harga masih rendah (atau MaX gamma continuation di area wajar)
            low_price_zone = pos_150 <= 0.45 or (gap_cost_pct is not None and -5.0 <= gap_cost_pct <= 4.0)
            g_acc_low_base = (
                low_price_zone
                and acc_detected
                and 35.0 <= rsi_t <= 68.0
                and b.volume >= v20_t * 1.15
                and b.close >= b.open
            )
            g_acc_max = gamma and gamma_ref is not None and b.close > gamma_ref
            if gamma:
                gamma_ref = b.close

            # Standard low anchor for ATR-based stop & R:R TP1 / TP2
            anchor_low = min(x.low for x in bars[max(0, t - 4) : t + 1])
            sl_atr = round_idx_tick(anchor_low - 0.25 * a14_t, direction="down")

            if emit_allowed and sl_atr > 0 and sl_atr < b.close and (g_acc_low_base or g_acc_max):
                risk_atr = b.close - sl_atr
                tp1_atr = round_idx_tick(b.close + 1.5 * risk_atr)
                tp2_atr = round_idx_tick(b.close + 2.5 * risk_atr)
                signals.append({
                    "date": b.date,
                    "ticker": ticker,
                    "signal_type": "G_ACC",
                    "entry_price": b.close,
                    "stop_loss": sl_atr,
                    "tp1": tp1_atr,
                    "tp2": tp2_atr,
                    "rr_tp1": round((tp1_atr - b.close) / risk_atr, 2),
                    "rr_tp2": round((tp2_atr - b.close) / risk_atr, 2),
                    "regime": regime,
                    "regime_action": regime_action,
                    "rule_checklist": {
                        "low_price_zone": low_price_zone,
                        "pos_range_150_pct": round(pos_150 * 100, 1),
                        "bandar_cost_gap_pct": round(gap_cost_pct, 2) if gap_cost_pct is not None else None,
                        "accumulation_detected": acc_detected,
                        "rsi14": round(rsi_t, 2),
                        "rvol": round(b.volume / v20_t, 2),
                    },
                    "notes": f"Akumulasi terdeteksi pada area harga rendah (posisi range 150H: {pos_150*100:.0f}%, RSI {rsi_t:.1f}, Vol {b.volume/v20_t:.1f}x).",
                    "_bar_index": t,
                })

    # Evaluate forward outcomes for every emitted signal using subsequent bars
    for sig in signals:
        t_idx = int(sig.pop("_bar_index"))
        outcomes = evaluate_signal_outcomes(
            entry_price=sig["entry_price"],
            stop_loss=sig["stop_loss"],
            tp1=sig["tp1"],
            tp2=sig["tp2"],
            future_bars=bars[t_idx + 1 :],
        )
        sig.update(outcomes)
        sig["evaluated_until_date"] = bars[-1].date

    return signals
