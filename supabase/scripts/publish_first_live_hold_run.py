"""Guarded one-off publication of actual captured data, including quality holds.

No provider fallback, synthetic trades, secret output or scheduler. Default is
offline evaluation; --execute is limited to the approved production and target.
"""

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, date, datetime

from idx_scanner.config_io import load_calendar, load_requests, load_universe
from idx_scanner.engine import scan
from idx_scanner.models import ScanState, canonical_json
from idx_scanner.persistence import (
    PersistenceError,
    SupabaseScanStore,
    series_from_revision,
)
from idx_scanner.runner import run_once
from prepare_dev_setup import ROOT, local_env

REF = "hcjfxbynqzsaidlwvdfx"
TARGET = date(2026, 10, 2)


def captured_series():
    folder = ROOT / "data/live-universe-2026-10-02"
    evidence = json.loads((folder / "evidence.json").read_text())
    if (
        evidence["requested_end"] != TARGET.isoformat()
        or len(evidence["results"]) != 100
    ):
        raise ValueError("full_same_target_capture_required")
    result = {}
    for row in evidence["results"]:
        ticker = row["ticker"]
        if not row["mapping_verified"] or ticker in result:
            raise ValueError("invalid_capture_mapping")
        raw_bytes = (folder / f"{ticker}.json").read_bytes()
        if hashlib.sha256(raw_bytes).hexdigest() != row["raw_sha256"]:
            raise ValueError("capture_checksum_mismatch")
        raw = json.loads(raw_bytes)
        value = {
            "metadata_source": canonical_json(
                {
                    k: v
                    for k, v in raw.items()
                    if k not in ("bars", "fetched_at", "provider_version")
                }
            ),
            "bar_sources": [canonical_json(bar) for bar in raw["bars"]],
            "fetched_at": raw["fetched_at"],
            "provider_version": raw["provider_version"],
            "input_digest": row["input_digest"],
        }
        series = series_from_revision(value)
        if series.provider != "yfinance" or series.ticker != ticker:
            raise ValueError("actual_yahoo_capture_required")
        if series.bars[-1].session != TARGET:
            raise ValueError("capture_target_stale")
        result[ticker] = series
    return result


class CapturedProvider:
    def __init__(self, series):
        self.series = series

    def fetch(self, request):
        series = self.series[request.ticker]
        if request.end != TARGET or request.symbol != series.provider_symbol:
            raise ValueError("capture_request_mismatch")
        return series


class ObservedStore(SupabaseScanStore):
    ingested = 0

    def ingest_series(self, *args, **kwargs):
        receipt = super().ingest_series(*args, **kwargs)
        self.ingested += 1
        if self.ingested % 10 == 0:
            print(json.dumps({"actual_revisions_ingested": self.ingested}), flush=True)
        return receipt


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
        "runner_scope": "local one-off using checksum-verified same-day actual Yahoo capture",
        "status": "preflight_pending",
        "stage": "offline_configuration",
    }
    try:
        calendar = load_calendar(ROOT / "config/live/idx-calendar-2024-2026.json")
        universe = load_universe(
            ROOT / "config/live/kompas100-universe.json",
            ROOT / "config/live/kompas100-universe.csv",
        )
        if calendar.data_mode != "live" or universe.data_mode != "live":
            raise ValueError("live_context_required")
        requests = load_requests(
            ROOT / "config/reference/yfinance-kompas100-verified-mappings.json",
            "yfinance",
            date(2024, 1, 1),
            TARGET,
        )
        series = captured_series()
        if set(series) != set(requests) or set(series) != set(universe.tickers):
            raise ValueError("full_verified_universe_required")
        observed = scan(
            series, TARGET, calendar, universe, datetime.now(UTC), ScanState()
        )
        report.update(
            quality_status=observed.status,
            coverage_valid=observed.coverage_valid,
            coverage_total=observed.coverage_total,
            signals=len(observed.signals),
            item_status_counts=dict(Counter(item.status for item in observed.items)),
            calendar_version=calendar.version,
            universe_version=universe.version,
            next_session=calendar.next(TARGET).day.isoformat(),
            publication_deadline=calendar.next(TARGET).opens_at.isoformat(),
        )
        # This operator helper publishes a hold-only diagnostic, never entry signals.
        if observed.coverage_valid or observed.signals:
            raise ValueError("hold_only_publication_required")
        report["status"] = "offline_preflight_passed_quality_failed"
        if args.execute:
            env = local_env(ROOT / ".env")
            url = f"https://{REF}.supabase.co"
            if env.get("SUPABASE_URL", "").rstrip("/") != url:
                raise ValueError("production_project_mismatch")
            report["stage"] = "production_schema_preflight"
            with ObservedStore(url, env["SUPABASE_SECRET_KEY"]) as store:
                store.require_live_schema()
                report["production_write_attempted"] = True
                report["stage"] = "actual_ingest_and_hold_publication"
                outcome = run_once(
                    CapturedProvider(series),
                    store,
                    requests,
                    TARGET,
                    calendar,
                    universe,
                    datetime.now(UTC),
                    clock=lambda: datetime.now(UTC),
                    normalize_calendar=False,  # Preserve this original hold-only operator scope.
                )
                report.update(
                    run_id=outcome.publication["run_id"],
                    replayed=outcome.publication["replayed"],
                    stored_and_digest_readback_verified=len(outcome.revision_ids),
                )
                report["stage"] = "production_readback"
                rows = store._request(
                    "GET",
                    "scan_runs",
                    params={
                        "id": "eq." + report["run_id"],
                        "select": "id,namespace,data_mode,session_date,status,coverage_valid,coverage_total",
                    },
                )
                if len(rows) != 1 or any(
                    rows[0][k] != v
                    for k, v in {
                        "namespace": "forward",
                        "data_mode": "live",
                        "session_date": TARGET.isoformat(),
                        "status": "failed",
                        "coverage_valid": 0,
                        "coverage_total": 100,
                    }.items()
                ):
                    raise ValueError("production_run_readback_mismatch")
                items = store._request(
                    "GET",
                    "scan_run_items",
                    params={
                        "run_id": "eq." + report["run_id"],
                        "select": "ticker,status",
                    },
                )
                if len(items) != 100 or any(
                    x["status"] != "data_quality_hold" for x in items
                ):
                    raise ValueError("production_hold_items_readback_mismatch")
                report["production_run_readback"] = rows[0]
                report["production_hold_items_verified"] = 100
                report["status"] = (
                    "published_actual_live_hold_run_scanner_quality_no_go"
                )
    except (PersistenceError, ValueError, KeyError, OSError) as error:
        report["status"] = "failed_stop_and_review"
        report["failure"] = (
            error.code if isinstance(error, PersistenceError) else type(error).__name__
        )
    report["completed_at_utc"] = datetime.now(UTC).isoformat()
    output = ROOT / "data/first-live-hold-run-20261002.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return int(report["status"] == "failed_stop_and_review")


if __name__ == "__main__":
    raise SystemExit(main())
