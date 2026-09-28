"""Synthetic only. Weekday fixture calendar is NOT an official IDX calendar."""

from datetime import UTC, date, datetime, time, timedelta
from math import sin

from .context import Calendar, Session, Universe
from .models import Bar, Series


def sample_market(count: int = 660) -> tuple[dict[str, Series], Calendar, Universe]:
    days, cursor = [], date(2024, 1, 2)
    while len(days) < count + 5:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    calendar = Calendar(
        tuple(
            Session(d, datetime.combine(d, time(2), UTC), datetime.combine(d, time(9), UTC))
            for d in days
        ),
        "SYNTHETIC-WEEKDAYS-v1",
        "synthetic://fixture-calendar",
        "fixture",
    )
    result = {}
    for k, ticker in enumerate(("DEMO-A", "DEMO-B", "DEMO-C", "DEMO-D", "DEMO-E")):
        bars = []
        for i, day in enumerate(days[:count]):
            close = round(
                1000 + k * 700 + i * (0.8 + k * 0.12) + 50 * sin(i / 8 + k) + 15 * sin(i / 2.8), 4
            )
            if i in (617 + k * 3, 640 + k * 2):
                close -= 150  # Synthetic stress candles, not market events.
            if i == count - 1 and k == 0:
                close += 150
            op = round(close + 8 * sin(i / 4), 4)
            bars.append(
                Bar(
                    day,
                    op,
                    round(max(op, close) + 15, 4),
                    round(min(op, close) - 15, 4),
                    close,
                    1000000 + (i % 12) * 100000,
                )
            )
        result[ticker] = Series(ticker, ticker, "fixture", "synthetic_ohlcv_v1", tuple(bars))
    universe = Universe(
        tuple(result),
        "SYNTHETIC-5-v1",
        days[0],
        days[-1] + timedelta(days=1),
        "synthetic://not-kompas100",
        "fixture",
    )
    return result, calendar, universe
