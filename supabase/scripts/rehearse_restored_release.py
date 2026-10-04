"""Native local rehearsal only; accepts no URL, password or remote connection."""

import hashlib
import json
import re


def checked_release(root):
    release = json.loads((root / "supabase/release-manifest.json").read_text("utf-8"))
    migrations = release["migrations"]
    expected = [
        "202609290001",
        "202609290002",
        "202609290003",
        "202609290004",
        "202609290005",
        "202609300006",
        "202610010007",
        "202610040008",
    ]
    if (
        release["project_ref"] != "hcjfxbynqzsaidlwvdfx"
        or [m["version"] for m in migrations] != expected
    ):
        raise RuntimeError("release_manifest_guard_failed")
    folder = root / "supabase/migrations"
    if sorted(p.name for p in folder.glob("*.sql")) != [m["file"] for m in migrations]:
        raise RuntimeError("migration_chain_changed_review_manifest")
    result = []
    for migration in migrations:
        sql = (folder / migration["file"]).read_text("utf-8")
        if (
            hashlib.sha256(sql.encode()).hexdigest() != migration["sha256_lf"]
            or "\nbegin;\n" not in sql
            or not sql.rstrip().endswith("commit;")
        ):
            raise RuntimeError("migration_checksum_or_transaction_guard_failed")
        result.append((migration["version"], sql))
    return result


def rehearse_release(name, root, before, report, *, sql_runner=None, failure_type=None):
    from restore_backup_prompt import (
        RestoreFailure,
        catalog_query,
        compare_catalog,
        local_sql,
    )

    if sql_runner is not None:
        local_sql = sql_runner
    if failure_type is not None:
        RestoreFailure = failure_type

    if not re.fullmatch(r"idx-restore-check-[a-f0-9]{32}", name):
        raise RuntimeError("invalid_local_container_name")
    release = checked_release(root)
    report["release_checksums_verified"] = True
    if before["data_mode"] != "live" or before["history_present"]:
        raise RuntimeError("restored_release_baseline_guard_failed")
    # This script can only exec the known local container over its Unix socket.
    # Exercise the EXACT guarded repair as the restored postgres operator.
    repair = (root / "supabase/operations/reconcile_foundation_acl.sql").read_text(
        "utf-8"
    )
    local_sql(name, "SET ROLE postgres;\n" + repair + "\nRESET ROLE;\n")
    inventory = (root / "supabase/operations/foundation_catalog.sql").read_text("utf-8")
    expected = json.loads(
        (root / "docs/evidence/foundation001-production-20261001.json").read_text(
            "utf-8"
        )
    )["expected_clean001"]
    if compare_catalog(json.loads(local_sql(name, catalog_query(inventory))), expected):
        raise RuntimeError("reconciled_foundation_catalog_does_not_match")
    report["local_acl_repair_and_clean001_catalog_passed"] = True
    report["local_postgres_prerequisites"] = json.loads(
        local_sql(
            name,
            "SET ROLE postgres; SELECT json_build_object("
            "'operator_is_postgres',current_user='postgres',"
            "'operator_is_superuser',(select rolsuper from pg_roles where rolname=current_user),"
            "'public_schema_create',has_schema_privilege(current_user,'public','CREATE'),"
            "'public_schema_usage',has_schema_privilege(current_user,'public','USAGE'),"
            "'database_create',has_database_privilege(current_user,current_database(),'CREATE'),"
            "'database_owned_by_postgres',(select datdba='postgres'::regrole from pg_database "
            "where datname=current_database())); RESET ROLE;",
        )
    )
    report["migration_history_cli_tested"] = False
    report["local_applied_migrations"] = []
    for version, sql in release[1:]:
        report["local_rehearsal_current_version"] = version
        if version == "202609290005":
            failed_sql = sql.rstrip().removesuffix("commit;") + (
                "DO $$ BEGIN RAISE SQLSTATE 'PZ005' USING MESSAGE='local_failure_rehearsal'; "
                "END $$;\ncommit;\n"
            )
            try:
                local_sql(name, "SET ROLE postgres;\n" + failed_sql)
            except RestoreFailure as error:
                if error.details["sqlstate"] != "PZ005":
                    raise
            else:
                raise RuntimeError("injected_migration_failure_not_observed")
            if (
                local_sql(
                    name, "SELECT to_regclass('public.actual_trades') IS NULL;"
                ).strip()
                != "t"
            ):
                raise RuntimeError("failed005_ddl_did_not_rollback")
            report["local005_injected_failure_rollback_passed"] = True
        local_sql(name, "SET ROLE postgres;\n" + sql + "\nRESET ROLE;\n")
        report["local_applied_migrations"].append(version)
    after = json.loads(
        local_sql(
            name,
            "SELECT json_build_object("
            "'data_mode',(select data_mode from public.deployment_settings where singleton),"
            "'auth_users',(select count(*) from auth.users),"
            "'auth_identities',(select count(*) from auth.identities),"
            "'owners',(select count(*) from public.app_members where enabled),"
            "'linked_owners',(select count(*) from public.app_members m join auth.users u "
            "on u.id=m.user_id where m.enabled),"
            "'actual_trades',(select count(*) from public.actual_trades),"
            "'fixture_runs',(select count(*) from public.scan_runs where data_mode='fixture'),"
            "'correction_fk',exists(select 1 from pg_constraint where "
            "conname='actual_fill_corrections_fill_id_fkey' and contype='f' "
            "and conrelid='public.actual_fill_corrections'::regclass "
            "and confrelid='public.actual_fills'::regclass),"
            "'journal_pt412',position('PT412' in pg_get_functiondef("
            "'public.apply_actual_journal(text,uuid,jsonb,uuid)'::regprocedure))>0,"
            "'analytics_contract',to_regprocedure('public.actual_journal_analytics(date,date,text,text,jsonb)') is not null,"
            "'export_contract',to_regprocedure('public.export_actual_journal(date,date,text,text,jsonb,uuid,integer,text)') is not null,"
            "'signal_pt412',position('PT412' in pg_get_functiondef("
            "'public.set_signal_action(text,text,integer,uuid)'::regprocedure))>0);",
        )
    )
    if (
        after["data_mode"] != "live"
        or after["actual_trades"]
        or after["fixture_runs"]
        or not all(
            after[k]
            for k in (
                "correction_fk",
                "journal_pt412",
                "signal_pt412",
                "analytics_contract",
                "export_contract",
            )
        )
        or after["auth_users"] != before["auth_user_count"]
        or after["auth_identities"] != before["auth_identity_count"]
        or after["owners"] != before["enabled_owner_count"]
        or after["linked_owners"] != before["linked_enabled_owner_count"]
    ):
        raise RuntimeError("local_migration_schema_or_preservation_check_failed")
    report["local_schema_after_release"] = after
    report["migration_rehearsal_tested"] = True
    report["migration_rehearsal_scope"] = (
        "native local ACL/schema/failure rollback; no CLI history/JWT/HTTP"
    )
