"""Closed-trade R metrics. No portfolio-return claims, no guessed zero denominators."""

from collections.abc import Sequence
from decimal import Decimal


def summarize(values: Sequence[Decimal], *, open_count: int = 0, ambiguous_count: int = 0) -> dict:
    if any(not v.is_finite() for v in values):
        raise ValueError("nonfinite realized R")
    zero = Decimal(0)
    wins, losses = [v for v in values if v > 0], [v for v in values if v < 0]
    positive, negative = sum(wins, zero), -sum(losses, zero)
    peak = cumulative = drawdown = zero
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return {
        "basis": "R",
        "closed": len(values),
        "open": open_count,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": values.count(zero),
        "win_rate": Decimal(len(wins)) / len(values) if values else None,
        "expectancy_r": sum(values, zero) / len(values) if values else None,
        "profit_factor": positive / negative if losses else None,
        "payoff_ratio": (positive / len(wins)) / (negative / len(losses))
        if wins and losses
        else None,
        "profit_factor_status": "defined" if losses else "no_losses" if values else "no_closed",
        "cumulative_closed_r": cumulative,
        "drawdown_closed_r": drawdown,
        "ambiguous_count": ambiguous_count,
    }
