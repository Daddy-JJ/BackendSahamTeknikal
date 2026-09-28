"""Pure daily-bar exit policies. Decimal monetary values, chronological event ordering."""

from dataclasses import dataclass
from decimal import Decimal

from .models import Bar, ExitConfig


def money(value: float | str | Decimal) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Nonfinite money")
    return result


@dataclass(frozen=True)
class ExitDecision:
    kind: str  # hold, pending_ma, exit
    price: Decimal | None = None
    reason: str = ""
    alternate_price: Decimal | None = None


def evaluate_exit(
    bar: Bar,
    stop: Decimal,
    target: Decimal | None,
    config: ExitConfig,
    *,
    ma: float | None = None,
    pending_ma: bool = False,
    entry_day: bool = False,
) -> ExitDecision:
    if not bar.valid() or bar.volume == 0:
        return ExitDecision("hold", reason="data_quality_hold")
    o, h, low, c = (money(x) for x in (bar.open, bar.high, bar.low, bar.close))
    if not entry_day and o <= stop:
        return ExitDecision("exit", o, "stop_gap")
    if config.mode == "fixed_rr":
        if target is None:
            raise ValueError("fixed_rr target missing")
        if not entry_day and o >= target:
            return ExitDecision("exit", target, "target_gap_conservative")
        if low <= stop and h >= target:
            return ExitDecision("exit", stop, "ambiguous_both_hit", target)
        if low <= stop:
            return ExitDecision("exit", stop, "stop")
        if h >= target:
            return ExitDecision("exit", target, "target")
    else:
        if pending_ma and not entry_day:
            return ExitDecision("exit", o, "ma_breakdown")
        if low <= stop:
            return ExitDecision("exit", stop, "stop")
        if ma is None:
            return ExitDecision("hold", reason="ma_unavailable")
        if c < money(ma):
            return ExitDecision("pending_ma", reason="ma_close_below")
    return ExitDecision("hold")
