"""Local checks for the dev owner JWT probe; no remote Supabase calls."""

import importlib.util
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "supabase/scripts/verify_dev_owner_rls.py"
SPEC = importlib.util.spec_from_file_location("verify_dev_owner_rls", SCRIPT)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def test_dashboard_pat_is_rejected_before_network(monkeypatch):
    monkeypatch.setattr(probe.getpass, "getpass", lambda _: "sbp_dashboard_token")
    monkeypatch.setattr(probe.httpx, "Client", lambda **_: pytest.fail("network attempted"))
    with pytest.raises(ValueError, match="app_auth_jwt_required_not_dashboard_access_token"):
        probe.owner_jwt("owner", "publishable", True)


@pytest.mark.parametrize(
    ("response_status", "response_uid", "expected"),
    [
        (401, None, "owner_jwt_validation_status_401"),
        (200, "another-user", "signed_in_user_is_not_dev_owner"),
        (200, "owner", None),
    ],
)
def test_auth_jwt_must_validate_as_dev_owner(
    monkeypatch, response_status, response_uid, expected
):
    token = "header.payload.signature"
    monkeypatch.setattr(probe.getpass, "getpass", lambda _: token)
    client_class = httpx.Client
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(response_status, json={"id": response_uid})

    def client_factory(**kwargs):
        return client_class(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(probe.httpx, "Client", client_factory)
    if expected:
        with pytest.raises(ValueError, match=expected):
            probe.owner_jwt("owner", "publishable", True)
    else:
        assert probe.owner_jwt("owner", "publishable", True) == token
    assert len(requests) == 1
    assert str(requests[0].url) == probe.DEV_URL + "/auth/v1/user"
    assert requests[0].headers["authorization"] == "Bearer " + token
    assert requests[0].headers["apikey"] == "publishable"
