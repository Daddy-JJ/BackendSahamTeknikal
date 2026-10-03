"""Manual full-universe engine smoke; no database, fixture fallback or scheduler.

Default uses checksum-verified actual capture. --execute-fetch obtains a new
Yahoo snapshot in a unique ignored folder. Output separates fresh provider IO
from offline capture evaluation. The existing deterministic engine owns signals.
"""

import argparse
import contextlib
import hashlib
import io
import json
import os
from collections import Counter
from datetime import UTC, date, datetime

from audit_scanner_quality_repairs import prepare
from prepare_dev_setup import ROOT
from publish_first_live_hold_run import TARGET

from idx_scanner.config_io import load_calendar, load_requests, load_universe
from idx_scanner.context import quality
from idx_scanner.corporate_actions import load_dividend_evidence, reconcile_dividends
from idx_scanner.engine import scan
from idx_scanner.models import ScanState, canonical_json
from idx_scanner.normalization import normalize_closed_sessions
from idx_scanner.providers import ProviderError, YFinanceProvider

MANIFEST = ROOT / "config/reference/ksei-reviewed-dividends-20261003.json"


def load_manual_context():
    release = json.loads((ROOT / "config/live/manual-runner-release.json").read_text())
    for row in release["files"]:
        path = (ROOT / row["file"]).resolve()
        content = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").encode()
        if (
            not path.is_relative_to(ROOT)
            or hashlib.sha256(content).hexdigest() != row["sha256_lf"]
        ):
            raise ValueError("manual_runner_config_checksum_mismatch")
    calendar = load_calendar(ROOT / "config/live/idx-calendar-2024-2026.json")
    universe = load_universe(
        ROOT / "config/live/kompas100-universe.json",
        ROOT / "config/live/kompas100-universe.csv",
    )
    proofs = load_dividend_evidence(MANIFEST, ROOT)
    if (
        calendar.data_mode != "live"
        or universe.data_mode != "live"
        or len(universe.tickers) != 100
    ):
        raise ValueError("full_live_universe_required")
    return calendar, universe, proofs


def prepare_series(raw, proofs, calendar, target):
    result, mismatches = {}, []
    for ticker, series in raw.items():
        normalized = normalize_closed_sessions(series, calendar, target)
        try:
            result[ticker] = reconcile_dividends(normalized, proofs, calendar, target)
        except ValueError as exc:
            if str(exc) != "dividend_provider_event_mismatch":
                raise
            # A changed source event invalidates this ticker's approvals; keep it
            # held, preserve the new raw receipt, and demand a new source review.
            result[ticker] = normalized
            mismatches.append(ticker)
    return result, mismatches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=date.fromisoformat, default=TARGET)
    parser.add_argument("--execute-fetch", action="store_true")
    parser.add_argument(
        "--require-usable", action="store_true", help="Fail if no ticker is evaluable"
    )
    args = parser.parse_args()
    target = args.target
    now = datetime.now(UTC)
    hosted = os.environ.get("GITHUB_ACTIONS") == "true"
    if args.execute_fetch:
        calendar, universe, proofs = load_manual_context()
        capture = {}
    else:
        if target != TARGET:
            raise ValueError("offline_capture_target_mismatch")
        calendar, universe, proofs, capture, _, _ = prepare(MANIFEST)
    universe.require(target)
    if now < calendar.get(target).closes_at:
        raise ValueError("target_session_not_closed")
    calendar.next(target)
    report = {
        "checked_at_utc": now.isoformat(),
        "target": target.isoformat(),
        "production_write": False,
        "database_connected": False,
        "scheduler_enabled": False,
        "provider_changed": False,
        "production_publication_attempted": False,
        "publication_receipt": None,
        "github_run_url": (
            "https://github.com/Daddy-JJ/BackendSahamTeknikal/actions/runs/"
            + os.environ["GITHUB_RUN_ID"]
            if hosted
            and os.environ.get("GITHUB_REPOSITORY") == "Daddy-JJ/BackendSahamTeknikal"
            and os.environ.get("GITHUB_RUN_ID", "").isdigit()
            else None
        ),
        "github_commit_sha": os.environ.get("GITHUB_SHA") if hosted else None,
        "environment": "fresh_provider_local_engine"
        if args.execute_fetch
        else "offline_actual_capture",
        "fresh_provider_fetch_executed": args.execute_fetch,
        "provider_errors": [],
    }
    raw = capture
    if args.execute_fetch:
        raw = {}
        folder = ROOT / "data/manual-scanner-smoke" / now.strftime("%Y%m%dT%H%M%SZ")
        folder.mkdir(parents=True, exist_ok=False)
        requests = load_requests(
            ROOT / "config/reference/yfinance-kompas100-verified-mappings.json",
            "yfinance",
            date(2024, 1, 1),
            target,
        )
        provider = YFinanceProvider()
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
                report["provider_errors"].append({"ticker": ticker, "code": exc.code})
            if index % 10 == 0:
                print(
                    json.dumps({"processed": index, "expected": len(requests)}),
                    flush=True,
                )
    prepared, mismatches = prepare_series(raw, proofs, calendar, target)
    evaluated_at = datetime.now(UTC)
    result = scan(prepared, target, calendar, universe, evaluated_at, ScanState())
    report.update(
        finished_at_utc=evaluated_at.isoformat(),
        fetched=len(raw),
        proof_count=len(proofs),
        evidence_mismatch_tickers=mismatches,
        status=result.status,
        coverage_valid=result.coverage_valid,
        coverage_total=result.coverage_total,
        ranking_status=result.ranking.status,
        signals=len(result.signals),
        run_digest=result.run_digest,
        counts=dict(Counter(i.status for i in result.items)),
        strategy_signal_counts=dict(
            Counter(s.candidate.strategy for s in result.signals)
        ),
        next_open=calendar.next(target).opens_at.isoformat(),
        items=[
            {
                "ticker": i.ticker,
                "status": i.status,
                "quality": quality(prepared[i.ticker], target, calendar)
                if i.ticker in prepared
                else "missing",
                "last_complete_session": raw[i.ticker].bars[-1].session.isoformat()
                if i.ticker in raw and raw[i.ticker].bars
                else None,
                "candidates": [
                    {
                        "strategy": c.strategy,
                        "reason": c.reason,
                        "triggered": c.triggered,
                    }
                    for c in i.candidates
                ],
            }
            for i in result.items
        ],
        scanner_quality_go=result.status == "complete"
        and result.ranking.status == "complete",
        hosted_github_runner_tested=hosted,
    )
    output = ROOT / "data/manual-scanner-smoke/latest-evidence.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "items"}, indent=2))
    return int(args.require_usable and result.coverage_valid == 0)


if __name__ == "__main__":
    raise SystemExit(main())
