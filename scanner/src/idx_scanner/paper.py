"""Trade-level EOD forward simulation, not a capital-constrained portfolio."""

import json
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal

from .context import Calendar
from .exits import evaluate_exit, money
from .indicators import ema, sma
from .metrics import summarize
from .models import Bar, Costs, ExitConfig, Series, Signal, canonical_json, digest
from .strategies import STRATEGIES


@dataclass(frozen=True)
class Experiment:
    id: str
    strategy: str
    exit: ExitConfig
    costs: Costs
    activated_at: datetime

    def __post_init__(self):
        if self.activated_at.tzinfo is None:
            raise ValueError("Timezone-aware activation required")

    @property
    def config_hash(self) -> str:
        return digest(self)


@dataclass(frozen=True)
class Event:
    session: date
    kind: str
    price: Decimal | None
    reason: str
    observed_at: datetime
    input_digest: str
    alternate_price: Decimal | None = None
    ma_value: Decimal | None = None
    ma_type: str | None = None
    ma_period: int | None = None


@dataclass(frozen=True)
class PaperTrade:
    id: str
    signal: Signal
    experiment: Experiment
    state: str = "pending_entry"
    reason: str = ""
    entry: Decimal | None = None
    stop: Decimal | None = None
    target: Decimal | None = None
    initial_risk: Decimal | None = None
    pending_exit: date | None = None
    last_session: date | None = None
    events: tuple[Event, ...] = ()
    net_pnl: Decimal | None = None
    realized_r: Decimal | None = None
    alternate_r: Decimal | None = None
    actionable: bool = True


def create_plan(signal: Signal, experiment: Experiment, calendar: Calendar) -> PaperTrade:
    if experiment.strategy != signal.candidate.strategy:
        raise ValueError("strategy_experiment_mismatch")
    identity = digest((signal.id, experiment.id))
    reason = ""
    if signal.cohort != "forward":
        reason = "late_or_backtest_signal"
    elif experiment.activated_at >= calendar.get(signal.planned_entry_session).opens_at:
        reason = "experiment_activated_too_late"
    elif not signal.candidate.execution_eligible:
        reason = signal.candidate.reason
    return PaperTrade(
        identity,
        signal,
        experiment,
        "skipped" if reason else "pending_entry",
        reason,
        stop=money(signal.candidate.stop) if signal.candidate.stop is not None else None,
    )


def step(
    trade: PaperTrade,
    session: date,
    bar: Bar | None,
    calendar: Calendar,
    observed_at: datetime,
    *,
    history: tuple[Bar, ...] = (),
    data_valid: bool = True,
    confirmed_untradable: bool = False,
) -> PaperTrade:
    """Replay a held session before any later session. Daily entry/exit events are idempotent."""
    if trade.state in ("closed", "skipped", "expired"):
        return trade
    session_info = calendar.get(session)
    if observed_at.tzinfo is None or observed_at < session_info.closes_at:
        raise ValueError("target_session_not_closed")
    if trade.last_session is not None and session <= trade.last_session:
        return trade
    expected = (
        trade.signal.planned_entry_session
        if trade.entry is None
        else calendar.next(trade.last_session).day
    )
    if session != expected:
        raise ValueError("chronological_replay_required")
    if confirmed_untradable:
        return replace(
            trade,
            state="expired" if trade.entry is None else "open",
            reason="expired_untradable" if trade.entry is None else "awaiting_tradable_session",
            last_session=session,
        )
    if bar is None or not data_valid or not bar.valid() or bar.volume == 0:
        return replace(trade, state="data_hold", reason="missing_or_invalid_bar")
    if bar.session != session:
        raise ValueError("bar_session_mismatch")
    entry_day = trade.entry is None
    stop = trade.stop
    assert stop is not None
    updated = trade
    events = trade.events
    if entry_day:
        entry = money(bar.open)
        if entry <= stop:
            return replace(
                trade, state="skipped", reason="skip_invalid_entry", last_session=session
            )
        risk = entry - stop
        target = (
            entry + trade.experiment.exit.target_r * risk
            if trade.experiment.exit.mode == "fixed_rr"
            else None
        )
        events += (Event(session, "entry", entry, "assumed_next_open", observed_at, digest(bar)),)
        updated = replace(trade, entry=entry, initial_risk=risk, target=target)
    ma = None
    exit_config = trade.experiment.exit
    needs_ma = (
        exit_config.mode == "ma_close"
        and not (trade.pending_exit is not None and session >= trade.pending_exit and not entry_day)
        and money(bar.low) > stop
    )
    if needs_ma:
        if (
            not history
            or history[-1] != bar
            or any(b.session > session for b in history)
            or tuple(b.session for b in history) != calendar.between(history[0].session, session)
            or any(not b.valid() or b.volume == 0 for b in history)
        ):
            raise ValueError("complete_ma_history_required")
        closes = [b.close for b in history]
        values = (
            sma(closes, exit_config.period)
            if exit_config.ma_type == "SMA"
            else ema(closes, exit_config.period)
        )
        ma = values[-1] if len(values) >= exit_config.period else None
    decision = evaluate_exit(
        bar,
        stop,
        updated.target,
        exit_config,
        ma=ma,
        pending_ma=trade.pending_exit is not None and session >= trade.pending_exit,
        entry_day=entry_day,
    )
    base = replace(
        updated, state="open", reason=decision.reason, events=events, last_session=session
    )
    if decision.kind == "pending_ma":
        next_session = calendar.next(session)
        timely = observed_at < next_session.opens_at
        return replace(
            base,
            pending_exit=next_session.day,
            actionable=base.actionable and timely,
            events=events
            + (
                Event(
                    session,
                    "pending_exit",
                    None,
                    "ma_close_below" if timely else "late_model_only",
                    observed_at,
                    digest((bar, ma, exit_config)),
                    ma_value=money(ma),
                    ma_type=exit_config.ma_type,
                    ma_period=exit_config.period,
                ),
            ),
        )
    if decision.kind != "exit":
        return base
    costs = trade.experiment.costs
    entry = updated.entry
    risk = updated.initial_risk
    assert entry is not None and risk is not None and decision.price is not None

    def pnl(price: Decimal) -> Decimal:
        return (
            price
            - entry
            - (
                entry * (costs.buy_bps + costs.slippage_bps)
                + price * (costs.sell_bps + costs.slippage_bps)
            )
            / Decimal(10000)
        )

    net = pnl(decision.price)
    return replace(
        base,
        state="closed",
        pending_exit=None,
        net_pnl=net,
        realized_r=net / risk,
        alternate_r=pnl(decision.alternate_price) / risk
        if decision.alternate_price is not None
        else None,
        events=events
        + (
            Event(
                session,
                "exit",
                decision.price,
                decision.reason,
                observed_at,
                digest(bar),
                decision.alternate_price,
            ),
        ),
    )


@dataclass
class PaperBook:
    trades: dict[str, PaperTrade] = field(default_factory=dict)
    experiments: dict[str, str] = field(default_factory=dict)

    def add(self, signal: Signal, experiment: Experiment, calendar: Calendar) -> PaperTrade:
        prior = self.experiments.setdefault(experiment.id, experiment.config_hash)
        if prior != experiment.config_hash:
            raise ValueError("experiment_id_config_immutable")
        plan = create_plan(signal, experiment, calendar)
        if plan.id in self.trades:
            return self.trades[plan.id]
        # Reserve at plan creation. On replay also block a position closed on entry session.
        for other in self.trades.values():
            if (
                other.signal.ticker == signal.ticker
                and other.experiment.id == experiment.id
                and (
                    other.state in ("pending_entry", "open", "data_hold")
                    or (
                        other.state == "closed"
                        and other.last_session == signal.planned_entry_session
                    )
                )
            ):
                plan = replace(plan, state="skipped", reason="position_at_session_start")
                break
        self.trades[plan.id] = plan
        return plan


def event_to_dict(event: Event) -> dict:
    return {
        "session": event.session.isoformat(),
        "kind": event.kind,
        "price": str(event.price) if event.price is not None else None,
        "reason": event.reason,
        "observed_at": event.observed_at.isoformat(),
        "input_digest": event.input_digest,
        "alternate_price": str(event.alternate_price)
        if event.alternate_price is not None
        else None,
        "ma_value": str(event.ma_value) if event.ma_value is not None else None,
        "ma_type": event.ma_type,
        "ma_period": event.ma_period,
    }


def event_from_dict(data: dict) -> Event:
    return Event(
        session=date.fromisoformat(data["session"]),
        kind=data["kind"],
        price=Decimal(data["price"]) if data.get("price") is not None else None,
        reason=data["reason"],
        observed_at=datetime.fromisoformat(data["observed_at"]),
        input_digest=data["input_digest"],
        alternate_price=Decimal(data["alternate_price"])
        if data.get("alternate_price") is not None
        else None,
        ma_value=Decimal(data["ma_value"]) if data.get("ma_value") is not None else None,
        ma_type=data.get("ma_type"),
        ma_period=data.get("ma_period"),
    )


def experiment_to_dict(exp: Experiment) -> dict:
    return {
        "id": exp.id,
        "strategy": exp.strategy,
        "exit": {
            "mode": exp.exit.mode,
            "target_r": str(exp.exit.target_r) if exp.exit.target_r is not None else None,
            "ma_type": exp.exit.ma_type,
            "period": exp.exit.period,
            "version": exp.exit.version,
        },
        "costs": {
            "buy_bps": str(exp.costs.buy_bps),
            "sell_bps": str(exp.costs.sell_bps),
            "slippage_bps": str(exp.costs.slippage_bps),
            "status": exp.costs.status,
        },
        "activated_at": exp.activated_at.isoformat(),
    }


def experiment_from_dict(data: dict) -> Experiment:
    exit_data = data["exit"]
    exit_cfg = ExitConfig(
        mode=exit_data["mode"],
        target_r=Decimal(exit_data["target_r"]) if exit_data.get("target_r") is not None else None,
        ma_type=exit_data.get("ma_type"),
        period=exit_data.get("period"),
        version=exit_data.get("version", "v1"),
    )
    cost_data = data.get("costs", {})
    costs = Costs(
        buy_bps=Decimal(cost_data.get("buy_bps", "0")),
        sell_bps=Decimal(cost_data.get("sell_bps", "0")),
        slippage_bps=Decimal(cost_data.get("slippage_bps", "0")),
        status=cost_data.get("status", "unset"),
    )
    return Experiment(
        id=data["id"],
        strategy=data["strategy"],
        exit=exit_cfg,
        costs=costs,
        activated_at=datetime.fromisoformat(data["activated_at"]),
    )


def paper_trade_to_dict(trade: PaperTrade) -> dict:
    return {
        "id": trade.id,
        "signal": json.loads(canonical_json(trade.signal)),
        "experiment": experiment_to_dict(trade.experiment),
        "state": trade.state,
        "reason": trade.reason,
        "entry": str(trade.entry) if trade.entry is not None else None,
        "stop": str(trade.stop) if trade.stop is not None else None,
        "target": str(trade.target) if trade.target is not None else None,
        "initial_risk": str(trade.initial_risk) if trade.initial_risk is not None else None,
        "pending_exit": trade.pending_exit.isoformat() if trade.pending_exit is not None else None,
        "last_session": trade.last_session.isoformat() if trade.last_session is not None else None,
        "events": [event_to_dict(e) for e in trade.events],
        "net_pnl": str(trade.net_pnl) if trade.net_pnl is not None else None,
        "realized_r": str(trade.realized_r) if trade.realized_r is not None else None,
        "alternate_r": str(trade.alternate_r) if trade.alternate_r is not None else None,
        "actionable": trade.actionable,
    }


def paper_trade_from_dict(data: dict) -> PaperTrade:
    from .persistence import signal_from_snapshot

    signal = signal_from_snapshot(data["signal"])
    experiment = experiment_from_dict(data["experiment"])
    return PaperTrade(
        id=data["id"],
        signal=signal,
        experiment=experiment,
        state=data["state"],
        reason=data.get("reason", ""),
        entry=Decimal(data["entry"]) if data.get("entry") is not None else None,
        stop=Decimal(data["stop"]) if data.get("stop") is not None else None,
        target=Decimal(data["target"]) if data.get("target") is not None else None,
        initial_risk=Decimal(data["initial_risk"])
        if data.get("initial_risk") is not None
        else None,
        pending_exit=date.fromisoformat(data["pending_exit"])
        if data.get("pending_exit") is not None
        else None,
        last_session=date.fromisoformat(data["last_session"])
        if data.get("last_session") is not None
        else None,
        events=tuple(event_from_dict(e) for e in data.get("events", ())),
        net_pnl=Decimal(data["net_pnl"]) if data.get("net_pnl") is not None else None,
        realized_r=Decimal(data["realized_r"]) if data.get("realized_r") is not None else None,
        alternate_r=Decimal(data["alternate_r"]) if data.get("alternate_r") is not None else None,
        actionable=data.get("actionable", True),
    )


def paper_book_to_dict(book: PaperBook) -> dict:
    return {
        "experiments": dict(book.experiments),
        "trades": {k: paper_trade_to_dict(v) for k, v in book.trades.items()},
    }


def paper_book_from_dict(data: dict) -> PaperBook:
    trades = {k: paper_trade_from_dict(v) for k, v in data.get("trades", {}).items()}
    experiments = dict(data.get("experiments", {}))
    return PaperBook(trades=trades, experiments=experiments)


def step_paper_book(
    book: PaperBook,
    session: date,
    series_by_ticker: dict[str, Series],
    calendar: Calendar,
    observed_at: datetime,
) -> dict[str, PaperTrade]:
    """Steps eligible pending_entry, open, or data_hold trades on the session."""
    updated: dict[str, PaperTrade] = {}
    for key, trade in tuple(book.trades.items()):
        if trade.state in ("pending_entry", "open", "data_hold"):
            if trade.entry is None and trade.signal.planned_entry_session > session:
                continue
            series = series_by_ticker.get(trade.signal.ticker)
            if series is None or not series.bars:
                book.trades[key] = step(
                    trade, session, None, calendar, observed_at, data_valid=False
                )
                updated[key] = book.trades[key]
                continue
            matching_bars = [b for b in series.bars if b.session <= session]
            if not matching_bars or matching_bars[-1].session != session:
                book.trades[key] = step(
                    trade, session, None, calendar, observed_at, data_valid=False
                )
                updated[key] = book.trades[key]
                continue
            book.trades[key] = step(
                trade,
                session,
                matching_bars[-1],
                calendar,
                observed_at,
                history=tuple(matching_bars),
                data_valid=series.actions_complete,
            )
            updated[key] = book.trades[key]
    return updated


def summarize_book(book: PaperBook) -> dict:
    closed = sorted(
        (t for t in book.trades.values() if t.state == "closed"),
        key=lambda t: (t.last_session or date.min, t.id),
    )
    open_count = sum(
        t.state in ("open", "pending_entry", "data_hold") for t in book.trades.values()
    )
    ambiguous = sum(t.alternate_r is not None for t in closed)
    metrics = summarize(
        [t.realized_r for t in closed if t.realized_r is not None],
        open_count=open_count,
        ambiguous_count=ambiguous,
    )
    strategy_metrics = {
        strategy: summarize(
            [
                t.realized_r
                for t in closed
                if t.signal.candidate.strategy == strategy and t.realized_r is not None
            ],
            open_count=sum(
                t.state in ("open", "pending_entry", "data_hold")
                and t.signal.candidate.strategy == strategy
                for t in book.trades.values()
            ),
            ambiguous_count=sum(
                t.alternate_r is not None and t.signal.candidate.strategy == strategy
                for t in closed
            ),
        )
        for strategy in STRATEGIES
    }
    return {
        "metrics": metrics,
        "strategy_metrics": strategy_metrics,
        "trades_count": len(book.trades),
        "closed_count": len(closed),
        "open_count": open_count,
    }
