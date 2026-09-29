"""Read-only owner JWT/RLS probe for the isolated Supabase development project.

The owner types credentials into a local terminal. Password and JWT stay in
memory and are never written to a file or printed.
"""

import argparse
import getpass
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
DEV_URL = "https://vgmkpsestahkfahzdtae.supabase.co"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        row = line.strip()
        if row and not row.startswith("#") and "=" in row:
            key, value = row.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
    return values


def config() -> tuple[str, str]:
    backend = read_env(ROOT / ".env.development")
    frontend = read_env(ROOT.parent / "frontend/.env.development.local")
    if (
        backend.get("SUPABASE_URL") != DEV_URL
        or frontend.get("NEXT_PUBLIC_SUPABASE_URL") != DEV_URL
        or not backend.get("APP_OWNER_USER_ID")
        or not frontend.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    ):
        raise ValueError("dev_owner_config_invalid")
    return backend["APP_OWNER_USER_ID"], frontend["NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"]


def verify() -> None:
    owner_uid, publishable = config()
    email = input("Email akun Auth owner di proyek development: ").strip()
    password = getpass.getpass("Password akun tersebut: ")
    if not email or not password:
        raise ValueError("credentials_missing")
    with httpx.Client(
        base_url=DEV_URL + "/auth/v1/",
        headers={"apikey": publishable},
        timeout=20,
        follow_redirects=False,
    ) as auth:
        response = auth.post(
            "token",
            params={"grant_type": "password"},
            json={"email": email, "password": password},
        )
    if response.status_code != 200:
        raise ValueError(f"owner_login_status_{response.status_code}")
    body = response.json()
    if body.get("user", {}).get("id") != owner_uid:
        raise ValueError("signed_in_user_is_not_dev_owner")
    jwt = body.get("access_token")
    if not isinstance(jwt, str) or not jwt:
        raise ValueError("owner_jwt_missing")
    with httpx.Client(
        base_url=DEV_URL + "/rest/v1/",
        headers={"apikey": publishable, "Authorization": f"Bearer {jwt}"},
        timeout=20,
        follow_redirects=False,
    ) as rest:
        membership = rest.get("app_members", params={"select": "user_id,role,enabled"})
        runs = rest.get(
            "scan_runs", params={"select": "id,data_mode", "namespace": "eq.dev_smoke_m2"}
        )
        signals = rest.get("signals", params={"select": "id", "namespace": "eq.dev_smoke_m2"})
        actions = rest.get("signal_actions", params={"select": "signal_id", "limit": "1"})
    if any(r.status_code != 200 for r in (membership, runs, signals, actions)):
        raise ValueError("owner_rls_read_status_failed")
    if membership.json() != [{"user_id": owner_uid, "role": "owner", "enabled": True}]:
        raise ValueError("owner_membership_not_visible")
    if len(runs.json()) != 1 or runs.json()[0].get("data_mode") != "fixture":
        raise ValueError("owner_scan_run_not_visible")
    if len(signals.json()) != 2:
        raise ValueError("owner_signals_not_visible")
    print("Dev owner JWT/RLS passed: membership, one fixture run, two signals visible.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args()
    try:
        if args.check_config:
            config()
            print("Dev owner RLS probe configured; no login attempted.")
        else:
            verify()
        return 0
    except (EOFError, OSError, KeyError, ValueError, httpx.HTTPError) as error:
        code = str(error) if isinstance(error, ValueError) else "owner_rls_probe_failed"
        print(f"Dev owner RLS probe failed: {code}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())