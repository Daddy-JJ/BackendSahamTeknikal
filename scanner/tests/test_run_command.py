"""Operational boundaries; no provider or database network in these tests."""

import json
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest

from idx_scanner import cli, run_command
from idx_scanner.fixtures import sample_market
from idx_scanner.providers import FetchRequest

REF = "abcdefghijklmnopqrst"


@pytest.fixture
def configured(monkeypatch):
    market, calendar, universe = sample_market(620)
    target = calendar.sessions[619]
    calendar, universe = replace(calendar, data_mode="live"), replace(universe, data_mode="live")
    requests = {
        t: FetchRequest(t, t, calendar.sessions[0].day, target.day, True) for t in universe.tickers
    }
    monkeypatch.setattr(run_command, "load_calendar", lambda _: calendar)
    monkeypatch.setattr(run_command, "load_universe", lambda *_: universe)
    monkeypatch.setattr(run_command, "load_requests", lambda *_: requests)
    monkeypatch.setattr(run_command, "utc_now", lambda: target.closes_at + timedelta(hours=3))
    monkeypatch.setattr(
        run_command, "SupabaseScanStore", lambda *_: pytest.fail("unexpected database IO")
    )
    monkeypatch.setattr(
        run_command, "make_provider", lambda *_: pytest.fail("unexpected provider IO")
    )
    return (
        SimpleNamespace(
            project_ref=REF,
            namespace="forward",
            provider="yfinance",
            execute=False,
            calendar=None,
            universe_metadata=None,
            universe_csv=None,
            mapping=None,
            start=calendar.sessions[0].day,
            target=target.day,
        ),
        calendar,
        universe,
        requests,
    )


def test_preflight_has_no_credentials_or_network(configured, monkeypatch):
    args, _, _, _ = configured
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    result = run_command.execute_run(args)
    assert result["status"] == "preflight_passed"
    assert result["executed"] is False and result["network_used"] is False


def test_fixture_context_cannot_be_published_by_live_command(configured, monkeypatch):
    args, calendar, _, _ = configured
    args.execute = True
    monkeypatch.setattr(
        run_command, "load_calendar", lambda _: replace(calendar, data_mode="fixture")
    )
    with pytest.raises(ValueError, match="live_context_required"):
        run_command.execute_run(args)


def test_target_project_mismatch_blocks_network(configured, monkeypatch):
    args, _, _, _ = configured
    args.execute = True
    monkeypatch.setenv("SUPABASE_URL", "https://different-project.supabase.co")
    with pytest.raises(ValueError, match="supabase_project_mismatch"):
        run_command.execute_run(args)


def test_incomplete_cross_section_blocks_network(configured):
    args, _, _, requests = configured
    requests.pop(next(iter(requests)))
    with pytest.raises(ValueError, match="complete_universe_mapping_required"):
        run_command.execute_run(args)


def test_execution_checks_database_mode_before_provider(configured, monkeypatch):
    args, _, _, _ = configured
    args.execute = True
    monkeypatch.setenv("SUPABASE_URL", f"https://{REF}.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-only")
    from idx_scanner.persistence import PersistenceError

    class Database:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def require_live_schema(self):
            raise PersistenceError("database_not_live")

    monkeypatch.setattr(run_command, "SupabaseScanStore", lambda *_: Database())
    with pytest.raises(PersistenceError, match="database_not_live"):
        run_command.execute_run(args)


@pytest.mark.parametrize("status,exit_code", [("complete", 0), ("partial", 3), ("failed", 3)])
def test_cli_reports_partial_as_non_success(status, exit_code, monkeypatch, capsys):
    monkeypatch.setattr(cli, "execute_run", lambda _: {"status": status, "executed": True})
    monkeypatch.setattr(
        "sys.argv",
        [
            "idx-scanner",
            "run",
            "--provider",
            "yfinance",
            "--calendar",
            "unused",
            "--universe-metadata",
            "unused",
            "--universe-csv",
            "unused",
            "--mapping",
            "unused",
            "--start",
            "2030-01-01",
            "--target",
            "2030-01-02",
            "--project-ref",
            REF,
        ],
    )
    assert cli.main() == exit_code
    assert json.loads(capsys.readouterr().out)["status"] == status
