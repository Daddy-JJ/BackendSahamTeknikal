from dataclasses import replace
from datetime import timedelta

import pytest

from idx_scanner.fixtures import sample_market
from idx_scanner.models import ScanState
from idx_scanner.providers import FetchRequest, ProviderError
from idx_scanner.runner import run_once


def setup_market():
    series, calendar, universe = sample_market(620)
    target = calendar.sessions[619]
    requests = {
        ticker: FetchRequest(ticker, ticker, calendar.sessions[0].day, target.day, True)
        for ticker in universe.tickers
    }
    return series, calendar, universe, target, requests


class FakeStore:
    def __init__(self, fail_ingest=False, fail_read=False):
        self.calls = []
        self.fail_ingest = fail_ingest
        self.fail_read = fail_read

    def load_state(self, **kwargs):
        self.calls.append(("load", kwargs["through_session"]))
        return ScanState()

    def ingest_series(self, series, **kwargs):
        self.calls.append(("ingest", series.ticker))
        if self.fail_ingest:
            raise RuntimeError("test-only-ingest-failure")
        return {"revision_id": "revision-" + series.ticker, "replayed": False}

    def load_series(self, revision_id, **kwargs):
        self.calls.append(("verify", revision_id))
        if self.fail_read:
            raise RuntimeError("test-only-read-failure")

    def publish(self, result, **kwargs):
        self.calls.append(("publish", result.status))
        return {"run_id": "test-run", "replayed": False}


class FakeProvider:
    def __init__(self, series, fail_ticker=None):
        self.series = series
        self.fail_ticker = fail_ticker
        self.calls = []

    def fetch(self, request):
        self.calls.append(request.ticker)
        if request.ticker == self.fail_ticker:
            raise ProviderError("provider_rate_limited")
        return self.series[request.ticker]


def test_run_persists_every_fetched_revision_before_publish():
    series, calendar, universe, target, requests = setup_market()
    store, provider = FakeStore(), FakeProvider(series)
    outcome = run_once(
        provider,
        store,
        requests,
        target.day,
        calendar,
        universe,
        target.closes_at + timedelta(hours=3),
    )
    assert len(outcome.revision_ids) == 5
    assert store.calls[0][0] == "load"
    assert [kind for kind, _ in store.calls[1:-1]] == ["ingest", "verify"] * 5
    assert store.calls[-1] == ("publish", outcome.pipeline.scan.status)
    assert outcome.pipeline.fetched == tuple(sorted(universe.tickers))


def test_partial_provider_failure_is_visible_and_only_fetched_inputs_are_stored():
    series, calendar, universe, target, requests = setup_market()
    store, provider = FakeStore(), FakeProvider(series, fail_ticker="DEMO-B")
    outcome = run_once(
        provider,
        store,
        requests,
        target.day,
        calendar,
        universe,
        target.closes_at + timedelta(hours=3),
    )
    assert outcome.pipeline.provider_errors == (("DEMO-B", "provider_rate_limited"),)
    assert outcome.pipeline.scan.status == "partial"
    assert len(outcome.revision_ids) == 4
    assert store.calls[-1] == ("publish", "partial")


def test_empty_provider_series_is_persisted_as_missing_not_no_signal():
    series, calendar, universe, target, requests = setup_market()
    series["DEMO-A"] = replace(series["DEMO-A"], bars=())
    store, provider = FakeStore(), FakeProvider(series)
    outcome = run_once(
        provider,
        store,
        requests,
        target.day,
        calendar,
        universe,
        target.closes_at + timedelta(hours=3),
    )
    assert outcome.pipeline.scan.status == "partial"
    assert ("ingest", "DEMO-A") in store.calls
    assert store.calls[-1] == ("publish", "partial")


def test_ingest_failure_blocks_publication():
    series, calendar, universe, target, requests = setup_market()
    store, provider = FakeStore(fail_ingest=True), FakeProvider(series)
    with pytest.raises(RuntimeError, match="test-only-ingest-failure"):
        run_once(
            provider,
            store,
            requests,
            target.day,
            calendar,
            universe,
            target.closes_at + timedelta(hours=3),
        )
    assert not any(kind == "publish" for kind, _ in store.calls)


def test_bad_calendar_blocks_database_and_provider_io():
    series, calendar, universe, target, requests = setup_market()
    store, provider = FakeStore(), FakeProvider(series)
    missing_next = replace(calendar, sessions=calendar.sessions[:620])
    with pytest.raises(ValueError, match="blocked_configuration"):
        run_once(
            provider,
            store,
            requests,
            target.day,
            missing_next,
            universe,
            target.closes_at + timedelta(hours=3),
        )
    assert store.calls == []
    assert provider.calls == []


def test_readback_failure_blocks_publication():
    series, calendar, universe, target, requests = setup_market()
    store, provider = FakeStore(fail_read=True), FakeProvider(series)
    with pytest.raises(RuntimeError, match="test-only-read-failure"):
        run_once(
            provider,
            store,
            requests,
            target.day,
            calendar,
            universe,
            target.closes_at + timedelta(hours=3),
        )
    assert not any(kind == "publish" for kind, _ in store.calls)


def test_provider_or_storage_delay_past_next_open_is_late_not_forward():
    series, calendar, universe, target, requests = setup_market()
    store, provider = FakeStore(), FakeProvider(series)
    late = calendar.next(target.day).opens_at + timedelta(seconds=1)

    def clock():
        assert store.calls[-1][0] == "verify"
        return late

    outcome = run_once(
        provider,
        store,
        requests,
        target.day,
        calendar,
        universe,
        target.closes_at + timedelta(hours=3),
        clock=clock,
    )
    assert outcome.pipeline.scan.signals
    assert all(
        signal.cohort == "late_model_only" and signal.published_at == late
        for signal in outcome.pipeline.scan.signals
    )


def test_crossing_next_open_during_evaluation_blocks_publication():
    series, calendar, universe, target, requests = setup_market()
    store, provider = FakeStore(), FakeProvider(series)
    next_open = calendar.next(target.day).opens_at
    ticks = iter((next_open - timedelta(seconds=1), next_open))
    with pytest.raises(ValueError, match="publication_window_elapsed"):
        run_once(
            provider,
            store,
            requests,
            target.day,
            calendar,
            universe,
            target.closes_at + timedelta(hours=3),
            clock=lambda: next(ticks),
        )
    assert not any(kind == "publish" for kind, _ in store.calls)


def test_live_runner_sends_calendar_deadline_to_atomic_publisher():
    series, calendar, universe, target, requests = setup_market()
    calendar = replace(calendar, data_mode="live")
    universe = replace(universe, data_mode="live")
    series = {ticker: replace(source, provider="yfinance") for ticker, source in series.items()}

    class DeadlineStore(FakeStore):
        def publish(self, result, **kwargs):
            assert kwargs["data_mode"] == "live"
            assert kwargs["publication_deadline"] == calendar.next(target.day).opens_at
            return super().publish(result, **kwargs)

    outcome = run_once(
        FakeProvider(series),
        DeadlineStore(),
        requests,
        target.day,
        calendar,
        universe,
        target.closes_at + timedelta(hours=3),
    )
    assert outcome.publication["run_id"] == "test-run"


def test_runner_holds_unreconciled_dividend_mismatch_without_crashing():
    from datetime import UTC, datetime
    from decimal import Decimal

    from idx_scanner.corporate_actions import DividendEvidence
    from idx_scanner.models import CorporateAction

    series, calendar, universe, target, requests = setup_market()
    calendar = replace(calendar, data_mode="live")
    universe = replace(universe, data_mode="live")
    first_ticker = sorted(requests)[0]
    bad_action = CorporateAction(session=target.day, kind="dividend", value=Decimal("100.0"))
    series_dict = {
        ticker: replace(
            s,
            provider="yfinance",
            actions=(bad_action,) if ticker == first_ticker else (),
            price_basis="yahoo_provider_ohlcv_auto_adjust_false_v1",
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        for ticker, s in series.items()
    }
    from idx_scanner.models import digest
    proof_action = CorporateAction(session=target.day, kind="dividend", value=Decimal("50.0"))
    mismatch_proof = DividendEvidence(
        ticker=first_ticker,
        session=target.day,
        kind="dividend",
        value="50.0",
        price_basis="yahoo_provider_ohlcv_auto_adjust_false_v1",
        action_digest=digest(proof_action),
        source="https://www.bca.co.id/test-evidence",
        source_sha256="1" * 64,
        source_locator="notice.pdf",
        published_date=target.day,
        date_method="explicit_regular_ex_date",
        reviewed_at=datetime(2026, 12, 1, tzinfo=UTC),
    )

    store = FakeStore()
    provider = FakeProvider(series_dict)
    outcome = run_once(
        provider,
        store,
        requests,
        target.day,
        calendar,
        universe,
        target.closes_at + timedelta(hours=3),
        dividend_evidence=(mismatch_proof,),
    )
    first_item = next(i for i in outcome.pipeline.scan.items if i.ticker == first_ticker)
    assert first_item.status == "corporate_action_hold"

