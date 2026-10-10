"""Chronological recovery of the persisted paper book and signal observations."""
import json
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

from .context import Calendar, quality
from .models import Costs, ExitConfig, Series, Signal, digest
from .paper import (
    Experiment,
    PaperBook,
    paper_book_from_dict,
    paper_book_to_dict,
    step,
    summarize_book,
)
from .paper_persistence import PaperRuntimeStore
from .paper_research import MODEL_VERSION, create_evaluation, evaluation_active, step_evaluation
from .strategies import STRATEGIES
from .untradable import evidence_for, merge_untradable_evidence, require_nontrading_source


def close_experiments(activation: datetime) -> dict[str, list[Experiment]]:
    costs = Costs(Decimal(15), Decimal(25), Decimal(0), "verified")
    return {strategy: [Experiment(
        id=f"{MODEL_VERSION}-{key}-{strategy}", strategy=strategy, exit=exit_config,
        costs=costs, activated_at=activation, entry_model="signal_close",
        risk_budget_idr=Decimal(1000000), model_version=MODEL_VERSION,
    ) for key, exit_config in (
        ("fixed2r", ExitConfig(mode="fixed_rr", target_r=Decimal(2))),
        ("ma10", ExitConfig(mode="ma_close", target_r=None, ma_type="SMA", period=10)),
    )] for strategy in STRATEGIES}


def session_source(series: Series | None, session: date, calendar: Calendar,
                   untradable_sessions: tuple[date, ...] = ()):
    if series is None:
        return None, (), False
    require_nontrading_source(series, untradable_sessions)
    original = tuple(b for b in series.bars if b.session <= session)
    current = original[-1] if original and original[-1].session == session else None
    history = tuple(b for b in original if b.session not in untradable_sessions)
    historical = replace(series, bars=original)
    valid = quality(historical, session, calendar,
                    untradable_sessions=untradable_sessions) == "valid"
    return current, history, valid


def next_trade_session(trade, calendar: Calendar):
    return trade.signal.planned_entry_session if trade.entry is None else calendar.next(
        trade.last_session
    ).day


def advance_runtime(book: PaperBook, evaluations: dict, signals: list[Signal],
                    activation: datetime, target: date, series: dict[str, Series],
                    calendar: Calendar, observed_at: datetime, mappings: dict[str, str],
                    *, untradable_evidence=()):
    experiments = close_experiments(activation)
    untradable_evidence = merge_untradable_evidence(untradable_evidence, book, evaluations)
    signals = [s for s in signals if s.published_at >= activation and s.cohort == "forward"
               and s.candidate.execution_eligible and s.session <= target]
    register = [s for s in signals if s.id not in evaluations or any(
        digest((s.id, e.id)) not in book.trades for e in experiments[s.candidate.strategy]
    )]
    dates = [s.session for s in register]
    dates += [next_trade_session(t, calendar) for t in book.trades.values()
              if t.state in ("pending_entry", "open", "data_hold")]
    dates += [calendar.next(date.fromisoformat(r["last_session"])).day
              if r["last_session"] else date.fromisoformat(r["entry_session"])
              for r in evaluations.values() if evaluation_active(r)]
    if not dates or min(dates) > target:
        return book, evaluations
    for day in calendar.between(min(dates), target):
        for key, trade in tuple(book.trades.items()):
            if (trade.state not in ("pending_entry", "open", "data_hold")
                or next_trade_session(trade, calendar) != day):
                continue
            proofs = evidence_for(untradable_evidence, trade.signal.ticker, observed_at,
                                  trade.signal.data_mode)
            known_days = tuple(d for d in proofs if d <= day)
            bar, history, valid = session_source(series.get(trade.signal.ticker), day, calendar,
                                                known_days)
            book.trades[key] = step(trade, day, bar, calendar, observed_at,
                                   history=history, data_valid=valid,
                                   untradable_evidence=proofs.get(day),
                                   untradable_sessions=known_days)
        for key, record in tuple(evaluations.items()):
            expected = (calendar.next(date.fromisoformat(record["last_session"])).day
                        if record["last_session"] else date.fromisoformat(record["entry_session"]))
            if not evaluation_active(record) or expected != day:
                continue
            proofs = evidence_for(untradable_evidence, record["ticker"], observed_at,
                                  record["data_mode"])
            known_days = tuple(d for d in proofs if d <= day)
            bar, _, valid = session_source(series.get(record["ticker"]), day, calendar, known_days)
            evaluations[key] = step_evaluation(record, day, bar, calendar, observed_at,
                                              data_valid=valid,
                                              untradable_evidence=proofs.get(day))
        for signal in register:
            if signal.session != day:
                continue
            if signal.id not in evaluations:
                evaluations[signal.id] = create_evaluation(signal, mappings.get(signal.ticker, ""))
            for experiment in experiments[signal.candidate.strategy]:
                book.add(signal, experiment, calendar)
    return book, evaluations


def process_persisted_paper_session(store: PaperRuntimeStore, target: date,
                                    series: dict[str, Series], calendar: Calendar,
                                    observed_at: datetime, *, source_run_id: str | None = None,
                                    mappings: dict[str, str] | None = None,
                                    committed_signals: list[Signal] | None = None,
                                    untradable_evidence=()):
    runtime = store.load()
    activation = datetime.fromisoformat(runtime["activated_at"])
    book = paper_book_from_dict(runtime["book"])
    evaluations = json.loads(json.dumps(runtime["evaluations"]))
    signals = committed_signals if committed_signals is not None else store.committed_signals(
        target, activation
    )
    book, evaluations = advance_runtime(book, evaluations, signals, activation, target,
                                        series, calendar, observed_at, mappings or {},
                                        untradable_evidence=untradable_evidence)
    serialized = paper_book_to_dict(book)
    request_id = digest((store.owner_id, MODEL_VERSION, target, serialized, evaluations))
    receipt = store.commit(revision=runtime["revision"], request_id=request_id,
                           session=target, book=serialized, evaluations=evaluations,
                           source_run_id=source_run_id)
    summary = summarize_book(book)
    summary.pop("metrics", None)
    summary.pop("strategy_metrics", None)
    summary.update(model_version=MODEL_VERSION, persistence="supabase",
                   runtime_revision=receipt["revision"], commit_replayed=receipt["replayed"],
                   last_session=target.isoformat(), last_updated_at=observed_at.isoformat(),
                   evaluations_count=len(evaluations))
    trade_holds = sum(t.state == "data_hold" for t in book.trades.values())
    evaluation_holds = sum("data_hold" in r["results"].values() for r in evaluations.values())
    summary.update(trades_data_hold_count=trade_holds,
                   evaluations_data_hold_count=evaluation_holds,
                   data_hold_count=trade_holds + evaluation_holds)
    return book, summary
