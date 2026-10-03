"""Operator doubles prove rejection boundaries; never hosted/market evidence."""

import importlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from idx_scanner.context import quality
from idx_scanner.fixtures import sample_market
from idx_scanner.models import CorporateAction


@pytest.fixture
def scripts(monkeypatch):
    folder = Path(__file__).resolve().parents[2] / "supabase/scripts"
    monkeypatch.syspath_prepend(str(folder))
    return SimpleNamespace(
        source=importlib.import_module("collect_ksei_action_sources"),
        review=importlib.import_module("review_ksei_dividend_candidates"),
        smoke=importlib.import_module("manual_scanner_smoke"),
        publisher=importlib.import_module("publish_ksei_reconciled_run"),
        hydrate=importlib.import_module("hydrate_reviewed_sources"),
    )


@pytest.mark.parametrize(
    "href",
    [
        "https://evil.example/a.pdf",
        "//evil.example/Announcement/Files/a.pdf",
        "/Announcement/Files/a.pdf?api_token=secret-test",
        "/private/a.pdf",
    ],
)
def test_public_source_url_cannot_redirect_collection_to_arbitrary_host(scripts, href):
    with pytest.raises(ValueError, match="unexpected_public_source"):
        scripts.source.source_url(href)


def test_source_cash_and_ex_date_are_not_recording_or_payment_date(scripts):
    text = (
        "Tanggal Ex Dividen di Pasar Regular & Pasar Negosiasi 19 Maret 2024\n"
        "Tanggal Pencatatan 20 Maret 2024\n"
        "Setiap 1 (Satu) saham akan mendapatkan dividen tunai sebesar Rp.49,89136"
    )
    session, value, _, _ = scripts.review.schedule_facts(text)
    assert session.isoformat() == "2024-03-19"
    assert value == Decimal("49.89136")


@pytest.mark.parametrize(
    "text",
    [
        "Tanggal Ex Dividen di Pasar Tunai 19 Maret 2024\n"
        "Setiap 1 (Satu) saham akan mendapatkan dividen tunai sebesar Rp.50",
        "Tanggal Ex Dividen di Pasar Regular & Pasar Negosiasi 19 Maret 2024\n"
        "Setiap 1 (Satu) saham akan mendapatkan dividen tunai sebesar USD.50",
        "Tanggal Ex Dividen di Pasar Regular & Pasar Negosiasi 19 Maret 2024\n"
        "Setiap 1 (Satu) saham akan mendapatkan dividen tunai sebesar Rp.1.747",
    ],
)
def test_foreign_currency_wrong_market_and_ambiguous_amount_require_review(scripts, text):
    with pytest.raises(ValueError):
        scripts.review.schedule_facts(text)


def test_changed_provider_event_retains_raw_prices_and_holds_ticker(scripts, monkeypatch):
    data, calendar, _ = sample_market(620)
    raw = data["DEMO-A"]
    target = raw.bars[-1].session
    raw = replace(raw, actions=(CorporateAction(target, "dividend", "99"),))

    def mismatch(*_):
        raise ValueError("dividend_provider_event_mismatch")

    monkeypatch.setattr(scripts.smoke, "reconcile_dividends", mismatch)
    prepared, mismatches = scripts.smoke.prepare_series({raw.ticker: raw}, (), calendar, target)
    assert mismatches == [raw.ticker]
    assert prepared[raw.ticker].bars == raw.bars
    assert prepared[raw.ticker].actions == raw.actions
    assert quality(prepared[raw.ticker], target, calendar) == "corporate_action_hold"


def test_unexpected_evidence_failure_is_not_silently_downgraded(scripts, monkeypatch):
    data, calendar, _ = sample_market(620)

    def mismatch(*_):
        raise ValueError("dividend_provider_basis_mismatch")

    monkeypatch.setattr(scripts.smoke, "reconcile_dividends", mismatch)
    with pytest.raises(ValueError, match="basis_mismatch"):
        scripts.smoke.prepare_series(data, (), calendar, calendar.sessions[-1].day)


def test_expired_forward_window_blocks_publication_before_secrets(scripts, monkeypatch):
    now = datetime.now(UTC)
    calendar = SimpleNamespace(next=lambda _: SimpleNamespace(opens_at=now - timedelta(days=1)))
    monkeypatch.setattr(scripts.publisher, "prepare", lambda _: (calendar, None, (), {}, {}, {}))
    monkeypatch.setattr(scripts.publisher, "local_env", lambda _: pytest.fail("secret read"))
    with pytest.raises(ValueError, match="window_elapsed"):
        scripts.publisher.reviewed_preflight(now)
