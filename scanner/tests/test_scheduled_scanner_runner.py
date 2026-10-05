"""Regression test for scheduled scanner runner contracts and pre-market window."""

import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Add backend and supabase/scripts to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from scheduled_scanner_runner import get_current_target_session  # noqa: E402

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
    """Prove night execution (e.g. 20:17 WIB) selects today's closed session."""
    series, calendar, universe = sample_market(20)
    s0 = calendar.sessions[0]

    # Time at 20:17 WIB on session 0 day (after s0.closes_at)
    night_wib = datetime(s0.day.year, s0.day.month, s0.day.day, 20, 17, tzinfo=WIB)
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
