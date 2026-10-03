"""Automated nightly scheduled scanner and paper journal runner.

Executed by GitHub Actions on trading nights (20:17 WIB primary / 22:17 WIB recovery)
or manually via workflow_dispatch.
Includes exchange calendar/holiday guards, corporate action reconciliation,
pure strategy engine evaluation, automated paper journal simulation,
and atomic Supabase publication.
"""

import argparse
import contextlib
import io
import json
import os
from collections import Counter
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from idx_scanner.config_io import load_requests
from idx_scanner.engine import scan
from idx_scanner.models import ScanState, canonical_json
from idx_scanner.persistence import PersistenceError, SupabaseScanStore
from idx_scanner.providers import ProviderError, YFinanceProvider
from idx_scanner.runner import run_once
from manual_scanner_smoke import load_manual_context, prepare_series
from paper_journal_runner import process_paper_session
from prepare_dev_setup import ROOT

WIB = ZoneInfo("Asia/Jakarta")
SCHEDULED_DIR = ROOT / "data" / "scheduled-scanner"
EVIDENCE_PATH = SCHEDULED_DIR / "latest-evidence.json"


def get_current_target_session(calendar, now_utc: datetime) -> tuple[date, bool, str]:
    """Determines target session date based on WIB calendar.

    Returns (target_date, is_tradable, reason).
    """
    now_wib = now_utc.astimezone(WIB)
    today_wib = now_wib.date()

    # Check weekend
    if today_wib.weekday() in (5, 6):
        return today_wib, False, "weekend"

    # Check if today is in calendar sessions
    session_days = {s.day for s in calendar.sessions}
    if today_wib not in session_days or today_wib in calendar.closed_days:
        return today_wib, False, "exchange_holiday_or_closed"

    session_info = calendar.get(today_wib)
    if now_utc < session_info.closes_at:
        return today_wib, False, "target_session_not_closed"

    next_session = calendar.next(today_wib)
    if now_utc >= next_session.opens_at:
        return today_wib, False, "publication_window_elapsed"

    return today_wib, True, "eligible"


def run_scheduled_scanner(
    target: date | None = None,
    execute_publication: bool = False,
    require_usable: bool = False,
) -> int:
    now = datetime.now(UTC)
    calendar, universe, proofs = load_manual_context()

    if target is None:
        target_date, is_tradable, reason = get_current_target_session(calendar, now)
        if not is_tradable:
            report = {
                "checked_at_utc": now.isoformat(),
                "target": target_date.isoformat(),
                "status": "skipped",
                "reason": reason,
                "production_write": False,
            }
            print(json.dumps(report, indent=2))
            SCHEDULED_DIR.mkdir(parents=True, exist_ok=True)
            EVIDENCE_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            return 0 if reason != "publication_window_elapsed" else 1
    else:
        target_date = target
        if target_date not in {s.day for s in calendar.sessions}:
            raise ValueError("target_not_in_calendar_sessions")
        if now < calendar.get(target_date).closes_at:
            raise ValueError("target_session_not_closed")

    universe.require(target_date)
    print(f"Executing scheduled scan for target session: {target_date.isoformat()} (now UTC: {now.isoformat()})")

    # Step 1: Fetch fresh public Yahoo data
    requests = load_requests(
        ROOT / "config/reference/yfinance-kompas100-verified-mappings.json",
        "yfinance",
        date(2024, 1, 1),
        target_date,
    )
    folder = SCHEDULED_DIR / now.strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True, exist_ok=True)

    provider = YFinanceProvider()
    raw = {}
    provider_errors = []
    for index, ticker in enumerate(sorted(requests), 1):
        try:
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                series = provider.fetch(requests[ticker])
            (folder / f"{ticker}.json").write_text(canonical_json(series), encoding="utf-8")
            raw[ticker] = series
        except ProviderError as exc:
            provider_errors.append({"ticker": ticker, "code": exc.code})
        if index % 20 == 0:
            print(f"Fetched {index}/{len(requests)} tickers...", flush=True)

    # Step 2: Prepare series (normalizations & KSEI dividend proofs)
    prepared, mismatches = prepare_series(raw, proofs, calendar, target_date)

    # Step 3: Run scan engine
    evaluated_at = datetime.now(UTC)
    result = scan(prepared, target_date, calendar, universe, evaluated_at, ScanState())

    # Step 4: Run automated Paper Journal simulation
    _paper_book, paper_summary = process_paper_session(
        target_date,
        prepared,
        result.signals,
        calendar,
        evaluated_at,
    )

    counts = dict(Counter(i.status for i in result.items))
    report = {
        "checked_at_utc": now.isoformat(),
        "evaluated_at_utc": evaluated_at.isoformat(),
        "target": target_date.isoformat(),
        "status": result.status,
        "coverage_valid": result.coverage_valid,
        "coverage_total": result.coverage_total,
        "counts": counts,
        "ranking_status": result.ranking.status,
        "signals_count": len(result.signals),
        "strategy_signals": dict(Counter(s.candidate.strategy for s in result.signals)),
        "paper_trades_total": paper_summary.get("trades_count", 0),
        "paper_closed_total": paper_summary.get("closed_count", 0),
        "paper_metrics": paper_summary.get("metrics", {}),
        "provider_errors": provider_errors,
        "evidence_mismatch_tickers": mismatches,
        "production_write": False,
        "publication_receipt": None,
    }

    # Step 5: Publish if requested and configured
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SECRET_KEY")

    if execute_publication and supabase_url and supabase_key:
        print("Connecting to Supabase for atomic publication...")
        try:
            with SupabaseScanStore(supabase_url, supabase_key) as store:
                store.require_live_schema()

                # Check if session is already published
                existing_runs = store._request(
                    "GET",
                    "scan_runs",
                    params={
                        "select": "id,status,coverage_valid,run_digest",
                        "namespace": "eq.forward",
                        "data_mode": "eq.live",
                        "session_date": f"eq.{target_date.isoformat()}",
                    },
                )
                if existing_runs and existing_runs[0].get("run_digest") == result.run_digest:
                    print("Scan run already published with identical digest. Recovery no-op.")
                    report["status"] = "recovery_clean_noop"
                    report["production_write"] = False
                    report["publication_receipt"] = {"run_id": existing_runs[0]["id"], "replayed": True}
                else:
                    outcome = run_once(
                        provider,
                        store,
                        requests,
                        target_date,
                        calendar,
                        universe,
                        evaluated_at,
                        dividend_evidence=proofs,
                    )
                    report["production_write"] = True
                    report["publication_receipt"] = outcome.publication
                    print(f"Publication complete! Run ID: {outcome.publication.get('run_id')}")
        except PersistenceError as exc:
            print(f"Persistence error during publication: {exc.code}")
            report["publication_error"] = exc.code
            return 1

    SCHEDULED_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "items"}, indent=2, default=str))

    if require_usable and result.coverage_valid == 0:
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=date.fromisoformat, help="Explicit target session YYYY-MM-DD")
    parser.add_argument("--execute", action="store_true", help="Publish to Supabase if configured")
    parser.add_argument("--require-usable", action="store_true", help="Fail if coverage_valid == 0")
    args = parser.parse_args()

    return run_scheduled_scanner(
        target=args.target,
        execute_publication=args.execute,
        require_usable=args.require_usable,
    )


if __name__ == "__main__":
    raise SystemExit(main())
