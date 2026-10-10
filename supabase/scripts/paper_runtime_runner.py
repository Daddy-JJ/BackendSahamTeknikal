"""Production paper processing using committed scanner and market snapshots."""
from datetime import date, datetime

from idx_scanner.paper import paper_book_from_dict
from idx_scanner.paper_persistence import PaperRuntimeStore
from idx_scanner.paper_research import evaluation_active
from idx_scanner.paper_runtime import process_persisted_paper_session
from idx_scanner.persistence import PersistenceError
from idx_scanner.providers import FetchRequest, ProviderError
from manual_scanner_smoke import prepare_series


def complete_persisted_paper(scan_store, paper_store: PaperRuntimeStore, prepared, requests,
                             target, calendar, proofs, observed_at, provider, run_id,
                             *, attempted_tickers=(), untradable_evidence=(), clock=None):
    runtime = paper_store.load()
    signals = paper_store.committed_signals(target, datetime.fromisoformat(runtime["activated_at"]))
    mappings = {ticker: request.symbol for ticker, request in requests.items()}
    records = runtime["evaluations"]
    for record in records.values():
        if record.get("provider_symbol"):
            mappings.setdefault(record["ticker"], record["provider_symbol"])
    book = paper_book_from_dict(runtime["book"])
    tracked = {t.signal.ticker for t in book.trades.values()
               if t.state in ("open", "pending_entry", "data_hold")}
    tracked |= {r["ticker"] for r in records.values() if evaluation_active(r)}
    tracked |= {s.ticker for s in signals if s.id not in records}
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
    # Requests describe verified mappings, not proof that a ticker was fetched.
    # Independent recovery has no prepared scanner input and must fetch tracked
    # universe members too. A primary run explicitly passes its attempted set,
    # so failed scanner captures stay holds instead of causing unbounded retries.
    for ticker in sorted(tracked - market.keys() - set(attempted_tickers)):
        if ticker not in mappings:
            raise PersistenceError("paper_verified_mapping_unavailable")
        request = FetchRequest(ticker, mappings[ticker], date(2024, 1, 1), target, True)
        try:
            raw = provider.fetch(request)
        except ProviderError as exc:
            errors.append({"ticker": ticker, "code": exc.code})
            continue
        scan_store.ingest_series(raw, data_mode=paper_store.data_mode)
        normalized, _ = prepare_series({ticker: raw}, proofs, calendar, target)
        source = normalized[ticker]
        receipt = scan_store.ingest_series(source, data_mode=paper_store.data_mode)
        market[ticker] = scan_store.load_series(receipt["revision_id"],
            data_mode=paper_store.data_mode, expected_input_digest=source.input_digest)
    # Eligibility of a delayed MA observation is determined after market IO,
    # not by the time the scheduler started fetching.
    observed_at = clock() if clock is not None else observed_at
    result, summary = process_persisted_paper_session(
        paper_store, target, market, calendar, observed_at, source_run_id=run_id,
        mappings=mappings, committed_signals=signals,
        untradable_evidence=untradable_evidence,
    )
    summary["provider_errors"] = errors
    return result, summary
