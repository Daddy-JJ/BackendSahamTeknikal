"""Generate reviewable UI fixture FROM the same engine used by live adapters."""

from dataclasses import asdict
from datetime import timedelta

from .engine import scan
from .fixtures import sample_market
from .indicators import calculate
from .metrics import summarize
from .models import Costs, ExitConfig, ScanState
from .paper import Experiment, PaperBook, step
from .strategies import STRATEGIES


def demo_snapshot() -> dict:
    series, calendar, universe = sample_market()
    state, book = ScanState(), PaperBook()
    experiments = {
        s: Experiment("baseline-" + s, s, ExitConfig(), Costs(), calendar.sessions[599].opens_at)
        for s in STRATEGIES
    }
    results = []
    for index in range(600, 660):
        session = calendar.sessions[index]
        observed = session.closes_at + timedelta(hours=3)
        for key, trade in tuple(book.trades.items()):
            if trade.state in ("pending_entry", "open", "data_hold"):
                bars = series[trade.signal.ticker].bars[: index + 1]
                book.trades[key] = step(
                    trade, session.day, bars[-1], calendar, observed, history=bars
                )
        result = scan(series, session.day, calendar, universe, observed, state)
        results.append(result)
        for signal in result.signals:
            book.add(signal, experiments[signal.candidate.strategy], calendar)
    last = results[-1]
    closed = sorted(
        (t for t in book.trades.values() if t.state == "closed"),
        key=lambda t: (t.last_session, t.id),
    )
    open_count = sum(t.state == "open" for t in book.trades.values())
    ambiguous = sum(t.alternate_r is not None for t in closed)
    metrics = summarize(
        [t.realized_r for t in closed], open_count=open_count, ambiguous_count=ambiguous
    )
    return {
        "schema_version": "1.0.0",
        "data_mode": "fixture",
        "label": "DEMO — data sintetis, bukan data pasar atau anggota KOMPAS100",
        "session": last.session.isoformat(),
        "status": last.status,
        "coverage": {"valid": last.coverage_valid, "total": last.coverage_total},
        "provider": "fixture",
        "universe": universe.version,
        "cost_label": Costs().label,
        "run_digest": last.run_digest,
        "ranking": asdict(last.ranking),
        "signals": [
            asdict(s)
            for s in sorted(
                state.signals.values(), key=lambda s: (s.session, s.ticker), reverse=True
            )
        ],
        "items": [asdict(i) for i in last.items],
        "charts": {
            t: [
                {
                    **asdict(b),
                    "ema20": f.ema20[j],
                    "ema50": f.ema50[j],
                    "ema200": f.ema200[j],
                    "histogram": f.histogram[j],
                }
                for j, b in enumerate(s.bars)
                if j >= len(s.bars) - 60
            ]
            for t, s in series.items()
            for f in [calculate(s.bars)]
        },
        "paper": [
            {
                "id": t.id,
                "ticker": t.signal.ticker,
                "strategy": t.signal.candidate.strategy,
                "state": t.state,
                "reason": t.reason,
                "entry": t.entry,
                "stop": t.stop,
                "target": t.target,
                "realized_r": t.realized_r,
                "alternate_r": t.alternate_r,
                "initial_risk": t.initial_risk,
                "exit_session": t.last_session if t.state == "closed" else None,
            }
            for t in book.trades.values()
        ],
        "metrics": metrics,
        "strategy_metrics": {
            strategy: summarize(
                [t.realized_r for t in closed if t.signal.candidate.strategy == strategy],
                open_count=sum(
                    t.state == "open" and t.signal.candidate.strategy == strategy
                    for t in book.trades.values()
                ),
                ambiguous_count=sum(
                    t.alternate_r is not None and t.signal.candidate.strategy == strategy
                    for t in closed
                ),
            )
            for strategy in STRATEGIES
        },
        "limitations": [
            "Kalender dan seluruh harga sintetis.",
            "Paper adalah evaluasi per trade, bukan return portfolio.",
            "Biaya diasumsikan nol untuk fixture.",
            "Supabase, owner auth, dan live provider belum terhubung.",
        ],
    }
