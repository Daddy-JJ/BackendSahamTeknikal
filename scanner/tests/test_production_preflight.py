"""Prove production readiness probes cannot accidentally mutate via HTTP."""

import importlib
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def preflight(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "supabase/scripts"))
    return importlib.import_module("preflight_production")


def test_production_probe_is_get_only_and_sanitized(preflight):
    requests = []

    def respond(request):
        requests.append(request)
        assert request.method == "GET"
        assert request.url.host == f"{preflight.PROD_REF}.supabase.co"
        assert request.content == b""
        path = request.url.path
        if path.endswith("deployment_settings"):
            return httpx.Response(200, json=[{"data_mode": "live"}])
        if path.endswith("app_members"):
            return httpx.Response(200, json=[{"role": "owner", "enabled": True}])
        if path.endswith("scan_publish_capabilities"):
            return httpx.Response(200, json={"deadline_version": 1})
        return httpx.Response(200, json=[], headers={"Content-Range": "*/0"})

    report = preflight.inspect({"SUPABASE_URL": preflight.PROD_URL,
                                "SUPABASE_SECRET_KEY": "test-secret-never-print",
                                "APP_OWNER_USER_ID": "test-owner-never-print"},
                               httpx.MockTransport(respond))
    assert requests
    assert report["checks"]["live_mode"] is True
    assert report["checks"]["configured_owner_enabled"] is True
    assert report["checks"]["scan_runs_fixture_count"] == "0"
    assert report["rls_smoke_proven"] is False
    assert report["deployment_authorized"] is False
    assert "never-print" not in str(report)


def test_preflight_rejects_wrong_project_before_network(preflight):
    with pytest.raises(ValueError, match="production_project_mismatch"):
        preflight.inspect({"SUPABASE_URL": "https://vgmkpsestahkfahzdtae.supabase.co"})


def test_preflight_does_not_follow_redirect_or_claim_missing_schema_as_rls(preflight):
    calls = []

    def respond(request):
        calls.append(request)
        if request.url.path.endswith("deployment_settings"):
            return httpx.Response(307, headers={"Location": "https://example.invalid/"})
        return httpx.Response(404, json={"code": "PGRST205", "message": "private detail"})

    report = preflight.inspect({"SUPABASE_URL": preflight.PROD_URL,
                                "SUPABASE_SECRET_KEY": "test"}, httpx.MockTransport(respond))
    assert all(r.url.host == f"{preflight.PROD_REF}.supabase.co" for r in calls)
    assert report["checks"]["live_mode"] is False
    assert report["checks"]["actual_trades"]["code"] == "PGRST205"
    assert report["rls_smoke_proven"] is False
    assert "private detail" not in str(report)
