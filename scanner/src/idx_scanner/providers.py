"""Provider IO boundary. No fallback, no indicators, no tokens in logs/errors."""

import os
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from importlib.metadata import version
from math import isfinite, isnan
from typing import Protocol

import httpx
import pandas as pd

from .context import Calendar
from .models import Bar, CorporateAction, ProviderRowIssue, Series, canonical_json

SHORT_RANGE_RECOVERY_VERSION = "yahoo_daily_short_range_recovery_v1"
OHLCV_FIELDS = ("open", "high", "low", "close", "volume")


def _number(value) -> float:
    """Missing scalars have one representation; non-scalar/malformed values fail."""
    return float("nan") if value is None or pd.isna(value) else float(value)


class ProviderError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class FetchRequest:
    ticker: str
    symbol: str
    start: date
    end: date  # inclusive for both adapters
    mapping_verified: bool

    def __post_init__(self):
        if (
            not self.mapping_verified
            or not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^_-]{0,39}", self.symbol)
            or not re.fullmatch(r"[A-Z0-9_-]{1,20}", self.ticker)
            or self.end < self.start
        ):
            raise ValueError("Explicit verified symbol mapping and valid date range required")


class Provider(Protocol):
    def fetch(self, request: FetchRequest) -> Series: ...


def _normalized(
    request: FetchRequest,
    rows: list[dict],
    actions: tuple[CorporateAction, ...],
    provider: str,
    basis: str,
    provider_version: str,
) -> Series:
    try:
        bars, missing, issues, seen = [], [], [], set()
        for row in rows:
            session = date.fromisoformat(str(row["date"])[:10])
            if session in seen or not request.start <= session <= request.end:
                raise ValueError()
            seen.add(session)
            values = tuple(_number(row[k]) for k in OHLCV_FIELDS)
            if any(isnan(v) for v in values):
                if any(not isfinite(v) and not isnan(v) for v in values):
                    raise ValueError()
                empty = all(isnan(v) for v in values[:4]) and (isnan(values[4]) or values[4] == 0)
                if empty:
                    missing.append(session)
                issues.append(
                    ProviderRowIssue(
                        session,
                        "missing_ohlcv" if empty else "incomplete_ohlcv",
                        tuple(
                            (key, None if isnan(value) else value)
                            for key, value in zip(
                                 OHLCV_FIELDS, values, strict=True
                            )
                        ),
                    )
                )
                continue
            adjusted = _number(row.get("adjusted_close"))
            bar = Bar(
                session,
                *values,
                None if isnan(adjusted) else adjusted,
            )
            if not bar.valid():
                raise ValueError()
            bars.append(bar)
        return Series(
            request.ticker,
            request.symbol,
            provider,
            basis,
            tuple(sorted(bars, key=lambda b: b.session)),
            actions,
            provider_version=provider_version,
            fetched_at=datetime.now(UTC),
            provider_missing_sessions=tuple(sorted(missing)),
            provider_row_issues=tuple(sorted(issues, key=lambda issue: issue.session)),
        )
    except (ValueError, TypeError, KeyError, OverflowError):
        raise ProviderError("invalid_provider_payload") from None


@dataclass
class YFinanceProvider:
    download: Callable | None = field(default=None, repr=False)
    sleep: Callable[[float], None] = field(default=time.sleep, repr=False)
    # Diagnostics are intentionally outside market content identity. Fetch time
    # and retry count must not create a new signal from identical final OHLC.
    fetch_diagnostics: dict[str, tuple[dict, ...]] = field(default_factory=dict, repr=False)
    calendar: Calendar | None = field(default=None, repr=False)
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC), repr=False)
    max_requests: int = 500
    max_elapsed_seconds: float = 1200
    request_interval_seconds: float = 0.2
    monotonic: Callable[[], float] = field(default=time.monotonic, repr=False)
    # Original rejected captures and short-range receipts are separate revisions.
    # The runner persists these before the recovered series, including on rejection.
    raw_recovery_captures: dict[str, tuple[Series, ...]] = field(default_factory=dict, repr=False)
    _request_count: int = field(default=0, init=False, repr=False)
    _started_at: float | None = field(default=None, init=False, repr=False)
    _last_request_at: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        if (type(self.max_requests) is not int or self.max_requests < 1
            or not isfinite(self.max_elapsed_seconds) or self.max_elapsed_seconds <= 0
            or not isfinite(self.request_interval_seconds) or self.request_interval_seconds < 0):
            raise ValueError("invalid_provider_budget")

    def _load(self, loader, request: FetchRequest, *, period: str | None = None):
        now = self.monotonic()
        if self._started_at is None:
            self._started_at = now
        if (self._request_count >= self.max_requests
            or now - self._started_at >= self.max_elapsed_seconds):
            raise ProviderError("provider_request_budget_exhausted")
        # Legacy/offline calls keep their existing timing. Verified live runs pace
        # the entire instance, so the 100-ticker scan cannot burst each new ticker.
        if self.calendar is not None and self._last_request_at is not None:
            remaining = self.request_interval_seconds - (now - self._last_request_at)
            if remaining > 0:
                self.sleep(remaining)
        now = self.monotonic()
        remaining = self.max_elapsed_seconds - (now - self._started_at)
        if remaining <= 0:
            raise ProviderError("provider_request_budget_exhausted")
        self._request_count += 1
        self._last_request_at = now
        options = {"interval": "1d", "auto_adjust": False, "back_adjust": False,
                   "actions": True, "repair": False, "keepna": True, "progress": False,
                   "threads": False, "ignore_tz": True, "rounding": False,
                   "timeout": min(20, remaining), "multi_level_index": False}
        if period is None:
            options.update(start=request.start.isoformat(),
                           end=(request.end + timedelta(days=1)).isoformat())
        else:
            options["period"] = period
        return loader(request.symbol, **options)

    def _retain(self, request: FetchRequest, series: Series):
        old = self.raw_recovery_captures[request.ticker]
        if all(s.input_digest != series.input_digest for s in old):
            self.raw_recovery_captures[request.ticker] = (*old, series)

    @staticmethod
    def _close_gaps(series: Series) -> tuple[ProviderRowIssue, ...]:
        return tuple(issue for issue in series.provider_row_issues
                     if issue.code == "incomplete_ohlcv"
                     and dict(issue.observed_values).get("close", "unknown") is None
                     and all(dict(issue.observed_values).get(key) is not None
                             for key in ("open", "high", "low", "volume")))

    def _closed_recovery_allowed(self, request: FetchRequest) -> bool:
        if self.calendar is None or self.calendar.data_mode != "live":
            return False
        now = self.clock()
        if now.tzinfo is None:
            return False
        try:
            return now >= self.calendar.get(request.end).closes_at
        except ValueError:
            return False

    @staticmethod
    def _recovery_metadata_matches(frame, request: FetchRequest) -> bool:
        # yfinance's explicit download flags are the basis contract. If a receipt
        # supplies contradictory metadata, never ignore it to force eligibility.
        expected = {"provider": "yfinance", "provider_symbol": request.symbol,
                    "price_basis": "yahoo_provider_ohlcv_auto_adjust_false_v1",
                    "interval": "1d", "dataGranularity": "1d"}
        if request.symbol.endswith(".JK"):
            expected.update(currency="IDR", exchangeTimezoneName="Asia/Jakarta")
        return all(key not in frame.attrs or frame.attrs[key] == value
                   for key, value in expected.items())

    def _merge_recovery(self, original: Series, receipt: Series, request: FetchRequest,
                        profile: str) -> Series:
        if ((receipt.provider, receipt.provider_symbol, receipt.price_basis,
             receipt.provider_version) != (original.provider, original.provider_symbol,
             original.price_basis, original.provider_version)
            or not original.actions_complete or not receipt.actions_complete):
            raise ProviderError("recovery_basis_or_actions_mismatch")
        if not receipt.bars or any(b.session > request.end for b in receipt.bars):
            raise ProviderError("recovery_wrong_session")
        if receipt.provider_row_issues or receipt.provider_missing_sessions:
            raise ProviderError("recovery_incomplete_daily_bar")
        incoming = {bar.session: bar for bar in receipt.bars}
        if request.end not in incoming:
            raise ProviderError("recovery_wrong_session")
        gaps = self._close_gaps(original)
        if not gaps or any(issue.session not in incoming for issue in gaps):
            raise ProviderError("recovery_required_session_missing")
        old_bars = {bar.session: bar for bar in original.bars}
        issues = {issue.session: dict(issue.observed_values)
                  for issue in original.provider_row_issues}
        for day, bar in incoming.items():
            if not bar.valid():
                raise ProviderError("recovery_invalid_daily_bar")
            known = ({key: getattr(old_bars[day], key) for key in OHLCV_FIELDS}
                     if day in old_bars else issues.get(day))
            if known is None or any(known.get(key) is not None
                                    and known[key] != getattr(bar, key)
                                    for key in OHLCV_FIELDS):
                raise ProviderError("recovery_overlap_conflict")
        covered = set(incoming)
        original_splits = tuple(a for a in original.actions
                                if a.session in covered and a.kind != "dividend")
        receipt_splits = tuple(a for a in receipt.actions
                               if a.session in covered and a.kind != "dividend")
        if original_splits != receipt_splits:
            raise ProviderError("recovery_actions_mismatch")
        repaired = {issue.session for issue in gaps}
        if any(incoming[day].volume <= 0 for day in repaired):
            raise ProviderError("recovery_invalid_daily_bar")
        dividends_changed = (tuple(a for a in original.actions
                                   if a.session in covered and a.kind == "dividend")
                             != tuple(a for a in receipt.actions
                                      if a.session in covered and a.kind == "dividend"))
        record = canonical_json({"kind": SHORT_RANGE_RECOVERY_VERSION, "status": "recovered",
                                 "target_session": request.end.isoformat(),
                                 "original_input_digest": original.input_digest,
                                 "recovery_input_digest": receipt.input_digest,
                                 "request_profile": profile,
                                 "calendar_version": self.calendar.version,
                                 "price_basis": original.price_basis,
                                 "replaced_sessions": sorted(day.isoformat() for day in repaired),
                                 "matched_fields": list(OHLCV_FIELDS),
                                 "cash_dividend_metadata_disagreement": dividends_changed})
        # Use the actual observed daily bar. Never synthesize its Close, alter
        # historical bars, or credit cash-dividend metadata to a trading ledger.
        bars = {**old_bars, **{day: incoming[day] for day in repaired}}
        return replace(original, bars=tuple(bars[day] for day in sorted(bars)),
                       provider_row_issues=tuple(issue for issue in original.provider_row_issues
                                                if issue.session not in repaired),
                       fetched_at=receipt.fetched_at, provenance=(*original.provenance, record))

    def _recover(self, loader, request: FetchRequest, original: Series, attempts: list[dict]):
        if not self._close_gaps(original) or not self._closed_recovery_allowed(request):
            return original
        for period in ("1d", "5d"):
            profile = "period_" + period
            diagnostic = {"attempt": len(attempts) + 1, "request_profile": profile,
                          "fetched_at": self.clock().isoformat(), "retryable": False}
            try:
                frame = self._load(loader, request, period=period)
                if frame is None or frame.empty:
                    raise ProviderError("recovery_empty")
                if not self._recovery_metadata_matches(frame, request):
                    raise ProviderError("recovery_basis_or_granularity_mismatch")
                dates = [index.date() for index in frame.index]
                # Preserve a wrong/future short-range receipt as evidence, but
                # the merge gate prohibits it from affecting the target session.
                capture_request = replace(request, start=min(dates), end=max(dates))
                raw_receipt = self._normalize_frame(capture_request, frame)
                self._retain(request, raw_receipt)
                # Period queries may include today's still-open bar while
                # catching up yesterday. Preserve the raw receipt separately;
                # only its exact closed historical prefix can influence data
                # content, recovery matching or the derived input digest.
                receipt = replace(raw_receipt,
                    bars=tuple(b for b in raw_receipt.bars if b.session <= request.end),
                    actions=tuple(a for a in raw_receipt.actions if a.session <= request.end),
                    provider_row_issues=tuple(i for i in raw_receipt.provider_row_issues
                                             if i.session <= request.end),
                    provider_missing_sessions=tuple(d for d in raw_receipt.provider_missing_sessions
                                                    if d <= request.end))
                self._retain(request, receipt)
                diagnostic["input_digest"] = receipt.input_digest
                recovered = self._merge_recovery(original, receipt, request, profile)
            except ProviderError as exc:
                diagnostic["status"] = exc.code
            except Exception:
                diagnostic["status"] = "recovery_transport_or_payload_error"
            else:
                diagnostic.update(status="daily_close_recovered", recovery_status="recovered",
                                  recovered_input_digest=recovered.input_digest)
                attempts.append(diagnostic)
                self.fetch_diagnostics[request.ticker] = tuple(attempts)
                return recovered
            attempts.append(diagnostic)
            self.fetch_diagnostics[request.ticker] = tuple(attempts)
            if diagnostic["status"] == "provider_request_budget_exhausted":
                break
        return original

    def fetch(self, request: FetchRequest) -> Series:
        import yfinance as yf

        loader = self.download or yf.download
        attempts = []
        self.fetch_diagnostics[request.ticker] = ()
        self.raw_recovery_captures[request.ticker] = ()
        for attempt in range(3):
            fetched_at = datetime.now(UTC).isoformat()
            try:
                frame = self._load(loader, request)
            except ProviderError as exc:
                attempts.append({"attempt": attempt + 1, "status": exc.code,
                                 "fetched_at": fetched_at, "retryable": False})
                self.fetch_diagnostics[request.ticker] = tuple(attempts)
                raise
            except Exception:
                # yfinance exceptions may contain transport details. Never serialize them.
                frame = None
                status = "transport_error"
            else:
                status = "provider_empty" if frame is None or frame.empty else "received"
            result = None
            if frame is not None and not frame.empty:
                try:
                    result = self._normalize_frame(request, frame)
                except ProviderError as exc:
                    attempts.append({"attempt": attempt + 1, "status": exc.code,
                                     "fetched_at": fetched_at, "retryable": False})
                    self.fetch_diagnostics[request.ticker] = tuple(attempts)
                    raise
                retryable = any(i.session <= request.end and i.code in (
                    "incomplete_ohlcv", "missing_ohlcv"
                ) for i in result.provider_row_issues)
                target_incomplete = any(i.session == request.end
                                        for i in result.provider_row_issues)
                status = ("target_bar_incomplete" if target_incomplete else
                          "history_bar_incomplete") if retryable else (
                    "valid_target_received"
                    if result.bars and result.bars[-1].session == request.end
                    else "target_bar_absent_or_stale"
                )
                if retryable:
                    self._retain(request, result)
            else:
                retryable = True
            diagnostic = {"attempt": attempt + 1, "status": status,
                          "fetched_at": fetched_at, "retryable": retryable}
            if result is not None:
                diagnostic["input_digest"] = result.input_digest
            attempts.append(diagnostic)
            self.fetch_diagnostics[request.ticker] = tuple(attempts)
            if result is not None and (not retryable or attempt == 2):
                # An exhausted incomplete capture remains incomplete. The quality
                # gate decides hold/failure; never substitute an earlier capture.
                return self._recover(loader, request, result, attempts)
            if attempt < 2:
                self.sleep(2**attempt + random.random())
        raise ProviderError("provider_empty_or_unavailable")

    @staticmethod
    def _normalize_frame(request: FetchRequest, frame) -> Series:
        rows, actions = [], []
        try:
            if not YFinanceProvider._recovery_metadata_matches(frame, request):
                raise ProviderError("provider_basis_or_granularity_mismatch")
            if "Dividends" not in frame.columns or "Stock Splits" not in frame.columns:
                raise ProviderError("corporate_actions_unknown")
            for index, row in frame.iterrows():
                session = index.date()
                rows.append(
                    {
                        "date": session.isoformat(),
                        **{
                            key.lower(): row[key]
                            for key in ("Open", "High", "Low", "Close", "Volume")
                        },
                        "adjusted_close": row.get("Adj Close"),
                    }
                )
                for column, kind in (("Dividends", "dividend"), ("Stock Splits", "split")):
                    value = float(row[column])
                    if not isfinite(value) or value < 0:
                        raise ProviderError("corporate_actions_unknown")
                    if value:
                        actions.append(CorporateAction(session, kind, str(value)))
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ProviderError("invalid_provider_payload") from None
        return _normalized(
            request,
            rows,
            tuple(actions),
            "yfinance",
            "yahoo_provider_ohlcv_auto_adjust_false_v1",
            version("yfinance"),
        )


@dataclass
class EODHDProvider:
    token: str = field(repr=False)
    client: httpx.Client = field(repr=False)
    sleep: Callable[[float], None] = field(default=time.sleep, repr=False)

    def __post_init__(self):
        if not self.token or self.token.lower() == "demo":
            raise ProviderError("eodhd_credentials_missing")

    def _get(self, endpoint: str, request: FetchRequest) -> list[dict]:
        params = {
            "api_token": self.token,
            "fmt": "json",
            "from": request.start.isoformat(),
            "to": request.end.isoformat(),
        }
        if endpoint == "eod":
            params.update(period="d", order="a")
        for attempt in range(3):
            try:
                response = self.client.get(
                    f"https://eodhd.com/api/{endpoint}/{request.symbol}",
                    params=params,
                    timeout=20,
                    follow_redirects=False,
                )
            except httpx.TransportError:
                if attempt == 2:
                    raise ProviderError("provider_unavailable") from None
            else:
                if response.status_code in (401, 403):
                    raise ProviderError("provider_auth_or_entitlement_denied")
                if response.status_code == 404:
                    raise ProviderError("provider_symbol_not_found")
                if response.status_code == 200:
                    try:
                        payload = response.json()
                        if not isinstance(payload, list) or any(
                            not isinstance(r, dict) for r in payload
                        ):
                            raise ValueError()
                        return payload
                    except (ValueError, TypeError):
                        raise ProviderError("invalid_provider_payload") from None
                if response.status_code != 429 and response.status_code < 500:
                    raise ProviderError("provider_request_rejected")
                if attempt == 2:
                    raise ProviderError(
                        "provider_rate_limited"
                        if response.status_code == 429
                        else "provider_unavailable"
                    )
            self.sleep(2**attempt + random.random())
        raise ProviderError("provider_unavailable")

    def fetch(self, request: FetchRequest) -> Series:
        rows = self._get("eod", request)
        if not rows:
            raise ProviderError("provider_empty")
        actions = []
        try:
            for endpoint, kind, key in (
                ("splits", "split", "split"),
                ("div", "dividend", "unadjustedValue"),
            ):
                for row in self._get(endpoint, request):
                    session = date.fromisoformat(row["date"])
                    value = row[key]
                    if not request.start <= session <= request.end or value is None:
                        raise ValueError()
                    actions.append(CorporateAction(session, kind, str(value)))
        except (KeyError, TypeError, ValueError):
            raise ProviderError("corporate_actions_unknown") from None
        return _normalized(
            request, rows, tuple(actions), "eodhd", "eodhd_unadjusted_ohlc_v1", "rest-v1"
        )


def make_provider(name: str, client: httpx.Client | None = None) -> Provider:
    if name == "yfinance":
        return YFinanceProvider()
    if name == "eodhd":
        if client is None:
            raise ValueError("A context-managed HTTP client is required")
        return EODHDProvider(os.environ.get("EODHD_API_TOKEN", ""), client)
    raise ValueError("Explicit provider must be yfinance or eodhd; no automatic fallback")
