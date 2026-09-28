"""Deterministic cross-section scan; provider IO is outside this module."""

from dataclasses import dataclass, replace
from datetime import date, datetime

from .context import Calendar, Universe, quality
from .indicators import calculate
from .models import DEFAULT_ENTRY_CONFIG, Candidate, EntryConfig, ScanState, Series, Signal, digest
from .strategies import Ranking, evaluate, rank_returns


@dataclass(frozen=True)
class ScanItem:
    ticker: str
    status: str
    candidates: tuple[Candidate, ...]


@dataclass(frozen=True)
class ScanResult:
    session: date
    status: str
    coverage_valid: int
    coverage_total: int
    ranking: Ranking
    items: tuple[ScanItem, ...]
    signals: tuple[Signal, ...]
    run_digest: str


def scan(
    series: dict[str, Series],
    target: date,
    calendar: Calendar,
    universe: Universe,
    published_at: datetime,
    state: ScanState,
    config: EntryConfig = DEFAULT_ENTRY_CONFIG,
    *,
    namespace: str = "forward",
) -> ScanResult:
    universe.require(target)
    current, next_session = calendar.get(target), calendar.next(target)
    if published_at.tzinfo is None or published_at < current.closes_at:
        raise ValueError("target_session_not_closed")
    if calendar.data_mode != universe.data_mode:
        raise ValueError("mixed_fixture_live_context")
    selected: dict[str, Series] = {}
    for ticker in universe.tickers:
        if ticker in series:
            s = series[ticker]
            if s.ticker != ticker:
                raise ValueError("ticker_mapping_mismatch")
            if (s.provider == "fixture") != (universe.data_mode == "fixture"):
                raise ValueError("mixed_fixture_live_data")
            selected[ticker] = replace(
                s,
                bars=tuple(b for b in s.bars if b.session <= target),
                actions=tuple(a for a in s.actions if a.session <= target),
                provider_row_issues=tuple(i for i in s.provider_row_issues if i.session <= target),
                provider_missing_sessions=tuple(
                    d for d in s.provider_missing_sessions if d <= target
                ),
                reconciled_actions=tuple(
                    digest(a)
                    for a in s.actions
                    if a.session <= target and digest(a) in s.reconciled_actions
                ),
            )
    bases = {(s.provider, s.price_basis) for s in selected.values()}
    if len(bases) > 1:
        raise ValueError("mixed_provider_or_price_basis")
    statuses = {
        t: quality(selected[t], target, calendar) if t in selected else "missing"
        for t in universe.tickers
    }
    hashes = {t: s.input_digest for t, s in selected.items()}
    snapshot_digest = digest(hashes)
    returns, excluded = {}, []
    for t, s in selected.items():
        if statuses[t] == "valid":
            if len(s.bars) >= 61:
                returns[t] = s.bars[-1].close / s.bars[-61].close - 1
            else:
                excluded.append(t)
    ranking = rank_returns(returns, universe.tickers, tuple(excluded), snapshot_digest)
    emitted, items = [], []
    for ticker in sorted(universe.tickers):
        if statuses[ticker] != "valid":
            items.append(ScanItem(ticker, statuses[ticker], ()))
            continue
        s = selected[ticker]
        features = calculate(s.bars)
        candidates = evaluate(ticker, s.bars, features, ranking, config)
        items.append(ScanItem(ticker, "evaluated", candidates))
        config_hash = digest((config, s.provider, s.price_basis, "effective-universe-v1"))
        for candidate in candidates:
            if not candidate.triggered:
                continue
            identity = digest(
                (namespace, candidate.strategy, config_hash, universe.version, ticker, target)
            )
            guard = digest(
                (namespace, candidate.strategy, config_hash, ticker, candidate.fractal_id)
            )
            # Immutable published snapshot: provider revision cannot silently replace it.
            if identity in state.signals:
                emitted.append(state.signals[identity])
                continue
            if candidate.fractal_id and guard in state.fractal_guards:
                continue
            cohort = (
                "backtest"
                if namespace != "forward"
                else "forward"
                if published_at < next_session.opens_at
                else "late_model_only"
            )
            signal = Signal(
                identity,
                ticker,
                target,
                candidate,
                config_hash,
                s.input_digest,
                universe.version,
                s.provider,
                s.price_basis,
                published_at,
                next_session.day,
                cohort,
                universe.data_mode,
                features.snapshot(),
                provider_version=s.provider_version,
                calendar_version=calendar.version,
            )
            state.signals[identity] = signal
            if candidate.fractal_id:
                state.fractal_guards.add(guard)
            emitted.append(signal)
    valid = sum(v == "valid" for v in statuses.values())
    status = "complete" if valid == len(universe.tickers) else "partial" if valid else "failed"
    return ScanResult(
        target,
        status,
        valid,
        len(universe.tickers),
        ranking,
        tuple(items),
        tuple(emitted),
        digest((target, config, hashes, statuses, namespace)),
    )
