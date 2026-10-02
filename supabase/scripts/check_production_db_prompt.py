"""Hidden local password prompt and fixed-target, read-only SQL connectivity probe.

No .env access, password file, SQL migration, database server or persistent volume.
The password is forwarded temporarily by Docker environment-variable name only.
Run in a real PowerShell terminal, not through a chat tool or recorded transcript.
"""

import argparse
import getpass
import json
import os
import re
import ssl
import subprocess
import sys
import warnings
from pathlib import Path
from uuid import uuid4

PROJECT = "hcjfxbynqzsaidlwvdfx"
HOST = "aws-0-ap-northeast-1.pooler.supabase.com"
USER = f"postgres.{PROJECT}"
SQL = """BEGIN READ ONLY;
SELECT pg_catalog.json_build_object(
  'project_ref', 'hcjfxbynqzsaidlwvdfx',
  'database', pg_catalog.current_database(),
  'server_version', pg_catalog.current_setting('server_version'),
  'read_only', pg_catalog.current_setting('transaction_read_only') = 'on',
  'data_mode', (SELECT data_mode FROM public.deployment_settings),
  'migration_history_present',
    pg_catalog.to_regclass('supabase_migrations.schema_migrations') IS NOT NULL
);
ROLLBACK;
"""


def docker(*args: str) -> list[str]:
    return ["docker", "--context", "desktop-linux", *args]


def image_digest() -> str:
    result = subprocess.run(
        docker("image", "inspect", "--format", "{{index .RepoDigests 0}}", "postgres:17"),
        capture_output=True, text=True, timeout=15, check=False,
    )
    digest = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"postgres@sha256:[a-f0-9]{64}", digest):
        raise RuntimeError("postgres_client_image_missing")
    return digest


def validate_ca_cert(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or resolved.stat().st_size > 1_000_000 or "," in str(resolved):
        raise RuntimeError("ca_certificate_invalid")
    content = resolved.read_bytes()
    if b"PRIVATE KEY" in content or b"-----BEGIN CERTIFICATE-----" not in content:
        raise RuntimeError("ca_certificate_invalid")
    try:
        ssl.create_default_context(cafile=str(resolved))
    except ssl.SSLError:
        raise RuntimeError("ca_certificate_invalid") from None
    return resolved


def driver_failure(stderr: str) -> str:
    error = stderr.lower()
    if "password authentication failed" in error:
        return "authentication_failed"
    if "no password supplied" in error:
        return "authentication_password_missing"
    if "tenant or user not found" in error:
        return "pooler_target_not_found"
    if "does not match host name" in error or "hostname mismatch" in error:
        return "tls_hostname_mismatch"
    if "root certificate" in error and "does not exist" in error:
        return "tls_ca_missing"
    if "certificate verify failed" in error or "certificate verification failed" in error:
        return "tls_verification_failed"
    if "ssl" in error or "tls" in error:
        return "tls_connection_failed"
    if "timeout" in error or "timed out" in error:
        return "connection_timeout"
    return "connection_or_query_failed"


def probe(password: str, image: str, ca_cert: Path | None = None,
          *, tls_only: bool = False) -> dict:
    if not password and not tls_only:
        raise ValueError("empty_password")
    client = f"idx-db-readonly-{uuid4().hex}"
    environment = os.environ.copy()
    environment.pop("PGPASSWORD", None)
    environment.update({
        "PGSSLMODE": "verify-full",
        "PGSSLROOTCERT": "/run/db-root-ca.pem" if ca_cert else "system",
        "PGCONNECT_TIMEOUT": "15",
        "PGOPTIONS": "-c default_transaction_read_only=on -c statement_timeout=15000 "
                     "-c lock_timeout=5000 -c search_path=",
    })
    if not tls_only:
        environment["PGPASSWORD"] = password
    mounts = (["--mount", f"type=bind,src={ca_cert},dst=/run/db-root-ca.pem,readonly"]
              if ca_cert else [])
    args = docker(
        "run", "--rm", "--pull=never", "--name", client, "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges", "-i",
        *mounts,
        "--env", "PGPASSWORD", "--env", "PGSSLMODE", "--env", "PGSSLROOTCERT",
        "--env", "PGCONNECT_TIMEOUT", "--env", "PGOPTIONS",
        "--entrypoint", "psql", image, "-X", "-qAt", "-w",
        "-v", "ON_ERROR_STOP=1", "-h", HOST, "-p", "5432", "-U", USER, "-d", "postgres",
    )
    try:
        result = subprocess.run(
            args, input="" if tls_only else SQL, capture_output=True, text=True, timeout=60,
            check=False, env=environment,
        )
        if result.returncode:
            reason = driver_failure(result.stderr)
            if tls_only and reason == "authentication_password_missing":
                return {"project_ref": PROJECT, "tls_verified": True,
                        "tls_mode": "verify-full", "password_tested": False,
                        "database_query_executed": False, "production_write": False,
                        "client_image": image}
            # Never print raw driver output, the password or environment.
            raise RuntimeError(reason)
        if tls_only:
            raise RuntimeError("unexpected_passwordless_authentication")
        report = json.loads(result.stdout)
        if (report.get("project_ref") != PROJECT or report.get("database") != "postgres"
                or report.get("read_only") is not True or report.get("data_mode") != "live"):
            raise RuntimeError("production_read_only_guard_failed")
        return {**report, "tls_mode": "verify-full", "client_image": image,
                "backup_created": False, "production_write": False}
    finally:
        environment.pop("PGPASSWORD", None)
        # Remove only this script's unique temporary client, including after timeout.
        subprocess.run(docker("rm", "--force", client), capture_output=True,
                       timeout=15, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-tooling", action="store_true")
    parser.add_argument("--ca-cert", type=Path,
                        help="Public CA certificate downloaded from this production Dashboard")
    parser.add_argument("--check-tls", action="store_true",
                        help="Verify TLS without entering a password or executing SQL")
    args = parser.parse_args()
    password = ""
    try:
        image = image_digest()
        if args.check_tooling:
            result = subprocess.run(
                docker("run", "--rm", "--pull=never", "--read-only", "--entrypoint",
                       "psql", image, "--version"),
                capture_output=True, text=True, timeout=20, check=False,
            )
            if result.returncode:
                raise RuntimeError("postgres_client_unavailable")
            print(json.dumps({"client_image": image, "client_version": result.stdout.strip(),
                              "database_connected": False}))
            return 0
        if not args.ca_cert:
            raise RuntimeError("production_ca_certificate_required")
        ca_cert = validate_ca_cert(args.ca_cert)
        if args.check_tls:
            print(json.dumps(probe("", image, ca_cert, tls_only=True), indent=2))
            return 0
        if not sys.stdin.isatty():
            raise RuntimeError("run_in_local_interactive_terminal")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass(f"Database password {PROJECT} (hidden): ")
        print(json.dumps(probe(password, image, ca_cert), indent=2))
        return 0
    except (KeyboardInterrupt, EOFError):
        print('{"probe_failed":"cancelled"}')
    except (OSError, subprocess.TimeoutExpired, getpass.GetPassWarning, ValueError):
        print('{"probe_failed":"local_tool_or_input_error"}')
    except RuntimeError as error:
        print(json.dumps({"probe_failed": str(error)}))
    finally:
        password = ""
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
