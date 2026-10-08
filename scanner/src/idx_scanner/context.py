"""Explicit calendar and effective-dated universe. Weekdays are not an exchange calendar."""

from dataclasses import dataclass
from datetime import date, datetime

from .models import Series, digest

CASH_DIVIDEND_POLICY_VERSION = "cash_dividend_metadata_nonblocking_v1"


def cash_dividends_are_metadata_only(series: Series) -> bool:
    """Only the approved non-dividend-adjusted Yahoo basis has this exemption."""
    return (
        series.provider == "yfinance"
        and series.price_basis == "yahoo_provider_ohlcv_auto_adjust_false_v1"
    )


@dataclass(frozen=True)
class Session:
    day: date
    opens_at: datetime
    closes_at: datetime

    def __post_init__(self):
        if (
            self.opens_at.tzinfo is None
            or self.closes_at.tzinfo is None
            or self.opens_at >= self.closes_at
        ):
            raise ValueError("Timezone-aware open/close required")


@dataclass(frozen=True)
class Calendar:
    sessions: tuple[Session, ...]
    version: str
    source: str
    data_mode: str
    historical_days: tuple[date, ...] = ()
    closed_days: tuple[date, ...] = ()

    def __post_init__(self):
        days = [s.day for s in self.sessions]
        if not self.source or days != sorted(set(days)) or not days:
            raise ValueError("Ordered unique sessions with source required")
        if self.data_mode not in ("fixture", "live"):
            raise ValueError("Invalid calendar mode")
        if list(self.historical_days) != sorted(set(self.historical_days)) or any(
            day >= days[0] for day in self.historical_days
        ):
            raise ValueError("Historical date-only sessions must precede timed sessions")
        if list(self.closed_days) != sorted(set(self.closed_days)) or set(
            self.closed_days
        ).intersection(self.historical_days + tuple(days)):
            raise ValueError("Explicit closed days must be ordered, unique and disjoint from opens")

    def get(self, day: date) -> Session:
        for session in self.sessions:
            if session.day == day:
                return session
        raise ValueError("blocked_configuration: session unknown")

    def next(self, day: date) -> Session:
        self.get(day)
        for session in self.sessions:
            if session.day > day:
                return session
        raise ValueError("blocked_configuration: next session unknown")

    def between(self, start: date, end: date) -> tuple[date, ...]:
        self.get(end)
        days = self.historical_days + tuple(s.day for s in self.sessions)
        if start not in days:
            raise ValueError("blocked_configuration: history start session unknown")
        return tuple(day for day in days if start <= day <= end)


@dataclass(frozen=True)
class Universe:
    tickers: tuple[str, ...]
    version: str
    effective_from: date
    effective_to: date
    source: str
    data_mode: str

    def __post_init__(self):
        if (
            not self.tickers
            or len(set(self.tickers)) != len(self.tickers)
            or self.effective_to <= self.effective_from
            or not self.source
            or self.data_mode not in ("fixture", "live")
        ):
            raise ValueError("Invalid effective universe")

    def require(self, target: date):
        if not self.effective_from <= target < self.effective_to:
            raise ValueError("blocked_configuration: universe not effective")


def quality(series: Series, target: date, calendar: Calendar) -> str:
    bars = series.bars
    if any(
        i.code == "incomplete_ohlcv" and i.session <= target for i in series.provider_row_issues
    ):
        return "data_quality_hold"
    if not bars:
        return "missing"
    days = [b.session for b in bars]
    if days != sorted(set(days)):
        return "invalid_sessions"
    if days[-1] != target:
        return "stale" if days[-1] < target else "future_data"
    if any(not bar.valid() for bar in bars):
        return "invalid_ohlcv"
    if (
        any(b.session in calendar.closed_days for b in bars)
        or any(b.volume == 0 for b in bars[-60:])
    ):
        return "data_quality_hold"
    try:
        if tuple(days) != calendar.between(days[0], target):
            return "history_gap"
    except ValueError:
        return "calendar_unknown"
    known_open = {d for d in calendar.historical_days if d <= target} | {
        s.day for s in calendar.sessions if s.day <= target
    }
    if known_open.intersection(series.provider_missing_sessions):
        return "missing_session"
    if not series.actions_complete:
        return "corporate_actions_unknown"
    if any(
        digest(action) not in series.reconciled_actions
        for action in series.actions
        if action.session <= target
        and not (action.kind == "dividend" and cash_dividends_are_metadata_only(series))
    ):
        return "corporate_action_hold"
    return "valid"
