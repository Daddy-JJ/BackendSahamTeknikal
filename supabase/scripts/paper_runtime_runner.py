"""Production paper processing using committed scanner and market snapshots."""
from datetime import date, datetime
from time import monotonic

from idx_scanner.context import quality
from idx_scanner.incremental_provider import persist_provider_captures
from idx_scanner.paper import paper_book_from_dict
from idx_scanner.paper_persistence import PaperRuntimeStore
from idx_scanner.paper_research import evaluation_active
from idx_scanner.paper_runtime import (
    next_trade_session,
    process_persisted_paper_session,
)
from idx_scanner.persistence import PersistenceError
from idx_scanner.providers import FetchRequest, ProviderError
from manual_scanner_smoke import prepare_series


def complete_persisted_paper(scan_store, paper_store: PaperRuntimeStore, prepared, requests,
                             target, calendar, proofs, observed_at, provider, run_id,
                             *, attempted_tickers=(), untradable_evidence=(), clock=None,
                             recovery_max_tickers=20, recovery_budget_seconds=300,
                             timer=monotonic, lease_check=None):
    runtime = paper_store.load()
    signals = paper_store.committed_signals(target, datetime.fromisoformat(runtime["activated_at"]))
    mappings = {ticker: request.symbol for ticker, request in requests.items()}
    records = runtime["evaluations"]
    for record in records.values():
        if record.get("provider_symbol"):
            mappings.setdefault(record["ticker"], record["provider_symbol"])
    book = paper_book_from_dict(runtime["book"])
    required = {}
    def require(ticker, day):
        if day <= target:
            required[ticker] = min(required.get(ticker, day), day)
    for trade in book.trades.values():
        if trade.state in ("open", "pending_entry", "data_hold"):
            require(trade.signal.ticker, next_trade_session(trade, calendar))
    for record in records.values():
        if evaluation_active(record):
            require(record["ticker"], calendar.next(date.fromisoformat(record["last_session"])).day
                    if record["last_session"] else date.fromisoformat(record["entry_session"]))
    for signal in signals:
        if signal.id not in records:
            require(signal.ticker, signal.planned_entry_session)
    for signal in signals:
        if signal.ticker in mappings:
            continue
        rows = scan_store._request("GET", "market_series_revisions", params={
            "select": "id,input_digest", "ticker": "eq." + signal.ticker,
            "namespace": "eq.forward", "data_mode": "eq." + paper_store.data_mode,
            "input_digest": "eq." + signal.input_digest, "limit": "1", "order": "id.asc",
        })
        if not rows:
            raise PersistenceError("paper_original_mapping_unavailable")
        original = scan_store.load_series(rows[0]["id"], data_mode=paper_store.data_mode,
                                          expected_input_digest=rows[0]["input_digest"])
        mappings[signal.ticker] = original.provider_symbol
    market = dict(prepared)
    errors = []
    # The book gets one independently budgeted fetch per invalid tracked ticker,
    # including primary failures. It never changes the scanner comparison set.
    candidates = {t for t in required if t not in market
                  or quality(market[t], target, calendar) != "valid"}
    needed = []
    for day in sorted({required[t] for t in candidates}):
        group = sorted(t for t in candidates if required[t] == day)
        offset = (getattr(paper_store, "recovery_sequence", 0) * recovery_max_tickers) % len(group)
        needed.extend(group[offset:] + group[:offset])
    started = timer()
    for index, ticker in enumerate(needed):
        if lease_check is not None:
            lease_check()
        if index >= recovery_max_tickers or timer() - started >= recovery_budget_seconds:
            errors.extend({"ticker": t, "code": "paper_recovery_budget_exhausted"}
                          for t in needed[index:])
            break
        if ticker not in mappings:
            raise PersistenceError("paper_verified_mapping_unavailable")
        request = FetchRequest(ticker, mappings[ticker], date(2024, 1, 1), target, True)
        try:
            raw = provider.fetch(request)
        except ProviderError as exc:
            errors.append({"ticker": ticker, "code": exc.code})
            continue
        persist_provider_captures(provider, scan_store, ticker, data_mode=paper_store.data_mode)
        scan_store.ingest_series(raw, data_mode=paper_store.data_mode)
        normalized, _ = prepare_series({ticker: raw}, proofs, calendar, target)
        source = normalized[ticker]
        receipt = scan_store.ingest_series(source, data_mode=paper_store.data_mode)
        market[ticker] = scan_store.load_series(receipt["revision_id"],
            data_mode=paper_store.data_mode, expected_input_digest=source.input_digest)
    # Eligibility of a delayed MA observation is determined after market IO,
    # not by the time the scheduler started fetching.
    observed_at = clock() if clock is not None else observed_at
    if lease_check is not None:
        lease_check()
    result, summary = process_persisted_paper_session(
        paper_store, target, market, calendar, observed_at, source_run_id=run_id,
        mappings=mappings, committed_signals=signals,
        untradable_evidence=untradable_evidence,
        lease_check=lease_check,
    )
    summary["provider_errors"] = errors
    return result, summary
