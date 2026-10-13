"""Synthetic reviewed-source repairs only: no network, real evidence or DB writes."""
import copy
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta

import pytest

from idx_scanner.context import Calendar, Session, quality
from idx_scanner.models import Bar, CorporateAction, ProviderRowIssue, Series, digest
from idx_scanner.providers import FetchRequest, ProviderError
from idx_scanner.reviewed_backfill import (
    BACKFILL_VERSION,
    ReviewedBackfillProvider,
    parse_reviewed_backfill_manifest,
)
from idx_scanner.runner import run_once

BASIS = "yahoo_provider_ohlcv_auto_adjust_false_v1"


@pytest.fixture
def case():
    days = [date(2026, 10, day) for day in (9, 12, 13, 14)]
    calendar = Calendar(tuple(Session(day, datetime.combine(day, datetime.min.time(), UTC)
        + timedelta(hours=2), datetime.combine(day, datetime.min.time(), UTC)
        + timedelta(hours=9)) for day in days), "SYNTHETIC-explicit-days",
        "synthetic://not-an-official-calendar", "fixture")
    bars = (Bar(days[0], 100, 105, 95, 101, 1000),
            Bar(days[1], 101, 110, 98, 108, 1100),
            Bar(days[2], 108, 112, 105, 109, 1200))
    source = Series("DEMO", "DEMO.JK", "yfinance", BASIS, bars[:2],
        provider_version="1.7.0", fetched_at=calendar.get(days[1]).closes_at
        + timedelta(minutes=3))
    issue = ProviderRowIssue(days[1], "incomplete_ohlcv", (
        ("open", 101), ("high", 110), ("low", 98), ("close", None), ("volume", 1100)))
    fresh = replace(source, bars=(bars[0], bars[2]), provider_row_issues=(issue,),
        fetched_at=calendar.get(days[2]).closes_at + timedelta(minutes=1))
    now = calendar.get(days[2]).closes_at + timedelta(minutes=10)
    payload = {"version": BACKFILL_VERSION, "data_mode": "live", "records": [{
        "ticker": source.ticker, "provider_symbol": source.provider_symbol,
        "provider": "yfinance", "price_basis": BASIS, "provider_version": "1.7.0",
        "session": str(days[1]), "source_input_digest": source.input_digest,
        "reference": {"source_url": "https://www.idx.co.id/test-only-synthetic-reference",
                      "document_sha256": "a" * 64,
                      "reviewed_at": (now - timedelta(minutes=5)).isoformat()},
    }]}
    request = FetchRequest(source.ticker, source.provider_symbol, days[0], days[2], True)
    return source, fresh, calendar, now, payload, request


class Provider:
    def __init__(self, source, failure=None):
        self.source, self.failure, self.requests = source, failure, []
        self.raw_recovery_captures = {}
        self.fetch_diagnostics = {}

    def fetch(self, request):
        self.requests.append(request)
        if self.failure:
            raise ProviderError(self.failure)
        return self.source


class Store:
    def __init__(self, source, rows=None):
        self.source, self.rows, self.lookups, self.loads = source, rows, [], []

    def _request(self, method, table, *, params):
        assert method == "GET" and table == "market_series_revisions"
        self.lookups.append(params)
        return self.rows if self.rows is not None else [
            {"id": "stored-reviewed-source", "input_digest": self.source.input_digest}]

    def load_series(self, revision, *, namespace, data_mode, expected_input_digest):
        assert revision == "stored-reviewed-source" and namespace == "forward"
        assert data_mode == "live"
        self.loads.append(expected_input_digest)
        return self.source


def wrapper(case, *, fresh=None, archived=None, payload=None, failure=None, rows=None):
    source, current, calendar, now, manifest, request = case
    provider = Provider(fresh if fresh is not None else current, failure)
    store = Store(archived if archived is not None else source, rows)
    records = parse_reviewed_backfill_manifest(payload if payload is not None else manifest)
    return ReviewedBackfillProvider(provider, store, calendar, records, clock=lambda: now), (
        provider, store, request)


def test_manifest_is_strict_and_immutable(case):
    records = parse_reviewed_backfill_manifest(case[4])
    assert isinstance(records, tuple) and records[0].session == date(2026, 10, 12)
    with pytest.raises(FrozenInstanceError):
        records[0].ticker = "CHANGED"
    with pytest.raises(FrozenInstanceError):
        records[0].reference.document_sha256 = "b" * 64


@pytest.mark.parametrize("change", ["version", "mode", "extra", "duplicate", "digest",
    "provider", "basis", "date", "symbol", "naive", "http", "credential_url", "query",
    "same_provider_reference", "reference_hash", "reference_extra", "records_type"])
def test_malformed_manifest_is_rejected(case, change):
    payload = copy.deepcopy(case[4])
    record = payload["records"][0]
    if change == "version":
        payload["version"] = "unreviewed"
    elif change == "mode":
        payload["data_mode"] = "fixture"
    elif change == "extra":
        payload["unsafe"] = True
    elif change == "duplicate":
        payload["records"] = [record, copy.deepcopy(record)]
    elif change == "records_type":
        payload["records"] = {}
    elif change == "digest":
        record["source_input_digest"] = "bad"
    elif change == "provider":
        record["provider"] = "eodhd"
    elif change == "basis":
        record["price_basis"] = "adjusted"
    elif change == "date":
        record["session"] = "2026-02-30"
    elif change == "symbol":
        record["provider_symbol"] = "bad symbol"
    elif change == "naive":
        record["reference"]["reviewed_at"] = "2026-10-13T09:05:00"
    elif change == "reference_hash":
        record["reference"]["document_sha256"] = "bad"
    elif change == "reference_extra":
        record["reference"]["token"] = "not-a-real-secret"
    else:
        record["reference"]["source_url"] = {
            "http": "http://www.idx.co.id/document",
            "credential_url": "https://user:password@www.idx.co.id/document",
            "query": "https://www.idx.co.id/document?token=not-a-real-token",
            "same_provider_reference": "https://finance.yahoo.com/quote/DEMO.JK",
        }[change]
    with pytest.raises(ValueError, match="invalid_reviewed_backfill_manifest"):
        parse_reviewed_backfill_manifest(payload)


def test_empty_allowlist_delegates_without_source_lookups(case):
    payload = {"version": BACKFILL_VERSION, "data_mode": "live", "records": []}
    repair, (provider, store, request) = wrapper(case, payload=payload)
    assert repair.fetch(request) is case[1]
    assert provider.requests == [request] and store.lookups == [] and store.loads == []


def test_repairs_reviewed_oct12_and_preserves_fresh_oct13_and_capture_truth(case):
    source, fresh, calendar, _, _, _ = case
    repair, (provider, store, request) = wrapper(case)
    result = repair.fetch(request)
    assert [b.session for b in result.bars] == [date(2026, 10, n) for n in (9, 12, 13)]
    assert result.bars[1] == source.bars[1] and result.bars[2] == fresh.bars[1]
    assert result.fetched_at == fresh.fetched_at and source.fetched_at != result.fetched_at
    assert result.provider_row_issues == () and quality(result, request.end, calendar) == "valid"
    assert fresh.provider_row_issues and len(fresh.bars) == 2
    assert store.lookups[0]["input_digest"] == "eq." + source.input_digest
    assert store.lookups[0]["provider"] == "eq.yfinance" and len(store.loads) == 1
    captures = repair.raw_recovery_captures[source.ticker]
    assert fresh in captures and source in captures
    audit = json.loads(result.provenance[-1])
    assert audit["kind"] == BACKFILL_VERSION and audit["replaced_sessions"] == ["2026-10-12"]
    assert audit["original_input_digest"] == fresh.input_digest
    assert audit["reviewed_input_digest"] == source.input_digest
    assert provider.requests == [request]


def test_archived_oct12_only_advances_available_prefix_without_inventing_oct13(case):
    source, fresh, calendar, _, _, request = case
    partial = replace(fresh, bars=fresh.bars[:1])
    repair, _ = wrapper(case, fresh=partial)
    result = repair.fetch(request)
    assert result.bars == source.bars and result.bars[-1].session == date(2026, 10, 12)
    assert quality(result, source.bars[-1].session, calendar) == "valid"
    assert quality(result, request.end, calendar) == "stale"


def test_wholly_missing_reviewed_bar_is_repaired_without_other_session_repairs(case):
    source, fresh, _, _, _, request = case
    earlier = ProviderRowIssue(source.bars[0].session, "incomplete_ohlcv", (
        ("open", 100), ("high", 105), ("low", 95), ("close", None), ("volume", 1000)))
    current = replace(fresh, bars=fresh.bars[1:], provider_row_issues=(earlier,),
        provider_missing_sessions=(source.bars[-1].session,))
    repair, _ = wrapper(case, fresh=current)
    result = repair.fetch(request)
    assert result.provider_row_issues == (earlier,)
    assert result.provider_missing_sessions == ()
    assert result.bars == (source.bars[-1], fresh.bars[-1])


@pytest.mark.parametrize("change", ["close", "history", "flat_prior_close", "split",
    "unknown_actions", "basis", "version", "symbol", "provider", "future_bar"])
def test_existing_price_or_basis_action_conflicts_are_rejected(case, change):
    source, fresh, _, _, _, request = case
    if change == "close":
        issue = replace(fresh.provider_row_issues[0], observed_values=(
            ("open", 101), ("high", 110), ("low", 98), ("close", 107), ("volume", None)))
        fresh = replace(fresh, provider_row_issues=(issue,))
    elif change == "history":
        fresh = replace(fresh, bars=(replace(fresh.bars[0], close=102), fresh.bars[-1]))
    elif change == "flat_prior_close":
        # Non-null EOD-style prior-close prices must not be changed to force the reference.
        issue = replace(fresh.provider_row_issues[0], observed_values=(
            ("open", 101), ("high", 101), ("low", 101), ("close", None), ("volume", 1100)))
        fresh = replace(fresh, provider_row_issues=(issue,))
    elif change == "split":
        fresh = replace(fresh, actions=(CorporateAction(source.bars[-1].session, "split", "2"),))
    elif change == "unknown_actions":
        fresh = replace(fresh, actions_complete=False)
    elif change == "future_bar":
        fresh = replace(fresh, bars=fresh.bars + (replace(fresh.bars[-1],
            session=date(2026, 10, 14)),))
    else:
        fresh = replace(fresh, **{{"basis": "price_basis", "version": "provider_version",
            "symbol": "provider_symbol", "provider": "provider"}[change]: "wrong"})
    repair, _ = wrapper(case, fresh=fresh)
    with pytest.raises(ProviderError, match="reviewed_backfill"):
        repair.fetch(request)


@pytest.mark.parametrize("change", ["digest", "wrong_cutoff", "wrong_symbol", "unreconciled_split",
    "missing_action_metadata", "invalid_bar", "future_fetch"])
def test_loaded_source_requires_exact_trusted_identity_and_valid_closed_history(case, change):
    source, fresh, _, now, payload, request = case
    if change == "digest":
        source = replace(source, bars=(source.bars[0], replace(source.bars[1], close=107)))
    elif change == "wrong_cutoff":
        source = replace(source, bars=source.bars + (fresh.bars[-1],))
    elif change == "wrong_symbol":
        source = replace(source, provider_symbol="OTHER.JK")
    elif change == "unreconciled_split":
        source = replace(source, actions=(CorporateAction(source.bars[-1].session, "split", "2"),))
    elif change == "missing_action_metadata":
        source = replace(source, actions_complete=False)
    elif change == "invalid_bar":
        source = replace(source, bars=(source.bars[0], replace(source.bars[1], high=100)))
    else:
        source = replace(source, fetched_at=now + timedelta(minutes=1))
    # Except deliberate digest mismatch, pin the changed digest to prove other gates independently.
    if change != "digest":
        payload = copy.deepcopy(payload)
        payload["records"][0]["source_input_digest"] = source.input_digest
    repair, _ = wrapper(case, archived=source, payload=payload)
    with pytest.raises(ProviderError, match="reviewed_backfill"):
        repair.fetch(request)


@pytest.mark.parametrize("when", ["before_close", "future", "open_target"])
def test_review_and_processing_times_cannot_be_backdated_or_future(case, when):
    source, _, calendar, now, payload, request = case
    if when == "open_target":
        repair, _ = wrapper(case)
        repair.clock = lambda: calendar.get(request.end).opens_at
    else:
        payload = copy.deepcopy(payload)
        instant = calendar.get(source.bars[-1].session).opens_at if when == "before_close" else (
            now + timedelta(seconds=1))
        payload["records"][0]["reference"]["reviewed_at"] = instant.isoformat()
        repair, _ = wrapper(case, payload=payload)
    with pytest.raises(ProviderError, match="reviewed_backfill"):
        repair.fetch(request)


@pytest.mark.parametrize("rows", [[], [{"id": "one", "input_digest": "b" * 64}], [{
    "id": "one", "input_digest": "a" * 64}, {"id": "two", "input_digest": "a" * 64}]])
def test_missing_or_ambiguous_persisted_receipt_is_not_a_fallback(case, rows):
    repair, (_, _, request) = wrapper(case, rows=rows)
    with pytest.raises(ProviderError, match="reviewed_backfill"):
        repair.fetch(request)


def test_provider_transport_failure_does_not_fall_back_to_stale_archive(case):
    repair, (_, store, request) = wrapper(case, failure="provider_unavailable")
    with pytest.raises(ProviderError, match="provider_unavailable"):
        repair.fetch(request)
    assert store.lookups == [] and store.loads == []


def test_retry_preserves_digest_and_source_capture_versions(case):
    repair, (provider, _, request) = wrapper(case)
    first = repair.fetch(request)
    provider.source = replace(provider.source, fetched_at=provider.source.fetched_at
        + timedelta(minutes=1))
    second = repair.fetch(request)
    assert first.input_digest == second.input_digest and first.bars == second.bars
    assert first.fetched_at != second.fetched_at


def test_matching_flat_daily_bar_is_not_blanket_rejected(case):
    source, fresh, _, _, payload, request = case
    flat = replace(source.bars[-1], open=101, high=101, low=101, close=101)
    source = replace(source, bars=(source.bars[0], flat))
    fresh = replace(fresh, provider_row_issues=(replace(fresh.provider_row_issues[0],
        observed_values=(("open", 101), ("high", 101), ("low", 101),
                         ("close", None), ("volume", 1100))),))
    payload = copy.deepcopy(payload)
    payload["records"][0]["source_input_digest"] = source.input_digest
    repair, _ = wrapper(case, fresh=fresh, archived=source, payload=payload)
    assert repair.fetch(request).bars[1] == flat


def test_cash_dividend_metadata_disagreement_is_audited_without_price_or_ledger_change(case):
    source, fresh, _, _, _, request = case
    fresh = replace(fresh, actions=(CorporateAction(source.bars[-1].session, "dividend", "10"),))
    repair, _ = wrapper(case, fresh=fresh)
    result = repair.fetch(request)
    assert result.actions == fresh.actions
    assert json.loads(result.provenance[-1])["cash_dividend_metadata_disagreement"]


def test_unreviewed_and_already_complete_sessions_are_not_repaired(case):
    source, fresh, _, _, payload, request = case
    unrelated = copy.deepcopy(payload)
    unrelated["records"][0].update(ticker="OTHER", provider_symbol="OTHER.JK")
    repair, (_, store, _) = wrapper(case, payload=unrelated)
    assert repair.fetch(request) == fresh and store.lookups == []
    complete = replace(fresh, bars=source.bars + fresh.bars[-1:], provider_row_issues=())
    repair, (_, store, _) = wrapper(case, fresh=complete)
    assert repair.fetch(request) == complete and len(store.lookups) == 1


def test_complete_session_conflicting_with_reviewed_record_is_rejected(case):
    source, fresh, _, _, _, request = case
    conflicting = replace(source.bars[-1], close=source.bars[-1].close + 10)
    complete = replace(fresh, bars=(source.bars[0], conflicting, fresh.bars[-1]),
                       provider_row_issues=())
    repair, _ = wrapper(case, fresh=complete)
    with pytest.raises(ProviderError, match="reviewed_backfill_overlap_conflict"):
        repair.fetch(request)


def test_scanner_run_once_rejects_reviewed_backfill_provider(case):
    repair, _ = wrapper(case)
    with pytest.raises(ValueError, match="scanner_reviewed_backfill_prohibited"):
        run_once(repair, None, {}, date(2026, 10, 13), None, None, datetime.now(UTC))


def test_record_symbol_mismatch_is_not_silently_ignored(case):
    payload = copy.deepcopy(case[4])
    payload["records"][0]["provider_symbol"] = "OTHER.JK"
    repair, (_, _, request) = wrapper(case, payload=payload)
    with pytest.raises(ProviderError, match="reviewed_backfill"):
        repair.fetch(request)


def test_existing_provider_capture_and_diagnostic_contracts_are_preserved(case):
    repair, (provider, _, request) = wrapper(case)
    provider.raw_recovery_captures = {"OTHER": (case[0],)}
    provider.fetch_diagnostics = {"OTHER": ({"status": "already_recorded"},)}
    repair.fetch(request)
    assert repair.raw_recovery_captures["OTHER"] == (case[0],)
    assert repair.fetch_diagnostics["OTHER"] == ({"status": "already_recorded"},)
    assert repair.fetch_diagnostics[request.ticker][-1]["status"] == "reviewed_backfill_applied"


@pytest.mark.parametrize("change", ["future_action", "future_issue", "future_missing_session",
                                    "capture_before_close"])
def test_archive_cannot_contain_future_information_or_unclosed_capture(case, change):
    source, _, calendar, _, payload, request = case
    future = date(2026, 10, 13)
    if change == "future_action":
        source = replace(source, actions=(CorporateAction(future, "dividend", "10"),))
    elif change == "future_issue":
        source = replace(source, provider_row_issues=(ProviderRowIssue(future, "missing_ohlcv",
            (("close", None),)),))
    elif change == "future_missing_session":
        source = replace(source, provider_missing_sessions=(future,))
    else:
        source = replace(source, fetched_at=calendar.get(source.bars[-1].session).opens_at)
    payload = copy.deepcopy(payload)
    payload["records"][0]["source_input_digest"] = source.input_digest
    repair, _ = wrapper(case, archived=source, payload=payload)
    with pytest.raises(ProviderError, match="reviewed_backfill"):
        repair.fetch(request)


def test_current_capture_cannot_know_last_bar_before_that_session_closed(case):
    _, fresh, calendar, _, _, request = case
    repair, _ = wrapper(case, fresh=replace(fresh,
        fetched_at=calendar.get(request.end).opens_at))
    with pytest.raises(ProviderError, match="reviewed_backfill"):
        repair.fetch(request)


def test_agreeing_reconciled_split_is_preserved(case):
    source, fresh, _, _, payload, request = case
    action = CorporateAction(source.bars[-1].session, "split", "2")
    source = replace(source, actions=(action,), reconciled_actions=(digest(action),))
    fresh = replace(fresh, actions=(action,), reconciled_actions=(digest(action),))
    payload = copy.deepcopy(payload)
    payload["records"][0]["source_input_digest"] = source.input_digest
    repair, _ = wrapper(case, archived=source, fresh=fresh, payload=payload)
    result = repair.fetch(request)
    assert result.actions == fresh.actions and result.reconciled_actions == fresh.reconciled_actions


def test_empty_current_capture_cannot_turn_into_a_healthy_short_history(case):
    _, fresh, _, _, _, request = case
    repair, _ = wrapper(case, fresh=replace(fresh, bars=()))
    with pytest.raises(ProviderError, match="reviewed_backfill"):
        repair.fetch(request)


@pytest.mark.parametrize("code", ["unverified_price_basis", "corporate_action_hold"])
def test_unknown_current_hold_flags_are_not_erased_by_a_daily_bar(case, code):
    _, fresh, _, _, _, request = case
    fresh = replace(fresh, provider_row_issues=(replace(fresh.provider_row_issues[0], code=code),))
    repair, _ = wrapper(case, fresh=fresh)
    with pytest.raises(ProviderError, match="reviewed_backfill"):
        repair.fetch(request)


def test_direct_duplicate_or_mutable_allowlist_is_rejected(case):
    source, fresh, calendar, now, payload, _ = case
    records = parse_reviewed_backfill_manifest(payload)
    for invalid in (list(records), records + records):
        with pytest.raises(ValueError, match="invalid_reviewed_backfill_manifest"):
            ReviewedBackfillProvider(Provider(fresh), Store(source), calendar, invalid,
                                     clock=lambda: now)


def test_manifest_session_requires_canonical_iso_date(case):
    payload = copy.deepcopy(case[4])
    payload["records"][0]["session"] = "20261012"
    with pytest.raises(ValueError, match="invalid_reviewed_backfill_manifest"):
        parse_reviewed_backfill_manifest(payload)
