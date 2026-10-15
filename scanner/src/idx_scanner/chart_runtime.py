"""Bounded cloud chart writer. Reads persisted state; never fetches or creates trades."""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from uuid import UUID

from .chart_artifact import (
    INDICATOR_VERSION,
    ChartReceipt,
    build_chart_artifact,
    resolve_signal_receipt,
    source_scope,
)
from .context import Calendar, Session, quality
from .models import digest
from .persistence import PersistenceError, series_from_revision
from .untradable import restore_untradable_evidence

DEFAULT_MAX_REVISIONS = 256
MAX_RECEIPT_READ_WORKERS = 4


def calendar_from_payload(payload: dict, mode: str) -> Calendar:
    try:
        if payload["data_mode"] != mode:
            raise ValueError()
        return Calendar(tuple(Session(date.fromisoformat(s["day"]),
                        datetime.fromisoformat(s["opens_at"]),
                        datetime.fromisoformat(s["closes_at"])) for s in payload["sessions"]),
                        payload["version"], payload["source"], mode,
                        tuple(date.fromisoformat(s) for s in payload.get("historical_days", [])),
                        tuple(date.fromisoformat(s) for s in payload.get("closed_days", [])))
    except (KeyError, TypeError, ValueError):
        raise PersistenceError("chart_invalid_calendar") from None


class ChartArtifactStore:
    def __init__(self, store, owner_id: str, data_mode="live"):
        if str(UUID(owner_id)) != owner_id or data_mode not in ("live", "fixture"):
            raise ValueError("invalid_chart_owner_context")
        self.store, self.owner_id, self.data_mode = store, owner_id, data_mode

    def load(self, ticker=None):
        if ticker is not None and not re.fullmatch(r"[A-Z0-9_-]{1,20}", ticker):
            raise ValueError("invalid_chart_ticker")
        payload = self.store._request("POST", "rpc/load_ticker_chart_inputs_v1", json={
            "p_owner_id": self.owner_id, "p_ticker": ticker})
        if (not isinstance(payload, dict) or payload.get("owner_id") != self.owner_id
            or payload.get("data_mode") != self.data_mode):
            raise PersistenceError("chart_owner_mode_mismatch")
        if ticker is not None and payload.get("ticker") != ticker:
            raise PersistenceError("chart_ticker_mismatch")
        return payload

    def receipts(self, rows, ticker, *, maximum=DEFAULT_MAX_REVISIONS):
        if not isinstance(rows, list) or len(rows) > maximum:
            raise PersistenceError("chart_revision_budget_exhausted")
        if any(not isinstance(row, dict) or row.get("data_mode") != self.data_mode
               or row.get("ticker") != ticker for row in rows):
            raise PersistenceError("chart_market_mode_mismatch")
        if not rows:
            return ()
        # Only source reads run concurrently. Detect errors promptly, cancel
        # queued work and drain in-flight reads before returning any projection.
        with ThreadPoolExecutor(max_workers=min(MAX_RECEIPT_READ_WORKERS, len(rows))) as workers:
            futures = tuple(workers.submit(self._read_receipt, row, ticker) for row in rows)
            try:
                for completed in as_completed(futures):
                    completed.result()
                return tuple(future.result() for future in futures)
            finally:
                for future in futures:
                    future.cancel()

    def _read_receipt(self, row, ticker):
        response = self.store._request("POST", "rpc/read_market_series",
                                        json={"p_revision_id": row["id"]})
        try:
            if (response["revision_id"] != row["id"]
                or response["namespace"] != row["namespace"]
                or response["data_mode"] != self.data_mode
                or response["input_digest"] != row["input_digest"]):
                raise ValueError()
            series = series_from_revision(response)
            if series.ticker != ticker:
                raise ValueError()
            return ChartReceipt(row["id"], row["namespace"], self.data_mode,
                                series, datetime.fromisoformat(row["stored_at"]))
        except (KeyError, TypeError, ValueError):
            raise PersistenceError("chart_invalid_market_revision") from None

    def persist(self, record):
        if record["owner_id"] != self.owner_id or record["data_mode"] != self.data_mode:
            raise ValueError("chart_owner_mode_mismatch")
        response = self.store._request("POST", "rpc/persist_ticker_chart_artifact_v1",
                                        json={"p_record": record})
        if (not isinstance(response, dict) or response.get("revision") != record["revision"]
            or type(response.get("replayed")) is not bool):
            raise PersistenceError("chart_invalid_write_receipt")
        return response

    def prune_cursors(self):
        """At most 200k expired metadata rows/job; never touches artifacts or ledger."""
        removed = 0
        for batch in range(1, 21):
            response = self.store._request("POST", "rpc/prune_ticker_chart_cursors_v1",
                                           json={"p_limit": 10000})
            if (not isinstance(response, dict) or set(response) != {"deleted", "has_more"}
                or type(response["deleted"]) is not int
                or not 0 <= response["deleted"] <= 10000
                or type(response["has_more"]) is not bool):
                raise PersistenceError("chart_invalid_cleanup_receipt")
            removed += response["deleted"]
            if not response["has_more"]:
                return {"deleted": removed, "has_more": False, "batches": batch}
        return {"deleted": removed, "has_more": True, "batches": 20}


def _observation(receipts, calendar, original=None, paper=False):
    eligible = tuple(r for r in receipts if (paper or r.namespace == "forward"
                                             and source_scope(r.series, r.namespace)
                                             != "paper_recovery")
                     and (original is None or (r.series.provider, r.series.price_basis) ==
                          (original.series.provider, original.series.price_basis)))
    if not eligible:
        raise ValueError("chart_source_unavailable")
    complete = tuple(r for r in eligible if r.series.bars and quality(
        r.series, r.series.bars[-1].session, calendar) == "valid")
    selected = max(complete or eligible, key=lambda r: (r.stored_at, r.series_id))
    newest = max(eligible, key=lambda r: (r.stored_at, r.series_id))
    return selected, selected.series_id != newest.series_id


def _older_observation(data, rejected_newer):
    if not rejected_newer:
        return data
    projected = {**data, "quality": {**data["quality"], "completeness": "partial",
                 "freshness": "stale", "warnings": [*data["quality"]["warnings"],
                                                     "newer_receipt_unusable"]}}
    return {**projected, "revision": digest((INDICATOR_VERSION,
                                            {k: v for k, v in projected.items()
                                             if k != "revision"}))}


def _proofs(bundle):
    audits = []
    for row in bundle.get("paper_events", []):
        audit = row.get("payload", {}).get("untradable_evidence")
        if audit:
            audits.append(audit)
    for row in bundle.get("evaluations", []):
        audits += row.get("payload", {}).get("untradable_evidence", [])
    result = {}
    for audit in audits:
        proof = restore_untradable_evidence(audit)
        key = (proof.ticker, proof.session, proof.data_mode)
        if key in result and result[key].input_digest != proof.input_digest:
            raise ValueError("conflicting_untradable_evidence")
        result[key] = proof
    return tuple(result.values())


def _context_data(bundle):
    signals = {r["id"]: r["snapshot"] for r in bundle.get("signals", [])}
    contexts = [("latest", None, None, None, None)]
    contexts += [("signal", key, value, None, None) for key, value in signals.items()]
    for row in bundle.get("paper_trades", []):
        paper = row.get("details", {})
        contexts.append(("paper", row["id"], paper.get("signal"), paper, None))
    for row in bundle.get("actual_trades", []):
        contexts.append(("actual", row["id"], signals.get(row.get("signal_id")), None, row))
    return contexts


def build_context_records(bundle, receipts, calendar, *, observed_at):
    records, errors = [], []
    evidence = _proofs(bundle)
    for kind, key, signal, paper, actual in _context_data(bundle):
        if kind in ("signal", "paper") and signal is None:
            errors.append({"context_kind": kind, "code": "snapshot_unavailable"})
            continue
        try:
            original = resolve_signal_receipt(receipts, signal) if signal else None
        except ValueError:
            errors.append({"context_kind": kind, "code": "snapshot_unavailable"})
            continue
        for view in (("snapshot", "followup") if kind in ("signal", "paper")
                     else ("followup",)):
            try:
                observation, older = (_observation(receipts, calendar, original,
                                                  paper=kind == "paper")
                                      if view == "followup" else (original, False))
                data = build_chart_artifact(original if view == "snapshot" else observation,
                    calendar, observed_at=observed_at, kind=kind, context_id=key, view=view,
                    signal=signal, signal_receipt=original, paper=paper, actual=actual,
                    fills=tuple(f for f in bundle.get("actual_fills", []) if f["trade_id"] == key),
                    stops=tuple(s for s in bundle.get("actual_stops", []) if s["trade_id"] == key),
                    evidence=evidence)
                data = _older_observation(data, older)
                records.append({"owner_id": bundle["owner_id"], "data_mode": bundle["data_mode"],
                    "ticker": bundle["ticker"], "context_kind": kind, "context_id": key,
                    "view": view, "revision": data["revision"], "data": data})
            except ValueError as exc:
                code = (str(exc) if str(exc) in ("snapshot_unavailable", "chart_source_unavailable",
                       "calendar_unavailable", "invalid_chart_sessions", "chart_nonmarket_bar")
                        else "chart_invalid_input")
                errors.append({"context_kind": kind, "code": code})
    return records, errors


def run_chart_job(store: ChartArtifactStore, *, observed_at: datetime, ticker=None,
                  execute=False, max_tickers=100, max_revisions=DEFAULT_MAX_REVISIONS):
    if not 1 <= max_tickers <= 100 or not 1 <= max_revisions <= 500:
        raise ValueError("invalid_chart_job_budget")
    maintenance = (store.prune_cursors() if execute else
                   {"deleted": 0, "has_more": False, "batches": 0})
    catalog = store.load()
    catalog_tickers = catalog.get("tickers")
    if (not isinstance(catalog_tickers, list) or len(catalog_tickers) > 5000
        or any(not isinstance(t, str) or not re.fullmatch(r"[A-Z0-9_-]{1,20}", t)
               for t in catalog_tickers) or len(catalog_tickers) != len(set(catalog_tickers))):
        raise PersistenceError("chart_ticker_budget_exhausted")
    tickers = [ticker] if ticker else sorted(catalog_tickers)
    if (not isinstance(tickers, list)
        or any(not isinstance(t, str) or not re.fullmatch(r"[A-Z0-9_-]{1,20}", t)
               for t in tickers) or len(tickers) != len(set(tickers))):
        raise PersistenceError("chart_ticker_budget_exhausted")
    total = len(tickers)
    offset = 0
    if total > max_tickers:
        offset = (int(observed_at.timestamp()) // 3600 * max_tickers) % total
        tickers = (tickers[offset:] + tickers[:offset])[:max_tickers]
    written, prepared, failures = 0, 0, []
    for symbol in tickers:
        try:
            bundle = store.load(symbol)
            calendar = calendar_from_payload(bundle["calendar"], store.data_mode)
            receipts = store.receipts(bundle["market_revisions"], symbol, maximum=max_revisions)
            records, errors = build_context_records(bundle, receipts, calendar,
                                                     observed_at=observed_at)
            prepared += len(records)
            failures += [{"ticker": symbol, **e} for e in errors]
            if execute:
                for record in records:
                    store.persist(record)
                    written += 1
        except PersistenceError as exc:
            failures.append({"ticker": symbol, "code": exc.code})
        except (KeyError, TypeError, ValueError):
            failures.append({"ticker": symbol, "code": "chart_invalid_input"})
    return {"contract_version": "chart-artifact-job-v1", "status": "failed" if failures
            else "ready", "execute": execute, "tickers": len(tickers), "prepared": prepared,
            "written": written, "failures": failures, "total_tickers": total,
            "deferred_tickers": total - len(tickers), "batch_offset": offset,
            "cursor_maintenance": maintenance}
