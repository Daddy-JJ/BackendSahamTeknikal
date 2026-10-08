"""Exact, source-reviewed cash-dividend approvals; no price or ledger adjustment."""

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from .context import (
    CASH_DIVIDEND_POLICY_VERSION,
    Calendar,
    cash_dividends_are_metadata_only,
)
from .models import CorporateAction, Series, canonical_json, digest

RECONCILIATION_VERSION = "reviewed_cash_dividends_no_adjust_v1"
ALLOWED_RECONCILIATION_VERSIONS = {
    RECONCILIATION_VERSION,
    "reviewed_corporate_actions_no_adjust_v1",
}


@dataclass(frozen=True)
class DividendEvidence:
    ticker: str
    session: date
    value: str
    action_digest: str
    price_basis: str
    source: str
    source_sha256: str
    published_date: date
    date_method: str
    source_locator: str
    reviewed_at: datetime
    cum_session: date | None = None
    kind: str = "dividend"

    def __post_init__(self):
        url = urlsplit(self.source)
        primary = ("bca.co.id", "ksei.co.id", "idx.id", "idx.co.id")
        if (
            url.scheme != "https"
            or not any(url.hostname == d or (url.hostname or "").endswith("." + d) for d in primary)
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("primary_dividend_source_required")
        value = Decimal(self.value)
        if (
            not value.is_finite()
            or value <= 0
            or not self.source_locator
            or not re.fullmatch(r"[a-f0-9]{64}", self.source_sha256)
            or self.reviewed_at.tzinfo is None
            or self.published_date > self.session
            or self.reviewed_at.date() < self.published_date
            or self.price_basis != "yahoo_provider_ohlcv_auto_adjust_false_v1"
            or self.action_digest != digest(CorporateAction(self.session, self.kind, self.value))
        ):
            raise ValueError("invalid_dividend_evidence")
        if self.date_method not in (
            "explicit_regular_ex_date",
            "next_known_session_after_cum",
            "trading_start_date_new_nominal",
        ):
            raise ValueError("unsupported_dividend_date_method")
        if (self.date_method == "next_known_session_after_cum") != (self.cum_session is not None):
            raise ValueError("dividend_cum_session_required")
        if self.kind not in ("dividend", "split"):
            raise ValueError("unsupported_action_kind")


CorporateActionEvidence = DividendEvidence


def load_dividend_evidence(path: Path, root: Path) -> tuple[DividendEvidence, ...]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    manifest_version = data.get("version")
    if manifest_version not in ALLOWED_RECONCILIATION_VERSIONS or data.get("data_mode") != "live":
        raise ValueError("unsupported_dividend_manifest")
    result = []
    seen = set()
    for row in data["events"]:
        if row.get("review_status") != "source_facts_verified":
            raise ValueError("dividend_source_review_required")
        kind = row.get("kind", "dividend")
        if manifest_version == RECONCILIATION_VERSION:
            if kind != "dividend" or row.get("currency") != "IDR":
                raise ValueError("cash_dividend_only_no_split_approval")
        else:
            if kind not in ("dividend", "split"):
                raise ValueError("cash_dividend_or_split_only")
            if kind == "dividend" and row.get("currency") != "IDR":
                raise ValueError("cash_dividend_currency_must_be_idr")
        source_file = (root / row["source_file"]).resolve()
        if not source_file.is_relative_to((root / "data/sources").resolve()):
            raise ValueError("dividend_source_path_outside_sources")
        if hashlib.sha256(source_file.read_bytes()).hexdigest() != row["source_sha256"]:
            raise ValueError("dividend_source_checksum_mismatch")
        proof = DividendEvidence(
            ticker=row["ticker"],
            session=date.fromisoformat(row["session"]),
            value=row["value"],
            action_digest=row["action_digest"],
            price_basis=row["price_basis"],
            source=row["source"],
            source_sha256=row["source_sha256"],
            published_date=date.fromisoformat(row["published_date"]),
            date_method=row["date_method"],
            source_locator=row["source_locator"],
            reviewed_at=datetime.fromisoformat(row["reviewed_at"]),
            cum_session=date.fromisoformat(row["cum_session"]) if row.get("cum_session") else None,
            kind=kind,
        )
        if (proof.ticker, proof.session, proof.kind) in seen:
            raise ValueError("duplicate_dividend_evidence")
        seen.add((proof.ticker, proof.session, proof.kind))
        result.append(proof)
    return tuple(result)


def reconcile_dividends(
    series: Series, proofs: tuple[DividendEvidence, ...], calendar: Calendar, target: date
) -> Series:
    approvals, dividend_mismatches = [], []
    open_days = sorted(calendar.historical_days + tuple(s.day for s in calendar.sessions))
    for proof in proofs:
        if proof.ticker != series.ticker or proof.session > target:
            continue
        if series.provider != "yfinance" or series.price_basis != proof.price_basis:
            raise ValueError("dividend_provider_basis_mismatch")
        if proof.session not in open_days:
            raise ValueError("dividend_ex_date_not_known_open")
        if proof.cum_session is not None:
            if (
                proof.cum_session not in open_days
                or next((d for d in open_days if d > proof.cum_session), None) != proof.session
            ):
                raise ValueError("dividend_cum_ex_calendar_mismatch")
        matching = [
            a for a in series.actions if a.session == proof.session and a.kind == proof.kind
        ]
        if len(matching) != 1 or digest(matching[0]) != proof.action_digest:
            if proof.kind == "dividend" and cash_dividends_are_metadata_only(series):
                # A metadata mismatch is not a price-basis mismatch. Do not approve
                # the changed event, and continue reviewing independent split facts.
                dividend_mismatches.append({
                    "reviewed_action_digest": proof.action_digest,
                    "observed_action_digests": sorted(digest(a) for a in matching),
                })
                continue
            raise ValueError("dividend_provider_event_mismatch")
        if proof.action_digest not in series.reconciled_actions:
            approvals.append(proof)
    approvals.sort(key=lambda p: (p.ticker, p.session, p.kind))
    reconciled = tuple(
        sorted(set(series.reconciled_actions) | {p.action_digest for p in approvals})
    )
    provenance = series.provenance
    if approvals:
        reason = (
            "cash_dividend_date_value_verified_unadjusted_baseline_retained"
            if all(p.kind == "dividend" for p in approvals)
            else "corporate_action_date_value_verified_unadjusted_baseline_retained"
        )
        provenance += (canonical_json({
            "kind": RECONCILIATION_VERSION,
            "source_input_digest": series.input_digest,
            "evidence": approvals,
            "price_changes": False,
            "ledger_changes": False,
            "reason": reason,
        }),)
    dividends = sorted(
        (a for a in series.actions if a.kind == "dividend" and a.session <= target),
        key=lambda a: (a.session, digest(a)),
    )
    if cash_dividends_are_metadata_only(series) and (dividends or dividend_mismatches):
        # Recorded separately from factual source approval. This does not credit
        # dividends, adjust candles or claim unreviewed provider values are correct.
        record = canonical_json({
            "kind": CASH_DIVIDEND_POLICY_VERSION,
            "price_basis": series.price_basis,
            "events": [{
                "action_digest": digest(a),
                "review_status": "verified" if digest(a) in reconciled else "unreviewed",
            } for a in dividends],
            "evidence_mismatches": sorted(
                dividend_mismatches, key=lambda m: m["reviewed_action_digest"]
            ),
            "price_changes": False,
            "ledger_changes": False,
            "reason": "cash_dividend_metadata_does_not_gate_unadjusted_ohlcv",
        })
        if record not in provenance:
            provenance += (record,)
    if not approvals and provenance == series.provenance:
        return series
    return replace(series, reconciled_actions=reconciled, provenance=provenance)
