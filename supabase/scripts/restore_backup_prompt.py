"""Restore only into this script's fresh, network-disabled local tmpfs database.

Hidden recovery-passphrase input only. No production credentials or remote access.
All SQL/records remain in memory/pipes; JSON output contains metadata and counts.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from backup_production_prompt import ROOT, verify_age
from check_production_db_prompt import PROJECT
from check_restore_target import run, start_command
from inspect_backup_prompt import (
    decrypt_memory,
    list_command,
    summarize,
    validate_bundle,
)

IMAGE = "supabase/postgres@sha256:0450166354dc9c1d25f0322ac8b580774d4fb0184d2b087f6e4fe9499c66cf53"
OPERATOR = "idx_restore_operator"


class RestoreFailure(RuntimeError):
    def __init__(self, reason: str, details: dict):
        super().__init__(reason)
        self.details = details


def safe_sql_diagnostic(stderr: str | bytes, sql: str = "") -> dict:
    """Expose only SQLSTATE and fixed categories, never SQL/records/raw messages."""
    message = (stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes)
               else stderr)
    state = re.search(r"(?:ERROR|FATAL):\s+([0-9A-Z]{5}):", message)
    category = "unclassified_sql_error"
    for needle, code in (
        ("unrecognized configuration parameter", "unsupported_role_configuration"),
        ("already exists", "object_already_exists"),
        ("must have admin option", "grantor_missing_admin_option"),
        ("must have ADMIN option", "grantor_missing_admin_option"),
        ("must be member of role", "role_membership_required"),
        ("permission denied to grant role", "role_grant_permission_denied"),
        ("permission denied to set parameter", "role_setting_permission_denied"),
        ("permission denied", "permission_denied"),
        ("does not exist", "required_object_missing"),
        ("extension", "extension_related_error"),
        ("syntax error", "sql_syntax_error"),
    ):
        if needle.lower() in message.lower():
            category = code
            break
    # psql line number refers to the private archive; it contains no SQL content.
    line = re.search(r"(?:<stdin>|stdin):(\d+):", message)
    line_number = int(line.group(1)) if line else None
    statement_kind = None
    if line_number and line_number <= len(sql.splitlines()):
        # pg_dumpall emits role statements on single lines. Return an enum only,
        # never role names, configuration names/values or raw SQL.
        statement = sql.splitlines()[line_number - 1].strip()
        for pattern, kind in (
            (r"^CREATE ROLE\b", "create_role"),
            (r"^ALTER ROLE\b.*\bSET\b", "alter_role_setting"),
            (r"^ALTER ROLE\b", "alter_role_attributes"),
            (r"^GRANT\b.*\bGRANTED BY\b", "grant_role_explicit_grantor"),
            (r"^GRANT\b", "grant_role"),
        ):
            if re.search(pattern, statement, re.IGNORECASE):
                statement_kind = kind
                break
    return {"sqlstate": state.group(1) if state else None,
            "category": category, "statement_line": line_number,
            "statement_kind": statement_kind}


def local_sql(name: str, sql: str) -> str:
    result = run("exec", "-i", name, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                 "-v", "VERBOSITY=verbose",
                 "-h", "/tmp", "-U", OPERATOR, "-d", "postgres", "-f", "-", input=sql,
                 text=True, timeout=60)
    if result.returncode:
        raise RestoreFailure("local_restore_sql_failed", safe_sql_diagnostic(result.stderr, sql))
    return result.stdout


def catalog_query(sql: str) -> str:
    # Preserve the canonical read-only inventory SQL; just aggregate its final rows.
    marker = "select c.category, count(i.object_key)::integer as object_count,"
    if sql.count(marker) != 1 or not sql.endswith("rollback;\n"):
        raise RuntimeError("catalog_query_changed_review_required")
    prefix, query = sql.split(marker, 1)
    query = marker + query
    query = query.removesuffix("rollback;\n").rstrip().removesuffix(";")
    return prefix + "select json_agg(row_to_json(q)) from (" + query + ") q;\nrollback;\n"


def compare_catalog(rows: list, expected: list) -> list[str]:
    if (len(rows) != 10 or len({r["category"] for r in rows}) != 10
            or len(expected) != 10):
        raise RuntimeError("restore_catalog_incomplete")
    actual = {r["category"]: r for r in rows}
    return [r["category"] for r in expected if actual.get(r["category"]) != r]


def bootstrap_roles_sql(sql: str, bootstrap: str | None) -> str:
    """Represent the source bootstrap CREATE via initdb; preserve all other SQL.

    PostgreSQL gives OID10 a special role-grant exemption. Do not substitute
    GRANTED BY or grant temporary ADMIN privileges to work around that rule.
    The supplied name must come from a read-only source pg_roles OID10 query.
    """
    if bootstrap is None:
        return sql
    if (not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", bootstrap)
            or bootstrap == OPERATOR):
        raise RuntimeError("invalid_source_bootstrap_role")
    declaration = re.compile(rf'^CREATE ROLE (?:{bootstrap}|"{bootstrap}");$', re.MULTILINE)
    attributes = re.compile(rf'^ALTER ROLE (?:{bootstrap}|"{bootstrap}") WITH '
                            r'[^\n]*\bSUPERUSER\b[^\n]*;$', re.MULTILINE)
    if len(declaration.findall(sql)) != 1 or len(attributes.findall(sql)) != 1:
        raise RuntimeError("source_bootstrap_declaration_or_superuser_attribute_missing")
    return declaration.sub("-- Source bootstrap CREATE ROLE represented by fresh initdb OID10.",
                           sql)


def launch_target(name: str, bootstrap: str | None = None) -> None:
    # Validate even if called independently of bootstrap_roles_sql.
    if bootstrap is not None and (not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", bootstrap)
                                  or bootstrap == OPERATOR):
        raise RuntimeError("invalid_source_bootstrap_role")
    initial_operator = bootstrap or OPERATOR
    command = list(start_command(name, IMAGE))
    command[-1] = command[-1].replace("-U postgres ", f"-U {initial_operator} ")
    if run(*command, text=True).returncode:
        raise RuntimeError("isolated_target_start_failed")
    for _ in range(60):
        if run("exec", name, "pg_isready", "-h", "/tmp", "-U", initial_operator,
               text=True, timeout=10).returncode == 0:
            if bootstrap:
                result = run("exec", "-i", name, "psql", "-X", "-qAt", "-v",
                             "ON_ERROR_STOP=1", "-h", "/tmp", "-U", bootstrap,
                             "-d", "postgres", text=True,
                             input=f"CREATE ROLE {OPERATOR} SUPERUSER LOGIN;\n")
                if result.returncode:
                    raise RuntimeError("independent_local_operator_creation_failed")
            return
        time.sleep(1)
    raise RuntimeError("isolated_target_not_ready")


def verify_bootstrap_identity(name: str, bootstrap: str | None) -> bool:
    if bootstrap is None:
        return False
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", bootstrap):
        raise RuntimeError("invalid_source_bootstrap_role")
    matched = local_sql(name, "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE oid=10 "
                        f"AND rolname='{bootstrap}' AND rolsuper);\n").strip() == "t"
    if not matched:
        raise RuntimeError("local_bootstrap_identity_does_not_match")
    return True


def set_source_database_owner(name: str, owner: str) -> dict:
    """Reproduce verified source ownership on the isolated target, no new grants."""
    if (not re.fullmatch(r"idx-restore-check-[a-f0-9]{32}", name)
            or not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", owner)
            or owner == OPERATOR):
        raise RuntimeError("invalid_local_source_database_owner")
    local_sql(name, f'ALTER DATABASE postgres OWNER TO "{owner}";\n')
    metadata = json.loads(local_sql(name, "SELECT json_build_object("
        f"'source_database_owner_matches', (select datdba='{owner}'::regrole "
        "from pg_database where datname=current_database()),"
        "'postgres_role_is_superuser',(select rolsuper from pg_roles where rolname='postgres'));"))
    if metadata["source_database_owner_matches"] is not True:
        raise RuntimeError("local_database_owner_verification_failed")
    return metadata


def check_roles(folder: Path, bootstrap: str | None = None) -> int:
    """Diagnose the failed stage with one passphrase, without database dump restore."""
    name = f"idx-restore-check-{uuid4().hex}"
    launched = False
    stage = "archive_validation"
    roles = b""
    report = {"source_project_ref": PROJECT, "production_write": False,
              "remote_database_connected": False, "restore_verified": False,
              "deployment_gate_passed": False, "logical_restore_completed": False,
              "scope": "local roles diagnostic only; database archive not decrypted"}
    try:
        if not sys.stdin.isatty():
            raise RuntimeError("run_in_local_interactive_terminal")
        folder = folder.resolve(strict=True)
        evidence = validate_bundle(folder)
        verify_age()
        entry = next(item for item in evidence["files"] if item["file"] == "roles.age")
        print("Diagnose roles: enter roles archive recovery passphrase at age's hidden prompt.")
        stage = "roles_archive_decryption"
        roles = decrypt_memory(folder / "roles.age", entry["plaintext_bytes"])
        text = roles.decode("utf-8")
        if re.search(r"\bPASSWORD\s+'", text, re.IGNORECASE):
            raise RuntimeError("unexpected_role_password_in_export")
        text = bootstrap_roles_sql(text, bootstrap)
        stage = "isolated_target_start"
        launched = True
        launch_target(name, bootstrap)
        stage = "local_roles_restore"
        local_sql(name, text)
        report["local_bootstrap_oid10_verified"] = verify_bootstrap_identity(name, bootstrap)
        report["source_bootstrap_identity_supplied"] = bootstrap is not None
        report["bootstrap_create_represented_by_initdb"] = bootstrap is not None
        report["source_grantor_clauses_preserved"] = True
        report["status"] = "local_roles_check_passed_not_a_database_restore"
    except RestoreFailure as error:
        report.update({"status": "local_roles_check_failed", "failure": str(error),
                       "failure_stage": stage, "sql_diagnostic": error.details})
    except RuntimeError as error:
        report.update({"status": "local_roles_check_failed", "failure": str(error),
                       "failure_stage": stage})
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError,
            UnicodeError, KeyboardInterrupt, EOFError):
        report.update({"status": "local_roles_check_failed", "failure": "local_tool_or_input_failed",
                       "failure_stage": stage})
    finally:
        roles = b""
        if launched:
            try:
                report["temporary_target_removed"] = run("rm", "--force", name,
                                                          text=True).returncode == 0
            except (OSError, subprocess.SubprocessError):
                report["temporary_target_removed"] = False
    print(json.dumps(report, indent=2))
    return 0 if report.get("status") == "local_roles_check_passed_not_a_database_restore" and (
        report.get("temporary_target_removed")) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-directory", required=True, type=Path)
    parser.add_argument("--check-roles", action="store_true",
                        help="Diagnose roles on a fresh isolated target; no database archive restore")
    parser.add_argument("--source-bootstrap-role",
                        help="Source pg_roles OID10 name verified by a read-only source query")
    parser.add_argument("--source-database-owner",
                        help="Verified source DB owner; reproduce on fresh local target only")
    parser.add_argument("--rehearse-release", action="store_true",
                        help="After restore, rehearse ACL repair and 002-007 on local target only")
    args = parser.parse_args()
    if args.rehearse_release and not args.source_database_owner:
        parser.error("--rehearse-release requires read-only verified --source-database-owner")
    if args.check_roles:
        if args.rehearse_release:
            parser.error("--check-roles cannot be combined with --rehearse-release")
        return check_roles(args.backup_directory, args.source_bootstrap_role)
    name = f"idx-restore-check-{uuid4().hex}"
    launch_attempted = False
    stage = "archive_validation"
    report = {"source_project_ref": PROJECT, "production_write": False,
              "remote_database_connected": False, "restore_verified": False,
              "deployment_gate_passed": False, "offsite_copy_verified": False,
              "writers_quiescent_verified": False, "logical_restore_completed": False}
    dump = roles = b""
    try:
        if not sys.stdin.isatty():
            raise RuntimeError("run_in_local_interactive_terminal")
        folder = args.backup_directory.resolve(strict=True)
        evidence = validate_bundle(folder)
        verify_age()
        entries = {item["file"]: item for item in evidence["files"]}
        print("Restore local: enter database archive recovery passphrase at age's hidden prompt.")
        stage = "database_archive_decryption"
        dump = decrypt_memory(folder / "database.age", entries["database.age"]["plaintext_bytes"])
        from backup_production_prompt import clean_environment

        toc = subprocess.run(list_command(), input=dump, capture_output=True,
                             env=clean_environment(), timeout=60, check=False)
        if toc.returncode:
            raise RuntimeError("archive_toc_failed")
        print("Restore local: enter roles archive recovery passphrase at age's hidden prompt.")
        stage = "roles_archive_decryption"
        roles = decrypt_memory(folder / "roles.age", entries["roles.age"]["plaintext_bytes"])
        summarize(toc.stdout.decode("utf-8"), roles.decode("utf-8"))
        roles_sql = bootstrap_roles_sql(roles.decode("utf-8"), args.source_bootstrap_role)
        # A distinct local operator avoids downgrading the restore connection.
        # If supplied, source bootstrap CREATE is represented by initdb OID10;
        # all source ALTER/GRANT statements retain their exact text and grantors.
        stage = "isolated_target_start"
        launch_attempted = True
        launch_target(name, args.source_bootstrap_role)
        stage = "local_roles_restore"
        local_sql(name, roles_sql)
        report["local_bootstrap_oid10_verified"] = verify_bootstrap_identity(
            name, args.source_bootstrap_role)
        report["source_bootstrap_identity_supplied"] = args.source_bootstrap_role is not None
        report["bootstrap_create_represented_by_initdb"] = args.source_bootstrap_role is not None
        report["source_grantor_clauses_preserved"] = True
        roles = b""
        if args.source_database_owner:
            stage = "local_source_database_owner"
            report.update(set_source_database_owner(name, args.source_database_owner))
        # Default public may already exist in initdb's fresh database. Drop it
        # only if the source archive itself will create it, on this local target.
        if re.search(r"^\d+; \d+ \d+ SCHEMA - public ", toc.stdout.decode("utf-8"), re.MULTILINE):
            local_sql(name, "DROP SCHEMA public;\n")
        stage = "local_database_restore"
        restored = run("exec", "-i", name, "pg_restore", "--exit-on-error",
                       "--single-transaction", "-h", "/tmp", "-U", OPERATOR, "-d", "postgres",
                       input=dump, timeout=120)
        dump = b""
        if restored.returncode:
            raise RestoreFailure("local_database_restore_failed_no_errors_ignored",
                                 safe_sql_diagnostic(restored.stderr))
        report["logical_restore_completed"] = True
        stage = "restored_catalog_verification"
        inventory = (ROOT / "supabase/operations/foundation_catalog.sql").read_text("utf-8")
        rows = json.loads(local_sql(name, catalog_query(inventory)))
        prior = json.loads((ROOT / "docs/evidence/foundation001-production-20261001.json")
                           .read_text("utf-8"))["observed_production"]
        differences = compare_catalog(rows, prior)
        report.update({"catalog_matches_prior_production": not differences,
                       "catalog_differences": differences})
        tables = ["app_members", "audit_events", "deployment_settings", "scan_run_items",
                  "scan_run_signals", "scan_runs", "signal_action_requests",
                  "signal_actions", "signals"]
        counts_sql = ",".join(f"'{t}',(select count(*) from public.{t})" for t in tables)
        metadata = json.loads(local_sql(name, "SELECT json_build_object("
            "'data_mode',(select data_mode from public.deployment_settings),"
            "'server_version',current_setting('server_version'),"
            "'table_counts',json_build_object(" + counts_sql + "),"
            "'auth_user_count',(select count(*) from auth.users),"
            "'auth_identity_count',(select count(*) from auth.identities),"
            "'enabled_owner_count',(select count(*) from public.app_members where enabled),"
            "'linked_enabled_owner_count',(select count(*) from public.app_members m "
            "join auth.users u on u.id=m.user_id where m.enabled),"
            "'history_present',to_regclass('supabase_migrations.schema_migrations') is not null);"))
        report.update(metadata)
        linked = (metadata["enabled_owner_count"] > 0
                  and metadata["enabled_owner_count"] == metadata["linked_enabled_owner_count"])
        report["owner_auth_linkage_verified"] = linked
        if differences or not linked or metadata["data_mode"] != "live":
            raise RuntimeError("restored_metadata_or_catalog_does_not_match")
        report.update({"status": "logical_restore_and_catalog_passed_recovery_gates_pending",
                       "target_image": IMAGE, "network": "none", "published_ports": [],
                       "storage": "temporary tmpfs", "source_row_count_comparison": "pending",
                       "owner_jwt_tested": False, "rls_tested": False,
                       "migration_rehearsal_tested": False})
        if args.rehearse_release:
            from rehearse_restored_release import rehearse_release

            stage = "local_migration_rehearsal"
            # Keep one exception class/function identity when this file runs as
            # __main__; importing it again in the rehearsal module loses details.
            rehearse_release(name, ROOT, metadata, report,
                             sql_runner=local_sql, failure_type=RestoreFailure)
            report["status"] = "logical_restore_and_local_release_passed_recovery_gates_pending"
    except RestoreFailure as error:
        report.update({"status": "local_restore_failed", "failure": str(error),
                       "failure_stage": stage, "sql_diagnostic": error.details})
    except RuntimeError as error:
        report.update({"status": "local_restore_failed", "failure": str(error),
                       "failure_stage": stage})
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError,
            UnicodeError, KeyboardInterrupt, EOFError):
        report.update({"status": "local_restore_failed", "failure": "local_tool_or_input_failed",
                       "failure_stage": stage})
    finally:
        dump = roles = b""
        if launch_attempted:
            try:
                report["temporary_target_removed"] = run("rm", "--force", name,
                                                          text=True).returncode == 0
            except (OSError, subprocess.SubprocessError):
                report["temporary_target_removed"] = False
    print(json.dumps(report, indent=2))
    return 0 if report.get("catalog_matches_prior_production") and report.get(
        "owner_auth_linkage_verified") and report.get("temporary_target_removed") and report.get(
        "status", "").startswith("logical_restore_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
