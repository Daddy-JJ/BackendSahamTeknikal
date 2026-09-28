"""Provider IO boundary. No fallback, no indicators, no tokens in logs/errors."""

import os
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from importlib.metadata import version
from math import isfinite, isnan
from typing import Protocol

import httpx

from .models import Bar, CorporateAction, ProviderRowIssue, Series


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
            values = tuple(
                float(row[k]) if row[k] is not None else float("nan")
                for k in ("open", "high", "low", "close", "volume")
            )
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
                                ("open", "high", "low", "close", "volume"), values, strict=True
                            )
                        ),
                    )
                )
                continue
            bar = Bar(
                session,
                *values,
                float(row["adjusted_close"]) if row.get("adjusted_close") is not None else None,
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

    def fetch(self, request: FetchRequest) -> Series:
        import yfinance as yf

        loader = self.download or yf.download
        frame = None
        for attempt in range(3):
            try:
                frame = loader(
                    request.symbol,
                    start=request.start.isoformat(),
                    end=(request.end + timedelta(days=1)).isoformat(),
                    interval="1d",
                    auto_adjust=False,
                    back_adjust=False,
                    actions=True,
                    repair=False,
                    keepna=True,
                    progress=False,
                    threads=False,
                    ignore_tz=True,
                    rounding=False,
                    timeout=20,
                    multi_level_index=False,
                )
                if frame is not None and not frame.empty:
                    break
            except Exception:
                # yfinance exceptions may contain transport details. Never serialize them.
                frame = None
            if attempt < 2:
                self.sleep(2**attempt + random.random())
        if frame is None or frame.empty:
            raise ProviderError("provider_empty_or_unavailable")
        rows, actions = [], []
        try:
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
