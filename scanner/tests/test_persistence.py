import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from idx_scanner.engine import scan
from idx_scanner.fixtures import sample_market
from idx_scanner.models import ScanState, canonical_json
from idx_scanner.persistence import (
    PersistenceError,
    SupabaseScanStore,
    market_series_envelope,
    scan_envelope,
    signal_from_snapshot,
)

SECRET = "test-only-never-real-service-token"


@pytest.fixture(scope="module")
def result():
    series, calendar, universe = sample_market(620)
    day = calendar.sessions[619]
    return scan(
        series, day.day, calendar, universe, day.closes_at + timedelta(hours=3), ScanState()
    )


def store(handler):
    return SupabaseScanStore(
        "https://fixture-project.supabase.co",
        SECRET,
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    )


def test_envelope_and_snapshot_roundtrip_do_not_change_engine_values(result):
    payload = scan_envelope(result, "forward", "fixture")
    assert payload["p_run"]["coverage_total"] == 5
    for original, snapshot in zip(result.signals, payload["p_signals"], strict=True):
        assert signal_from_snapshot(snapshot) == original
    with pytest.raises(ValueError, match="mixed_fixture_live"):
        scan_envelope(result, "forward", "live")


def test_atomic_rpc_retry_uses_identical_payload_and_safe_headers(result):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        assert request.url.path == "/rest/v1/rpc/publish_scan"
        assert request.headers["apikey"] == SECRET
        assert "authorization" not in request.headers
        if len(sent) == 1:
            raise httpx.ReadTimeout("could contain " + SECRET)
        return httpx.Response(200, json={"run_id": "uuid-from-rpc", "replayed": True})

    with store(handler) as db:
        assert db.publish(result, data_mode="fixture")["replayed"]
    assert sent[0] == sent[1]


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "database_unauthorized"),
        (403, "database_forbidden"),
        (409, "database_conflict"),
        (302, "database_request_failed"),
    ],
)
def test_error_payload_and_redirect_never_leak_credentials(result, status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text=SECRET, headers={"location": "https://evil.invalid"})

    with store(handler) as db:
        with pytest.raises(PersistenceError, match=code) as error:
            db.publish(result, data_mode="fixture")
        assert SECRET not in str(error.value) + repr(db)
    assert len(calls) == 1


def test_retry_is_bounded(result):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503, text=SECRET)

    with store(handler) as db:
        with pytest.raises(PersistenceError, match="database_request_failed"):
            db.publish(result, data_mode="fixture")
    assert len(calls) == 3


def test_paginated_reload_preserves_original_snapshots_and_fractal_guards(result):
    # Small page size proves continuation; through-session must exclude future state.
    original = sorted(result.signals, key=lambda s: s.id)
    snapshots = json.loads(canonical_json(original))
    sent = []

    def handler(request):
        q = request.url.params
        sent.append(q)
        assert q["session_date"] == "lte." + result.session.isoformat()
        assert q["namespace"] == "eq.forward" and q["data_mode"] == "eq.fixture"
        cursor = q.get("id", "gt.")[3:]
        page = [s for s in snapshots if s["id"] > cursor][:2]
        return httpx.Response(200, json=[{"id": s["id"], "snapshot": s} for s in page])

    with store(handler) as db:
        state = db.load_state(through_session=result.session, data_mode="fixture", page_size=2)
    assert list(state.signals.values()) == original
    assert len(sent) >= 2
    assert len(state.fractal_guards) == sum(bool(s.candidate.fractal_id) for s in original)


def test_future_snapshot_or_broken_pagination_rejected(result):
    snapshot = json.loads(
        canonical_json(replace(result.signals[0], session=result.session + timedelta(days=1)))
    )
    with store(
        lambda _: httpx.Response(200, json=[{"id": snapshot["id"], "snapshot": snapshot}])
    ) as db:
        with pytest.raises(PersistenceError, match="database_invalid_snapshot"):
            db.load_state(through_session=result.session, data_mode="fixture")


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://fixture-project.supabase.co",
        "https://fixture-project.supabase.co@evil.invalid",
        "https://fixture-project.supabase.co?token=value",
    ],
)
def test_service_key_only_sent_to_explicit_supabase_origin(url):
    with pytest.raises(PersistenceError, match="invalid_supabase_origin"):
        SupabaseScanStore(url, SECRET)


def test_market_revision_adapter_keeps_content_digest_and_retries_safely():
    series, _, _ = sample_market(620)
    source = replace(series["DEMO-A"], fetched_at=datetime(2030, 1, 2, tzinfo=UTC))
    body = market_series_envelope(source, namespace="forward", data_mode="fixture")
    assert body["p_record"]["input_digest"] == source.input_digest
    assert "fetched_at" not in body["p_record"]["snapshot"]
    assert "provider_version" not in body["p_record"]["snapshot"]
    calls = []

    def handler(request):
        assert request.url.path == "/rest/v1/rpc/ingest_market_series"
        assert request.headers["apikey"] == SECRET
        assert "authorization" not in request.headers
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            raise httpx.ReadTimeout("secret-safe")
        return httpx.Response(200, json={"revision_id": "saved-revision", "replayed": True})

    with store(handler) as db:
        assert db.ingest_series(source, data_mode="fixture") == {
            "revision_id": "saved-revision",
            "replayed": True,
        }
    assert calls == [body, body]
    with pytest.raises(ValueError, match="mixed_fixture_live"):
        market_series_envelope(source, namespace="forward", data_mode="live")
    missing = replace(source, bars=())
    assert (
        market_series_envelope(missing, namespace="forward", data_mode="fixture")["p_record"][
            "snapshot"
        ]["bars"]
        == []
    )


REVISION_ID = "12345678-1234-4234-8234-123456789012"


def revision_response():
    series, _, _ = sample_market(3)
    source = replace(series["DEMO-A"], fetched_at=datetime(2030, 1, 2, tzinfo=UTC))
    record = market_series_envelope(source, namespace="forward", data_mode="fixture")["p_record"]
    return source, {**record, "revision_id": REVISION_ID}


def test_read_revision_checks_exact_digest_and_context():
    source, response = revision_response()

    def handler(request):
        assert request.url.path == "/rest/v1/rpc/read_market_series"
        assert json.loads(request.content) == {"p_revision_id": REVISION_ID}
        return httpx.Response(200, json=response)

    with store(handler) as db:
        restored = db.load_series(
            REVISION_ID, data_mode="fixture", expected_input_digest=source.input_digest
        )
    assert restored == source


@pytest.mark.parametrize(
    "corruption",
    [
        "bar",
        "namespace",
        "data_mode",
        "revision_id",
        "input_digest",
        "metadata",
        "time",
        "malformed",
    ],
)
def test_read_revision_rejects_corruption_without_secret_leak(corruption):
    source, response = revision_response()
    if corruption == "bar":
        bar = json.loads(response["bar_sources"][0])
        bar["close"] += 1
        response["bar_sources"][0] = json.dumps(bar)
    elif corruption == "metadata":
        response["metadata_source"] = SECRET
    elif corruption == "time":
        response["fetched_at"] = "2030-01-02T00:00:00"
    elif corruption == "malformed":
        response = []
    else:
        response[corruption] = SECRET
    with store(lambda _: httpx.Response(200, json=response)) as db:
        with pytest.raises(PersistenceError, match="database_invalid_market_revision") as error:
            db.load_series(
                REVISION_ID, data_mode="fixture", expected_input_digest=source.input_digest
            )
    assert SECRET not in str(error.value)
