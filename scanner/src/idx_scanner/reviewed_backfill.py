"""Explicit reviewed Yahoo historical receipts for paper recovery, never scanner fallback.

Reference hashes attest to an operator's prior review; this module does not claim
to independently verify a document or declare an unreviewed provider correct.
"""
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from urllib.parse import urlsplit

from .context import quality
from .models import Series, canonical_json, digest
from .providers import OHLCV_FIELDS, FetchRequest, ProviderError

BACKFILL_VERSION = "reviewed_historical_backfill_v1"
YAHOO_BASIS = "yahoo_provider_ohlcv_auto_adjust_false_v1"
_HASH = re.compile(r"[a-f0-9]{64}")


def _hash(value):
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _aware(value):
    return (isinstance(value, datetime) and value.tzinfo is not None
            and value.utcoffset() is not None)


@dataclass(frozen=True)
class IndependentReference:
    source_url: str
    document_sha256: str
    reviewed_at: datetime

    def __post_init__(self):
        if not isinstance(self.source_url, str) or not _hash(self.document_sha256):
            raise ValueError("invalid_reviewed_backfill_manifest")
        url = urlsplit(self.source_url)
        host = url.hostname or ""
        same_provider = any(host == name or host.endswith("." + name)
                            for name in ("yahoo.com", "yahoo.net", "yimg.com", "yfapi.net"))
        if (url.scheme != "https" or not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", host)
            or url.username is not None or url.password is not None
            or url.port not in (None, 443) or url.query or url.fragment or same_provider
            or self.source_url != self.source_url.strip()
            or any(ord(character) < 32 for character in self.source_url)
            or not _aware(self.reviewed_at)):
            raise ValueError("invalid_reviewed_backfill_manifest")


@dataclass(frozen=True)
class ReviewedBackfill:
    ticker: str
    provider_symbol: str
    session: date
    provider: str
    price_basis: str
    provider_version: str
    source_input_digest: str
    reference: IndependentReference

    def __post_init__(self):
        if (not isinstance(self.ticker, str)
            or not re.fullmatch(r"[A-Z0-9_-]{1,20}", self.ticker)
            or not isinstance(self.provider_symbol, str)
            or not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^_-]{0,39}", self.provider_symbol)
            or type(self.session) is not date or self.provider != "yfinance"
            or self.price_basis != YAHOO_BASIS or not isinstance(self.provider_version, str)
            or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", self.provider_version)
            or not _hash(self.source_input_digest)
            or not isinstance(self.reference, IndependentReference)):
            raise ValueError("invalid_reviewed_backfill_manifest")


def parse_reviewed_backfill_manifest(payload) -> tuple[ReviewedBackfill, ...]:
    """Strict, immutable allowlist. An empty live manifest grants no recovery rights."""
    fields = set(ReviewedBackfill.__dataclass_fields__)
    references = set(IndependentReference.__dataclass_fields__)
    try:
        if (type(payload) is not dict or set(payload) != {"version", "data_mode", "records"}
            or payload["version"] != BACKFILL_VERSION or payload["data_mode"] != "live"
            or type(payload["records"]) is not list or len(payload["records"]) > 100):
            raise ValueError()
        result = []
        for record in payload["records"]:
            if (type(record) is not dict or set(record) != fields
                or type(record["reference"]) is not dict
                or set(record["reference"]) != references):
                raise ValueError()
            reference = record["reference"]
            value = ReviewedBackfill(**{**record,
                "session": date.fromisoformat(record["session"]),
                "reference": IndependentReference(**{**reference,
                    "reviewed_at": datetime.fromisoformat(reference["reviewed_at"])}),
            })
            if record["session"] != value.session.isoformat():
                raise ValueError()
            result = [*result, value]
        if len({(value.ticker, value.session) for value in result}) != len(result):
            raise ValueError()
        return tuple(sorted(result, key=lambda value: (value.ticker, value.session)))
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
        raise ValueError("invalid_reviewed_backfill_manifest") from None


def _needs_receipt(series: Series, session: date) -> bool:
    bar = next((bar for bar in series.bars if bar.session == session), None)
    return (bar is None or not bar.valid() or session in series.provider_missing_sessions
            or any(issue.session == session for issue in series.provider_row_issues))


def _identity(series, record):
    return (series.ticker, series.provider_symbol, series.provider, series.price_basis,
            series.provider_version) == (record.ticker, record.provider_symbol, record.provider,
                                       record.price_basis, record.provider_version)


def _price_actions(series, start, end):
    return tuple(action for action in series.actions
                 if start <= action.session <= end and action.kind != "dividend")


def _future_content(series, end):
    return (any(bar.session > end for bar in series.bars)
            or any(action.session > end for action in series.actions)
            or any(issue.session > end for issue in series.provider_row_issues)
            or any(day > end for day in series.provider_missing_sessions))


def _known_fields_agree(fresh, archived):
    incoming = {bar.session: bar for bar in archived.bars}
    for bar in fresh.bars:
        if bar.session in incoming and (not bar.valid() or any(
            getattr(bar, key) != getattr(incoming[bar.session], key) for key in OHLCV_FIELDS)):
            raise ProviderError("reviewed_backfill_overlap_conflict")
    for issue in fresh.provider_row_issues:
        if issue.session not in incoming:
            continue
        values = dict(issue.observed_values)
        if len(values) != len(issue.observed_values) or set(values) - set(OHLCV_FIELDS):
            raise ProviderError("reviewed_backfill_invalid_known_fields")
        if any(value is not None and value != getattr(incoming[issue.session], key)
               for key, value in values.items()):
            raise ProviderError("reviewed_backfill_overlap_conflict")


def _merge(fresh, archived, record, manifest_digest):
    if any(issue.session == record.session and issue.code not in (
        "missing_ohlcv", "incomplete_ohlcv") for issue in fresh.provider_row_issues):
        raise ProviderError("reviewed_backfill_unreviewed_hold_flag")
    _known_fields_agree(fresh, archived)
    start = max(fresh.bars[0].session, archived.bars[0].session) if fresh.bars else (
        archived.bars[0].session)
    if _price_actions(fresh, start, record.session) != _price_actions(
        archived, start, record.session):
        raise ProviderError("reviewed_backfill_actions_conflict")
    accepted = next(bar for bar in archived.bars if bar.session == record.session)
    existing = {bar.session: bar for bar in fresh.bars}
    bars = {**existing, record.session: accepted}
    original_dividends = tuple(action for action in fresh.actions
                              if start <= action.session <= record.session
                              and action.kind == "dividend")
    reviewed_dividends = tuple(action for action in archived.actions
                              if start <= action.session <= record.session
                              and action.kind == "dividend")
    provenance = canonical_json({"kind": BACKFILL_VERSION, "status": "recovered",
        "original_input_digest": fresh.input_digest,
        "reviewed_input_digest": archived.input_digest, "manifest_digest": manifest_digest,
        "replaced_sessions": [record.session.isoformat()], "matched_fields": list(OHLCV_FIELDS),
        "reviewed_source_fetched_at": archived.fetched_at,
        "independent_reference": asdict(record.reference),
        "cash_dividend_metadata_disagreement": original_dividends != reviewed_dividends,
    })
    return replace(fresh, bars=tuple(bars[day] for day in sorted(bars)),
        provider_row_issues=tuple(issue for issue in fresh.provider_row_issues
                                 if issue.session != record.session),
        provider_missing_sessions=tuple(day for day in fresh.provider_missing_sessions
                                        if day != record.session),
        provenance=(*fresh.provenance, provenance))


class ReviewedBackfillProvider:
    """Opt-in paper-provider wrapper. Never substitute an archive on fetch failure."""
    def __init__(self, provider, store, calendar, records, *, clock=lambda: datetime.now(UTC)):
        if (type(records) is not tuple or len(records) > 100
            or any(not isinstance(r, ReviewedBackfill) for r in records)
            or len({(record.ticker, record.session) for record in records}) != len(records)):
            raise ValueError("invalid_reviewed_backfill_manifest")
        self.provider, self.store, self.calendar = provider, store, calendar
        self.records = tuple(sorted(records, key=lambda record: (record.ticker, record.session)))
        self.clock = clock
        self.manifest_digest = digest((BACKFILL_VERSION, self.records))
        self._captures, self._diagnostics = {}, {}

    @property
    def raw_recovery_captures(self):
        original = getattr(self.provider, "raw_recovery_captures", {})
        return {ticker: tuple({source.input_digest: source for source in (
            *original.get(ticker, ()), *self._captures.get(ticker, ()))}.values())
            for ticker in set(original) | set(self._captures)}

    @property
    def fetch_diagnostics(self):
        original = getattr(self.provider, "fetch_diagnostics", {})
        return {ticker: (*original.get(ticker, ()), *self._diagnostics.get(ticker, ()))
                for ticker in set(original) | set(self._diagnostics)}

    def _retain(self, ticker, *sources):
        values = (*self._captures.get(ticker, ()), *sources)
        self._captures = {**self._captures, ticker: tuple({source.input_digest: source
            for source in values}.values())}

    def _load(self, record, now):
        rows = self.store._request("GET", "market_series_revisions", params={
            "select": "id,input_digest", "namespace": "eq.forward", "data_mode": "eq.live",
            "provider": "eq.yfinance", "ticker": "eq." + record.ticker,
            "provider_symbol": "eq." + record.provider_symbol,
            "price_basis": "eq." + record.price_basis,
            "provider_version": "eq." + record.provider_version,
            "input_digest": "eq." + record.source_input_digest,
            "order": "stored_at.desc,id.desc", "limit": "2",
        })
        if (type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict
            or rows[0].get("input_digest") != record.source_input_digest
            or not isinstance(rows[0].get("id"), str)):
            raise ProviderError("reviewed_backfill_source_unavailable")
        source = self.store.load_series(rows[0]["id"], namespace="forward", data_mode="live",
                                        expected_input_digest=record.source_input_digest)
        if (not _identity(source, record) or source.input_digest != record.source_input_digest
            or not _aware(source.fetched_at) or source.fetched_at > record.reference.reviewed_at
            or not source.bars or source.bars[-1].session != record.session
            or _future_content(source, record.session)
            or source.fetched_at < self.calendar.get(record.session).closes_at
            or source.fetched_at > now
            or quality(source, record.session, self.calendar) != "valid"):
            raise ProviderError("reviewed_backfill_source_mismatch")
        return source

    def _check_context(self, record, fresh, request, now):
        if record.provider_symbol != request.symbol or not _identity(fresh, record):
            raise ProviderError("reviewed_backfill_request_mismatch")
        if not _aware(now) or not _aware(fresh.fetched_at) or fresh.fetched_at > now:
            raise ProviderError("reviewed_backfill_invalid_observation_time")
        try:
            close = self.calendar.get(record.session).closes_at
            target_close = self.calendar.get(request.end).closes_at
        except ValueError:
            raise ProviderError("reviewed_backfill_calendar_unknown") from None
        if (now < target_close or fresh.fetched_at < target_close
            or record.reference.reviewed_at < close
            or record.reference.reviewed_at > now):
            raise ProviderError("reviewed_backfill_unclosed_or_unreviewed_session")
        if (not fresh.bars or not fresh.actions_complete or _future_content(fresh, request.end)
            or tuple(bar.session for bar in fresh.bars) != tuple(sorted({
                bar.session for bar in fresh.bars}))):
            raise ProviderError("reviewed_backfill_invalid_current_source")

    def fetch(self, request: FetchRequest) -> Series:
        # A transport failure propagates. A reviewed receipt cannot pretend a
        # failed current fetch succeeded, and an empty allowlist adds no IO.
        fresh = self.provider.fetch(request)
        records = tuple(record for record in self.records if record.ticker == request.ticker
                        and request.start <= record.session <= request.end)
        for record in records:
            if not _needs_receipt(fresh, record.session):
                continue
            now = self.clock()
            self._retain(request.ticker, fresh)
            self._check_context(record, fresh, request, now)
            archived = self._load(record, now)
            self._retain(request.ticker, archived)
            fresh = _merge(fresh, archived, record, self.manifest_digest)
            diagnostic = {"status": "reviewed_backfill_applied", "session": str(record.session),
                          "input_digest": fresh.input_digest, "fetched_at": now.isoformat()}
            self._diagnostics = {**self._diagnostics, request.ticker: (
                *self._diagnostics.get(request.ticker, ()), diagnostic)}
        return fresh
