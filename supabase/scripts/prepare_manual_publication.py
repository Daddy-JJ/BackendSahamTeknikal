"""Checksum-bound, zero-signal manual publisher; offline unless --execute.

Execution uses process environment only, never reads/writes .env. An approved
plan SHA256 and explicit production project are required. No Auth or ledger
mutation, scheduler or new trading calculation. Canonical run_once owns IO.
"""

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from idx_scanner.config_io import load_requests
from idx_scanner.engine import scan
from idx_scanner.models import ScanState, canonical_json
from idx_scanner.persistence import (
    PersistenceError,
    SupabaseScanStore,
    series_from_revision,
)
from idx_scanner.runner import run_once
from manual_scanner_smoke import load_manual_context, prepare_series
from prepare_dev_setup import ROOT
from publish_first_live_hold_run import REF

EXPECTED_COUNTS = {"evaluated": 45, "corporate_action_hold": 25, "data_quality_hold": 30}
CONTRACT = "manual-zero-signal-publication-v1"
LEDGER_ORDER = {
    "actual_trades": "id.asc", "actual_fills": "id.asc",
    "actual_fill_corrections": "sequence.asc", "actual_stop_events": "id.asc",
    "actual_notes": "id.asc", "actual_trade_tags": "trade_id.asc,tag.asc",
    "actual_journal_requests": "owner_id.asc,request_id.asc",
}
SCAN_ORDER = {
    "scan_run_items": "run_id.asc,ticker.asc",
    "scan_run_signals": "run_id.asc,signal_id.asc",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def window(calendar, target, now):
    if now.tzinfo is None or now < calendar.get(target).closes_at:
        raise ValueError("target_session_not_closed")
    if now >= calendar.next(target).opens_at:
        raise ValueError("forward_publication_window_elapsed")


def load_capture(folder, requests, now):
    files = {p.name for p in folder.iterdir() if p.is_file()}
    if files != {f"{t}.json" for t in requests}:
        raise ValueError("capture_members_mismatch")
    raw, manifest = {}, []
    for ticker, request in sorted(requests.items()):
        path = folder / f"{ticker}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        series = series_from_revision({
            "metadata_source": canonical_json({
                k: v for k, v in data.items()
                if k not in ("bars", "fetched_at", "provider_version")
            }),
            "bar_sources": [canonical_json(bar) for bar in data["bars"]],
            "fetched_at": data["fetched_at"],
            "provider_version": data["provider_version"],
            "input_digest": source_digest(data),
        })
        if (series.provider != "yfinance" or series.ticker != ticker
                or series.provider_symbol != request.symbol
                or not series.bars or series.bars[-1].session != request.end):
            raise ValueError("capture_target_or_mapping_mismatch")
        if not timedelta(0) <= now - series.fetched_at <= timedelta(hours=24):
            raise ValueError("capture_fetch_age_outside_manual_window")
        bar = series.bars[-1]
        if any(getattr(bar, name) is None for name in ("open", "high", "low", "close", "volume")):
            raise ValueError("target_candle_incomplete")
        raw[ticker] = series
        manifest.append({"file": path.name, "sha256": sha(path),
                         "input_digest": series.input_digest,
                         "fetched_at": series.fetched_at.isoformat()})
    return raw, manifest


def source_digest(data):
    # Source-token representation of Series.input_digest; regression checked
    # against the canonical property, with no indicator/ledger calculations.
    from idx_scanner.models import digest

    content = {"ticker": data["ticker"], "provider": data["provider"],
               "symbol": data["provider_symbol"], "basis": data["price_basis"],
               "bars": data["bars"], "actions": data["actions"],
               "reconciled": data["reconciled_actions"],
               "actions_complete": data["actions_complete"],
               "provider_missing_sessions": data["provider_missing_sessions"],
               "provider_row_issues": data["provider_row_issues"]}
    if data.get("provenance"):
        content["provenance"] = data["provenance"]
    return digest(content)


def prepare(folder, target, now):
    calendar, universe, proofs = load_manual_context()
    window(calendar, target, now)
    universe.require(target)
    requests = load_requests(ROOT / "config/reference/yfinance-kompas100-verified-mappings.json",
                             "yfinance", date(2024, 1, 1), target)
    if set(requests) != set(universe.tickers) or len(requests) != 100:
        raise ValueError("full_verified_universe_required")
    raw, manifest = load_capture(folder, requests, now)
    prepared, mismatches = prepare_series(raw, proofs, calendar, target)
    if mismatches:
        raise ValueError("source_amendment_requires_review")
    result = scan(prepared, target, calendar, universe, now, ScanState())
    require_approved_result(result)
    plan = {
        "contract": CONTRACT, "project_ref": REF, "target": target.isoformat(),
        "namespace": "forward", "data_mode": "live", "scheduler_enabled": False,
        "next_open": calendar.next(target).opens_at.isoformat(),
        "calendar_version": calendar.version, "universe_version": universe.version,
        "run_digest": result.run_digest, "counts": dict(Counter(i.status for i in result.items)),
        "signals": 0, "ranking_status": result.ranking.status,
        "config_release_sha256": sha(ROOT / "config/live/manual-runner-release.json"),
        "sources_manifest_sha256": sha(
            ROOT / "config/reference/ksei-reviewed-dividends-20261003.json"
        ),
        "capture": manifest,
    }
    return plan, calendar, universe, proofs, requests, raw


def require_approved_result(result):
    if (dict(Counter(i.status for i in result.items)) != EXPECTED_COUNTS
            or result.signals or result.ranking.status != "cross_section_incomplete"):
        raise ValueError("publication_result_requires_new_review")


def verify_plan(path, expected_sha, current):
    if len(expected_sha) != 64 or sha(path) != expected_sha:
        raise ValueError("approved_plan_checksum_mismatch")
    if json.loads(path.read_text(encoding="utf-8")) != current:
        raise ValueError("approved_plan_inputs_changed")


def read_rows(store, table, params=None):
    rows, offset = [], 0
    while True:
        page = store._request("GET", table, params={"select": "*",
                              "order": LEDGER_ORDER.get(table, SCAN_ORDER.get(table, "id.asc")),
                              **(params or {}), "offset": str(offset), "limit": "200"})
        rows.extend(page)
        if len(page) < 200:
            return rows
        offset += 200


def fingerprint(rows):
    return hashlib.sha256(canonical_json(rows).encode()).hexdigest()


class BoundProvider:
    def __init__(self, raw, requests):
        self.raw, self.requests = raw, requests

    def fetch(self, request):
        if request != self.requests[request.ticker]:
            raise ValueError("approved_request_changed")
        return self.raw[request.ticker]


class BoundStore(SupabaseScanStore):
    def __init__(self, *args, plan, calendar, target, **kwargs):
        super().__init__(*args, **kwargs)
        self.plan, self.calendar, self.target = plan, calendar, target

    def publish(self, result, **kwargs):
        window(self.calendar, self.target, datetime.now(UTC))
        require_approved_result(result)
        if result.run_digest != self.plan["run_digest"]:
            raise ValueError("approved_run_digest_changed")
        return super().publish(result, **kwargs)


def execute(plan, calendar, universe, proofs, requests, raw, report):
    url = f"https://{REF}.supabase.co"
    if os.environ.get("SUPABASE_URL", "").rstrip("/") != url:
        raise ValueError("production_target_mismatch")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not key:
        raise ValueError("protected_publisher_secret_missing")
    target = date.fromisoformat(plan["target"])
    with BoundStore(url, key, plan=plan, calendar=calendar, target=target) as store:
        store.require_live_schema()
        old_runs = read_rows(store, "scan_runs")
        ledger = {t: fingerprint(read_rows(store, t)) for t in LEDGER_ORDER}
        if store.load_state(through_session=target).signals:
            raise ValueError("prior_signals_require_review")
        window(calendar, target, datetime.now(UTC))
        # Persist only safe hashes before any write so a postflight error cannot
        # discard the immutable baseline. Never serialize journal row bodies.
        report["before_journal_fingerprints"] = ledger
        report["before_run_fingerprints"] = {row["id"]: fingerprint([row]) for row in old_runs}
        report["interrupted_execution_outcome"] = "unknown_until_get_reconciliation"
        checkpoint = ROOT / "data/manual-publication/latest-evidence.json"
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        report["production_write_attempted"] = True
        report["stage"] = "ingest_and_publish"
        outcome = run_once(BoundProvider(raw, requests), store, requests, target,
                           calendar, universe, datetime.now(UTC), clock=lambda: datetime.now(UTC),
                           dividend_evidence=proofs)
        report["publication_receipt"] = outcome.publication
        run_id = outcome.publication["run_id"]
        report["stage"] = "readback"
        runs = read_rows(store, "scan_runs", {"id": "eq." + run_id})
        if len(runs) != 1 or any(runs[0][k] != v for k, v in {
                "namespace": "forward", "data_mode": "live", "session_date": target.isoformat(),
                "run_digest": plan["run_digest"], "status": "partial",
                "coverage_valid": 45, "coverage_total": 100}.items()):
            raise ValueError("publication_readback_mismatch")
        items = read_rows(store, "scan_run_items", {"run_id": "eq." + run_id})
        if len(items) != 100 or len({i["ticker"] for i in items}) != 100 or {
                i["ticker"]: i["status"] for i in items} != {
                i.ticker: i.status for i in outcome.pipeline.scan.items}:
            raise ValueError("publication_items_mismatch")
        if read_rows(store, "scan_run_signals", {"run_id": "eq." + run_id}):
            raise ValueError("unexpected_published_signals")
        after = read_rows(store, "scan_runs")
        if any(row not in after for row in old_runs):
            raise ValueError("prior_run_changed")
        if any(fingerprint(read_rows(store, t)) != value for t, value in ledger.items()):
            raise ValueError("ledger_or_audit_changed_during_publication")
        for table in ("scan_runs", "market_series_revisions", "signals"):
            if read_rows(store, table, {"data_mode": "eq.fixture"}):
                raise ValueError("fixture_data_detected")
        report.update(status="manual_partial_publication_readback_passed",
                      stored_at=runs[0]["stored_at"], old_runs_unchanged=True,
                      journal_tables_unchanged=list(LEDGER_ORDER), fixture_rows_absent=True,
                      revision_readbacks=len(outcome.revision_ids), full_quality_go=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--target", type=date.fromisoformat, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--approved-plan-sha256")
    parser.add_argument("--project-ref")
    args = parser.parse_args()
    report = {"project_ref": REF, "production_write_attempted": False,
              "publication_receipt": None, "scheduler_enabled": False,
              "stage": "offline_plan", "full_stack_live": False}
    failed = False
    try:
        values = prepare(args.capture.resolve(), args.target, datetime.now(UTC))
        plan, calendar, universe, proofs, requests, raw = values
        if args.execute:
            if args.project_ref != REF or not args.approved_plan_sha256:
                raise ValueError("explicit_project_and_plan_approval_required")
            verify_plan(args.plan, args.approved_plan_sha256, plan)
            report["approved_plan_sha256"] = args.approved_plan_sha256
            execute(plan, calendar, universe, proofs, requests, raw, report)
        else:
            args.plan.parent.mkdir(parents=True, exist_ok=True)
            with args.plan.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(plan, indent=2) + "\n")
            report.update(status="offline_publication_plan_ready", plan_sha256=sha(args.plan),
                          run_digest=plan["run_digest"], counts=plan["counts"],
                          target=plan["target"], next_open=plan["next_open"])
    except (ValueError, PersistenceError, FileExistsError) as exc:
        failed = True
        code = (str(exc) if isinstance(exc, (ValueError, PersistenceError))
                else "plan_already_exists")
        if not re.fullmatch("[a-z_]{1,100}", code):
            code = "operator_failure_redacted"
        report.update(status="failed", failure=code)
    except Exception:  # noqa: BLE001
        failed = True
        report.update(status="failed", failure="operator_failure_redacted")
    report["checked_at_utc"] = datetime.now(UTC).isoformat()
    output = ROOT / "data/manual-publication/latest-evidence.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
