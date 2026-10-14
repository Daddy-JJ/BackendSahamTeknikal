"""Immutable chart projection from exact persisted inputs; no provider IO or economics."""

import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from math import isfinite
from uuid import UUID
from zoneinfo import ZoneInfo

from .chart_overlays import build_overlays
from .context import Calendar, cash_dividends_are_metadata_only
from .indicators import calculate, sma
from .models import Series, digest
from .untradable import VerifiedUntradable, require_nontrading_source

INDICATOR_VERSION = "sot-v1-full-history-chart-v1"
INDICATOR_KEYS = ("sma10", "ema200", "macd", "macd_signal", "macd_histogram")


@dataclass(frozen=True)
class ChartReceipt:
    series_id: str
    namespace: str
    data_mode: str
    series: Series
    stored_at: datetime

    def __post_init__(self):
        if (str(UUID(self.series_id)) != self.series_id
            or not re.fullmatch(r"[a-z0-9_-]{1,64}", self.namespace)
            or self.data_mode not in ("fixture", "live")
            or self.stored_at.tzinfo is None
            or self.series.fetched_at is None or self.series.fetched_at.tzinfo is None):
            raise ValueError("invalid_chart_receipt")


def cutoff_series(series: Series, cutoff: date) -> Series:
    """Matches engine.scan input cropping, including action reconciliation order."""
    return replace(
        series,
        bars=tuple(b for b in series.bars if b.session <= cutoff),
        actions=tuple(a for a in series.actions if a.session <= cutoff),
        provider_row_issues=tuple(i for i in series.provider_row_issues if i.session <= cutoff),
        provider_missing_sessions=tuple(d for d in series.provider_missing_sessions if d <= cutoff),
        reconciled_actions=tuple(digest(a) for a in series.actions
                                 if a.session <= cutoff and digest(a) in series.reconciled_actions),
    )


def source_scope(series: Series, namespace: str) -> str:
    if series.provider == "fixture":
        return "fixture"
    provenance = tuple(json.loads(p) for p in series.provenance)
    if namespace.startswith("paper") or any(
        p.get("kind") == "reviewed_historical_backfill_v1" for p in provenance
    ):
        return "paper_recovery"
    if namespace != "forward":
        raise ValueError("chart_source_scope_unavailable")
    return "forward"


def resolve_signal_receipt(receipts, signal: dict) -> ChartReceipt:
    cutoff = date.fromisoformat(signal["session"])
    for receipt in sorted(receipts, key=lambda r: (r.stored_at, r.series_id)):
        series = receipt.series
        if (series.ticker == signal["ticker"] and series.provider == signal["provider"]
            and series.price_basis == signal["price_basis"]
            and series.provider_version == signal["provider_version"]
            and receipt.data_mode == signal["data_mode"]
            and source_scope(series, receipt.namespace) != "paper_recovery"
            and cutoff_series(series, cutoff).input_digest == signal["input_digest"]):
            return receipt
    raise ValueError("snapshot_unavailable")


def decimal_string(value) -> str:
    if isinstance(value, bool):
        raise ValueError("invalid_chart_number")
    number = Decimal(str(value))
    if (not number.is_finite() or number <= 0 or number > Decimal(2**53 - 1)
        or not isfinite(float(number))):
        raise ValueError("invalid_chart_number")
    return format(number, "f")


def source_reference(receipt: ChartReceipt, resolved: Series, cutoff: date) -> dict:
    if not resolved.bars or receipt.series.fetched_at is None:
        raise ValueError("chart_source_unavailable")
    return {"series_id": receipt.series_id, "input_digest": receipt.series.input_digest,
            "resolved_input_digest": resolved.input_digest, "resolved_cutoff": str(cutoff),
            "provider": resolved.provider, "provider_version": resolved.provider_version,
            "price_basis": resolved.price_basis,
            "scope": source_scope(resolved, receipt.namespace),
            "fetched_at": receipt.series.fetched_at.astimezone(UTC).isoformat(),
            "stored_at": receipt.stored_at.astimezone(UTC).isoformat(),
            "history_start": str(resolved.bars[0].session),
            "last_market_session": str(resolved.bars[-1].session)}


def chart_cutoff(calendar: Calendar, observed_at: datetime):
    if observed_at.tzinfo is None:
        raise ValueError("chart_observation_timezone_required")
    closed = tuple(s.day for s in calendar.sessions if s.closes_at <= observed_at)
    if not closed:
        if not calendar.historical_days:
            raise ValueError("calendar_unavailable")
        return calendar.historical_days[-1], None
    cutoff = closed[-1]
    # An expired calendar cannot attest to today's expected market session.
    known = observed_at.astimezone(ZoneInfo("Asia/Jakarta")).date()
    return cutoff, cutoff if known <= calendar.sessions[-1].day else None


def _bar_payload(bar):
    if (isinstance(bar.volume, bool) or int(bar.volume) != bar.volume
        or bar.volume > 2**53 - 1):
        raise ValueError("invalid_chart_volume")
    return {"session": str(bar.session), **{key: decimal_string(getattr(bar, key))
            for key in ("open", "high", "low", "close")}, "volume": str(int(bar.volume))}


def _market_projection(series, sessions, evidence, observed_at, mode):
    excluded = {p.session for p in evidence if p.ticker == series.ticker
                and p.data_mode == mode and p.verified_at <= observed_at}
    if any(p.data_mode != mode for p in evidence):
        raise ValueError("chart_mode_mismatch")
    require_nontrading_source(series, excluded)
    raw = {bar.session: bar for bar in series.bars}
    if len(raw) != len(series.bars) or list(raw) != sorted(raw):
        raise ValueError("invalid_chart_sessions")
    action_hold = tuple(a.session for a in series.actions
                        if digest(a) not in series.reconciled_actions
                        and not (a.kind == "dividend" and cash_dividends_are_metadata_only(series)))
    issues = {issue.session for issue in series.provider_row_issues}
    recent = {bar.session for bar in series.bars[-60:]}
    gaps, bars, valid, prefix = [], [], [], True
    for day in sessions:
        bar = raw.get(day)
        reason = ("verified_untradable" if day in excluded else
                  "corporate_action_hold" if any(a <= day for a in action_hold) else
                  "data_quality_hold" if day in issues else
                  "missing_bar" if bar is None else
                  "invalid_ohlcv" if not bar.valid() else
                  "zero_volume" if bar.volume == 0 and day in recent else None)
        if reason:
            gaps.append({"session": str(day), "reason": reason})
            if reason != "verified_untradable":
                prefix = False
        else:
            bars.append(_bar_payload(bar))
            if prefix:
                valid.append(bar)
    return bars, gaps, tuple(valid)


def _indicators(history, sessions, *, actions_complete=True):
    if not actions_complete:
        return {name: {"status": "unavailable", "reason": "corporate_actions_unknown",
                       "definition_version": INDICATOR_VERSION, "artifact_digest": None,
                       "history_count": len(history), "eligible_from": None, "points": []}
                for name in INDICATOR_KEYS}
    features = calculate(history) if history else None
    values = {"sma10": sma([b.close for b in history], 10),
              "ema200": features.ema200 if features else (),
              "macd": features.macd if features else (),
              "macd_signal": features.signal if features else (),
              "macd_histogram": features.histogram if features else ()}
    result = {}
    for name in INDICATOR_KEYS:
        points = dict(zip((b.session for b in history), values[name], strict=True))
        minimum = 10 if name == "sma10" else 600
        result[name] = {"status": "ready" if history else "unavailable",
                        "reason": (None if len(history) >= minimum else
                                   "insufficient_history" if history else "history_unavailable"),
                        "definition_version": INDICATOR_VERSION,
                        "artifact_digest": digest((INDICATOR_VERSION, name, history)) if history
                        else None, "history_count": len(history),
                        "eligible_from": str(history[minimum - 1].session)
                        if len(history) >= minimum else None,
                        "points": [{"session": str(day), "value": points.get(day)}
                                   for day in sessions] if history else []}
    return result


def build_chart_artifact(receipt: ChartReceipt, calendar: Calendar, *, observed_at: datetime,
                         kind="latest", context_id=None, view="followup", signal=None,
                         signal_receipt=None, paper=None, actual=None, fills=(), stops=(),
                         evidence: tuple[VerifiedUntradable, ...] = ()) -> dict:
    """Full-history artifact; SQL reader crops immutable revision to bounded pages."""
    if (receipt.data_mode != calendar.data_mode
        or (receipt.series.provider == "fixture") != (receipt.data_mode == "fixture")):
        raise ValueError("chart_mode_mismatch")
    if (kind not in ("latest", "signal", "paper", "actual")
        or view not in ("snapshot", "followup") or (kind == "latest") != (context_id is None)
        or kind in ("signal", "paper") and signal is None
        or kind == "actual" and view == "snapshot"
        or kind == "latest" and view == "snapshot"):
        raise ValueError("invalid_chart_context")
    cutoff, expected = chart_cutoff(calendar, observed_at)
    if view == "snapshot":
        signal_cutoff = date.fromisoformat(signal["session"])
        if signal_cutoff > cutoff:
            raise ValueError("invalid_chart_context")
        cutoff = signal_cutoff
        expected = cutoff
    resolved = cutoff_series(receipt.series, cutoff)
    # Scanner snapshot recurrence must match its original source; later paper
    # reviews cannot retroactively remove bars from that immutable input.
    evidence = () if view == "snapshot" else evidence
    if not resolved.bars:
        raise ValueError("chart_source_unavailable")
    all_days = calendar.historical_days + tuple(s.day for s in calendar.sessions)
    if resolved.bars[0].session not in all_days or cutoff not in all_days:
        raise ValueError("calendar_unavailable")
    sessions = tuple(d for d in all_days if resolved.bars[0].session <= d <= cutoff)
    if any(b.session not in sessions for b in resolved.bars):
        raise ValueError("chart_nonmarket_bar")
    bars, gaps, history = _market_projection(resolved, sessions, evidence,
                                             observed_at, receipt.data_mode)
    if not bars:
        raise ValueError("chart_source_unavailable")
    source = {**source_reference(receipt, resolved, cutoff),
              "last_market_session": bars[-1]["session"]}
    original = signal_receipt or (receipt if signal and view == "snapshot" else None)
    signal_source = (source_reference(original, cutoff_series(original.series,
                     date.fromisoformat(signal["session"])), date.fromisoformat(signal["session"]))
                     if signal and original else None)
    if signal and (signal_source is None or
                   signal_source["resolved_input_digest"] != signal["input_digest"]):
        raise ValueError("snapshot_unavailable")
    overlays = build_overlays(kind=kind, view=view, cutoff=cutoff, source=source,
                              signal_source=signal_source, signal=signal, paper=paper,
                              actual=actual, fills=fills, stops=stops, calendar=calendar,
                              receipt_series=resolved, evidence=evidence)
    warnings = [] if expected else ["calendar_current_unknown"]
    reasons = sorted({g["reason"] for g in gaps})
    if not resolved.actions_complete:
        reasons.append("corporate_actions_unknown")
    freshness = ("unknown" if expected is None else "current"
                 if source["last_market_session"] == str(expected) else "stale")
    data = {"ticker": resolved.ticker, "data_mode": receipt.data_mode, "timeframe": "1d",
            "exchange": "XIDX", "timezone": "Asia/Jakarta", "currency": "IDR",
            "volume_unit": "shares", "context": {"kind": kind, "id": context_id,
            "view": view, "signal_session": signal["session"] if signal else None,
            "snapshot_cutoff": str(cutoff) if view == "snapshot" else None,
            "model_version": paper.get("experiment", {}).get("model_version") if paper else None,
            "experiment": paper.get("experiment", {}).get("id") if paper else None,
            "engine_source_revision": signal.get("source_revision") if signal else None},
            "source": source, "signal_source": signal_source,
            "quality": {"completeness": "partial" if reasons else "complete",
                        "freshness": freshness,
                        "expected_session": str(expected) if expected else None,
                        "reasons": reasons[:20], "warnings": warnings},
            "sessions": [str(d) for d in sessions], "bars": bars, "gaps": gaps,
            "indicators": _indicators(history, sessions,
                                      actions_complete=resolved.actions_complete),
            "overlays": overlays}
    return {**data, "revision": digest((INDICATOR_VERSION, data))}
