"""Automated nightly scheduled scanner and paper journal runner.

Executed by GitHub Actions on trading nights (18:18 WIB primary / 19:19 WIB recovery)
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
import sys
from collections import Counter
from datetime import UTC, date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from idx_scanner.config_io import load_requests
from idx_scanner.engine import current_source_revision, scan
from idx_scanner.models import ScanState, canonical_json
from idx_scanner.paper_persistence import PaperRuntimeStore
from idx_scanner.persistence import PersistenceError, SupabaseScanStore
from idx_scanner.providers import ProviderError, YFinanceProvider
from idx_scanner.runner import run_once
from idx_scanner.untradable import load_untradable_evidence
from manual_scanner_smoke import load_manual_context, prepare_series
from paper_journal_runner import process_paper_session
from paper_runtime_runner import complete_persisted_paper
from prepare_dev_setup import ROOT

WIB = ZoneInfo("Asia/Jakarta")
SCHEDULED_DIR = ROOT / "data" / "scheduled-scanner"
EVIDENCE_PATH = SCHEDULED_DIR / "latest-evidence.json"


def latest_closed_session(calendar, now_utc: datetime) -> date:
    """Use the verified exchange calendar, including weekend/holiday recovery."""
    today = now_utc.astimezone(WIB).date()
    days = {s.day for s in calendar.sessions}
    known_until = max((*days, *calendar.closed_days))
    if (today < calendar.sessions[0].day or today > known_until
        or (today not in days and today not in calendar.closed_days and today.weekday() < 5)):
        raise ValueError("blocked_configuration: calendar_unknown")
    closed = [s for s in calendar.sessions if s.closes_at <= now_utc]
    if not closed:
        raise ValueError("blocked_configuration: no_closed_session")
    return closed[-1].day


def publication_window_open(calendar, target: date, now_utc: datetime) -> bool:
    return calendar.get(target).closes_at <= now_utc < calendar.next(target).opens_at


def get_current_target_session(calendar, now_utc: datetime) -> tuple[date, bool, str]:
    """Determines target session date based on WIB calendar.

    Returns (target_date, is_tradable, reason).
    """
    now_wib = now_utc.astimezone(WIB)
    today_wib = now_wib.date()

    # Closed civil days can still be inside the previous session's publication
    # window. Friday published Saturday remains forward before Monday's open.
    if today_wib.weekday() in (5, 6) or today_wib in calendar.closed_days:
        previous = latest_closed_session(calendar, now_utc)
        if publication_window_open(calendar, previous, now_utc):
            return previous, True, "eligible"
        return previous, False, "publication_window_elapsed"

    # Check if today is known in calendar
    session_days = {s.day for s in calendar.sessions}
    if today_wib not in session_days:
        return today_wib, False, "blocked_configuration: calendar_unknown"

    session_info = calendar.get(today_wib)
    if now_utc < session_info.closes_at:
        # If running in the early morning before exchange opens (e.g. 00:00 to 08:59 WIB),
        # the previous closed session remains in its valid publication window.
        if now_utc < session_info.opens_at:
            prev_sessions = [s for s in calendar.sessions if s.day < today_wib]
            if prev_sessions:
                prev = prev_sessions[-1]
                if prev.closes_at <= now_utc < session_info.opens_at:
                    return prev.day, True, "eligible"
        return today_wib, False, "target_session_not_closed"

    next_session = calendar.next(today_wib)
    if now_utc >= next_session.opens_at:
        return today_wib, False, "publication_window_elapsed"

    return today_wib, True, "eligible"


def _write_report(report):
    SCHEDULED_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


def _run_live(target, calendar, universe, proofs, requests, provider, now, *, paper_only):
    """Publication and existing-book processing are independent, audited stages."""
    publication_receipt: dict | None = None
    report = {"checked_at_utc": now.isoformat(), "target": target.isoformat(),
              "production_write": False, "scanner_status": "not_run", "paper_status": "not_run"}
    job_id = (os.environ.get("GITHUB_RUN_ID", "local-" + uuid4().hex)
              + "-" + os.environ.get("GITHUB_RUN_ATTEMPT", "1"))
    context = {"observed_at": now.isoformat(), "calendar_version": calendar.version}
    for variable, key in (("GITHUB_RUN_ID", "run_id"), ("GITHUB_EVENT_NAME", "event"),
                          ("GITHUB_WORKFLOW", "workflow"), ("SCANNER_SCHEDULE", "schedule"),
                          ("GITHUB_SHA", "source_sha")):
        if os.environ.get(variable):
            context[key] = os.environ[variable]
    scanner_failure = None
    phase = "preflight"
    try:
        evidence = load_untradable_evidence(
            ROOT / "supabase/config/verified_untradable_live_v1.json", "live")
        with SupabaseScanStore(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"]) as store:
            store.require_live_schema()
            owner = os.environ.get("APP_OWNER_USER_ID")
            if not owner:
                raise PersistenceError("missing_paper_owner")
            try:
                paper_store = PaperRuntimeStore(store, owner)
            except ValueError:
                raise PersistenceError("invalid_paper_owner") from None
            report["production_write_attempted"] = True
            paper_store.initialize()
            report["activation_status"] = "initialized_or_existing"
            # Initialization is a writer RPC, even if it reuses the old model.
            # Its receipt does not distinguish a new activation from a replay.
            report["production_write"] = True
            def record(stage, status, failure=None):
                paper_store.record_job(job_id=job_id, phase=stage, status=status,
                                       session=target, failure_code=failure, context=context)
            record("job", "running")
            prepared, attempted = {}, ()
            if paper_only:
                record("publication", "skipped")
                report["scanner_status"] = "skipped"
                report["scanner_skip_reason"] = "paper_recovery_only"
            else:
                phase = "publication"
                record("publication", "running")
                try:
                    universe.require(target)
                    outcome = run_once(provider, store, requests, target, calendar, universe,
                                       now, dividend_evidence=proofs,
                                       source_revision=current_source_revision(),
                                       clock=lambda: datetime.now(UTC))
                    publication_receipt = outcome.publication
                    result = outcome.pipeline.scan
                    prepared = {s.ticker: s for s in outcome.pipeline.prepared_series}
                    attempted = tuple(requests)
                    report.update(scanner_status="published", production_write=True,
                                  publication_receipt=publication_receipt, status=result.status,
                                  coverage_valid=result.coverage_valid, coverage_total=result.coverage_total,
                                  counts=dict(Counter(i.status for i in result.items)),
                                  ranking_status=result.ranking.status, signals_count=len(result.signals),
                                  strategy_signals=dict(Counter(s.candidate.strategy for s in result.signals)),
                                  provider_errors=[{"ticker": t, "code": c}
                                                   for t, c in outcome.pipeline.provider_errors])
                    if result.coverage_valid == 0:
                        scanner_failure = "zero_usable_coverage"
                        record("publication", "failed", scanner_failure)
                    else:
                        record("publication", "succeeded")
                except (PersistenceError, ValueError) as exc:
                    scanner_failure = exc.code if isinstance(exc, PersistenceError) else "validation_failed"
                    report["scanner_status"] = "failed"
                    record("publication", "failed", scanner_failure)
                    # Recover only persisted forward signals. No regenerated
                    # signal, local book or failed unpublished capture is used.
                    prepared, attempted = {}, ()
            phase = "paper_commit"
            record("paper", "running")
            try:
                _book, summary = complete_persisted_paper(
                    store, paper_store, prepared, requests, target, calendar, proofs,
                    now, provider, publication_receipt["run_id"] if publication_receipt else None,
                    attempted_tickers=attempted, untradable_evidence=evidence,
                    clock=lambda: datetime.now(UTC),
                )
                held = summary["data_hold_count"] > 0
                report.update(paper_status="data_hold" if held else "complete",
                              production_write=True, paper_summary=summary,
                              paper_persistence=summary["persistence"],
                              paper_runtime_revision=summary["runtime_revision"],
                              paper_trades_total=summary.get("trades_count", 0),
                              paper_closed_total=summary.get("closed_count", 0),
                              paper_experiment_metrics=summary.get("experiment_metrics", {}),
                              paper_provider_errors=summary.get("provider_errors", []))
                record("paper", "succeeded")
            except (PersistenceError, ValueError) as exc:
                code = exc.code if isinstance(exc, PersistenceError) else "validation_failed"
                report.update(paper_status="failed", failure="paper_commit_error: " + code)
                record("paper", "failed", code)
                record("job", "failed", code)
                report["status"] = "failed"
                _write_report(report)
                return 1
            record("job", "failed" if scanner_failure else "succeeded", scanner_failure)
    except (PersistenceError, ValueError, OSError) as exc:
        code = exc.code if isinstance(exc, PersistenceError) else "validation_failed"
        report.update(status="failed", failure=phase + "_error: " + code)
        _write_report(report)
        return 1
    report["fetch_diagnostics"] = provider.fetch_diagnostics
    if scanner_failure:
        report.update(status="failed", failure=scanner_failure)
    else:
        report.setdefault("status", "complete")
    _write_report(report)
    return 1 if scanner_failure else 0


def _run_scheduled_scanner(
    target: date | None = None,
    execute_publication: bool = False,
    require_usable: bool = False,
    paper_only: bool = False,
) -> int:
    now = datetime.now(UTC)
    calendar, universe, proofs = load_manual_context()

    if target is None and execute_publication:
        target = latest_closed_session(calendar, now)
    if execute_publication:
        if target not in {s.day for s in calendar.sessions} or now < calendar.get(target).closes_at:
            raise ValueError("target_session_not_closed_or_unknown")
        if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SECRET_KEY"):
            _write_report({"status": "failed", "failure": "missing_credentials", "production_write": False})
            return 1
        paper_only = paper_only or not publication_window_open(calendar, target, now)
        requests = load_requests(ROOT / "config/reference/yfinance-kompas100-verified-mappings.json",
                                 "yfinance", date(2024, 1, 1), target)
        return _run_live(target, calendar, universe, proofs, requests, YFinanceProvider(), now,
                         paper_only=paper_only)
    if paper_only:
        raise ValueError("paper_only_requires_execute")
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
            return 0 if reason in ("weekend", "exchange_holiday_or_closed") else 1
    else:
        target_date = target
        if target_date not in {s.day for s in calendar.sessions}:
            raise ValueError("target_not_in_calendar_sessions")
        if now < calendar.get(target_date).closes_at:
            raise ValueError("target_session_not_closed")

    universe.require(target_date)
    print(
        f"Executing scheduled scan for target session: {target_date.isoformat()} "
        f"(now UTC: {now.isoformat()})"
    )

    requests = load_requests(
        ROOT / "config/reference/yfinance-kompas100-verified-mappings.json",
        "yfinance",
        date(2024, 1, 1),
        target_date,
    )
    folder = SCHEDULED_DIR / now.strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True, exist_ok=True)
    provider = YFinanceProvider()

    paper_summary = None

    # Explicit offline diagnostic, never used after a live failure.
    # Dry-run / offline check: Single fetch without database write
    raw = {}
    provider_errors = []
    for index, ticker in enumerate(sorted(requests), 1):
        try:
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                series = provider.fetch(requests[ticker])
            (folder / f"{ticker}.json").write_text(
                canonical_json(series), encoding="utf-8"
            )
            raw[ticker] = series
        except ProviderError as exc:
            provider_errors.append({"ticker": ticker, "code": exc.code})
        if index % 20 == 0:
            print(f"Fetched {index}/{len(requests)} tickers...", flush=True)

    prepared, mismatches = prepare_series(raw, proofs, calendar, target_date)
    evaluated_at = datetime.now(UTC)
    result = scan(
        prepared,
        target_date,
        calendar,
        universe,
        evaluated_at,
        ScanState(),
        source_revision=current_source_revision(),
    )
    production_write = False
    publication_receipt = None

    # Step 3: Require usable coverage (Fail-closed)
    if result.coverage_valid == 0:
        print(
            "ERROR: Usable coverage is 0! No valid signals can be verified.",
            file=sys.stderr,
        )
        report = {
            "checked_at_utc": now.isoformat(),
            "target": target_date.isoformat(),
            "status": "failed",
            "failure": "zero_usable_coverage",
            "production_write": production_write,
            "publication_receipt": publication_receipt,
            "paper_status": "complete" if paper_summary is not None else "not_run",
            "paper_summary": paper_summary,
        }
        SCHEDULED_DIR.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PATH.write_text(
            json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
        )
        return 1

    # Step 4: Run automated Paper Journal simulation on committed snapshot
    if paper_summary is None:
        # Explicit offline diagnostic path, never a fallback for a live write failure.
        _paper_book, paper_summary = process_paper_session(
            target_date, prepared, result.signals, calendar, evaluated_at,
        )
        paper_summary["persistence"] = "local_legacy_dry_run"

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
        "paper_experiment_metrics": paper_summary.get("experiment_metrics", {}),
        "paper_persistence": paper_summary.get("persistence"),
        "paper_status": "complete",
        "paper_runtime_revision": paper_summary.get("runtime_revision"),
        "paper_provider_errors": paper_summary.get("provider_errors", []),
        "provider_errors": provider_errors,
        "evidence_mismatch_tickers": mismatches,
        "production_write": production_write,
        "publication_receipt": publication_receipt,
    }

    SCHEDULED_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(
        json.dumps({k: v for k, v in report.items() if k != "items"}, indent=2, default=str)
    )

    return 0


def run_scheduled_scanner(target: date | None = None, execute_publication: bool = False,
                          require_usable: bool = False, paper_only: bool = False) -> int:
    try:
        return _run_scheduled_scanner(target, execute_publication, require_usable, paper_only)
    except (PersistenceError, ValueError, OSError) as exc:
        code = exc.code if isinstance(exc, PersistenceError) else "configuration_invalid"
        _write_report({"checked_at_utc": datetime.now(UTC).isoformat(),
                       "target": target.isoformat() if target else None,
                       "status": "failed", "failure": "preflight_error: " + code,
                       "scanner_status": "not_run", "paper_status": "not_run",
                       "production_write": False})
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target", type=date.fromisoformat, help="Explicit target session YYYY-MM-DD"
    )
    parser.add_argument("--execute", action="store_true", help="Publish to Supabase if configured")
    parser.add_argument("--require-usable", action="store_true", help="Fail if coverage_valid == 0")
    parser.add_argument("--paper-only", action="store_true", help="Recover persisted paper without publishing signals")
    args = parser.parse_args()

    return run_scheduled_scanner(
        target=args.target,
        execute_publication=args.execute,
        require_usable=args.require_usable,
        paper_only=args.paper_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())
