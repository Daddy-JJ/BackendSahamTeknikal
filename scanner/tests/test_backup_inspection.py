"""Inspection must fail closed without SQL/row/credential output or remote access."""

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def inspect_backup(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "supabase/scripts"))
    return importlib.import_module("inspect_backup_prompt")


def bundle(module, path):
    files = []
    for name in ("database.age", "roles.age"):
        archive = path / name
        archive.write_bytes(b"synthetic encrypted candidate")
        files.append({"file": name, "bytes": archive.stat().st_size,
                      "sha256": module.digest_file(archive), "decryption_verified": True})
    evidence = {"source_project_ref": module.PROJECT, "production_write": False,
                "status": "encrypted_candidate_decrypt_verified_restore_pending", "files": files}
    (path / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    return evidence


def test_bundle_rejects_corrupted_ciphertext(inspect_backup, tmp_path):
    bundle(inspect_backup, tmp_path)
    assert inspect_backup.validate_bundle(tmp_path)["production_write"] is False
    (tmp_path / "database.age").write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="archive_integrity_failed"):
        inspect_backup.validate_bundle(tmp_path)


def test_bundle_rejects_wrong_project_and_path(inspect_backup, tmp_path):
    evidence = bundle(inspect_backup, tmp_path)
    evidence["source_project_ref"] = "another-project"
    (tmp_path / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(RuntimeError, match="backup_evidence_guard_failed"):
        inspect_backup.validate_bundle(tmp_path)
    evidence["source_project_ref"] = inspect_backup.PROJECT
    evidence["files"][0]["file"] = "../database.age"
    (tmp_path / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(RuntimeError, match="backup_files_incomplete"):
        inspect_backup.validate_bundle(tmp_path)


def test_offline_inspection_cannot_connect_or_execute_sql(inspect_backup):
    command = inspect_backup.list_command()
    assert "--network=none" in command and "--read-only" in command
    assert "pg_restore" in command and command[-1] == "--list"
    assert "PGPASSWORD" not in command and "--dbname" not in command
    assert "--host" not in command and "--clean" not in command


TOC = """1; 0 0 EXTENSION - pgcrypto -
2; 0 0 EXTENSION - supabase_vault -
3; 1 1 TABLE public app_members postgres
4; 1 2 TABLE auth users supabase_auth_admin
5; 1 3 TABLE auth identities supabase_auth_admin
6; 0 2 TABLE DATA auth users supabase_auth_admin
7; 0 3 TABLE DATA auth identities supabase_auth_admin
"""


def test_metadata_only_and_required_auth_present(inspect_backup):
    result = inspect_backup.summarize(TOC, "CREATE ROLE anon;\nCREATE ROLE authenticated;\n")
    assert result["public_tables"] == ["app_members"]
    assert result["required_extensions"] == ["pgcrypto", "supabase_vault"]
    assert result["auth_users_data_entry_present"] is True
    assert result["auth_identities_data_entry_present"] is True
    assert result["role_definition_count"] == 2
    assert result["application_history_schema_present"] is False


def test_role_password_or_missing_auth_abort(inspect_backup):
    with pytest.raises(RuntimeError, match="unexpected_role_password_in_export"):
        inspect_backup.summarize(TOC, "ALTER ROLE private PASSWORD 'synthetic';")
    with pytest.raises(RuntimeError, match="required_application_or_auth_schema_missing"):
        inspect_backup.summarize("1; 1 1 TABLE public app_members postgres", "")
