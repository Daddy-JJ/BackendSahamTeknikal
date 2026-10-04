"""Guarded approved partial production run for the original actual capture.

Only 129 exact cash-dividend proofs are accepted. The original two runs remain
immutable. Default is offline; --execute writes real market revisions/run only,
never QA trades, Auth settings, migrations or scheduler configuration.
"""

import argparse
import json
from collections import Counter
from datetime import UTC, date, datetime

from audit_scanner_quality_repairs import prepare
from idx_scanner.config_io import load_requests
from idx_scanner.context import quality
from idx_scanner.engine import scan
from idx_scanner.models import ScanState
from idx_scanner.persistence import PersistenceError
from idx_scanner.runner import run_once
from prepare_dev_setup import ROOT, local_env
from publish_first_live_hold_run import REF, TARGET, CapturedProvider, ObservedStore

MANIFEST = ROOT / "config/reference/ksei-reviewed-dividends-20261003.json"
OLD_RUNS = (
    "08fb1080-5889-45e6-903d-3d2400bbf375",
    "b2bba460-abe3-4f68-9946-b13554a7c712",
)
EXPECTED = {"corporate_action_hold": 25, "data_quality_hold": 30, "valid": 45}


def reviewed_preflight(now):
    calendar, universe, proofs, raw, _, prepared = prepare(MANIFEST)
    if now >= calendar.next(TARGET).opens_at:
        raise ValueError("forward_publication_window_elapsed")
    result = scan(prepared, TARGET, calendar, universe, now, ScanState())
    if (
        len(proofs) != 129
        or len({p.ticker for p in proofs}) != 42
        or dict(Counter(quality(s, TARGET, calendar) for s in prepared.values()))
        != EXPECTED
        or result.signals
        or result.ranking.status != "cross_section_incomplete"
    ):
        raise ValueError("reviewed_partial_result_changed")
    requests = load_requests(
        ROOT / "config/reference/yfinance-kompas100-verified-mappings.json",
        "yfinance",
        date(2024, 1, 1),
        TARGET,
    )
    return calendar, universe, proofs, raw, requests, result


def prior_runs(store):
    rows = store._request(
        "GET",
        "scan_runs",
        params={
            "id": "in.(" + ",".join(OLD_RUNS) + ")",
            "select": (
                "id,namespace,data_mode,session_date,status,coverage_valid,"
                "coverage_total,run_digest,stored_at"
            ),
            "order": "id.asc",
        },
    )
    if (
        len(rows) != 2
        or {r["id"] for r in rows} != set(OLD_RUNS)
        or any(
            r["data_mode"] != "live"
            or r["namespace"] != "forward"
            or r["session_date"] != TARGET.isoformat()
            for r in rows
        )
    ):
        raise ValueError("prior_production_runs_not_confirmed")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    report = {
        "project_ref": REF,
        "target": TARGET.isoformat(),
        "started_at_utc": datetime.now(UTC).isoformat(),
        "production_write_attempted": False,
        "scheduler_enabled": False,
        "actual_trades_created": False,
        "scope": "same-target immutable actual Yahoo capture plus reviewed KSEI dividends",
        "stage": "offline_review",
        "hosted_github_runner_tested": False,
    }
    failed = False
    try:
        calendar, universe, proofs, raw, requests, result = reviewed_preflight(
            datetime.now(UTC)
        )
        report.update(
            status="offline_review_passed",
            proof_count=len(proofs),
            coverage_valid=result.coverage_valid,
            coverage_total=result.coverage_total,
            signals=len(result.signals),
            ranking_status=result.ranking.status,
            run_digest=result.run_digest,
        )
        if args.execute:
            env = local_env(ROOT / ".env")
            url = f"https://{REF}.supabase.co"
            if env.get("SUPABASE_URL", "").rstrip("/") != url:
                raise ValueError("production_target_mismatch")
            report["stage"] = "production_read_only_preflight"
            with ObservedStore(url, env["SUPABASE_SECRET_KEY"]) as store:
                store.require_live_schema()
                before = prior_runs(store)
                if store.load_state(through_session=TARGET).signals:
                    raise ValueError("prior_signal_state_requires_review")
                trades_before = store._request(
                    "GET", "actual_trades", params={"select": "id"}
                )
                report["production_write_attempted"] = True
                report["stage"] = "raw_replay_and_derived_revision_publication"
                outcome = run_once(
                    CapturedProvider(raw),
                    store,
                    requests,
                    TARGET,
                    calendar,
                    universe,
                    datetime.now(UTC),
                    clock=lambda: datetime.now(UTC),
                    dividend_evidence=proofs,
                )
                report.update(
                    run_id=outcome.publication["run_id"],
                    replayed=outcome.publication["replayed"],
                    revisions_digest_readback_verified=len(outcome.revision_ids),
                )
                report["stage"] = "production_postflight"
                rows = store._request(
                    "GET",
                    "scan_runs",
                    params={
                        "id": "eq." + report["run_id"],
                        "select": (
                            "id,namespace,data_mode,session_date,status,coverage_valid,"
                            "coverage_total,run_digest,stored_at"
                        ),
                    },
                )
                expected = {
                    "namespace": "forward",
                    "data_mode": "live",
                    "session_date": TARGET.isoformat(),
                    "status": "partial",
                    "coverage_valid": 45,
                    "coverage_total": 100,
                    "run_digest": result.run_digest,
                }
                if len(rows) != 1 or any(rows[0][k] != v for k, v in expected.items()):
                    raise ValueError("production_run_readback_mismatch")
                items = store._request(
                    "GET",
                    "scan_run_items",
                    params={
                        "run_id": "eq." + report["run_id"],
                        "select": "ticker,status",
                    },
                )
                if len(items) != 100 or {i["ticker"]: i["status"] for i in items} != {
                    i.ticker: i.status for i in result.items
                }:
                    raise ValueError("production_item_readback_mismatch")
                if prior_runs(store) != before:
                    raise ValueError("prior_runs_changed")
                if (
                    store._request("GET", "actual_trades", params={"select": "id"})
                    != trades_before
                ):
                    raise ValueError("actual_ledger_count_changed")
                for table in ("scan_runs", "market_series_revisions", "signals"):
                    if store._request(
                        "GET",
                        table,
                        params={
                            "data_mode": "eq.fixture",
                            "select": "id",
                            "limit": "1",
                        },
                    ):
                        raise ValueError("fixture_data_detected")
                report.update(
                    status="production_partial_reconciliation_verified",
                    stored_at=rows[0]["stored_at"],
                    old_runs_unchanged=True,
                    actual_ledger_unchanged=True,
                    fixture_rows_absent=True,
                    counts=dict(Counter(i["status"] for i in items)),
                    production_owner_jwt_tested=False,
                    scanner_full_quality_go=False,
                )
    except (ValueError, PersistenceError) as exc:
        failed = True
        report.update(status="failed", failure=str(exc))
    except Exception:  # noqa: BLE001
        failed = True
        report.update(status="failed", failure="operator_or_transport_failure_redacted")
    report["finished_at_utc"] = datetime.now(UTC).isoformat()
    path = ROOT / "data/ksei-production-run-20261003.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
