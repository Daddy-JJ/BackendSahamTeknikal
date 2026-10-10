"""Explicit incident-shaped fixture: Oct8 plans resume Oct9 without rescreening.

Prices transcribed from the read-only incident audit's observed source capture;
these fixture signals are never published to production.
"""
import copy
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from test_paper_runtime import PersistedFixtureStore, initial

from idx_scanner.context import Calendar, Session
from idx_scanner.models import Bar, Series
from idx_scanner.paper_runtime import process_persisted_paper_session


def test_eight_original_plans_recover_chronologically_and_retry_preserves_events(signal):
    days = (date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 12), date(2026, 10, 13))
    calendar = Calendar(tuple(Session(day, datetime.combine(day, datetime.min.time(), UTC)
        .replace(hour=2), datetime.combine(day, datetime.min.time(), UTC).replace(hour=9))
        for day in days), "incident-fixture-v1", "synthetic://incident", "fixture")
    cases = (
        ("ADRO", "MACD_EMA200_V1", 2550, 2390, (2540, 2600, 2510, 2580, 19314700)),
        ("GGRM", "MACD_EMA200_V1", 16975, 16500, (16975, 18225, 16975, 18000, 1179200)),
        ("BFIN", "FRACTAL_BREAKOUT_V1", 945, 890, (945, 945, 925, 935, 5476800)),
        ("BFIN", "PULLBACK_RECLAIM_V1", 945, 901.6167157982887,
         (945, 945, 925, 935, 5476800)),
    )
    signals, sources = [], {}
    for index, (ticker, strategy, entry, stop, candle) in enumerate(cases):
        signals.append(replace(signal, id=f"incident-fixture-{index}", ticker=ticker,
            session=days[0], planned_entry_session=days[1],
            published_at=calendar.sessions[0].closes_at,
            candidate=replace(signal.candidate, strategy=strategy,
                              reference_close=entry, stop=stop)))
        sources[ticker] = Series(ticker, ticker + ".JK", "fixture", "incident-fixture",
            (Bar(days[0], entry, entry, entry, entry, 1000), Bar(days[1], *candle),
             Bar(days[2], *candle)), actions_complete=True)
    durable = initial(calendar)
    first = PersistedFixtureStore(durable, signals)
    planned, _ = process_persisted_paper_session(first, days[0], {}, calendar,
                                                calendar.sessions[0].closes_at)
    assert len(planned.trades) == 8 and all(t.entry is None for t in planned.trades.values())
    frozen = {key: (t.planned_entry_price, t.signal.candidate.stop, t.lots, t.initial_risk)
              for key, t in planned.trades.items()}
    # Restart with persisted book only; several sessions can be caught up in one job.
    restart = PersistedFixtureStore(durable, signals)
    recovered, _ = process_persisted_paper_session(restart, days[2], sources, calendar,
                                                  calendar.sessions[2].closes_at)
    assert len(recovered.trades) == 8
    assert sum(t.state == "open" for t in recovered.trades.values()) == 7
    closed = [t for t in recovered.trades.values() if t.state == "closed"]
    assert len(closed) == 1 and closed[0].signal.ticker == "GGRM"
    assert closed[0].events[-1].price == Decimal("17925")
    assert closed[0].net_pnl == Decimal("1583505.00")
    assert all(t.events[0].session == days[1] and t.entry == t.planned_entry_price
               for t in recovered.trades.values())
    assert frozen == {key: (t.planned_entry_price, t.signal.candidate.stop, t.lots, t.initial_risk)
                       for key, t in recovered.trades.items()}
    assert all(record["observed_sessions"] == 2 for record in durable["evaluations"].values())
    before = copy.deepcopy(durable)
    _, retry = process_persisted_paper_session(restart, days[2], sources, calendar,
                                              calendar.sessions[2].closes_at)
    assert retry["commit_replayed"] and durable == before
