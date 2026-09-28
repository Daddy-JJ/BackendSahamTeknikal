"""Trade-level EOD forward simulation, not a capital-constrained portfolio."""

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal

from .context import Calendar
from .exits import evaluate_exit, money
from .indicators import ema, sma
from .models import Bar, Costs, ExitConfig, Signal, digest


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
