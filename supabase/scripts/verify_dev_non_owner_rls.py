"""Verify non-owner RLS with a disposable Supabase development Auth user.

The temporary account uses a reserved .invalid email domain, is deleted in a
finally block, and a local ignored marker supports cleanup if interrupted.
"""

import argparse
import json
import secrets
import sys
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[2]
DEV_URL = "https://vgmkpsestahkfahzdtae.supabase.co"
MARKER = ROOT / "data/dev-rls-temp-user.json"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        row = line.strip()
        if row and not row.startswith("#") and "=" in row:
            key, value = row.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
    return values


def verify() -> None:
    backend = read_env(ROOT / ".env.development")
    frontend = read_env(ROOT.parent / "frontend/.env.development.local")
    if (
        backend.get("SUPABASE_URL") != DEV_URL
        or frontend.get("NEXT_PUBLIC_SUPABASE_URL") != DEV_URL
        or not backend.get("SUPABASE_SECRET_KEY")
        or not frontend.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    ):
        raise ValueError("dev_project_config_invalid")
    if MARKER.exists():
        raise ValueError("previous_temp_user_cleanup_required")

    secret = backend["SUPABASE_SECRET_KEY"]
    publishable = frontend["NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"]
    email = f"idx-rls-{uuid4().hex}@example.invalid"
    password = secrets.token_urlsafe(36)
    user_id: str | None = None
    cleanup_ok = False
    auth_url = DEV_URL + "/auth/v1/"
    rest_url = DEV_URL + "/rest/v1/"
    with (
        httpx.Client(
            base_url=auth_url,
            headers={"apikey": secret},
            timeout=20,
            follow_redirects=False,
        ) as admin,
        httpx.Client(
            base_url=auth_url,
            headers={"apikey": publishable},
            timeout=20,
            follow_redirects=False,
        ) as auth,
        httpx.Client(
            base_url=rest_url,
            headers={"apikey": secret},
            timeout=20,
            follow_redirects=False,
        ) as service,
    ):
        try:
            signals = service.get(
                "signals", params={"select": "id", "namespace": "eq.dev_smoke_m2"}
            )
            if signals.status_code != 200 or not signals.json():
                raise ValueError("dev_fixture_signal_missing")
            signal_id = signals.json()[0]["id"]
            before = service.get("signal_actions", params={"select": "owner_id"})
            if before.status_code != 200:
                raise ValueError("action_baseline_unavailable")
            before_count = len(before.json())

            created = admin.post(
                "admin/users",
                json={
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {"purpose": "temporary_dev_rls_test"},
                },
            )
            if created.status_code not in (200, 201):
                raise ValueError(f"temp_user_create_status_{created.status_code}")
            user_id = created.json().get("id")
            if not isinstance(user_id, str):
                raise TypeError("temp_user_id_missing")
            MARKER.parent.mkdir(parents=True, exist_ok=True)
            MARKER.write_text(json.dumps({"user_id": user_id}), encoding="utf-8")

            signed_in = auth.post(
                "token",
                params={"grant_type": "password"},
                json={"email": email, "password": password},
            )
            if signed_in.status_code != 200:
                raise ValueError(f"temp_user_login_status_{signed_in.status_code}")
            jwt = signed_in.json().get("access_token")
            if not isinstance(jwt, str) or not jwt:
                raise ValueError("temp_user_jwt_missing")
            with httpx.Client(
                base_url=rest_url,
                headers={"apikey": publishable, "Authorization": f"Bearer {jwt}"},
                timeout=20,
                follow_redirects=False,
            ) as outsider:
                for table in ("scan_runs", "signals", "app_members"):
                    response = outsider.get(table, params={"select": "*", "limit": "5"})
                    if response.status_code != 200 or response.json() != []:
                        raise ValueError(f"non_owner_{table}_not_empty")
                action = outsider.post(
                    "rpc/set_signal_action",
                    json={
                        "p_signal_id": signal_id,
                        "p_action": "planned",
                        "p_expected_revision": 0,
                        "p_request_id": str(uuid4()),
                    },
                )
                if action.status_code not in (400, 403):
                    raise ValueError(f"non_owner_action_status_{action.status_code}")
                if action.json().get("code") != "42501":
                    raise ValueError("non_owner_action_wrong_error")
            after = service.get("signal_actions", params={"select": "owner_id"})
            if after.status_code != 200 or len(after.json()) != before_count:
                raise ValueError("non_owner_action_left_residue")
            print("Dev non-owner JWT: three private reads empty, action denied, no residue.")
        finally:
            if user_id is not None:
                try:
                    deleted = admin.delete(f"admin/users/{user_id}")
                    cleanup_ok = deleted.status_code in (200, 204)
                except httpx.HTTPError:
                    cleanup_ok = False
                if cleanup_ok:
                    MARKER.unlink(missing_ok=True)
                else:
                    print(
                        "Temporary dev user cleanup failed; inspect ignored "
                        "backend/data/dev-rls-temp-user.json before rerunning.",
                        file=sys.stderr,
                    )
    if user_id is not None and not cleanup_ok:
        raise ValueError("temp_user_cleanup_failed")
    print("Temporary development Auth user deleted.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print("Dry run only. Pass --execute for disposable dev Auth/RLS test.")
        return 0
    try:
        verify()
        return 0
    except (OSError, KeyError, TypeError, ValueError, httpx.HTTPError) as error:
        code = str(error) if isinstance(error, ValueError) else "dev_rls_test_failed"
        print(f"Dev RLS verification failed: {code}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())