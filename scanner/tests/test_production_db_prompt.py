"""Credential containment and read-only guards, without a remote DB connection."""

import importlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

IMAGE = "postgres@sha256:" + "a" * 64
SECRET = "dummy-sensitive-password"


@pytest.fixture
def prompt(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "supabase/scripts"))
    return importlib.import_module("check_production_db_prompt")


def mocked_runner(monkeypatch, prompt, response):
    calls = []

    def run(args, **kwargs):
        observed = dict(kwargs)
        if "env" in kwargs:
            observed["password_at_invocation"] = kwargs["env"].get("PGPASSWORD")
        calls.append((args, observed))
        if "rm" in args:
            return SimpleNamespace(returncode=0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(prompt.subprocess, "run", run)
    return calls


def test_password_contained_read_only_and_client_removed(prompt, monkeypatch):
    calls = mocked_runner(monkeypatch, prompt, SimpleNamespace(
        returncode=0, stdout=json.dumps({"project_ref": prompt.PROJECT,
                                        "database": "postgres", "read_only": True,
                                        "data_mode": "live"}), stderr=""))
    report = prompt.probe(SECRET, IMAGE)
    args, kwargs = calls[0]
    assert SECRET not in " ".join(args)
    assert kwargs["password_at_invocation"] == SECRET
    assert "PGPASSWORD" not in kwargs["env"]  # removed from child env copy after return
    assert "--pull=never" in args and IMAGE in args and "--read-only" in args
    assert kwargs["env"]["PGSSLMODE"] == "verify-full"
    assert "BEGIN READ ONLY;" in kwargs["input"] and "ROLLBACK;" in kwargs["input"]
    assert SECRET not in json.dumps(report)
    client = args[args.index("--name") + 1]
    assert calls[1][0] == prompt.docker("rm", "--force", client)


def test_raw_driver_error_is_not_exposed(prompt, monkeypatch):
    mocked_runner(monkeypatch, prompt, SimpleNamespace(
        returncode=2, stdout="", stderr=f"password authentication failed: {SECRET}"))
    with pytest.raises(RuntimeError, match="^authentication_failed$"):
        prompt.probe(SECRET, IMAGE)


def test_timeout_removes_only_own_temporary_client(prompt, monkeypatch):
    calls = mocked_runner(monkeypatch, prompt, subprocess.TimeoutExpired("docker", 60))
    with pytest.raises(subprocess.TimeoutExpired):
        prompt.probe(SECRET, IMAGE)
    assert len(calls) == 2
    assert calls[1][0][-1].startswith("idx-db-readonly-")
    assert SECRET not in " ".join(calls[1][0])


def test_fixture_target_fails_guard(prompt, monkeypatch):
    mocked_runner(monkeypatch, prompt, SimpleNamespace(
        returncode=0, stdout=json.dumps({"project_ref": prompt.PROJECT,
                                        "database": "postgres", "read_only": True,
                                        "data_mode": "fixture"}), stderr=""))
    with pytest.raises(RuntimeError, match="^production_read_only_guard_failed$"):
        prompt.probe(SECRET, IMAGE)


def test_noninteractive_prompt_refuses_password(prompt, monkeypatch, capsys):
    monkeypatch.setattr(prompt, "image_digest", lambda: IMAGE)
    monkeypatch.setattr(prompt.sys, "argv", ["check_production_db_prompt.py",
                                            "--ca-cert", "test-public-ca.crt"])
    monkeypatch.setattr(prompt, "validate_ca_cert", lambda path: path)
    monkeypatch.setattr(prompt.sys.stdin, "isatty", lambda: False)

    def forbidden(*args, **kwargs):
        pytest.fail("noninteractive terminal must never request a password")

    monkeypatch.setattr(prompt.getpass, "getpass", forbidden)
    assert prompt.main() == 1
    assert "run_in_local_interactive_terminal" in capsys.readouterr().out


def test_unpinned_or_unexpected_image_rejected(prompt, monkeypatch):
    monkeypatch.setattr(prompt.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout="other@sha256:" + "b" * 64))
    with pytest.raises(RuntimeError, match="^postgres_client_image_missing$"):
        prompt.image_digest()


def test_tls_preflight_sends_no_password_or_sql(prompt, monkeypatch, tmp_path):
    monkeypatch.setenv("PGPASSWORD", SECRET)
    cert = tmp_path / "public-ca.crt"
    calls = mocked_runner(monkeypatch, prompt, SimpleNamespace(
        returncode=2, stdout="", stderr="fe_sendauth: no password supplied"))
    report = prompt.probe("", IMAGE, cert, tls_only=True)
    args, kwargs = calls[0]
    assert kwargs["input"] == ""
    assert kwargs["password_at_invocation"] is None
    assert kwargs["env"]["PGSSLROOTCERT"] == "/run/db-root-ca.pem"
    assert f"type=bind,src={cert},dst=/run/db-root-ca.pem,readonly" in args
    assert report["tls_verified"] is True and report["password_tested"] is False
    assert report["database_query_executed"] is False


@pytest.mark.parametrize(("stderr", "expected"), [
    ("SSL error: certificate verify failed", "tls_verification_failed"),
    ('server certificate does not match host name "host"', "tls_hostname_mismatch"),
    ('root certificate file "file" does not exist', "tls_ca_missing"),
    ("SSL connection has been closed unexpectedly", "tls_connection_failed"),
    ("password authentication failed", "authentication_failed"),
    ("Tenant or user not found", "pooler_target_not_found"),
])
def test_driver_error_classification(prompt, stderr, expected):
    assert prompt.driver_failure(stderr) == expected


def test_private_key_cannot_be_mounted_as_public_ca(prompt, tmp_path):
    path = tmp_path / "bad.crt"
    path.write_text("-----BEGIN CERTIFICATE-----\n-----BEGIN PRIVATE KEY-----\n")
    with pytest.raises(RuntimeError, match="^ca_certificate_invalid$"):
        prompt.validate_ca_cert(path)


def test_missing_ca_refuses_password_prompt(prompt, monkeypatch, capsys):
    monkeypatch.setattr(prompt, "image_digest", lambda: IMAGE)
    monkeypatch.setattr(prompt.sys, "argv", ["check_production_db_prompt.py"])

    def forbidden(*args, **kwargs):
        pytest.fail("missing CA must be rejected before requesting a password")

    monkeypatch.setattr(prompt.getpass, "getpass", forbidden)
    assert prompt.main() == 1
    assert "production_ca_certificate_required" in capsys.readouterr().out
