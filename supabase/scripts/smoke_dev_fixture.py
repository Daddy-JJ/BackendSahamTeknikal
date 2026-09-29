"""Publish one labeled synthetic scan to the isolated Supabase development project.

The production project is rejected before any network write. This script is
manual and requires --execute; the fixture stays in its own namespace.
"""

import argparse
import sys
from datetime import timedelta
from pathlib import Path

import httpx
from idx_scanner.engine import scan
from idx_scanner.fixtures import sample_market
from idx_scanner.models import ScanState
from idx_scanner.persistence import PersistenceError, SupabaseScanStore

ROOT = Path(__file__).resolve().parents[2]
DEV_URL = "https://vgmkpsestahkfahzdtae.supabase.co"
NAMESPACE = "dev_smoke_m2"


def dev_env() -> tuple[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env.development").read_text(encoding="utf-8-sig").splitlines():
        row = line.strip()
        if not row or row.startswith("#") or "=" not in row:
            continue
        key, value = row.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    if values.get("SUPABASE_URL") != DEV_URL or not values.get("SUPABASE_SECRET_KEY"):
        raise ValueError("dev_project_config_invalid")
    return DEV_URL, values["SUPABASE_SECRET_KEY"]


def fixture_scan():
    series, calendar, universe = sample_market(620)
    session = calendar.sessions[619]
    result = scan(
        series,
        session.day,
        calendar,
        universe,
        session.closes_at + timedelta(hours=3),
        ScanState(),
    )
    if result.status != "complete" or len(result.signals) == 0 or any(
        signal.data_mode != "fixture" for signal in result.signals
    ):
        raise ValueError("fixture_snapshot_invalid")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        url, key = dev_env()
        result = fixture_scan()
        with httpx.Client(
            base_url=url + "/rest/v1/",
            headers={"apikey": key},
            timeout=20,
            follow_redirects=False,
        ) as client:
            setting = client.get(
                "deployment_settings",
                params={"select": "data_mode", "singleton": "eq.true"},
            )
            if setting.status_code != 200 or setting.json() != [{"data_mode": "fixture"}]:
                raise ValueError("dev_database_not_in_fixture_mode")
            print(
                f"Dev fixture ready: namespace={NAMESPACE}, "
                f"coverage={result.coverage_valid}/{result.coverage_total}, "
                f"signals={len(result.signals)}"
            )
            if not args.execute:
                print("Dry run only. Pass --execute to publish and verify replay.")
                return 0
            with SupabaseScanStore(url, key) as store:
                first = store.publish(result, namespace=NAMESPACE, data_mode="fixture")
                replay = store.publish(result, namespace=NAMESPACE, data_mode="fixture")
                loaded = store.load_state(
                    through_session=result.session, namespace=NAMESPACE, data_mode="fixture"
                )
            if set(loaded.signals) != {signal.id for signal in result.signals}:
                raise ValueError("saved_signal_reload_mismatch")
            if first["run_id"] != replay["run_id"] or replay["replayed"] is not True:
                raise ValueError("idempotency_result_mismatch")
            rows = client.get(
                "scan_runs",
                params={
                    "select": "id,data_mode,status,coverage_valid,coverage_total",
                    "namespace": f"eq.{NAMESPACE}",
                },
            )
            if rows.status_code != 200 or len(rows.json()) != 1:
                raise ValueError("run_count_mismatch")
            saved = rows.json()[0]
            if (
                saved["id"] != first["run_id"]
                or saved["data_mode"] != "fixture"
                or saved["status"] != result.status
                or saved["coverage_valid"] != result.coverage_valid
                or saved["coverage_total"] != result.coverage_total
            ):
                raise ValueError("saved_run_mismatch")
            items = client.get(
                "scan_run_items",
                params={"select": "ticker", "run_id": f"eq.{first['run_id']}"},
            )
            signals = client.get(
                "signals", params={"select": "id", "namespace": f"eq.{NAMESPACE}"}
            )
            audits = client.get(
                "audit_events",
                params={
                    "select": "id",
                    "entity_id": f"eq.{first['run_id']}",
                    "action": "eq.scan_published",
                },
            )
            if any(response.status_code != 200 for response in (items, signals, audits)):
                raise ValueError("related_read_failed")
            if (len(items.json()), len(signals.json()), len(audits.json())) != (
                result.coverage_total, len(result.signals), 1
            ):
                raise ValueError("related_count_mismatch")
            print("Dev RPC, exact replay, reload and related counts verified; one labeled run stored.")
            return 0
    except (OSError, KeyError, ValueError, httpx.HTTPError, PersistenceError) as error:
        code = error.code if isinstance(error, PersistenceError) else (
            str(error) if isinstance(error, ValueError) else "dev_smoke_failed"
        )
        print(f"Dev smoke failed: {code}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())