"""Read-only development schema/embedding readiness, never an RLS smoke claim."""

import json
import sys

import httpx
from verify_dev_non_owner_rls import DEV_URL, ROOT, read_env

FILL_SELECT = (
    "id,side,filled_at,sequence,quantity,price_idr,fee_idr,fee_status,"
    "latest_correction:actual_fill_corrections!actual_fill_corrections_fill_id_fkey"
    "(sequence,filled_at,fill_id,quantity,price_idr,fee_idr,fee_status,reason)"
)
TABLES = (
    "actual_trades", "actual_fills", "actual_fill_corrections", "actual_stop_events",
    "actual_notes", "actual_trade_tags", "actual_journal_requests",
)


def check() -> bool:
    env = read_env(ROOT / ".env.development")
    if env.get("SUPABASE_URL", "").rstrip("/") != DEV_URL:
        raise ValueError("development_project_mismatch")
    with httpx.Client(
        base_url=DEV_URL + "/rest/v1/", headers={"apikey": env["SUPABASE_SECRET_KEY"]},
        timeout=20, follow_redirects=False,
    ) as rest:
        mode = rest.get("deployment_settings", params={"select": "data_mode"})
        if mode.status_code != 200 or mode.json() != [{"data_mode": "fixture"}]:
            raise ValueError("development_fixture_mode_required")
        ready = True
        for table in TABLES:
            response = rest.get(table, params={"select": "*", "limit": 0})
            body = response.json()
            passed = response.status_code == 200 and body == []
            ready = ready and passed
            print(json.dumps({"table": table, "http": response.status_code,
                              "ready": passed,
                              "code": body.get("code") if isinstance(body, dict) else None}))
        if ready:
            response = rest.get("actual_fills", params={
                "select": FILL_SELECT, "order": "sequence.desc", "limit": 0,
                "latest_correction.order": "sequence.desc", "latest_correction.limit": 1,
            })
            ready = response.status_code == 200 and response.json() == []
            print(json.dumps({"embedding_query_ready": ready, "http": response.status_code}))
        print(json.dumps({"project": DEV_URL, "data_mode": "fixture", "schema_ready": ready,
                          "owner_jwt_tested_by_this_script": False,
                          "concurrency_tested_by_this_script": False}))
        return ready


if __name__ == "__main__":
    try:
        raise SystemExit(0 if check() else 2)
    except (httpx.HTTPError, ValueError, KeyError, OSError) as error:
        # Never print exception text from HTTP requests or local credential parsing.
        print(json.dumps({"check_failed": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
