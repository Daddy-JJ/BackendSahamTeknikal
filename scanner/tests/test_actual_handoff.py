"""Offline checks only: never read local credentials or connect to Supabase."""

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def handoff(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / "supabase/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "actual_handoff", scripts / "prepare_dev_actual_setup.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The helper import is cached but contains no env loading or network IO.
    assert "prepare_dev_setup" in sys.modules
    return module


@pytest.mark.parametrize("url", [
    "https://hcjfxbynqzsaidlwvdfx.supabase.co",
    "https://another-project.supabase.co",
    "http://vgmkpsestahkfahzdtae.supabase.co",
    "",
])
def test_handoff_ref_guard(handoff, monkeypatch, url):
    monkeypatch.setattr(handoff, "local_env", lambda _: {"SUPABASE_URL": url})
    with pytest.raises(ValueError, match="development_project_mismatch"):
        handoff.main()


def test_handoff_rejects_invalid_owner(handoff):
    with pytest.raises(ValueError):
        handoff.render_setup("not-a-uuid")
