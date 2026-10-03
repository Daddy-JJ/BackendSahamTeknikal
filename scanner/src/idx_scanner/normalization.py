"""Source-backed closed-session exclusion. Never repair or synthesize a price."""

from dataclasses import replace
from datetime import date

from .context import Calendar
from .models import Series, canonical_json, digest

NORMALIZATION_VERSION = "explicit_closed_sessions_v1"


def normalize_closed_sessions(series: Series, calendar: Calendar, target: date) -> Series:
    calendar.get(target)
    if any(b.session > target for b in series.bars):
        raise ValueError("normalization_future_bars")
    if (series.provider == "fixture") != (calendar.data_mode == "fixture"):
        raise ValueError("mixed_fixture_live_normalization")
    days = [b.session for b in series.bars]
    if days != sorted(set(days)):
        return series  # Do not hide a duplicate/out-of-order provider receipt.
    closed = {d for d in calendar.closed_days if d <= target}
    removed = tuple(
        b
        for b in series.bars
        if b.session in closed
        and b.valid()
        and b.volume == 0
        and b.open == b.high == b.low == b.close
    )
    removed_issues = tuple(
        i
        for i in series.provider_row_issues
        if i.session in closed
        and i.code == "missing_ohlcv"
        and all(
            dict(i.observed_values).get(k, "unknown") is None
            for k in ("open", "high", "low", "close")
        )
        and dict(i.observed_values).get("volume") in (None, 0)
    )
    removed_missing = tuple(d for d in series.provider_missing_sessions if d in closed)
    if not (removed or removed_issues or removed_missing):
        return series
    record = canonical_json(
        {
            "kind": NORMALIZATION_VERSION,
            "source_input_digest": series.input_digest,
            "calendar_version": calendar.version,
            "calendar_source": calendar.source,
            "calendar_digest": digest(calendar),
            "reason": "explicit_exchange_closed_day_not_a_trading_bar",
            "excluded_bars": removed,
            "excluded_issues": removed_issues,
            "excluded_missing_sessions": removed_missing,
        }
    )
    return replace(
        series,
        bars=tuple(b for b in series.bars if b not in removed),
        provider_row_issues=tuple(i for i in series.provider_row_issues if i not in removed_issues),
        provider_missing_sessions=tuple(
            d for d in series.provider_missing_sessions if d not in removed_missing
        ),
        provenance=series.provenance + (record,),
    )
