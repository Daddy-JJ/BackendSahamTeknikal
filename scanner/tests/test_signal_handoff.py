"""Offline safety checks for the development-only migration 007 handoff."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def handoff(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / "supabase/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "signal_handoff", scripts / "prepare_dev_signal_conflict_fix.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("url", [
    "https://hcjfxbynqzsaidlwvdfx.supabase.co",
    "https://another-project.supabase.co",
    "http://vgmkpsestahkfahzdtae.supabase.co",
])
def test_handoff_rejects_non_development_project(handoff, monkeypatch, url):
    monkeypatch.setattr(handoff, "local_env", lambda _: {"SUPABASE_URL": url})
    with pytest.raises(ValueError, match="development_project_mismatch"):
        handoff.main()


def test_handoff_rejects_migration_checksum_drift(handoff, monkeypatch, tmp_path):
    changed = tmp_path / "changed.sql"
    changed.write_text("begin;\nselect 1;\ncommit;\n", encoding="utf-8")
    monkeypatch.setattr(handoff, "MIGRATION", changed)
    with pytest.raises(ValueError, match="migration_checksum_mismatch"):
        handoff.render_fix()
