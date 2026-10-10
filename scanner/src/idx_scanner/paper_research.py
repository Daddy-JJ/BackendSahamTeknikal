"""Independent signal observations; horizons never schedule trade exits."""

import copy
import json
from datetime import date, datetime
from decimal import Decimal

from .context import Calendar
from .exits import evaluate_exit, money
from .models import Bar, ExitConfig, Signal, canonical_json, digest
from .untradable import VerifiedUntradable, require_nontrading_bar

MODEL_VERSION = "close-signal-risk-v1"
RESULT_KEYS = ("target_1r", "target_2r", "net_5", "net_10")
UNRESOLVED = ("pending", "data_hold")


def create_evaluation(signal: Signal, provider_symbol: str = "") -> dict:
    if signal.cohort != "forward" or not signal.candidate.execution_eligible:
        raise ValueError("research_requires_valid_forward_signal")
    entry, stop = money(signal.candidate.reference_close), money(signal.candidate.stop)
    return {
        "signal_id": signal.id, "ticker": signal.ticker,
        "strategy": signal.candidate.strategy, "signal_session": signal.session.isoformat(),
        "entry_session": signal.planned_entry_session.isoformat(),
        "entry_price": str(entry), "initial_stop": str(stop),
        "target_1r": str(entry + entry - stop), "target_2r": str(entry + 2 * (entry - stop)),
        "observed_sessions": 0, "last_session": None,
        "results": dict.fromkeys(RESULT_KEYS, "pending"), "exclusion_reasons": {},
        "signal": json.loads(canonical_json(signal)), "input_digests": [],
        "provider_symbol": provider_symbol, "data_mode": signal.data_mode,
        "model_version": MODEL_VERSION,
    }


def evaluation_active(record: dict) -> bool:
    return any(value in UNRESOLVED for value in record["results"].values())


def step_evaluation(record: dict, session: date, bar: Bar | None,
                    calendar: Calendar, observed_at: datetime, *, data_valid: bool = True,
                    untradable_evidence: VerifiedUntradable | None = None) -> dict:
    if not evaluation_active(record):
        return record
    last = date.fromisoformat(record["last_session"]) if record["last_session"] else None
    if last is not None and session <= last:
        return record
    expected = calendar.next(last).day if last else date.fromisoformat(record["entry_session"])
    if session != expected:
        raise ValueError("chronological_research_replay_required")
    if observed_at.tzinfo is None or observed_at < calendar.get(session).closes_at:
        raise ValueError("target_session_not_closed")
    updated = copy.deepcopy(record)
    results = updated["results"]
    if untradable_evidence is not None:
        require_nontrading_bar(untradable_evidence, record["ticker"], session,
                              observed_at, bar, record["data_mode"])
        updated.setdefault("untradable_evidence", []).append({
            **untradable_evidence.audit(), "observed_at": observed_at.isoformat()
        })
        updated.pop("hold_reason", None)
        if last is None:
            for key in RESULT_KEYS:
                results[key] = "excluded"
                updated["exclusion_reasons"][key] = "official_untradable_entry"
            return updated
        observed = record["observed_sessions"] + 1
        for key in RESULT_KEYS:
            if results[key] in UNRESOLVED:
                results[key] = "pending"
        for key, horizon in (("net_5", 5), ("net_10", 10)):
            if observed == horizon and results[key] == "pending":
                results[key] = "excluded"
                updated["exclusion_reasons"][key] = "official_untradable_horizon"
        updated["observed_sessions"] = observed
        updated["last_session"] = session.isoformat()
        updated["input_digests"].append({"session": session.isoformat(),
                                         "digest": untradable_evidence.input_digest,
                                         "observed_at": observed_at.isoformat()})
        return updated
    if bar is None or not data_valid or not bar.valid() or bar.volume == 0:
        for key in RESULT_KEYS:
            if results[key] in UNRESOLVED:
                results[key] = "data_hold"
        updated["hold_reason"] = "missing_bar" if bar is None else "invalid_or_unreconciled_data"
        return updated
    if bar.session != session:
        raise ValueError("bar_session_mismatch")
    updated.pop("hold_reason", None)
    entry, stop = Decimal(record["entry_price"]), Decimal(record["initial_stop"])
    for key in RESULT_KEYS:
        if results[key] in UNRESOLVED:
            results[key] = "pending"
    for key, rr in (("target_1r", 1), ("target_2r", 2)):
        if results[key] != "pending":
            continue
        decision = evaluate_exit(bar, stop, Decimal(record[key]),
                                 ExitConfig(target_r=Decimal(rr)), entry_day=False)
        if decision.alternate_price is not None:
            results[key] = "ambiguous"
        elif decision.kind == "exit":
            results[key] = "won" if decision.reason.startswith("target") else "lost"
    observed = record["observed_sessions"] + 1
    for key, horizon in (("net_5", 5), ("net_10", 10)):
        if results[key] != "pending":
            continue
        if money(bar.low) <= stop:
            results[key] = "lost"
        elif observed == horizon:
            net = money(bar.close) * Decimal("0.9975") - entry * Decimal("1.0015")
            results[key] = "won" if net > 0 else "lost"
    updated["observed_sessions"] = observed
    updated["last_session"] = session.isoformat()
    updated["input_digests"].append({
        "session": session.isoformat(), "digest": digest(bar),
        "observed_at": observed_at.isoformat(),
    })
    return updated
