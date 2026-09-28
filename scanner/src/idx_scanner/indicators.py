"""SOT v1 indicators. Float64 recurrence, no rounding and no future input."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite

from .models import Bar


def _check(values: Sequence[float], period: int) -> None:
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise ValueError("period must be a positive integer")
    if any(not isfinite(v) for v in values):
        raise ValueError("nonfinite indicator input")


def ema(values: Sequence[float], period: int) -> tuple[float, ...]:
    _check(values, period)
    if not values:
        return ()
    result = [float(values[0])]
    alpha = 2.0 / (period + 1)
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return tuple(result)


def sma(values: Sequence[float], period: int) -> tuple[float | None, ...]:
    _check(values, period)
    return tuple(
        None if i < period - 1 else sum(values[i - period + 1 : i + 1]) / period
        for i in range(len(values))
    )


def atr(bars: Sequence[Bar], period: int = 14) -> tuple[float | None, ...]:
    _check([b.close for b in bars], period)
    if any(not b.valid() for b in bars):
        raise ValueError("invalid OHLCV")
    tr = [
        max(b.high - b.low, abs(b.high - bars[i - 1].close), abs(b.low - bars[i - 1].close))
        if i
        else b.high - b.low
        for i, b in enumerate(bars)
    ]
    result: list[float | None] = [None] * len(bars)
    if len(bars) >= period:
        current = sum(tr[:period]) / period
        result[period - 1] = current
        for i in range(period, len(bars)):
            current = ((period - 1) * current + tr[i]) / period
            result[i] = current
    return tuple(result)


@dataclass(frozen=True)
class Features:
    ema20: tuple[float, ...]
    ema50: tuple[float, ...]
    ema200: tuple[float, ...]
    macd: tuple[float, ...]
    signal: tuple[float, ...]
    histogram: tuple[float, ...]
    atr14: tuple[float | None, ...]

    def snapshot(self) -> tuple[tuple[str, float | None], ...]:
        return tuple((name, getattr(self, name)[-1]) for name in self.__dataclass_fields__)


def calculate(bars: Sequence[Bar]) -> Features:
    if not bars:
        raise ValueError("empty history")
    closes = [b.close for b in bars]
    fast, slow = ema(closes, 12), ema(closes, 26)
    macd = tuple(a - b for a, b in zip(fast, slow, strict=True))
    signal = ema(macd, 9)
    return Features(
        ema(closes, 20),
        ema(closes, 50),
        ema(closes, 200),
        macd,
        signal,
        tuple(a - b for a, b in zip(macd, signal, strict=True)),
        atr(bars),
    )
