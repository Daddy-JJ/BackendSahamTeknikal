"""Immutable data contracts. Dates are exchange sessions; audit instants are UTC."""

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from math import isfinite
from typing import Literal

ProviderName = Literal["fixture", "yfinance", "eodhd"]


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(type(value).__name__)


def canonical_json(value) -> str:
    return json.dumps(
        value, default=_json_default, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value) -> str:
    return sha256(canonical_json(value).encode()).hexdigest()


@dataclass(frozen=True)
class Bar:
    session: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    adjusted_close: float | None = None

    def valid(self) -> bool:
        values = (self.open, self.high, self.low, self.close, self.volume)
        return (
            all(isfinite(x) for x in values)
            and min(values[:4]) > 0
            and self.volume >= 0
            and self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high
            and (
                self.adjusted_close is None
                or (isfinite(self.adjusted_close) and self.adjusted_close > 0)
            )
        )


@dataclass(frozen=True)
class CorporateAction:
    session: date
    kind: Literal["split", "dividend"]
    value: str


@dataclass(frozen=True)
class ProviderRowIssue:
    session: date
    code: str
    observed_values: tuple[tuple[str, float | None], ...]


@dataclass(frozen=True)
class Series:
    ticker: str
    provider_symbol: str
    provider: ProviderName
    price_basis: str
    bars: tuple[Bar, ...]
    actions: tuple[CorporateAction, ...] = ()
    actions_complete: bool = True
    reconciled_actions: tuple[str, ...] = ()
    provider_version: str = "fixture-v1"
    fetched_at: datetime | None = None
    provider_missing_sessions: tuple[date, ...] = ()
    provider_row_issues: tuple[ProviderRowIssue, ...] = ()
    # Canonical JSON audit records; empty preserves legacy input/replay identities.
    provenance: tuple[str, ...] = ()

    @property
    def input_digest(self) -> str:
        # A retry at a different time must not change identity. Content and basis do.
        content = {
            "ticker": self.ticker,
            "provider": self.provider,
            "symbol": self.provider_symbol,
            "basis": self.price_basis,
            "bars": self.bars,
            "actions": self.actions,
            "reconciled": self.reconciled_actions,
            "actions_complete": self.actions_complete,
            "provider_missing_sessions": self.provider_missing_sessions,
            "provider_row_issues": self.provider_row_issues,
        }
        if self.provenance:
            content["provenance"] = self.provenance
        return digest(content)


@dataclass(frozen=True)
class EntryConfig:
    definition: str = "v1"
    min_history: int = 600
    pivot_left: int = 2
    pivot_right: int = 2
    swing_lookback: int = 60

    def __post_init__(self):
        # V1 rules are fixed. Experiments must introduce a named version, not mutate V1.
        if (
            self.definition,
            self.min_history,
            self.pivot_left,
            self.pivot_right,
            self.swing_lookback,
        ) != ("v1", 600, 2, 2, 60):
            raise ValueError("V1 entry parameters are immutable; define a new strategy version")


DEFAULT_ENTRY_CONFIG = EntryConfig()


@dataclass(frozen=True)
class ExitConfig:
    mode: Literal["fixed_rr", "ma_close"] = "fixed_rr"
    target_r: Decimal | None = Decimal("2")
    ma_type: Literal["SMA", "EMA"] | None = None
    period: int | None = None
    version: str = "v1"

    def __post_init__(self):
        if self.mode == "fixed_rr":
            if (
                not isinstance(self.target_r, Decimal)
                or not self.target_r.is_finite()
                or self.target_r <= 0
                or self.ma_type is not None
                or self.period is not None
            ):
                raise ValueError("fixed_rr requires finite positive Decimal target_r only")
        elif self.mode == "ma_close":
            if (
                self.target_r is not None
                or self.ma_type not in ("SMA", "EMA")
                or self.period not in (5, 10, 20)
            ):
                raise ValueError("ma_close requires null target_r, SMA/EMA and period 5/10/20")
        else:
            raise ValueError("Unknown exit mode")

    @property
    def config_hash(self) -> str:
        return digest(self)


@dataclass(frozen=True)
class Costs:
    buy_bps: Decimal = Decimal("0")
    sell_bps: Decimal = Decimal("0")
    slippage_bps: Decimal = Decimal("0")
    status: Literal["unset", "provisional", "verified"] = "unset"

    def __post_init__(self):
        if self.status not in ("unset", "provisional", "verified"):
            raise ValueError("Invalid cost status")
        if any(
            not isinstance(x, Decimal) or not x.is_finite() or x < 0
            for x in (self.buy_bps, self.sell_bps, self.slippage_bps)
        ):
            raise ValueError("Costs must be finite nonnegative Decimal bps")

        if self.status == "unset" and any((self.buy_bps, self.sell_bps, self.slippage_bps)):
            raise ValueError("Unset costs require zero-cost assumption")

    @property
    def label(self) -> str:
        if self.status == "unset":
            return "GROSS / ZERO-COST ASSUMPTION"
        return "NET VERIFIED" if self.status == "verified" else "NET ESTIMATED"


@dataclass(frozen=True)
class Rule:
    name: str
    passed: bool


@dataclass(frozen=True)
class Candidate:
    strategy: str
    triggered: bool
    stop: float | None
    reference_close: float
    rules: tuple[Rule, ...]
    reason: str
    level: float | None = None
    fractal_id: str | None = None
    pivot_date: date | None = None
    available_session: date | None = None

    @property
    def execution_eligible(self) -> bool:
        return self.triggered and self.stop is not None and 0 < self.stop < self.reference_close


@dataclass(frozen=True)
class Signal:
    id: str
    ticker: str
    session: date
    candidate: Candidate
    config_hash: str
    input_digest: str
    universe_version: str
    provider: str
    price_basis: str
    published_at: datetime
    planned_entry_session: date
    cohort: Literal["forward", "late_model_only", "backtest"]
    data_mode: Literal["fixture", "live"]
    features: tuple[tuple[str, float | None], ...] = ()
    provider_version: str = "unspecified"
    calendar_version: str = "unspecified"
    engine_version: str = "0.1.0"
    source_revision: str = "local-uncommitted"


@dataclass
class ScanState:
    """In-memory M1 store; database adapter must provide the same atomic guarantees in M2."""

    signals: dict[str, Signal] = field(default_factory=dict)
    fractal_guards: set[str] = field(default_factory=set)
