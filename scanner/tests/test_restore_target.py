"""Local restore preflight cannot contact hosted DBs or expose network ports."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def target(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "supabase/scripts"))
    return importlib.import_module("check_restore_target")


def test_target_is_disposable_isolated_and_digest_pinned(target):
    command = target.start_command("idx-restore-check-" + "a" * 32,
                                   "supabase/postgres@sha256:" + "b" * 64)
    for flag in ("--network=none", "--read-only", "--rm", "--pull=never", "--cap-drop=ALL"):
        assert flag in command
    assert "/tmp:rw,size=536870912,mode=1777" in command
    assert "-p" not in command and "--publish" not in command and "--mount" not in command
    assert "--user" in command
    assert "listen_addresses=''" in command[-1]
    assert "supabase.com" not in repr(command)


def test_unrelated_container_or_mutable_image_is_rejected(target):
    with pytest.raises(RuntimeError, match="invalid_local_container_name"):
        target.start_command("production", "supabase/postgres@sha256:" + "b" * 64)
    with pytest.raises(RuntimeError, match="restore_image_digest_required"):
        target.start_command("idx-restore-check-" + "a" * 32, target.TAG)
