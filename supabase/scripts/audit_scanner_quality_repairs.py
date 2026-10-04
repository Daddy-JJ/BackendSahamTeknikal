"""Offline audit of approved calendar normalization and reviewed BBCA dividends.

Only checksum-verified captured market data is evaluated. No database connection.
"""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime

from idx_scanner.config_io import load_calendar, load_universe
from idx_scanner.context import quality
from idx_scanner.corporate_actions import load_dividend_evidence, reconcile_dividends
from idx_scanner.engine import scan
from idx_scanner.models import ScanState, digest
from idx_scanner.normalization import normalize_closed_sessions
from prepare_dev_setup import ROOT
from publish_first_live_hold_run import TARGET, captured_series


def prepare(evidence_path=None):
    metadata = json.loads(
        (ROOT / "config/live/idx-calendar-2024-2026.json").read_text()
    )
    if digest(metadata["source_manifest"]) != metadata["source_checksum"]:
        raise ValueError("calendar_source_manifest_checksum_mismatch")
    for ref in metadata["source_manifest"]["calendar_references"]:
        if (
            digest(json.loads((ROOT / ref["reference"]).read_text()))
            != ref["reference_sha256"]
        ):
            raise ValueError("calendar_reference_checksum_mismatch")
    calendar = load_calendar(ROOT / "config/live/idx-calendar-2024-2026.json")
    universe = load_universe(
        ROOT / "config/live/kompas100-universe.json",
        ROOT / "config/live/kompas100-universe.csv",
    )
    roster = json.loads((ROOT / "config/live/kompas100-universe.json").read_text())
    if (
        hashlib.sha256(
            (ROOT / "data/sources" / roster["source_file_name"]).read_bytes()
        ).hexdigest()
        != roster["source_checksum"]
    ):
        raise ValueError("universe_workbook_checksum_mismatch")
    proofs = load_dividend_evidence(
        evidence_path or ROOT / "config/reference/bbca-reviewed-dividends-20261002.json", ROOT
    )
    raw = captured_series()
    if set(raw) != set(universe.tickers) or len(raw) != 100:
        raise ValueError("full_official_universe_required")
    normalized = {
        t: normalize_closed_sessions(s, calendar, TARGET) for t, s in raw.items()
    }
    prepared = {
        t: reconcile_dividends(s, proofs, calendar, TARGET)
        for t, s in normalized.items()
    }
    return calendar, universe, proofs, raw, normalized, prepared


def audit():
    calendar, universe, proofs, raw, normalized, prepared = prepare()
    now = datetime.now(UTC)
    report = {
        "purpose": "actual_capture_offline_quality_repair_audit_not_hosted_smoke",
        "checked_at_utc": now.isoformat(),
        "target": TARGET.isoformat(),
        "production_write": False,
        "scheduler_enabled": False,
        "raw_capture_count": len(raw),
        "raw_capture_checksums_verified": True,
        "calendar_version": calendar.version,
        "calendar_closed_days": len(calendar.closed_days),
        "source_hashes_verified": True,
        "reviewed_cash_dividend_events": len(proofs),
        "explicit_regular_ex_dates": sum(
            p.date_method == "explicit_regular_ex_date" for p in proofs
        ),
        "calendar_derived_regular_ex_dates": sum(
            p.date_method == "next_known_session_after_cum" for p in proofs
        ),
        "stage_quality": {
            label: dict(Counter(quality(s, TARGET, calendar) for s in values.values()))
            for label, values in (
                ("raw", raw),
                ("A_calendar", normalized),
                ("A_plus_B", prepared),
            )
        },
        "excluded_closed_bars": sum(
            len(raw[t].bars) - len(normalized[t].bars) for t in raw
        ),
        "excluded_closed_row_issues": sum(
            len(raw[t].provider_row_issues) - len(normalized[t].provider_row_issues)
            for t in raw
        ),
        "derived_revisions_required": sum(
            prepared[t].input_digest != raw[t].input_digest for t in raw
        ),
        "details": [],
    }
    result = scan(prepared, TARGET, calendar, universe, now, ScanState())
    report.update(
        scan_status=result.status,
        coverage_valid=result.coverage_valid,
        coverage_total=result.coverage_total,
        rs_complete=result.ranking.status == "complete",
        rs_reason=result.ranking.status,
        signals=len(result.signals),
        run_digest=result.run_digest,
        namespace="forward",
        publication_attempted=False,
    )
    items = {i.ticker: i for i in result.items}
    for t in sorted(prepared):
        s = prepared[t]
        report["details"].append(
            {
                "ticker": t,
                "quality": quality(s, TARGET, calendar),
                "open_bars": len(s.bars),
                "raw_input_digest": raw[t].input_digest,
                "derived_input_digest": s.input_digest,
                "unreconciled_actions": len(s.actions) - len(s.reconciled_actions),
                "zero_volume_open_sessions": [
                    b.session.isoformat() for b in s.bars if b.volume == 0
                ],
                "candidate_results": [
                    {
                        "strategy": c.strategy,
                        "triggered": c.triggered,
                        "reason": c.reason,
                    }
                    for c in items[t].candidates
                ],
            }
        )
    return report


def main():
    report = audit()
    path = ROOT / "data/scanner-quality-repair-audit-20261002.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "details"}, indent=2))


if __name__ == "__main__":
    main()
