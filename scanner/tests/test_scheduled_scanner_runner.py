import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Add backend and supabase/scripts to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from scheduled_scanner_runner import (  # noqa: E402
    get_current_target_session,
    latest_closed_session,
)

from idx_scanner.fixtures import sample_market  # noqa: E402
from idx_scanner.pipeline import PipelineResult  # noqa: E402

WIB = ZoneInfo("Asia/Jakarta")


def test_pipeline_result_contract_has_provider_errors():
    """Prove PipelineResult defines provider_errors rather than errors."""
    series, calendar, universe = sample_market(10)
    # Instantiate PipelineResult dummy to verify contract
    pipeline = PipelineResult(
        scan=None,  # type: ignore[arg-type]
        provider_errors=(("DEMO-A", "provider_rate_limited"),),
        fetched=("DEMO-A",),
        fetched_series=(),
        prepared_series=(),
    )
    assert hasattr(pipeline, "provider_errors")
    assert not hasattr(pipeline, "errors")
    # Verify extraction logic used in scheduled_scanner_runner
    extracted = [{"ticker": t, "code": c} for t, c in pipeline.provider_errors]
    assert extracted == [{"ticker": "DEMO-A", "code": "provider_rate_limited"}]


def test_get_current_target_session_pre_market_window():
    """Prove morning execution (e.g. 06:30 WIB) selects previous closed session."""
    series, calendar, universe = sample_market(20)
    # Session 0: day 0. Session 1: day 1.
    s0 = calendar.sessions[0]
    s1 = calendar.sessions[1]

    # Time at 06:30 WIB on session 1 day (before s1.opens_at)
    morning_wib = datetime(s1.day.year, s1.day.month, s1.day.day, 6, 30, tzinfo=WIB)
    morning_utc = morning_wib.astimezone(UTC)

    target, tradable, reason = get_current_target_session(calendar, morning_utc)
    assert target == s0.day
    assert tradable is True
    assert reason == "eligible"


def test_get_current_target_session_night_window():
    """Prove night execution (e.g. 18:18 WIB) selects today's closed session."""
    series, calendar, universe = sample_market(20)
    s0 = calendar.sessions[0]

    # Time at 18:18 WIB on session 0 day (after s0.closes_at)
    night_wib = datetime(s0.day.year, s0.day.month, s0.day.day, 18, 18, tzinfo=WIB)
    night_utc = night_wib.astimezone(UTC)

    target, tradable, reason = get_current_target_session(calendar, night_utc)
    assert target == s0.day
    assert tradable is True
    assert reason == "eligible"


def test_get_current_target_session_intraday_not_closed():
    """Prove intraday execution while market is open rejects target."""
    series, calendar, universe = sample_market(20)
    s0 = calendar.sessions[0]

    # Time at 11:00 WIB on session 0 day (between opens_at and closes_at)
    intraday_wib = datetime(s0.day.year, s0.day.month, s0.day.day, 11, 0, tzinfo=WIB)
    intraday_utc = intraday_wib.astimezone(UTC)

    target, tradable, reason = get_current_target_session(calendar, intraday_utc)
    assert target == s0.day
    assert tradable is False
    assert reason == "target_session_not_closed"


def test_friday_delayed_to_saturday_keeps_forward_window():
    _, calendar, _ = sample_market(30)
    friday = next(s for s in calendar.sessions if s.day.weekday() == 4)
    saturday = datetime.combine(friday.day, datetime.min.time(), WIB)
    from datetime import timedelta
    saturday += timedelta(days=1, hours=22)
    assert get_current_target_session(calendar, saturday.astimezone(UTC)) == (
        friday.day, True, "eligible")
    assert latest_closed_session(calendar, saturday.astimezone(UTC)) == friday.day


def test_explicit_exchange_holiday_recovers_previous_closed_session():
    _, calendar, _ = sample_market(30)
    closed = calendar.sessions[2]
    holiday_calendar = replace(calendar,
        sessions=tuple(s for s in calendar.sessions if s != closed), closed_days=(closed.day,))
    now = datetime.combine(closed.day, datetime.min.time(), WIB).replace(hour=18)
    assert get_current_target_session(holiday_calendar, now.astimezone(UTC)) == (
        calendar.sessions[1].day, True, "eligible")


def test_unknown_calendar_range_does_not_guess_closed_session():
    import pytest
    _, calendar, _ = sample_market(30)
    with pytest.raises(ValueError, match="calendar_unknown"):
        latest_closed_session(calendar, datetime(2099, 1, 1, tzinfo=UTC))


def test_intraday_recovery_target_is_previous_closed_session():
    _, calendar, _ = sample_market(30)
    current = calendar.sessions[1]
    assert latest_closed_session(calendar, current.opens_at) == calendar.sessions[0].day
