"""Native local release guards and rollback, without secrets or hosted connection."""

import importlib
import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "supabase/scripts"))
    return importlib.import_module("restore_backup_prompt"), importlib.import_module(
        "rehearse_restored_release"
    )


def test_release_checksums_and_remote_name_fail_closed(modules, tmp_path):
    restore, rehearsal = modules
    assert len(rehearsal.checked_release(restore.ROOT)) == 8
    shutil.copytree(restore.ROOT / "supabase/migrations", tmp_path / "supabase/migrations")
    shutil.copy2(
        restore.ROOT / "supabase/release-manifest.json", tmp_path / "supabase/release-manifest.json"
    )
    migration = next((tmp_path / "supabase/migrations").glob("*005*"))
    migration.write_text(migration.read_text("utf-8") + "-- changed\n", "utf-8")
    with pytest.raises(RuntimeError, match="checksum_or_transaction"):
        rehearsal.checked_release(tmp_path)
    with pytest.raises(RuntimeError, match="invalid_local_container_name"):
        rehearsal.rehearse_release("hcjfxbynqzsaidlwvdfx", restore.ROOT, {}, {})


@pytest.mark.skipif(
    os.environ.get("IDX_NATIVE_RESTORE_TEST") != "1",
    reason="Explicit native no-network Docker invocation required",
)
def test_native_database_owner_changes_non_superuser_schema_create(modules):
    restore, _ = modules
    name = "idx-restore-check-" + uuid4().hex
    try:
        restore.launch_target(name)
        restore.local_sql(name, "CREATE ROLE postgres NOSUPERUSER LOGIN;")
        with pytest.raises(restore.RestoreFailure) as error:
            restore.local_sql(
                name, "SET ROLE postgres; CREATE TABLE public.local_owner_probe(id int);"
            )
        assert error.value.details["sqlstate"] == "42501"
        verified = restore.set_source_database_owner(name, "postgres")
        assert verified["source_database_owner_matches"] is True
        assert verified["postgres_role_is_superuser"] is False
        restore.local_sql(name, "SET ROLE postgres; CREATE TABLE public.local_owner_probe(id int);")
    finally:
        assert restore.run("rm", "--force", name, text=True).returncode == 0


@pytest.mark.skipif(
    os.environ.get("IDX_NATIVE_RESTORE_TEST") != "1",
    reason="Explicit native no-network Docker invocation required",
)
def test_native_acl_repair_release_failure_rollback_and_schema(modules, tmp_path):
    restore, rehearsal = modules
    name = "idx-restore-check-" + uuid4().hex
    try:
        restore.launch_target(name)
        restore.local_sql(
            name,
            "CREATE ROLE postgres NOSUPERUSER LOGIN; CREATE ROLE anon; "
            "CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; "
            "CREATE SCHEMA auth; CREATE TABLE auth.users(id uuid PRIMARY KEY); "
            "CREATE TABLE auth.identities(id uuid PRIMARY KEY); "
            "CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS $$ SELECT NULL::uuid $$;",
        )
        restore.set_source_database_owner(name, "postgres")
        restore.local_sql(name, "GRANT USAGE ON SCHEMA auth TO postgres; "
                          "GRANT REFERENCES ON auth.users TO postgres;")
        root = restore.ROOT
        restore.local_sql(
            name,
            "SET ROLE postgres;\n"
            + (root / "supabase/migrations/202609290001_scan_foundation.sql").read_text("utf-8"),
        )
        inventory = (root / "supabase/operations/foundation_catalog.sql").read_text("utf-8")
        clean = json.loads(restore.local_sql(name, restore.catalog_query(inventory)))
        restore.local_sql(
            name,
            "SET ROLE postgres; GRANT EXECUTE ON FUNCTION "
            "public.reject_immutable_mutation() TO service_role;",
        )
        shutil.copytree(root / "supabase/migrations", tmp_path / "supabase/migrations")
        shutil.copytree(root / "supabase/operations", tmp_path / "supabase/operations")
        shutil.copy2(
            root / "supabase/release-manifest.json", tmp_path / "supabase/release-manifest.json"
        )
        (tmp_path / "docs/evidence").mkdir(parents=True)
        (tmp_path / "docs/evidence/foundation001-production-20261001.json").write_text(
            json.dumps({"expected_clean001": clean}), "utf-8"
        )
        report = {}
        rehearsal.rehearse_release(
            name,
            tmp_path,
            {
                "data_mode": "live",
                "history_present": False,
                "auth_user_count": 0,
                "auth_identity_count": 0,
                "enabled_owner_count": 0,
                "linked_enabled_owner_count": 0,
            },
            report,
        )
        assert report["migration_rehearsal_tested"] is True
        assert report["local005_injected_failure_rollback_passed"] is True
        assert report["local_acl_repair_and_clean001_catalog_passed"] is True
        assert len(report["local_applied_migrations"]) == 6
        assert report["local_schema_after_release"]["correction_fk"] is True
        assert report["local_schema_after_release"]["actual_trades"] == 0
        assert report["migration_history_cli_tested"] is False
    finally:
        assert restore.run("rm", "--force", name, text=True).returncode == 0
