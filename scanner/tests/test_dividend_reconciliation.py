"""Synthetic evidence exercises exact approval boundaries, never live proof."""

import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime

import pytest

from idx_scanner.context import quality
from idx_scanner.corporate_actions import (
    RECONCILIATION_VERSION,
    DividendEvidence,
    load_dividend_evidence,
    reconcile_dividends,
)
from idx_scanner.fixtures import sample_market
from idx_scanner.models import CorporateAction, canonical_json, digest
from idx_scanner.persistence import market_series_envelope, series_from_revision


def example():
    series, calendar, _ = sample_market(620)
    calendar = replace(calendar, data_mode="live")
    raw = replace(
        series["DEMO-A"],
        provider="yfinance",
        provider_symbol="DEMO-A.JK",
        price_basis="yahoo_provider_ohlcv_auto_adjust_false_v1",
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    action = CorporateAction(raw.bars[10].session, "dividend", "12.5")
    raw = replace(raw, actions=(action,))
    proof = DividendEvidence(
        ticker=raw.ticker,
        session=action.session,
        value=action.value,
        action_digest=digest(action),
        price_basis=raw.price_basis,
        source="https://www.bca.co.id/test-only-synthetic-evidence",
        source_sha256=hashlib.sha256(
            b"synthetic test evidence, not a real announcement"
        ).hexdigest(),
        published_date=raw.bars[0].session,
        date_method="explicit_regular_ex_date",
        source_locator="synthetic test",
        reviewed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return raw, proof, calendar, calendar.sessions[619].day


def test_exact_reviewed_dividend_changes_only_approval_and_provenance():
    raw, proof, calendar, target = example()
    assert quality(raw, target, calendar) == "corporate_action_hold"
    result = reconcile_dividends(raw, (proof,), calendar, target)
    assert quality(result, target, calendar) == "valid"
    assert result.bars == raw.bars and result.actions == raw.actions
    assert result.price_basis == raw.price_basis
    assert not json.loads(result.provenance[-1])["price_changes"]
    assert not json.loads(result.provenance[-1])["ledger_changes"]
    assert reconcile_dividends(result, (proof,), calendar, target) is result
    record = market_series_envelope(result, namespace="test", data_mode="live")["p_record"]
    assert series_from_revision(record) == result


def test_unreviewed_events_and_splits_are_never_blanket_approved():
    raw, proof, calendar, target = example()
    extra = CorporateAction(raw.bars[11].session, "split", "4.0")
    raw = replace(raw, actions=raw.actions + (extra,))
    result = reconcile_dividends(raw, (proof,), calendar, target)
    assert digest(extra) not in result.reconciled_actions
    assert quality(result, target, calendar) == "corporate_action_hold"
    assert reconcile_dividends(raw, (), calendar, target) is raw


@pytest.mark.parametrize("change", ["value", "duplicate", "basis"])
def test_wrong_provider_event_or_basis_cannot_reuse_evidence(change):
    raw, proof, calendar, target = example()
    if change == "value":
        raw = replace(raw, actions=(replace(raw.actions[0], value="13.0"),))
    if change == "duplicate":
        raw = replace(raw, actions=raw.actions * 2)
    if change == "basis":
        raw = replace(raw, price_basis="different-adjusted-feed")
    with pytest.raises(ValueError, match="mismatch"):
        reconcile_dividends(raw, (proof,), calendar, target)


def test_other_ticker_and_future_event_do_not_approve_current_input():
    raw, proof, calendar, target = example()
    assert reconcile_dividends(raw, (replace(proof, ticker="OTHER"),), calendar, target) is raw
    assert reconcile_dividends(raw, (proof,), calendar, raw.bars[9].session) is raw


def test_cum_date_derivation_requires_known_adjacent_exchange_sessions():
    raw, proof, calendar, target = example()
    proof = replace(
        proof, date_method="next_known_session_after_cum", cum_session=raw.bars[9].session
    )
    assert (
        quality(reconcile_dividends(raw, (proof,), calendar, target), target, calendar) == "valid"
    )
    with pytest.raises(ValueError, match="cum_ex_calendar_mismatch"):
        reconcile_dividends(
            raw, (replace(proof, cum_session=raw.bars[8].session),), calendar, target
        )


@pytest.mark.parametrize(
    "source",
    [
        "https://bca.co.id.evil.example/proof",
        "http://www.bca.co.id/a",
        "https://www.bca.co.id/a?api_token=test-only",
    ],
)
def test_nonprimary_or_credential_bearing_sources_are_rejected(source):
    _, proof, _, _ = example()
    with pytest.raises(ValueError, match="primary_dividend_source_required"):
        replace(proof, source=source)


def test_manifest_source_hash_pending_review_and_split_are_rejected(tmp_path):
    raw, proof, _, _ = example()
    folder = tmp_path / "data/sources"
    folder.mkdir(parents=True)
    source = folder / "test.txt"
    source.write_bytes(b"synthetic test evidence, not a real announcement")
    row = json.loads(canonical_json(asdict(proof)))
    row.update(
        kind="dividend",
        currency="IDR",
        source_file="data/sources/test.txt",
        review_status="source_facts_verified",
    )
    manifest = tmp_path / "manifest.json"

    def load():
        manifest.write_text(
            json.dumps({"version": RECONCILIATION_VERSION, "data_mode": "live", "events": [row]})
        )
        return load_dividend_evidence(manifest, tmp_path)

    assert load() == (proof,)
    row["review_status"] = "pending"
    with pytest.raises(ValueError, match="review_required"):
        load()
    row["review_status"] = "source_facts_verified"
    row["kind"] = "split"
    with pytest.raises(ValueError, match="no_split_approval"):
        load()
    row["kind"] = "dividend"
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum_mismatch"):
        load()


def test_exact_reviewed_split_reconciles_cleanly_without_altering_candles(tmp_path):
    raw, proof, calendar, target = example()
    split_action = CorporateAction(raw.bars[11].session, "split", "4.0")
    raw_with_both = replace(raw, actions=raw.actions + (split_action,))
    
    folder = tmp_path / "data/sources"
    folder.mkdir(parents=True)
    source = folder / "split.txt"
    source.write_bytes(b"ksei split announcement text")
    
    split_proof = replace(
        proof,
        session=split_action.session,
        value="4.0",
        action_digest=digest(split_action),
        kind="split",
        date_method="trading_start_date_new_nominal",
        source_sha256=hashlib.sha256(b"ksei split announcement text").hexdigest(),
    )
    
    # Reconciling both dividend and split:
    result = reconcile_dividends(raw_with_both, (proof, split_proof), calendar, target)
    assert quality(result, target, calendar) == "valid"
    assert digest(split_action) in result.reconciled_actions
    assert digest(raw.actions[0]) in result.reconciled_actions
    assert result.bars == raw.bars
    prov = json.loads(result.provenance[-1])
    assert not prov["price_changes"]
    assert not prov["ledger_changes"]

