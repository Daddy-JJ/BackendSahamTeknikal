"""Explicit live scan entrypoint. Preflight is offline; execution is opt-in."""

import os
import re
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from .config_io import load_calendar, load_requests, load_universe
from .corporate_actions import load_dividend_evidence
from .persistence import SupabaseScanStore
from .pipeline import require_scan_context
from .providers import make_provider
from .runner import run_once


def utc_now() -> datetime:
    return datetime.now(UTC)


def execute_run(args) -> dict:
    if not re.fullmatch(r"[a-z0-9]{20}", args.project_ref):
        raise ValueError("invalid_project_reference")
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", args.namespace):
        raise ValueError("invalid_namespace")
    calendar = load_calendar(args.calendar)
    universe = load_universe(args.universe_metadata, args.universe_csv)
    if calendar.data_mode != "live" or universe.data_mode != "live":
        raise ValueError("live_context_required")
    requests = load_requests(args.mapping, args.provider, args.start, args.target)
    require_scan_context(requests, args.target, calendar, universe, utc_now())
    evidence_path = getattr(args, "dividend_evidence", None)
    evidence = (
        load_dividend_evidence(evidence_path, Path(__file__).resolve().parents[3])
        if evidence_path
        else ()
    )
    summary = {
        "data_mode": "live",
        "provider": args.provider,
        "namespace": args.namespace,
        "target": args.target.isoformat(),
        "tickers": len(requests),
        "calendar_version": calendar.version,
        "universe_version": universe.version,
        "executed": False,
    }
    if not args.execute:
        return {**summary, "status": "preflight_passed", "network_used": False}
    # No implicit dotenv loading: bind the intended environment to the requested project.
    expected_url = f"https://{args.project_ref}.supabase.co"
    if os.environ.get("SUPABASE_URL", "").rstrip("/") != expected_url:
        raise ValueError("supabase_project_mismatch")
    key = os.environ.get("SUPABASE_SECRET_KEY", "")
    with SupabaseScanStore(expected_url, key) as store, httpx.Client() as client:
        store.require_live_schema()
        outcome = run_once(
            make_provider(args.provider, client),
            store,
            requests,
            args.target,
            calendar,
            universe,
            utc_now(),
            namespace=args.namespace,
            clock=utc_now,
            dividend_evidence=evidence,
        )
    return {
        **summary,
        "executed": True,
        "status": outcome.pipeline.scan.status,
        "run_id": outcome.publication["run_id"],
        "replayed": outcome.publication["replayed"],
        "coverage_valid": outcome.pipeline.scan.coverage_valid,
        "coverage_total": outcome.pipeline.scan.coverage_total,
        "signals": len(outcome.pipeline.scan.signals),
        "stored_revisions": len(outcome.revision_ids),
        "provider_errors": outcome.pipeline.provider_errors,
    }


def add_run_parser(commands) -> None:
    parser = commands.add_parser(
        "run", help="Validate live configuration; --execute fetches and publishes"
    )
    parser.add_argument("--provider", choices=("yfinance", "eodhd"), required=True)
    parser.add_argument(
        "--dividend-evidence", type=Path, help="Reviewed manifest; sources must exist locally"
    )
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument("--universe-metadata", type=Path, required=True)
    parser.add_argument("--universe-csv", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--target", type=date.fromisoformat, required=True)
    parser.add_argument("--project-ref", required=True)
    parser.add_argument("--namespace", default="forward")
    parser.add_argument("--execute", action="store_true")
