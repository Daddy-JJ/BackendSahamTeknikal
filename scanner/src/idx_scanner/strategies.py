"""Pure entry evaluation. Trading rules are project additions; see SOT.md."""

from dataclasses import dataclass
from math import ceil

from .fractal import Level, levels
from .indicators import Features
from .models import DEFAULT_ENTRY_CONFIG, Bar, Candidate, EntryConfig, Rule

STRATEGIES = ("MACD_EMA200_V1", "FRACTAL_BREAKOUT_V1", "RS_BREAKOUT_V1", "PULLBACK_RECLAIM_V1")


@dataclass(frozen=True)
class Ranking:
    status: str
    ordered: tuple[tuple[str, float], ...]
    excluded: tuple[str, ...]
    input_digest: str

    @property
    def top(self) -> frozenset[str]:
        return frozenset(t for t, _ in self.ordered[: ceil(0.20 * len(self.ordered))])


def rank_returns(
    returns: dict[str, float],
    expected: tuple[str, ...],
    excluded: tuple[str, ...],
    input_digest: str,
) -> Ranking:
    if set(returns) | set(excluded) != set(expected) or set(returns) & set(excluded):
        return Ranking("cross_section_incomplete", (), excluded, input_digest)
    ordered = tuple(sorted(returns.items(), key=lambda pair: (-pair[1], pair[0])))
    return Ranking("complete", ordered, tuple(sorted(excluded)), input_digest)


def swing_stop(bars: tuple[Bar, ...], config: EntryConfig) -> float | None:
    t = len(bars) - 1
    for j in range(t - 2, max(2, t - config.swing_lookback) - 1, -1):
        if all(bars[j].low <= bars[k].low for k in (j - 2, j - 1, j + 1, j + 2)):
            return bars[j].low
    return None


def _candidate(
    strategy: str,
    close: float,
    stop: float | None,
    rules: dict[str, bool],
    level: float | None = None,
    fractal: Level | None = None,
) -> Candidate:
    triggered = all(rules.values())
    reason = (
        "no_signal"
        if not triggered
        else "missing_stop"
        if stop is None
        else "stop_invalid"
        if not 0 < stop < close
        else "eligible"
    )
    return Candidate(
        strategy,
        triggered,
        stop,
        close,
        tuple(Rule(k, v) for k, v in rules.items()),
        reason,
        level,
        fractal.id if fractal else None,
        fractal.pivot_date if fractal else None,
        fractal.available_session if fractal else None,
    )


def evaluate(
    ticker: str,
    bars: tuple[Bar, ...],
    f: Features,
    ranking: Ranking,
    config: EntryConfig = DEFAULT_ENTRY_CONFIG,
) -> tuple[Candidate, ...]:
    c, prev = bars[-1].close, bars[-2].close if len(bars) > 1 else bars[-1].close
    enough = len(bars) >= config.min_history
    upper, lower = levels(bars)[-1]
    fractal = _candidate(
        STRATEGIES[1],
        c,
        lower.price if lower else None,
        {
            "level_available": upper is not None,
            "previous_close_at_or_below_level": upper is not None and prev <= upper.price,
            "close_above_level": upper is not None and c > upper.price,
        },
        upper.price if upper else None,
        upper,
    )
    result = [fractal]
    if not enough:
        return tuple(
            result
            + [
                Candidate(s, False, None, c, (), "insufficient_history")
                for s in STRATEGIES
                if s != STRATEGIES[1]
            ]
        )
    result.append(
        _candidate(
            STRATEGIES[0],
            c,
            swing_stop(bars, config),
            {
                "close_above_ema200": c > f.ema200[-1],
                "bullish_macd_crossover": f.histogram[-2] <= 0 < f.histogram[-1],
            },
        )
    )
    atr14 = f.atr14[-1]
    assert atr14 is not None
    trend = c > f.ema50[-1] > f.ema200[-1]
    threshold = max(b.high for b in bars[-21:-1])
    if ranking.status != "complete":
        result.append(Candidate(STRATEGIES[2], False, None, c, (), "cross_section_incomplete"))
    else:
        result.append(
            _candidate(
                STRATEGIES[2],
                c,
                min(b.low for b in bars[-5:]) - 0.25 * atr14,
                {
                    "trend_above_ema50_ema200": trend,
                    "rs_top_20_percent": ticker in ranking.top,
                    "close_breaks_prior20_high": c > threshold,
                },
                threshold,
            )
        )
    result.append(
        _candidate(
            STRATEGIES[3],
            c,
            min(b.low for b in bars[-4:]) - 0.25 * atr14,
            {
                "trend_above_ema50_ema200": trend,
                "prior3_pullback_below_ema20": any(
                    bars[j].close < f.ema20[j] for j in (-4, -3, -2)
                ),
                "prior3_hold_above_ema50": all(bars[j].close > f.ema50[j] for j in (-4, -3, -2)),
                "previous_close_at_or_below_ema20": prev <= f.ema20[-2],
                "strict_ema20_reclaim": c > f.ema20[-1],
                "close_above_previous_high": c > bars[-2].high,
            },
            bars[-2].high,
        )
    )
    return tuple(result)
