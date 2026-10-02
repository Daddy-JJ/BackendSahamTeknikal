"""Inspect encrypted backup prerequisites locally; never restore or contact Supabase.

Plaintext exists briefly in memory only. Passphrases go to age's hidden console.
Output is a metadata summary, never SQL, records, passwords or full driver errors.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from backup_production_prompt import (
    AGE,
    IMAGE,
    clean_environment,
    digest_file,
    stderr_code,
    verify_age,
)
from check_production_db_prompt import PROJECT, docker

MAX_ARCHIVE_BYTES = 32 * 1024 * 1024


def validate_bundle(folder: Path) -> dict:
    evidence_path = folder / "evidence.json"
    if evidence_path.stat().st_size > 100000:
        raise RuntimeError("backup_evidence_invalid")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if (evidence.get("source_project_ref") != PROJECT
            or evidence.get("production_write") is not False
            or evidence.get("status") != "encrypted_candidate_decrypt_verified_restore_pending"):
        raise RuntimeError("backup_evidence_guard_failed")
    files = evidence.get("files", [])
    if (len(files) != 2 or {item.get("file") for item in files}
            != {"database.age", "roles.age"}):
        raise RuntimeError("backup_files_incomplete")
    for item in files:
        archive = folder / item["file"]
        if archive.is_symlink() or archive.resolve().parent != folder.resolve():
            raise RuntimeError("archive_path_not_in_bundle")
        size = archive.stat().st_size
        if (not 0 < size <= MAX_ARCHIVE_BYTES or size != item["bytes"]
                or item.get("decryption_verified") is not True
                or digest_file(archive) != item["sha256"]):
            raise RuntimeError("archive_integrity_failed")
    return evidence


def decrypt_memory(path: Path, expected_bytes: int) -> bytes:
    result = subprocess.run([str(AGE), "--decrypt", str(path)], capture_output=True,
                            env=clean_environment(), timeout=300,
                            check=False)
    if result.returncode:
        raise RuntimeError(stderr_code(result.stderr, "encryption"))
    if len(result.stdout) != expected_bytes or not 0 < len(result.stdout) <= MAX_ARCHIVE_BYTES:
        raise RuntimeError("plaintext_size_mismatch")
    return result.stdout


def list_command() -> list[str]:
    return docker("run", "--rm", "--pull=never", "--network=none", "--read-only",
                  "--cap-drop=ALL", "--security-opt=no-new-privileges", "-i",
                  "--entrypoint", "pg_restore", IMAGE, "--list")


def summarize(toc: str, roles: str) -> dict:
    extensions = sorted(set(re.findall(r"^\d+; \d+ \d+ EXTENSION - ([\w-]+) ", toc, re.MULTILINE)))
    public_tables = sorted(set(re.findall(r"^\d+; \d+ \d+ TABLE public (\w+) ", toc, re.MULTILINE)))
    auth_tables = set(re.findall(r"^\d+; \d+ \d+ TABLE auth (\w+) ", toc, re.MULTILINE))
    auth_data = set(re.findall(r"^\d+; \d+ \d+ TABLE DATA auth (\w+) ", toc, re.MULTILINE))
    if not public_tables or "users" not in auth_tables:
        raise RuntimeError("required_application_or_auth_schema_missing")
    has_password = bool(re.search(r"\bPASSWORD\s+'", roles, re.IGNORECASE))
    if has_password:
        raise RuntimeError("unexpected_role_password_in_export")
    return {"public_tables": public_tables, "required_extensions": extensions,
            "auth_users_schema_present": "users" in auth_tables,
            "auth_users_data_entry_present": "users" in auth_data,
            "auth_identities_schema_present": "identities" in auth_tables,
            "auth_identities_data_entry_present": "identities" in auth_data,
            "role_definition_count": len(re.findall(r"^CREATE ROLE ", roles, re.MULTILINE)),
            "role_password_statements_present": False,
            "application_history_schema_present": bool(re.search(
                r"^\d+; \d+ \d+ TABLE supabase_migrations schema_migrations ", toc, re.MULTILINE))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-directory", required=True, type=Path)
    args = parser.parse_args()
    report = {"source_project_ref": PROJECT, "production_write": False,
              "database_connected": False, "restore_verified": False,
              "deployment_gate_passed": False}
    dump = roles = b""
    try:
        if not sys.stdin.isatty():
            raise RuntimeError("run_in_local_interactive_terminal")
        folder = args.backup_directory.resolve(strict=True)
        evidence = validate_bundle(folder)
        verify_age()
        entries = {item["file"]: item for item in evidence["files"]}
        print("Inspect database archive: enter its recovery passphrase in age's hidden prompt.")
        dump = decrypt_memory(folder / "database.age", entries["database.age"]["plaintext_bytes"])
        result = subprocess.run(list_command(), input=dump, capture_output=True,
                                env=clean_environment(), timeout=60,
                                check=False)
        dump = b""
        if result.returncode:
            raise RuntimeError("offline_archive_table_of_contents_failed")
        print("Inspect roles archive: enter its recovery passphrase in age's hidden prompt.")
        roles = decrypt_memory(folder / "roles.age", entries["roles.age"]["plaintext_bytes"])
        report.update(summarize(result.stdout.decode("utf-8"), roles.decode("utf-8")))
        roles = b""
        report.update({"status": "archive_inspected_restore_pending",
                       "ciphertext_checksums_match": True,
                       "archive_structure_readable": True,
                       "managed_extension_compatible_target_required": True})
        print(json.dumps(report, indent=2))
        return 0
    except RuntimeError as error:
        report["failure"] = str(error)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, UnicodeError):
        report["failure"] = "local_inspection_failed"
    except (KeyboardInterrupt, EOFError):
        report["failure"] = "cancelled"
    finally:
        dump = roles = b""
    print(json.dumps({**report, "status": "inspection_failed_do_not_restore"}, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
