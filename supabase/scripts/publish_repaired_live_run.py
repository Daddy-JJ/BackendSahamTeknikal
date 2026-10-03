"""Guarded one-off publication of the reviewed 2026-10-02 partial live scan.

Defaults to offline. Production execution preserves the original held run and
all raw receipts, stores derived revisions, and never creates trades or schedules.
This narrowly reviewed capture currently has zero entry signals.
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

ORIGINAL_RUN = "08fb1080-5889-45e6-903d-3d2400bbf375"
EXPECTED = {"corporate_action_hold": 59, "data_quality_hold": 30, "valid": 11}


def reviewed_preflight(now):
    calendar, universe, proofs, raw, _, prepared = prepare()
    requests = load_requests(
        ROOT / "config/reference/yfinance-kompas100-verified-mappings.json",
        "yfinance",
        date(2024, 1, 1),
        TARGET,
    )
    if (
        calendar.data_mode != "live"
        or universe.data_mode != "live"
        or set(requests) != set(raw)
    ):
        raise ValueError("reviewed_live_context_required")
    if now >= calendar.next(TARGET).opens_at:
        raise ValueError("reviewed_capture_publication_window_elapsed")
    counts = dict(Counter(quality(s, TARGET, calendar) for s in prepared.values()))
    result = scan(prepared, TARGET, calendar, universe, now, ScanState())
    if (
        counts != EXPECTED
        or result.signals
        or result.ranking.status != "cross_section_incomplete"
    ):
        raise ValueError("reviewed_partial_zero_signal_result_required")
    if len(proofs) != 7 or {p.ticker for p in proofs} != {"BBCA"}:
        raise ValueError("reviewed_bbca_evidence_required")
    return calendar, universe, proofs, raw, requests, result


def read_original(store):
    rows = store._request(
        "GET",
        "scan_runs",
        params={
            "id": "eq." + ORIGINAL_RUN,
            "select": "id,namespace,data_mode,session_date,status,coverage_valid,coverage_total,stored_at,run_digest",
        },
    )
    if len(rows) != 1 or any(
        rows[0][k] != v
        for k, v in {
            "data_mode": "live",
            "namespace": "forward",
            "session_date": TARGET.isoformat(),
            "status": "failed",
            "coverage_valid": 0,
            "coverage_total": 100,
        }.items()
    ):
        raise ValueError("original_held_run_precondition_failed")
    return rows[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    report = {
        "project_ref": REF,
        "target": TARGET.isoformat(),
        "started_at_utc": datetime.now(UTC).isoformat(),
        "stage": "offline_review",
        "production_write_attempted": False,
        "scheduler_enabled": False,
        "actual_trades_created": False,
        "provider": "yfinance",
        "scope": "approved A normalization plus seven source-reviewed BBCA cash dividends; local one-off runner",
    }
    try:
        calendar, universe, proofs, raw, requests, result = reviewed_preflight(
            datetime.now(UTC)
        )
        report.update(
            status="offline_review_passed",
            coverage_valid=11,
            coverage_total=100,
            signals=0,
            ranking_status=result.ranking.status,
            run_digest=result.run_digest,
        )
        if args.execute:
            env = local_env(ROOT / ".env")
            url = f"https://{REF}.supabase.co"
            if env.get("SUPABASE_URL", "").rstrip("/") != url:
                raise ValueError("production_project_mismatch")
            report["stage"] = "production_read_only_preflight"
            with ObservedStore(url, env["SUPABASE_SECRET_KEY"]) as store:
                store.require_live_schema()
                original = read_original(store)
                if store.load_state(through_session=TARGET).signals:
                    raise ValueError("unexpected_prior_signal_state_review_required")
                report["production_write_attempted"] = True
                report["stage"] = "raw_replay_derived_ingest_and_partial_publish"
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
                        "select": "id,namespace,data_mode,session_date,status,coverage_valid,coverage_total,run_digest,stored_at",
                    },
                )
                if len(rows) != 1 or any(
                    rows[0][k] != v
                    for k, v in {
                        "data_mode": "live",
                        "namespace": "forward",
                        "session_date": TARGET.isoformat(),
                        "status": "partial",
                        "coverage_valid": 11,
                        "coverage_total": 100,
                        "run_digest": result.run_digest,
                    }.items()
                ):
                    raise ValueError("partial_run_readback_mismatch")
                items = store._request(
                    "GET",
                    "scan_run_items",
                    params={
                        "run_id": "eq." + report["run_id"],
                        "select": "ticker,status",
                    },
                )
                expected_items = {i.ticker: i.status for i in result.items}
                if (
                    len(items) != 100
                    or {i["ticker"]: i["status"] for i in items} != expected_items
                ):
                    raise ValueError("partial_items_readback_mismatch")
                if read_original(store) != original:
                    raise ValueError("original_held_run_changed")
                for table in (
                    "scan_runs",
                    "signals",
                    "market_series_revisions",
                    "actual_trades",
                ):
                    if store._request(
                        "GET",
                        table,
                        params={
                            "data_mode": "eq.fixture",
                            "select": "id",
                            "limit": "1",
                        },
                    ):
                        raise ValueError("unexpected_production_fixture_data")
                if store.load_state(through_session=TARGET).signals:
                    raise ValueError("unexpected_signal_after_zero_signal_run")
                report.update(
                    status="production_partial_repair_verified_scanner_quality_no_go",
                    stored_at=rows[0]["stored_at"],
                    original_held_run_unchanged=True,
                    item_status_counts=dict(Counter(i["status"] for i in items)),
                    fixture_rows_absent=True,
                    production_signals=0,
                    production_mode="live",
                    owner_jwt_read_tested=False,
                )
    except (PersistenceError, ValueError, KeyError, OSError) as error:
        report.update(
            status="failed_stop_and_review",
            failure=error.code
            if isinstance(error, PersistenceError)
            else type(error).__name__,
        )
    report["completed_at_utc"] = datetime.now(UTC).isoformat()
    (ROOT / "data/repaired-live-run-20261002.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return int(report["status"] == "failed_stop_and_review")


if __name__ == "__main__":
    raise SystemExit(main())
