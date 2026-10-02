"""Measure local PG17 extension compatibility in a network-disabled disposable container.

No backup is decrypted, no production/dev connection is made and no Auth API runs.
The temporary database is tmpfs; removal is not a promise of secure swap erasure.
"""

import json
import re
import subprocess
import time
from uuid import uuid4

from backup_production_prompt import clean_environment
from check_production_db_prompt import docker

TAG = "supabase/postgres:17.11.0.002"
INIT = (
    "set -eu; initdb -D /tmp/idxpg -U postgres --auth=trust "
    "--encoding=UTF8 --no-locale >/dev/null 2>&1; "
    "exec postgres -D /tmp/idxpg -c listen_addresses='' "
    "-c unix_socket_directories=/tmp -c shared_preload_libraries=pg_stat_statements"
)
SQL = """CREATE EXTENSION pg_stat_statements;
CREATE EXTENSION pgcrypto;
CREATE EXTENSION "uuid-ossp";
CREATE EXTENSION supabase_vault;
SELECT json_build_object('server_version', current_setting('server_version'),
 'extensions', (SELECT jsonb_object_agg(extname,extversion) FROM pg_extension));
"""


def run(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(docker(*args), capture_output=True, env=clean_environment(),
                          timeout=kwargs.pop("timeout", 30), check=False, **kwargs)


def start_command(name: str, image: str) -> tuple[str, ...]:
    if not re.fullmatch(r"idx-restore-check-[a-f0-9]{32}", name):
        raise RuntimeError("invalid_local_container_name")
    if not re.fullmatch(r"supabase/postgres@sha256:[a-f0-9]{64}", image):
        raise RuntimeError("restore_image_digest_required")
    return ("run", "--detach", "--rm", "--pull=never", "--name", name,
            "--network=none", "--read-only", "--user", "postgres", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--tmpfs", "/tmp:rw,size=536870912,mode=1777",
            "--entrypoint", "bash", image, "-c", INIT)


def main() -> int:
    name = f"idx-restore-check-{uuid4().hex}"
    report = {"production_write": False, "remote_database_connected": False,
              "backup_decrypted": False, "restore_verified": False,
              "deployment_gate_passed": False}
    try:
        inspected = run("image", "inspect", "--format", "{{index .RepoDigests 0}}", TAG,
                        text=True)
        image = inspected.stdout.strip()
        args = start_command(name, image)
        report["target_image"] = image
        if run(*args, text=True).returncode:
            raise RuntimeError("isolated_target_start_failed")
        for _ in range(60):
            ready = run("exec", name, "pg_isready", "-h", "/tmp", "-U", "postgres",
                        text=True, timeout=10)
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("isolated_target_not_ready")
        result = run("exec", "-i", name, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                     "-h", "/tmp", "-U", "postgres", "-d", "postgres", input=SQL,
                     text=True)
        if result.returncode:
            raise RuntimeError("managed_extension_preflight_failed")
        measured = json.loads(result.stdout)
        report.update(measured)
        expected = {"pg_stat_statements": "1.11", "pgcrypto": "1.3",
                    "uuid-ossp": "1.1", "supabase_vault": "0.3.1"}
        if (not measured["server_version"].startswith("17.")
                or any(measured["extensions"].get(k) != v for k, v in expected.items())):
            raise RuntimeError("source_extension_versions_do_not_match")
        report.update({"status": "isolated_pg17_extension_preflight_passed_not_a_restore",
                       "source_required_extensions_match": True,
                       "network": "none", "published_ports": [], "storage": "temporary tmpfs"})
    except RuntimeError as error:
        report.update({"status": "target_preflight_failed", "failure": str(error)})
    except (OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt):
        report.update({"status": "target_preflight_failed", "failure": "local_tool_failed"})
    finally:
        removed = run("rm", "--force", name, text=True)
        report["temporary_target_removed"] = removed.returncode == 0
    print(json.dumps(report, indent=2))
    return 0 if report.get("source_required_extensions_match") else 1


if __name__ == "__main__":
    raise SystemExit(main())
