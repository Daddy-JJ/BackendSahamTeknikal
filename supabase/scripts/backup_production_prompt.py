"""Create and decrypt-check encrypted logical backup candidates, without production writes.

Run only in an unrecorded local terminal. age asks for a separate recovery passphrase.
This is not a restore rehearsal or a production deployment authorization gate.
"""

import argparse
import errno
import getpass
import hashlib
import json
import os
import subprocess
import sys
import threading
import warnings
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from check_production_db_prompt import (
    HOST,
    PROJECT,
    USER,
    docker,
    probe,
    validate_ca_cert,
)

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "postgres@sha256:d74eeac9a635390a49bc21bd49fccd973de707e2a53a76ac49b552b8712ec46f"
AGE = ROOT / "data/tools/age-v1.3.2/verified/age/age.exe"
AGE_ZIP = ROOT / "data/tools/age-v1.3.2/age-v1.3.2-windows-amd64.zip"
AGE_ZIP_SHA = "f48d8f8f9ebe903ab5027ed067652f2cc1db94bc206976430133b905dcd8e8c7"


class PipelineFailure(RuntimeError):
    """Only fixed reason codes and exit codes escape the subprocess boundary."""

    def __init__(self, details: dict, reason: str = "encrypted_backup_pipeline_failed"):
        super().__init__(reason)
        self.details = details


def stderr_code(stderr: bytes, kind: str) -> str:
    message = stderr.decode("utf-8", errors="replace").lower()
    if not message:
        return "no_driver_diagnostic"
    if kind == "encryption":
        for needle, code in (
            ("could not read passphrase", "crypto_hidden_prompt_failed"),
            ("passphrases do not match", "crypto_passphrase_confirmation_mismatch"),
            ("incorrect passphrase", "crypto_incorrect_passphrase"),
            ("no identity matched", "crypto_identity_mismatch"),
            ("failed to decrypt", "crypto_decryption_failed"),
            ("too many input", "crypto_arguments_invalid"),
        ):
            if needle in message:
                return code
        return "crypto_command_failed"
    for needle, code in (
        ("permission denied", "dump_permission_denied"),
        ("server version mismatch", "dump_server_version_mismatch"),
        ("password authentication failed", "dump_authentication_failed"),
        ("certificate verify failed", "dump_tls_verification_failed"),
        ("unrecognized option", "dump_arguments_invalid"),
        ("conflicting or redundant options", "dump_arguments_invalid"),
        ("error during connect", "docker_connection_failed"),
        ("cannot connect to the docker", "docker_connection_failed"),
        ("timed out", "dump_timeout"),
    ):
        if needle in message:
            return code
    return "dump_or_docker_failed"


def capture_stderr(process: subprocess.Popen) -> tuple[bytearray, threading.Thread]:
    """Drain fully to prevent pipe deadlock, retain at most64KiB in memory only."""
    captured = bytearray()

    def drain():
        assert process.stderr is not None
        with process.stderr as source:
            while chunk := source.read(4096):
                captured.extend(chunk[:max(0, 65536 - len(captured))])

    thread = threading.Thread(target=drain, daemon=True)
    thread.start()
    return captured, thread


def digest_file(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def verify_age() -> None:
    if digest_file(AGE_ZIP) != AGE_ZIP_SHA:
        raise RuntimeError("age_distribution_checksum_mismatch")
    with ZipFile(AGE_ZIP) as distribution:
        binary = distribution.read("age/age.exe")
    if hashlib.sha256(binary).hexdigest() != digest_file(AGE):
        raise RuntimeError("age_executable_checksum_mismatch")
    version = subprocess.run([str(AGE), "--version"], capture_output=True,
                             text=True, check=True, timeout=15, env=clean_environment())
    if version.stdout.strip() != "v1.3.2":
        raise RuntimeError("age_version_mismatch")


def clean_environment() -> dict[str, str]:
    # The crypto child never needs provider/API/database credentials.
    allowed = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP",
               "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA",
               "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "COMMONPROGRAMFILES",
               "ALLUSERSPROFILE", "OS", "DOCKER_CONFIG"}
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def dump_command(kind: str, client: str, ca: Path) -> list[str]:
    if kind not in ("database", "roles"):
        raise ValueError("invalid_backup_kind")
    executable = "pg_dump" if kind == "database" else "pg_dumpall"
    flags = (["--format=custom", "--quote-all-identifiers", "--lock-wait-timeout=5000"]
             if kind == "database" else ["--roles-only", "--no-role-passwords"])
    return docker(
        "run", "--rm", "--pull=never", "--name", client, "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--mount", f"type=bind,src={ca},dst=/run/db-root-ca.pem,readonly",
        *[flag for key in ("PGPASSWORD", "PGSSLMODE", "PGSSLROOTCERT", "PGOPTIONS",
                          "PGCONNECT_TIMEOUT") for flag in ("--env", key)],
        "--entrypoint", executable, IMAGE, "--no-password", "--host", HOST,
        "--port", "5432", "--username", USER,
        *( ["--dbname", "postgres"] if kind == "database"
           else ["--database", "postgres"] ),
        "--role=postgres", *flags,
    )


def stream_encrypt(command: list[str], environment: dict[str, str], output: Path,
                   crypto_command: list[str]) -> tuple[str, int]:
    """Binary pipes only; no plaintext file, shell pipeline, argv secret or raw stderr."""
    producer = consumer = None
    captures = []
    digest = hashlib.sha256()
    size = 0
    try:
        # Exclusive creation also protects against age's normal overwrite behavior.
        with output.open("xb") as archive:
            consumer = subprocess.Popen(crypto_command, stdin=subprocess.PIPE, stdout=archive,
                                        stderr=subprocess.PIPE, env=clean_environment())
            crypto_stderr, crypto_thread = capture_stderr(consumer)
            captures.append(crypto_thread)
            producer = subprocess.Popen(command, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, env=environment)
            dump_stderr, dump_thread = capture_stderr(producer)
            captures.append(dump_thread)
            assert producer.stdout is not None and consumer.stdin is not None
            broken_pipe = False
            try:
                while block := producer.stdout.read(1024 * 1024):
                    digest.update(block)
                    size += len(block)
                    consumer.stdin.write(block)
                consumer.stdin.close()
            except OSError as error:
                # Windows may report EINVAL instead of EPIPE for an exited consumer.
                if error.errno not in (errno.EPIPE, errno.EINVAL):
                    raise
                broken_pipe = True
                if producer.poll() is None:
                    producer.kill()
            finally:
                producer.stdout.close()
            dump_exit = producer.wait(timeout=900)
            crypto_exit = consumer.wait(timeout=900)
            for thread in captures:
                thread.join(timeout=15)
            if broken_pipe or dump_exit or crypto_exit or size == 0:
                raise PipelineFailure({
                    "dump_exit_code": dump_exit, "crypto_exit_code": crypto_exit,
                    "broken_pipe": broken_pipe, "plaintext_bytes_read": size,
                    "dump_diagnostic": stderr_code(bytes(dump_stderr), "dump"),
                    "crypto_diagnostic": stderr_code(bytes(crypto_stderr), "encryption"),
                })
        return digest.hexdigest(), size
    finally:
        for process in (producer, consumer):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=15)
        for thread in captures:
            thread.join(timeout=15)


def decrypted_digest(command: list[str]) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=clean_environment()) as process:
        errors, thread = capture_stderr(process)
        assert process.stdout is not None
        try:
            while block := process.stdout.read(1024 * 1024):
                digest.update(block)
                size += len(block)
            exit_code = process.wait(timeout=900)
            thread.join(timeout=15)
            if exit_code:
                raise PipelineFailure({"crypto_exit_code": exit_code,
                                       "crypto_diagnostic": stderr_code(bytes(errors), "encryption")},
                                      "backup_decryption_failed")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=15)
            thread.join(timeout=15)
    return digest.hexdigest(), size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca-cert", type=Path)
    parser.add_argument("--check-encryption", action="store_true",
                        help="Test the hidden age console with synthetic bytes only; no DB access")
    parser.add_argument("--output-directory", required=True, type=Path,
                        help="Private local backup directory outside any Git repository")
    args = parser.parse_args()
    password = ""
    folder = None
    stage = "local_preflight"
    report = {"source_project_ref": PROJECT, "production_write": False,
              "restore_verified": False, "offsite_copy_verified": False,
              "writers_quiescent_verified": False, "deployment_gate_passed": False}
    try:
        if not sys.stdin.isatty():
            raise RuntimeError("run_in_local_interactive_terminal")
        if not args.check_encryption and not args.ca_cert:
            raise RuntimeError("production_ca_certificate_required")
        ca = validate_ca_cert(args.ca_cert) if args.ca_cert else None
        destination = args.output_directory.resolve()
        if destination == ROOT.parent or ROOT.parent in destination.parents:
            raise RuntimeError("backup_directory_must_be_outside_workspace")
        if any((parent / ".git").exists() for parent in (destination, *destination.parents)):
            raise RuntimeError("backup_directory_must_be_outside_git")
        verify_age()
        if args.check_encryption:
            folder = destination / f"synthetic-crypto-check-{uuid4().hex}"
            stage = "synthetic_directory_creation"
            folder.mkdir(parents=True, exist_ok=False)
            archive = folder / "synthetic.age"
            report.update({"scope": "synthetic bytes only; not a database backup",
                           "database_connected": False})
            stage = "synthetic_encryption"
            print("Synthetic test: enter a recovery passphrase in age's hidden console prompt.")
            expected = stream_encrypt(
                [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'IDX-test'*4096)"],
                clean_environment(), archive, [str(AGE), "--encrypt", "--passphrase"])
            stage = "synthetic_decryption"
            print("Verify synthetic test: enter that passphrase again.")
            observed = decrypted_digest([str(AGE), "--decrypt", str(archive)])
            if observed != expected:
                raise RuntimeError("synthetic_decryption_digest_mismatch")
            report.update({"status": "synthetic_console_crypto_passed_not_a_backup",
                           "encryption_verified": True, "decryption_verified": True})
            (folder / "evidence.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))
            return 0
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass(f"Database password {PROJECT} (hidden): ")
        stage = "database_connectivity"
        connectivity = probe(password, IMAGE, ca)
        report.update({"server_version": connectivity["server_version"],
                       "data_mode": connectivity["data_mode"], "tls_mode": "verify-full",
                       "client_image": IMAGE, "age_version": "v1.3.2",
                       "capture_start_utc": datetime.now(UTC).isoformat(),
                       "migration_history_present": connectivity["migration_history_present"],
                       "scope": "Unfiltered pg_dump database plus roles without role passwords",
                       "exclusions": ["role passwords", "Storage object bytes",
                                      "project/API/OAuth/provider secrets and platform settings"],
                       "files": []})
        folder = destination / f"{PROJECT}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
        stage = "backup_directory_creation"
        folder.mkdir(parents=True, exist_ok=False)
        for kind in ("database", "roles"):
            client = f"idx-backup-readonly-{uuid4().hex}"
            archive = folder / f"{kind}.age"
            environment = clean_environment()
            environment.update({"PGPASSWORD": password, "PGSSLMODE": "verify-full",
                                "PGSSLROOTCERT": "/run/db-root-ca.pem",
                                "PGCONNECT_TIMEOUT": "15",
                                "PGOPTIONS": "-c default_transaction_read_only=on "
                                             "-c lock_timeout=5000 -c search_path="})
            print(f"Encrypt {kind}: enter a recovery passphrase in age's hidden console prompt.")
            stage = f"{kind}_dump_encryption"
            try:
                expected = stream_encrypt(dump_command(kind, client, ca), environment, archive,
                                          [str(AGE), "--encrypt", "--passphrase"])
            finally:
                environment.pop("PGPASSWORD", None)
                subprocess.run(docker("rm", "--force", client), capture_output=True,
                               timeout=15, check=False)
            print(f"Verify {kind}: enter the recovery passphrase again; no plaintext file is saved.")
            stage = f"{kind}_decryption_verification"
            observed = decrypted_digest([str(AGE), "--decrypt", str(archive)])
            if observed != expected:
                raise RuntimeError("backup_decryption_digest_mismatch")
            report["files"].append({"file": archive.name, "bytes": archive.stat().st_size,
                                    "sha256": digest_file(archive),
                                    "plaintext_bytes": expected[1], "decryption_verified": True})
        report.update({"status": "encrypted_candidate_decrypt_verified_restore_pending",
                       "capture_end_utc": datetime.now(UTC).isoformat(),
                       "snapshot": "Single pg_dump database snapshot; roles captured separately"})
        (folder / "evidence.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({**report, "backup_directory": str(folder)}, indent=2))
        return 0
    except (KeyboardInterrupt, EOFError):
        reason = "cancelled"
    except PipelineFailure as error:
        reason = str(error)
        report["pipeline"] = error.details
    except RuntimeError as error:
        reason = str(error)
    except OSError as error:
        reason = "local_os_error"
        report["os_error"] = {"type": type(error).__name__, "errno": error.errno,
                              "winerror": getattr(error, "winerror", None)}
    except (ValueError, subprocess.SubprocessError, getpass.GetPassWarning):
        reason = "local_tool_or_stream_failed"
    finally:
        password = ""
    report.update({"status": "failed_incomplete_candidate_do_not_use", "failure": reason,
                   "failure_stage": stage})
    if folder is not None:
        try:
            (folder / "evidence.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        except OSError:
            report["failure_evidence_file_written"] = False
    print(json.dumps(report, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
