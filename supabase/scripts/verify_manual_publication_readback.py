"""GET-only recovery of the single approved publication; never retry a write."""

import json
from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal

from manual_scanner_smoke import prepare_series
from prepare_dev_setup import ROOT, local_env
from prepare_manual_publication import LEDGER_ORDER, fingerprint, prepare, read_rows, verify_plan
from publish_first_live_hold_run import REF

from idx_scanner.persistence import SupabaseScanStore

RUN_ID = "3c700de4-8389-400e-b862-31f2c8998a64"
PLAN_SHA = "838183f9e3fcb5bcfe6c4681be885e87a1410672137d73eeed0f1a3d2ff4ffb0"
TRADE = "e6dcfcc6-fd57-4e1d-9148-ecd5a738edc4"


def main():
    report = {"project_ref": REF, "method": "GET only", "production_write": False,
              "publication_retried": False, "run_id": RUN_ID, "scheduler_enabled": False,
              "owner_jwt_tested": False, "full_stack_live": False}
    failed = False
    try:
        values = prepare(ROOT / "data/manual-scanner-smoke/20261003T093419Z",
                         date(2026, 10, 2), datetime.now(UTC))
        plan, calendar, _, proofs, _, raw = values
        verify_plan(ROOT / "data/manual-publication/plan-local-20261003.json", PLAN_SHA, plan)
        prepared, _ = prepare_series(raw, proofs, calendar, date(2026, 10, 2))
        conf = local_env(ROOT / ".env")
        url = f"https://{REF}.supabase.co"
        if conf.get("SUPABASE_URL", "").rstrip("/") != url:
            raise ValueError("target_mismatch")
        with SupabaseScanStore(url, conf["SUPABASE_SECRET_KEY"]) as store:
            # Reproduce only the failed GET and retain status/code, not private body.
            response = store._client.get("scan_run_items", params={
                "run_id": "eq." + RUN_ID, "select": "ticker", "order": "id.asc", "limit": "1"})
            report["original_readback_get_diagnostic"] = {
                "http": response.status_code, "code": response.json().get("code")}
            runs = read_rows(store, "scan_runs", {"id": "eq." + RUN_ID})
            if len(runs) != 1 or any(runs[0][k] != v for k, v in {
                    "run_digest": plan["run_digest"], "session_date": plan["target"],
                    "namespace": "forward", "data_mode": "live", "status": "partial",
                    "coverage_valid": 45, "coverage_total": 100}.items()):
                raise ValueError("run_mismatch")
            items = read_rows(store, "scan_run_items", {"run_id": "eq." + RUN_ID})
            if (len(items) != 100 or len({i["ticker"] for i in items}) != 100
                    or dict(Counter(i["status"] for i in items)) != plan["counts"]):
                raise ValueError("items_mismatch")
            # Compare each status to the canonical plan inputs, not merely aggregate counts.
            from idx_scanner.engine import scan
            from idx_scanner.models import ScanState

            result = scan(prepared, date(2026, 10, 2), calendar, values[2],
                          datetime.now(UTC), ScanState())
            if {i["ticker"]: i["status"] for i in items} != {
                    i.ticker: i.status for i in result.items}:
                raise ValueError("item_status_mismatch")
            if (read_rows(store, "scan_run_signals", {"run_id": "eq." + RUN_ID})
                    or runs[0]["snapshot"]["ranking"]["status"] != "cross_section_incomplete"):
                raise ValueError("unexpected_signals_or_rs")
            revisions = read_rows(store, "market_series_revisions", {
                "select": "id,ticker,provider_version,input_digest,fetched_at,stored_at",
                "data_mode": "eq.live", "namespace": "eq.forward", "provider": "eq.yfinance"})
            by_key = {(r["ticker"], r["provider_version"], r["input_digest"]): r for r in revisions}
            expected = {(s.ticker, s.provider_version, s.input_digest)
                        for s in (*raw.values(), *prepared.values())}
            if not expected.issubset(by_key):
                raise ValueError("revision_key_missing")
            all_runs = read_rows(store, "scan_runs")
            old_path = ROOT / "docs/evidence/production-ksei-reconciliation-20261003.json"
            old_report = json.loads(old_path.read_text(encoding="utf-8"))
            old = next(r for r in all_runs if r["id"] == old_report["run_id"])
            if (old["run_digest"] != old_report["run_digest"]
                    or old["stored_at"] != old_report["stored_at"]
                    or old["coverage_valid"] != 45):
                raise ValueError("prior_run_metadata_mismatch")
            journal = {table: read_rows(store, table) for table in LEDGER_ORDER}
            trades = journal["actual_trades"]
            if len(trades) != 1 or trades[0]["id"] != TRADE:
                raise ValueError("trade_set_mismatch")
            trade = trades[0]
            if trade["revision"] != 5 or trade["status"] != "closed":
                raise ValueError("real_trade_projection_changed")
            for field, value in {"initial_risk_idr": "6500", "realized_pnl_idr": "1244",
                                 "fee_total_idr": "256", "realized_r": "0.191384615385"}.items():
                if Decimal(str(trade[field])) != Decimal(value):
                    raise ValueError("real_trade_projection_changed")
            for table in ("scan_runs", "market_series_revisions", "signals", "actual_trades"):
                if read_rows(store, table, {"select": "id", "data_mode": "eq.fixture"}):
                    raise ValueError("fixture_detected")
            report.update(status="published_partial_run_get_readback_passed",
                          run_digest=plan["run_digest"], stored_at=runs[0]["stored_at"],
                          target=plan["target"], counts=plan["counts"], unique_tickers=100,
                          signals=0, ranking_status="cross_section_incomplete",
                          revision_manifest_keys_verified=len(expected),
                          revision_manifest=[by_key[k] for k in sorted(expected)],
                          full_bar_rpc_readbacks_this_check=0, old_run_metadata_matches_prior=True,
                          prior_run_ids_present=[r["id"] for r in all_runs if r["id"] != RUN_ID],
                          real_trade_projection_matches_prior=True,
                          journal_table_counts={t: len(rows) for t, rows in journal.items()},
                          postpublication_journal_fingerprints={t: fingerprint(rows)
                                                               for t, rows in journal.items()},
                          prepublication_journal_fingerprints_recovered=False,
                          full_journal_before_after_equality=(
                              "NOT VERIFIED: original in-memory baseline lost "
                              "after postflight error"
                          ),
                          fixture_rows_absent=True, auth_mutation_executed=False,
                          scanner_full_quality_go=False, hosted_github_publisher_tested=False)
    except Exception:
        failed = True
        report.update(status="readback_failed", failure="readback_failure_redacted")
    report["checked_at_utc"] = datetime.now(UTC).isoformat()
    output = ROOT / "docs/evidence/manual-production-publication-readback-20261003.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    safe = {k: v for k, v in report.items()
            if k not in ("revision_manifest", "postpublication_journal_fingerprints")}
    print(json.dumps(safe, indent=2))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
