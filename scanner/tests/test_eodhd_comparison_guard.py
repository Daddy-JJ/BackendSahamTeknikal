"""Bounded read-only discovery and safe errors; synthetic HTTP responses only."""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def helper(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / "supabase/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "eodhd_comparison_guard_test", scripts / "probe_eodhd_comparison.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_entitlement_error_does_not_echo_token_or_body_or_retry(helper):
    marker = "synthetic-token-never-echo"
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(403, text=marker)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        report = helper.discover(client, marker)
    assert len(calls) == 1
    assert report["status"] == "auth_or_entitlement_denied"
    assert marker not in json.dumps(report)
    assert not report["production_write"] and not report["provider_changed"]


def test_absent_indonesia_stops_before_symbol_or_price_requests(helper):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=[{"Code": "US", "Currency": "USD"}])
        )
    ) as client:
        report = helper.discover(client, "synthetic")
    assert report["http_requests"] == 1
    assert report["status"] == "blocked_indonesia_exchange_not_in_supported_list"


def test_indonesia_discovery_filters_identity_fields_and_never_fetches_prices(helper):
    paths = []

    def respond(request):
        paths.append(request.url.path)
        rows = (
            [{"Code": "JK", "Name": "Jakarta Exchange", "Currency": "IDR"}]
            if "exchanges-list" in request.url.path
            else [{"Code": "BBCA", "Name": "Synthetic", "untrusted_field": "not_logged"}]
        )
        return httpx.Response(200, json=rows)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        report = helper.discover(client, "synthetic")
    assert len(paths) == 2
    assert report["status"] == "identities_pending_review_before_price_requests"
    assert "not_logged" not in json.dumps(report)
    assert report["price_comparison_completed"] is False
