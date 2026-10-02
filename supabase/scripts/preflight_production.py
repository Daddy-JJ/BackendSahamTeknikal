"""GET-only production API preflight. No financial data or credentials in output."""

import json
import sys

import httpx
from check_dev_actual_ready import FILL_SELECT, TABLES
from prepare_dev_setup import ROOT, local_env

PROD_REF = "hcjfxbynqzsaidlwvdfx"
PROD_URL = f"https://{PROD_REF}.supabase.co"


def inspect(env: dict[str, str], transport=None) -> dict:
    if env.get("SUPABASE_URL", "").rstrip("/") != PROD_URL:
        raise ValueError("production_project_mismatch")
    report = {"project_ref": PROD_REF, "method": "GET only", "checks": {}}
    with httpx.Client(
        base_url=PROD_URL + "/rest/v1/",
        headers={"apikey": env["SUPABASE_SECRET_KEY"]},
        transport=transport, timeout=20, follow_redirects=False,
    ) as client:
        checks = report["checks"]
        mode = client.get("deployment_settings", params={"select": "data_mode"})
        checks["live_mode"] = mode.status_code == 200 and mode.json() == [{"data_mode": "live"}]
        owner = env.get("APP_OWNER_USER_ID")
        if owner:
            response = client.get("app_members", params={
                "select": "role,enabled", "user_id": f"eq.{owner}",
            })
            checks["configured_owner_enabled"] = (
                response.status_code == 200
                and response.json() == [{"role": "owner", "enabled": True}]
            )
        else:
            checks["configured_owner_enabled"] = None
        for table in ("market_series_revisions", "market_bar_revisions", *TABLES):
            response = client.get(table, params={"select": "*", "limit": 0})
            body = response.json()
            checks[table] = {"http": response.status_code,
                             "code": body.get("code") if isinstance(body, dict) else None}
        response = client.get("rpc/scan_publish_capabilities")
        checks["scan_publish_capabilities"] = {
            "http": response.status_code,
            "deadline_version": response.json().get("deadline_version")
            if response.status_code == 200 else None,
        }
        response = client.get("actual_fills", params={
            "select": FILL_SELECT, "limit": 0,
            "latest_correction.order": "sequence.desc", "latest_correction.limit": 1,
        })
        checks["correction_embedding_http"] = response.status_code
        # Only aggregate counts, never return signal/trade records.
        for table in ("scan_runs", "signals", "market_series_revisions", "actual_trades"):
            response = client.get(table, params={
                "select": "id", "data_mode": "eq.fixture", "limit": 0,
            }, headers={"Prefer": "count=exact"})
            checks[f"{table}_fixture_count"] = (
                response.headers.get("content-range", "unknown").split("/")[-1]
                if response.status_code == 200 else "schema_unavailable"
            )
    report["rls_smoke_proven"] = False
    report["deployment_authorized"] = False
    return report


if __name__ == "__main__":
    try:
        print(json.dumps(inspect(local_env(ROOT / ".env")), indent=2))
    except (httpx.HTTPError, ValueError, KeyError, OSError) as error:
        print(json.dumps({"preflight_failed": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
