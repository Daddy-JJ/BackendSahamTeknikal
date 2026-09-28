from datetime import UTC, date, datetime, timedelta

import pytest

from idx_scanner.context import Calendar, Session
from idx_scanner.models import Bar, Candidate, Rule, Signal


@pytest.fixture
def calendar():
    # Friday -> Tuesday: Monday is an explicit synthetic holiday.
    days = [date(2026, 1, 2), date(2026, 1, 6), date(2026, 1, 7), date(2026, 1, 8)]
    return Calendar(
        tuple(
            Session(
                d,
                datetime(d.year, d.month, d.day, 2, tzinfo=UTC),
                datetime(d.year, d.month, d.day, 9, tzinfo=UTC),
            )
            for d in days
        ),
        "test-v1",
        "synthetic://calendar",
        "fixture",
    )


@pytest.fixture
def signal(calendar):
    candidate = Candidate(
        "FRACTAL_BREAKOUT_V1", True, 95, 101, (Rule("close_above_level", True),), "eligible", 100
    )
    return Signal(
        "s1",
        "TEST",
        calendar.sessions[0].day,
        candidate,
        "config",
        "input",
        "universe",
        "fixture",
        "test",
        calendar.sessions[0].closes_at + timedelta(hours=3),
        calendar.sessions[1].day,
        "forward",
        "fixture",
    )


def bar(day, o=100, h=104, low=96, c=102, volume=1000):
    return Bar(day, o, h, low, c, volume)
