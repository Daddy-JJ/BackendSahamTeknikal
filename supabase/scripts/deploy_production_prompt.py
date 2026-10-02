"""Authorized production CLI release; run in an unrecorded interactive terminal.

Fixed production target, no seeds/roles/vault, hidden password, sanitized output.
This changes migration history/schema; it does not enable Auth or any scheduler.
"""

import argparse
import getpass
import json
import re
import subprocess
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from backup_production_prompt import IMAGE, ROOT, clean_environment
from check_production_db_prompt import HOST, PROJECT, USER, docker, validate_ca_cert
from rehearse_restored_release import checked_release

CLI_VERSION = "2.119.0"


def checked_cli(path):
    path = path.resolve(strict=True)
    result = subprocess.run([str(path), "--version"], capture_output=True, text=True,
                            env=clean_environment(), timeout=20, check=False)
    if result.returncode or result.stdout.strip() != CLI_VERSION:
        raise RuntimeError("pinned_cli_required")
    return path


def connection_url(ca):
    # Deliberately no password or colon after the username; pgx reads PGPASSWORD.
    return f"postgresql://{USER}@{HOST}:5432/postgres?" + urlencode({
        "sslmode": "verify-full", "sslrootcert": str(ca), "connect_timeout": "15",
    })


def query(sql, password, ca):
    name = f"idx-release-readonly-{uuid4().hex}"
    env = clean_environment()
    env.update(PGPASSWORD=password, PGSSLMODE="verify-full",
               PGSSLROOTCERT="/run/db-root-ca.pem", PGCONNECT_TIMEOUT="15",
               PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=30000")
    try:
        result = subprocess.run(docker(
            "run", "--rm", "--pull=never", "--name", name, "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "-i",
            "--mount", f"type=bind,src={ca},dst=/run/db-root-ca.pem,readonly",
            "--env", "PGPASSWORD", "--env", "PGSSLMODE", "--env", "PGSSLROOTCERT",
            "--env", "PGCONNECT_TIMEOUT", "--env", "PGOPTIONS",
            "--entrypoint", "psql", IMAGE, "-XqAt", "-w", "-F", "|",
            "-v", "ON_ERROR_STOP=1", "-h", HOST, "-p", "5432", "-U", USER,
            "-d", "postgres"), input=sql, capture_output=True, text=True,
            env=env, timeout=90, check=False)
        if result.returncode:
            raise RuntimeError("read_only_database_query_failed")
        return result.stdout.strip()
    finally:
        env.pop("PGPASSWORD", None)
        subprocess.run(docker("rm", "--force", name), capture_output=True,
                       timeout=20, check=False, env=clean_environment())


def state(password, ca):
    base = json.loads(query("""begin read only;
select json_build_object('data_mode',(select data_mode from public.deployment_settings),
'history_present',to_regclass('supabase_migrations.schema_migrations') is not null,
'operator_is_postgres',current_user='postgres',
'acl',(select proacl::text from pg_proc where
oid='public.reject_immutable_mutation()'::regprocedure),
'verified_at_utc',clock_timestamp()); rollback;""", password, ca))
    if (base["data_mode"] != "live" or not base["operator_is_postgres"]
            or base["acl"] != "{postgres=X/postgres}"):
        raise RuntimeError("production_baseline_guard_failed")
    history = []
    if base["history_present"]:
        history = json.loads(query("""begin read only;
select coalesce(json_agg(version order by version),'[]'::json)
from supabase_migrations.schema_migrations; rollback;""", password, ca))
    return base, history


def cli_run(cli, args, password, ca):
    env = clean_environment()
    env.update(PGPASSWORD=password, SUPABASE_DB_PASSWORD=password,
               PGSSLMODE="verify-full", PGSSLROOTCERT=str(ca))
    try:
        result = subprocess.run([str(cli), *args, "--db-url", connection_url(ca),
                                 "--workdir", str(ROOT)], cwd=ROOT, env=env,
                                input="", capture_output=True, text=True,
                                timeout=600, check=False)
        if result.returncode:
            # Never emit raw CLI diagnostics/connection details or SQL bodies.
            raise RuntimeError("supabase_cli_stage_failed")
        return result.stdout + result.stderr
    finally:
        env.pop("PGPASSWORD", None)
        env.pop("SUPABASE_DB_PASSWORD", None)


def deploy(cli, ca, password, report):
    release = checked_release(ROOT)
    versions = [version for version, _ in release]
    manifest = json.loads((ROOT / "supabase/release-manifest.json").read_text("utf-8"))
    report["release_checksums_verified"] = True
    base, history = state(password, ca)
    if history != versions[:len(history)]:
        raise RuntimeError("history_not_exact_release_prefix")
    report["history_before"] = history
    if not history:
        report["stage"] = "foundation_catalog"
        rows = query((ROOT / "supabase/operations/foundation_catalog.sql").read_text("utf-8"),
                     password, ca).splitlines()
        observed = [{"category": p[0], "object_count": int(p[1]), "sha256": p[2]}
                    for row in rows if len(p := row.split("|")) == 3]
        expected = json.loads((ROOT / "docs/evidence/foundation001-production-20261001.json")
                              .read_text("utf-8"))["expected_clean001"]
        if observed != expected:
            raise RuntimeError("foundation_ten_group_mismatch")
        report["foundation_clean001_verified"] = True
        report["stage"] = "repair_001"
        report["production_write_attempted"] = True
        cli_run(cli, ["migration", "repair", "202609290001", "--status", "applied"],
                password, ca)
        _, history = state(password, ca)
        if history != versions[:1]:
            raise RuntimeError("repair001_readback_failed")
        report["history_001_repaired_via_cli"] = True
    pending = manifest["migrations"][len(history):]
    report["stage"] = "dry_run"
    preview = cli_run(cli, ["db", "push", "--dry-run", "--skip-vault"], password, ca)
    planned = sorted(set(re.findall(r"\b\d{12}_[A-Za-z0-9_]+\.sql\b", preview)))
    if planned != [migration["file"] for migration in pending]:
        raise RuntimeError("dry_run_not_exact_pending_chain")
    report["cli_dry_run_pending"] = planned
    if pending:
        report["stage"] = "push"
        report["production_write_attempted"] = True
        cli_run(cli, ["db", "push", "--skip-vault", "--yes"], password, ca)
    report["stage"] = "postflight_history"
    base, history = state(password, ca)
    report["history_after"] = history
    report["verified_at_utc"] = base["verified_at_utc"]
    if history != versions:
        raise RuntimeError("release_history_readback_failed")
    report["migration_history_cli_verified"] = True
    report["status"] = "cli_release_completed_smoke_pending"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--ca-cert", type=Path, required=True)
    args = parser.parse_args()
    report = {"project_ref": PROJECT, "production_write_attempted": False,
              "production_smoke_passed": False, "full_stack_live": False,
              "started_at_utc": datetime.now(UTC).isoformat(), "cli_version": CLI_VERSION,
              "stage": "local_validation"}
    password = ""
    try:
        cli = checked_cli(args.cli)
        ca = validate_ca_cert(args.ca_cert)
        checked_release(ROOT)
        if not sys.stdin.isatty():
            raise RuntimeError("unrecorded_interactive_terminal_required")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass(f"Database password {PROJECT} (hidden): ")
        if not password:
            raise RuntimeError("empty_password")
        deploy(cli, ca, password, report)
        code = 0
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
        report["status"] = "release_incomplete_review_remote_history_before_resume"
        report["failure"] = "stage_failed_details_suppressed"
        code = 1
    finally:
        password = ""
    # Evidence contains only fixed metadata, checksums/version names and stage results.
    folder = ROOT / "data/production-release-evidence"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".json")
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**report, "evidence_path": str(target)}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
