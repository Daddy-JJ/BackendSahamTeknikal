"""Real anonymous/outsider PostgREST checks; never impersonates the owner."""

import argparse
import json
import secrets
import sys
from uuid import uuid4

import httpx
from check_dev_actual_ready import FILL_SELECT, TABLES
from verify_dev_non_owner_rls import DEV_URL, ROOT, read_env

MARKER = ROOT / "data/dev-m4-outsider-cleanup.json"


def verify() -> None:
    env = read_env(ROOT / ".env.development")
    frontend = read_env(ROOT.parent / "frontend/.env.development.local")
    if env.get("SUPABASE_URL", "").rstrip("/") != DEV_URL or frontend.get(
        "NEXT_PUBLIC_SUPABASE_URL", ""
    ).rstrip("/") != DEV_URL:
        raise ValueError("development_project_mismatch")
    if MARKER.exists():
        raise ValueError("prior_temp_user_cleanup_required")
    key = frontend["NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"]
    with (
        httpx.Client(base_url=DEV_URL + "/", headers={"apikey": env["SUPABASE_SECRET_KEY"]},
                     timeout=20, follow_redirects=False) as admin,
        httpx.Client(base_url=DEV_URL + "/", headers={"apikey": key},
                     timeout=20, follow_redirects=False) as public,
    ):
        mode = admin.get("rest/v1/deployment_settings", params={"select": "data_mode"})
        if mode.status_code != 200 or mode.json() != [{"data_mode": "fixture"}]:
            raise ValueError("development_fixture_mode_required")
        trades = admin.get("rest/v1/actual_trades", params={"select": "id", "limit": 1})
        if trades.status_code != 200:
            raise ValueError("migration_005_required")
        populated = bool(trades.json())
        trade_id = trades.json()[0]["id"] if populated else str(uuid4())
        mutations = {
            "apply_actual_journal": {"p_action": "note", "p_trade_id": trade_id,
                                     "p_payload": {"expected_revision": 1,
                                                   "body": "Must be denied"},
                                     "p_request_id": str(uuid4())},
            "actual_journal_analytics": {"p_exit_snapshot": None},
            "export_actual_journal": {"p_status": "closed", "p_limit": 200,
                                      "p_after": None, "p_exit_snapshot": None},
        }

        def denial(response: httpx.Response) -> None:
            if response.status_code not in (401, 403) or response.json().get("code") != "42501":
                raise ValueError("expected_42501_denial_missing")

        for table in (*TABLES, "audit_events"):
            denial(public.get("rest/v1/" + table, params={"select": "*", "limit": 1}))
        for name, payload in mutations.items():
            denial(public.post("rest/v1/rpc/" + name, json=payload))
        print("Anonymous: eight table reads and three named RPC requests denied with 42501.")
        email = f"idx-m4-{uuid4().hex}@example.invalid"
        password = secrets.token_urlsafe(36)
        user_id = None
        try:
            created = admin.post("auth/v1/admin/users", json={
                "email": email, "password": password, "email_confirm": True,
                "user_metadata": {"purpose": "temporary_dev_m4_outsider"},
            })
            if created.status_code not in (200, 201):
                raise ValueError("outsider_create_failed")
            user_id = created.json()["id"]
            MARKER.write_text(json.dumps({"user_id": user_id}), encoding="utf-8")
            signed = public.post("auth/v1/token", params={"grant_type": "password"},
                                 json={"email": email, "password": password})
            if signed.status_code != 200:
                raise ValueError("outsider_login_failed")
            with httpx.Client(
                base_url=DEV_URL + "/rest/v1/",
                headers={"apikey": key, "Authorization": "Bearer " + signed.json()["access_token"]},
                timeout=20, follow_redirects=False,
            ) as outsider:
                for table in (*TABLES, "audit_events"):
                    response = outsider.get(table, params={"select": "*", "limit": 1})
                    if response.status_code != 200 or response.json() != []:
                        raise ValueError("outsider_table_not_isolated")
                embedded = outsider.get("actual_fills", params={
                    "select": FILL_SELECT, "trade_id": "eq." + trade_id,
                    "latest_correction.order": "sequence.desc", "latest_correction.limit": 1,
                })
                if embedded.status_code != 200 or embedded.json() != []:
                    raise ValueError("outsider_embedding_not_isolated")
                for name, payload in mutations.items():
                    denial(outsider.post("rpc/" + name, json=payload))
            print("Real outsider JWT: eight tables/embedding empty; three RPCs denied with 42501.")
            if not populated:
                print("Ledger had no rows: cross-owner row isolation is not proven by this read.")
        finally:
            if user_id:
                deleted = admin.delete("auth/v1/admin/users/" + user_id)
                if deleted.status_code not in (200, 204):
                    raise ValueError("outsider_cleanup_required_marker_retained")
                MARKER.unlink(missing_ok=True)
                print("Disposable outsider Auth account deleted; no email sent.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute required for disposable development Auth account")
    try:
        verify()
    except (httpx.HTTPError, ValueError, KeyError, OSError) as error:
        # Explicit ValueError messages are static codes; never dump HTTP bodies/headers.
        print(str(error) if isinstance(error, ValueError) else type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from None
