"""Reviewed whole-session non-trading evidence, never inferred from missing prices."""

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from .models import Bar, Series, digest

EVIDENCE_VERSION = "verified_untradable_v1"


@dataclass(frozen=True)
class VerifiedUntradable:
    ticker: str
    session: date
    data_mode: str
    source_url: str
    document_sha256: str
    verified_at: datetime
    reason: str = "official_whole_session_suspension"

    def __post_init__(self):
        url = urlparse(self.source_url)
        official = (url.scheme == "https" and url.hostname is not None
                    and (url.hostname == "idx.co.id" or url.hostname.endswith(".idx.co.id"))
                    and not url.username and not url.password)
        fixture = self.data_mode == "fixture" and url.scheme == "synthetic"
        if (not re.fullmatch(r"[A-Z0-9_-]{1,20}", self.ticker)
            or self.data_mode not in ("live", "fixture") or not (official or fixture)
            or not re.fullmatch(r"[a-f0-9]{64}", self.document_sha256)
            or self.verified_at.tzinfo is None
            or self.reason != "official_whole_session_suspension"):
            raise ValueError("invalid_untradable_evidence")

    @property
    def input_digest(self):
        return digest((EVIDENCE_VERSION, self))

    def audit(self):
        return {"version": EVIDENCE_VERSION, "ticker": self.ticker,
                "session": self.session.isoformat(), "data_mode": self.data_mode,
                "source_url": self.source_url, "document_sha256": self.document_sha256,
                "verified_at": self.verified_at.isoformat(), "reason": self.reason,
                "digest": self.input_digest}


def load_untradable_evidence(path: Path, data_mode: str) -> tuple[VerifiedUntradable, ...]:
    """Load operator-reviewed evidence. An explicit empty file grants no exemptions."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (set(payload) != {"version", "data_mode", "records"}
            or payload["version"] != EVIDENCE_VERSION or payload["data_mode"] != data_mode
            or not isinstance(payload["records"], list)):
            raise ValueError()
        records = tuple(VerifiedUntradable(
            ticker=r["ticker"], session=date.fromisoformat(r["session"]),
            data_mode=data_mode, source_url=r["source_url"],
            document_sha256=r["document_sha256"],
            verified_at=datetime.fromisoformat(r["verified_at"]), reason=r["reason"],
        ) for r in payload["records"] if set(r) == {
            "ticker", "session", "source_url", "document_sha256", "verified_at", "reason"
        })
        if len(records) != len(payload["records"]) or len({
            (r.ticker, r.session) for r in records
        }) != len(records):
            raise ValueError()
        return records
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("invalid_untradable_evidence_file") from None


def evidence_for(evidence, ticker: str, observed_at: datetime, data_mode: str):
    if observed_at.tzinfo is None:
        raise ValueError("untradable_observation_timezone_required")
    matching = {}
    for proof in evidence:
        if proof.data_mode != data_mode:
            raise ValueError("mixed_untradable_evidence_mode")
        if proof.ticker == ticker and proof.verified_at <= observed_at:
            if proof.session in matching:
                raise ValueError("duplicate_untradable_evidence")
            matching[proof.session] = proof
    return matching


def restore_untradable_evidence(audit: dict) -> VerifiedUntradable:
    try:
        expected = {"version", "ticker", "session", "data_mode", "source_url",
                    "document_sha256", "verified_at", "reason", "digest"}
        if set(audit) not in (expected, expected | {"observed_at"}):
            raise ValueError()
        proof = VerifiedUntradable(
            audit["ticker"], date.fromisoformat(audit["session"]), audit["data_mode"],
            audit["source_url"], audit["document_sha256"],
            datetime.fromisoformat(audit["verified_at"]), audit["reason"],
        )
        if audit["version"] != EVIDENCE_VERSION or audit["digest"] != proof.input_digest:
            raise ValueError()
        if "observed_at" in audit:
            observed_at = datetime.fromisoformat(audit["observed_at"])
            if observed_at.tzinfo is None or proof.verified_at > observed_at:
                raise ValueError()
        return proof
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("invalid_frozen_untradable_evidence") from None


def merge_untradable_evidence(configured, book, evaluations) -> tuple[VerifiedUntradable, ...]:
    """Frozen reviews remain available on restart without the operator's local file."""
    frozen = []
    for trade in book.trades.values():
        for event in trade.events:
            if event.untradable_evidence is None:
                continue
            proof = restore_untradable_evidence(event.untradable_evidence)
            if (proof.ticker != trade.signal.ticker or proof.data_mode != trade.signal.data_mode
                or proof.session != event.session or proof.verified_at > event.observed_at):
                raise ValueError("frozen_untradable_event_context_mismatch")
            frozen.append(proof)
    for record in evaluations.values():
        for audit in record.get("untradable_evidence", []):
            proof = restore_untradable_evidence(audit)
            if (proof.ticker != record["ticker"] or proof.data_mode != record["data_mode"]
                or "observed_at" not in audit):
                raise ValueError("frozen_untradable_evaluation_context_mismatch")
            frozen.append(proof)
    merged = {}
    for proof in (*configured, *frozen):
        key = (proof.ticker, proof.session, proof.data_mode)
        if key in merged and merged[key].input_digest != proof.input_digest:
            raise ValueError("conflicting_untradable_evidence")
        merged[key] = proof
    return tuple(merged[key] for key in sorted(merged))


def require_nontrading_source(series: Series | None, sessions):
    """A source claiming trades conflicts with a reviewed whole-session suspension."""
    if series is None:
        return
    if any(b.session in sessions and b.volume > 0 for b in series.bars) or any(
        i.session in sessions and (dict(i.observed_values).get("volume") or 0) > 0
        for i in series.provider_row_issues
    ):
        raise ValueError("untradable_evidence_conflicts_with_provider")


def require_nontrading_bar(proof: VerifiedUntradable, ticker: str, session: date,
                          observed_at: datetime, bar: Bar | None, data_mode: str):
    if (proof.ticker != ticker or proof.session != session or proof.data_mode != data_mode
        or proof.verified_at > observed_at):
        raise ValueError("untradable_evidence_context_mismatch")
    if bar is not None and bar.volume > 0:
        raise ValueError("untradable_evidence_conflicts_with_provider")
