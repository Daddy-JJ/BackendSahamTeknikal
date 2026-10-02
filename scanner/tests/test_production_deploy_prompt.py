"""Release guards and credential containment; no remote connection or deployment."""

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "supabase/scripts"))
    return importlib.import_module("deploy_production_prompt")


def test_cli_password_only_in_child_environment(module, monkeypatch):
    secret = "synthetic-password&never-log"
    calls = []

    def run(args, **kwargs):
        calls.append((args, dict(kwargs), kwargs["env"].get("PGPASSWORD")))
        return SimpleNamespace(returncode=0, stdout="completed", stderr="")

    monkeypatch.setattr(module.subprocess, "run", run)
    module.cli_run(Path("supabase.exe"), ["db", "push", "--skip-vault"], secret,
                   Path("C:/public certificate.crt"))
    args, kwargs, password = calls[0]
    assert secret not in " ".join(args)
    assert password == secret
    assert "PGPASSWORD" not in kwargs["env"]
    assert "SUPABASE_DB_PASSWORD" not in kwargs["env"]
    uri = args[args.index("--db-url") + 1]
    assert "sslmode=verify-full" in uri and "sslrootcert=" in uri
    assert "--include-seed" not in args and "--include-roles" not in args


def test_cli_error_does_not_expose_raw_output(module, monkeypatch):
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=1, stdout="raw secret", stderr="raw secret"))
    with pytest.raises(RuntimeError, match="^supabase_cli_stage_failed$"):
        module.cli_run(Path("supabase.exe"), ["db", "push"], "synthetic", Path("public.crt"))


def test_unexpected_history_stops_before_cli(module, monkeypatch):
    monkeypatch.setattr(module, "state", lambda *args: ({}, ["202609290002"]))
    monkeypatch.setattr(module, "cli_run", lambda *args: pytest.fail("CLI must not run"))
    with pytest.raises(RuntimeError, match="^history_not_exact_release_prefix$"):
        module.deploy(Path("supabase.exe"), Path("public.crt"), "synthetic", {})


def test_dry_run_extra_seed_or_migration_stops_push(module, monkeypatch):
    monkeypatch.setattr(module, "state", lambda *args: ({}, ["202609290001"]))
    calls = []

    def cli_run(cli, args, *rest):
        calls.append(args)
        return "202609290002_market_series_revisions.sql\n202610020008_unreviewed.sql"

    monkeypatch.setattr(module, "cli_run", cli_run)
    with pytest.raises(RuntimeError, match="^dry_run_not_exact_pending_chain$"):
        module.deploy(Path("supabase.exe"), Path("public.crt"), "synthetic", {})
    assert len(calls) == 1 and "--dry-run" in calls[0]


def test_exact_pending_chain_push_then_history_readback(module, monkeypatch):
    manifest = json.loads((module.ROOT / "supabase/release-manifest.json").read_text("utf-8"))
    versions = [m["version"] for m in manifest["migrations"]]
    states = iter([({}, versions[:1]), ({"verified_at_utc": "synthetic-clock"}, versions)])
    monkeypatch.setattr(module, "state", lambda *args: next(states))
    calls = []

    def cli_run(cli, args, *rest):
        calls.append(args)
        return "\n".join(m["file"] for m in manifest["migrations"][1:])

    monkeypatch.setattr(module, "cli_run", cli_run)
    report = {}
    module.deploy(Path("supabase.exe"), Path("public.crt"), "synthetic", report)
    assert calls == [["db", "push", "--dry-run", "--skip-vault"],
                     ["db", "push", "--skip-vault", "--yes"]]
    assert report["migration_history_cli_verified"] is True
    assert report["status"] == "cli_release_completed_smoke_pending"


def test_foundation_mismatch_stops_history_repair(module, monkeypatch):
    monkeypatch.setattr(module, "state", lambda *args: ({}, []))
    monkeypatch.setattr(module, "query", lambda *args: "columns|0|wrong")
    monkeypatch.setattr(module, "cli_run", lambda *args: pytest.fail("history repair forbidden"))
    with pytest.raises(RuntimeError, match="^foundation_ten_group_mismatch$"):
        module.deploy(Path("supabase.exe"), Path("public.crt"), "synthetic", {})
