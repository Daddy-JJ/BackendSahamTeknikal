"""Guard checks plus opt-in native PG17 restore with synthetic records only."""

import importlib
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def restore(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "supabase/scripts"))
    return importlib.import_module("restore_backup_prompt")


def test_catalog_wrapper_preserves_read_only_and_all_groups(restore):
    sql = (restore.ROOT / "supabase/operations/foundation_catalog.sql").read_text("utf-8")
    wrapped = restore.catalog_query(sql)
    assert "begin read only;" in wrapped and wrapped.endswith("rollback;\n")
    assert "select json_agg(row_to_json(q))" in wrapped
    with pytest.raises(RuntimeError, match="catalog_query_changed_review_required"):
        restore.catalog_query("select 1;")


def test_catalog_missing_or_different_group_fails(restore):
    expected = [{"category": str(n), "sha256": "a", "object_count": 1} for n in range(10)]
    assert restore.compare_catalog(expected, expected) == []
    changed = [{**row} for row in expected]
    changed[0]["sha256"] = "b"
    assert restore.compare_catalog(changed, expected) == ["0"]
    with pytest.raises(RuntimeError, match="restore_catalog_incomplete"):
        restore.compare_catalog(changed[:-1], expected)


def test_sql_diagnostic_never_returns_raw_secret_or_sql(restore):
    result = restore.safe_sql_diagnostic(
        'ERROR: 42704: unrecognized configuration parameter "synthetic-private-value"\n'
        'STATEMENT: ALTER ROLE private SET private = synthetic-secret;')
    assert result["sqlstate"] == "42704"
    assert result["category"] == "unsupported_role_configuration"
    assert "synthetic" not in repr(result)
    result = restore.safe_sql_diagnostic(b'ERROR: 42501: must have ADMIN option on role private')
    assert result["category"] == "grantor_missing_admin_option"
    assert result["sqlstate"] == "42501"


def test_role_diagnostic_reports_only_line_and_statement_enum(restore):
    result = restore.safe_sql_diagnostic(
        'psql:<stdin>:2: ERROR: 42501: permission denied to grant role secret-role',
        '-- private archive\nGRANT private TO other GRANTED BY hidden;\n')
    assert result == {"sqlstate": "42501", "category": "role_grant_permission_denied",
                      "statement_line": 2, "statement_kind": "grant_role_explicit_grantor"}
    assert "private" not in repr(result) and "hidden" not in repr(result)


def test_local_sql_verbose_error_is_sanitized(restore, monkeypatch):
    from types import SimpleNamespace

    calls = []

    def failing(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1, stderr="ERROR: 42710: role private already exists",
                               stdout="")

    monkeypatch.setattr(restore, "run", failing)
    with pytest.raises(restore.RestoreFailure) as failure:
        restore.local_sql("idx-restore-check-" + "a" * 32, "synthetic SQL")
    assert "VERBOSITY=verbose" in calls[0]
    assert calls[0][-2:] == ("-f", "-")
    assert failure.value.details["sqlstate"] == "42710"
    assert failure.value.details["category"] == "object_already_exists"
    assert "private" not in repr(failure.value.details)


def test_bootstrap_restore_preserves_attributes_and_grantor(restore):
    sql = ('CREATE ROLE source_boot;\nALTER ROLE source_boot WITH SUPERUSER LOGIN;\n'
           'GRANT pg_monitor TO member GRANTED BY source_boot;\n')
    changed = restore.bootstrap_roles_sql(sql, "source_boot")
    assert changed.count("\n") == sql.count("\n")
    assert changed.splitlines()[1:] == sql.splitlines()[1:]
    assert restore.bootstrap_roles_sql(sql, None) == sql
    for name in ("source_boot;DROP", restore.OPERATOR, "missing"):
        with pytest.raises(RuntimeError):
            restore.bootstrap_roles_sql(sql, name)
    with pytest.raises(RuntimeError):
        restore.bootstrap_roles_sql(sql.replace("SUPERUSER", "NOSUPERUSER"), "source_boot")


@pytest.mark.skipif(os.environ.get("IDX_NATIVE_RESTORE_TEST") != "1",
                    reason="Native disposable Docker test requires explicit invocation")
def test_native_roles_error_reports_state_and_cleans_target(restore, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(restore, "validate_bundle", lambda _: {"files": [
        {"file": "roles.age", "plaintext_bytes": 1}]})

    def synthetic_roles(path, _):
        assert path.name == "roles.age"
        return (b"CREATE ROLE synthetic_test;\n"
                b"ALTER ROLE synthetic_test SET not_a_server_setting='synthetic-private';")

    monkeypatch.setattr(restore, "decrypt_memory", synthetic_roles)
    assert restore.check_roles(tmp_path) == 1
    output = capsys.readouterr().out
    report = json.loads(output[output.index("{\n"):])
    assert report["failure_stage"] == "local_roles_restore"
    assert report["sql_diagnostic"]["sqlstate"] == "42704"
    assert report["sql_diagnostic"]["category"] == "unsupported_role_configuration"
    assert report["sql_diagnostic"]["statement_line"] == 2
    assert report["sql_diagnostic"]["statement_kind"] == "alter_role_setting"
    assert report["temporary_target_removed"] is True
    assert "synthetic-private" not in output
    assert report["logical_restore_completed"] is False


@pytest.mark.skipif(os.environ.get("IDX_NATIVE_RESTORE_TEST") != "1",
                    reason="Native disposable Docker test requires explicit invocation")
def test_native_nonbootstrap_superuser_grantor_requires_admin(restore):
    name = "idx-restore-check-" + uuid4().hex
    try:
        restore.launch_target(name)
        restore.local_sql(name, "CREATE ROLE original_bootstrap SUPERUSER;\n"
                          "CREATE ROLE restore_member;\n")
        with pytest.raises(restore.RestoreFailure) as error:
            restore.local_sql(name, "GRANT pg_monitor TO restore_member "
                              "GRANTED BY original_bootstrap;\n")
        assert error.value.details["sqlstate"] == "42501"
        restore.local_sql(name, "GRANT pg_monitor TO restore_member "
                          f"GRANTED BY {restore.OPERATOR};\n")
    finally:
        assert restore.run("rm", "--force", name, text=True).returncode == 0


@pytest.mark.skipif(os.environ.get("IDX_NATIVE_RESTORE_TEST") != "1",
                    reason="Native disposable Docker test requires explicit invocation")
def test_native_pg17_full_synthetic_dump_restores_and_cleans_target(
        restore, monkeypatch, tmp_path, capsys):
    # Neither this source nor the target has a network or published ports.
    source = "idx-restore-check-" + uuid4().hex
    source_operator = "idx_source_operator"
    command = list(restore.start_command(source, restore.IMAGE))
    command[-1] = command[-1].replace("-U postgres ", f"-U {source_operator} ")

    def source_sql(sql):
        result = restore.run("exec", "-i", source, "psql", "-X", "-qAt", "-v",
                             "ON_ERROR_STOP=1", "-h", "/tmp", "-U", source_operator,
                             "-d", "postgres", input=sql, text=True, timeout=60)
        assert result.returncode == 0, "synthetic source SQL failed"
        return result.stdout

    try:
        assert restore.run(*command, text=True).returncode == 0
        for _ in range(60):
            if restore.run("exec", source, "pg_isready", "-h", "/tmp", "-U", source_operator,
                           text=True).returncode == 0:
                break
            time.sleep(1)
        else:
            pytest.fail("synthetic source not ready")
        source_sql("""CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN;
          CREATE ROLE service_role NOLOGIN BYPASSRLS;
          CREATE SCHEMA auth;
          CREATE TABLE auth.users(id uuid PRIMARY KEY);
          CREATE TABLE auth.identities(id uuid PRIMARY KEY, user_id uuid REFERENCES auth.users);
          CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
            SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid;
          $$;
          GRANT USAGE ON SCHEMA auth,public TO anon,authenticated,service_role;
        """)
        # Source OID10 can grant a built-in role without an ADMIN membership.
        # Preserve that grantor when restoring into a second independent cluster.
        source_sql(f"GRANT pg_monitor TO authenticated GRANTED BY {source_operator};")
        root = restore.ROOT
        source_sql((root / "supabase/migrations/202609290001_scan_foundation.sql")
                   .read_text("utf-8"))
        source_sql("""INSERT INTO auth.users VALUES('11111111-1111-4111-8111-111111111111');
          INSERT INTO auth.identities VALUES('22222222-2222-4222-8222-222222222222',
            '11111111-1111-4111-8111-111111111111');
          INSERT INTO public.app_members(user_id) VALUES('11111111-1111-4111-8111-111111111111');
        """)
        query = (root / "supabase/operations/foundation_catalog.sql").read_text("utf-8")
        snapshot = json.loads(source_sql(restore.catalog_query(query)))
        database = restore.run("exec", source, "pg_dump", "--format=custom", "-h", "/tmp",
                               "-U", source_operator, "-d", "postgres", timeout=60)
        roles = restore.run("exec", source, "pg_dumpall", "--roles-only", "--no-role-passwords",
                            "-h", "/tmp", "-U", source_operator, timeout=60)
        assert database.returncode == roles.returncode == 0
        # Replace only secret-input/archive provenance with synthetic in-memory data.
        # main still creates a second real container, restores roles/full dump, queries
        # its catalog/owner linkage/counts and removes it.
        (tmp_path / "supabase/operations").mkdir(parents=True)
        (tmp_path / "docs/evidence").mkdir(parents=True)
        (tmp_path / "supabase/operations/foundation_catalog.sql").write_text(query, "utf-8")
        (tmp_path / "docs/evidence/foundation001-production-20261001.json").write_text(
            json.dumps({"observed_production": snapshot}), "utf-8")
        monkeypatch.setattr(restore, "ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["restore", "--backup-directory", str(tmp_path),
                                        "--source-bootstrap-role", source_operator])
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(restore, "validate_bundle", lambda _: {"files": [
            {"file": "database.age", "plaintext_bytes": len(database.stdout)},
            {"file": "roles.age", "plaintext_bytes": len(roles.stdout)}]})
        monkeypatch.setattr(restore, "decrypt_memory", lambda path, _: (
            database.stdout if path.name == "database.age" else roles.stdout))
        exit_code = restore.main()
        output = capsys.readouterr().out
        report = json.loads(output[output.index("{\n"):])
        assert exit_code == 0, json.dumps({k: report.get(k) for k in (
            "status", "failure", "failure_stage", "catalog_differences")})
        assert report["logical_restore_completed"] is True
        assert report["source_grantor_clauses_preserved"] is True
        assert report["bootstrap_create_represented_by_initdb"] is True
        assert report["local_bootstrap_oid10_verified"] is True
        assert report["catalog_matches_prior_production"] is True
        assert report["owner_auth_linkage_verified"] is True
        assert report["table_counts"]["app_members"] == 1
        assert report["auth_identity_count"] == 1
        assert report["temporary_target_removed"] is True
        assert report["production_write"] is False
        assert report["restore_verified"] is False  # recovery gates are intentionally still open
    finally:
        restore.run("rm", "--force", source, text=True)
