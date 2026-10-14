"""Canonical chart levels/events. Never infer fills or intraday ordering from candles."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from .indicators import ema, sma
from .models import ExitConfig, digest


def _price(value):
    number = Decimal(str(value))
    if not number.is_finite() or number <= 0:
        raise ValueError("invalid_chart_overlay_price")
    return format(number, "f")


def _day(value):
    return str(datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Jakarta")).date())


def _available(value, calendar):
    """Knowledge date moves to next attested session on non-session capture dates."""
    day = date.fromisoformat(_day(value))
    sessions = calendar.historical_days + tuple(s.day for s in calendar.sessions)
    return next((str(s) for s in sessions if s >= day), None)


def _level(key, kind, price, starts, available, source_id, *, origin=None, status="planned"):
    return {"id": key, "kind": kind, "price": _price(price), "starts_at": starts,
            "ends_at": None, "available_session": available, "origin_session": origin,
            "source_id": source_id, "status": status}


def _marker(key, kind, session, available, price, source_id, status):
    return {"id": key, "kind": kind, "session": session, "available_session": available,
            "price": _price(price) if price is not None else None,
            "source_id": source_id, "status": status}


def _signal(signal, paper):
    candidate = signal["candidate"]
    day, entry, key = signal["session"], signal["planned_entry_session"], signal["id"]
    levels = [_level(key + ":entry", "planned_entry", paper.get("planned_entry_price")
                     or candidate["reference_close"], entry, day, key)]
    if candidate.get("stop") is not None:
        levels.append(_level(key + ":stop", "initial_stop", candidate["stop"], entry, day, key))
    if paper.get("target") is not None:
        levels.append(_level(key + ":target", "target", paper["target"], entry, day, key))
    if candidate.get("level") is not None and candidate.get("available_session"):
        available = candidate["available_session"]
        levels.append(_level(key + ":fractal", "fractal", candidate["level"], available,
                              available, key, origin=candidate.get("pivot_date"),
                              status="effective"))
    markers = [_marker(key + ":signal", "signal", day, day, candidate["reference_close"],
                        key, "confirmed")]
    return levels, markers


def _ma_event_proven(event, paper, calendar, receipt_series, evidence):
    try:
        config = paper["experiment"]["exit"]
        policy = ExitConfig(mode=config["mode"], target_r=None, ma_type=config["ma_type"],
                            period=config["period"], version=config["version"])
        day = date.fromisoformat(event["session"])
        observed = datetime.fromisoformat(event["observed_at"])
        excluded = {p.session for p in evidence if p.ticker == receipt_series.ticker
                    and p.verified_at <= observed}
        history = tuple(b for b in receipt_series.bars if b.session <= day
                        and b.session not in excluded)
        expected = tuple(d for d in calendar.between(history[0].session, day)
                         if d not in excluded)
        if tuple(b.session for b in history) != expected or any(not b.valid() for b in history):
            return False
        values = sma([b.close for b in history], policy.period) if policy.ma_type == "SMA" else ema(
            [b.close for b in history], policy.period)
        return values[-1] is not None and digest((history[-1], values[-1], policy)) == event[
            "input_digest"]
    except (KeyError, ValueError, IndexError, TypeError):
        return False


def _paper_events(paper, cutoff, calendar, receipt_series, evidence):
    result, reasons = [], []
    bars = {str(b.session): b for b in receipt_series.bars}
    for index, event in enumerate(paper.get("events", [])):
        if event["kind"] not in ("entry", "pending_exit", "exit"):
            continue
        available = _available(event["observed_at"], calendar)
        if not available or available > cutoff or event["session"] > cutoff:
            continue
        proven = (_ma_event_proven(event, paper, calendar, receipt_series, evidence)
                  if event["kind"] == "pending_exit" else event["session"] in bars
                  and digest(bars[event["session"]]) == event.get("input_digest"))
        if not proven:
            reasons.append("event_basis_unverified")
            continue
        kind = {"entry": "entry_fill", "pending_exit": "ma_exit_trigger", "exit": "exit_fill"}[
            event["kind"]]
        ambiguous = event.get("alternate_price") is not None
        if ambiguous:
            kind = "ambiguous"
        result.append(_marker(paper["id"] + ":" + str(index), kind, event["session"],
                              available, None if ambiguous else event.get("price"), paper["id"],
                              "ambiguous" if ambiguous else "simulated"))
    return result, reasons


def _actual_events(actual, fills, stops, cutoff, calendar):
    levels, markers = [], []
    created = _available(actual["created_at"], calendar)
    if created and created <= cutoff:
        levels.append(_level(actual["id"] + ":initial", "initial_stop", actual["initial_stop"],
                              created, created, actual["id"], status="effective"))
    for fill in fills:
        day = _day(fill["filled_at"])
        availability = max(datetime.fromisoformat(fill["created_at"]), datetime.fromisoformat(
            fill.get("correction_created_at") or fill["created_at"]))
        available = _available(availability.isoformat(), calendar)
        if available and available <= cutoff and day <= cutoff:
            markers.append(_marker(fill["id"], "entry_fill" if fill["side"] == "buy"
                                    else "exit_fill", day, available, fill["price_idr"],
                                    actual["id"], "confirmed"))
    for event in stops:
        available = _available(event["occurred_at"], calendar)
        if available and available <= cutoff:
            levels.append(_level(event["id"], "current_stop", event["new_stop"], available,
                                  available, actual["id"], status="effective"))
    changes = [level for level in levels if level["kind"] == "current_stop"]
    times = {event["id"]: datetime.fromisoformat(event["occurred_at"]) for event in stops}
    replacements = {}
    for old in changes:
        later = [new for new in changes if times[new["id"]] > times[old["id"]]]
        if later:
            first = min(later, key=lambda new: times[new["id"]])
            replacements[old["id"]] = {**old, "ends_at": first["starts_at"], "status": "ended"}
    return [replacements.get(level["id"], level) for level in levels], markers


def build_overlays(*, kind, view, cutoff, source, signal_source, signal, paper, actual,
                   fills, stops, calendar, receipt_series, evidence=()):
    cutoff = str(cutoff)
    empty = {"status": "ready", "reason": None, "levels": [], "markers": [],
             "has_more": False, "next_cursor": None}
    if kind == "latest":
        return empty
    if signal_source and ((source["provider"], source["price_basis"]) !=
                          (signal_source["provider"], signal_source["price_basis"])):
        return {**empty, "status": "unavailable", "reason": "overlay_price_basis_mismatch"}
    if kind == "actual" and (not actual or actual.get("price_basis") != source["price_basis"]):
        return {**empty, "status": "unavailable", "reason": "actual_price_basis_unverified"}
    levels, markers = _signal(signal, paper or {}) if signal else ([], [])
    reasons = []
    if paper and view == "followup":
        events, reasons = _paper_events(paper, cutoff, calendar, receipt_series, evidence)
        markers += events
        entries = [event["session"] for event in events if event["kind"] == "entry_fill"]
        exits = [event["session"] for event in events
                 if event["kind"] in ("exit_fill", "ambiguous")]
        if entries:
            levels = [{**level, "status": "ended" if exits else "effective",
                       "ends_at": min(exits) if exits else None}
                      if level["kind"] in ("planned_entry", "initial_stop", "target") else level
                      for level in levels]
    if actual:
        actual_levels, actual_markers = _actual_events(actual, fills, stops, cutoff, calendar)
        levels += actual_levels
        markers += actual_markers
        instants = [datetime.fromisoformat(event["occurred_at"]) for event in stops]
        if len(instants) != len(set(instants)):
            reasons.append("stop_sequence_ambiguous")
    ordered_levels = sorted((level for level in levels if level["available_session"] <= cutoff),
                            key=lambda x: (x["available_session"], x["id"]))
    ordered_markers = sorted((m for m in markers if m["available_session"] <= cutoff
                              and m["session"] <= cutoff),
                             key=lambda x: (x["available_session"], x["id"]))
    return {**empty, "levels": ordered_levels, "markers": ordered_markers,
            "status": "partial" if reasons else "ready",
            "reason": reasons[0] if reasons else None}
