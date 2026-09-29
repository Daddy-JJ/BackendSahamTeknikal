"""Provider orchestration separate from pure engine; partial failures are visible."""

from dataclasses import dataclass
from datetime import date, datetime

from .context import Calendar, Universe
from .engine import ScanResult, scan
from .models import ScanState, Series
from .providers import FetchRequest, Provider, ProviderError


@dataclass(frozen=True)
class PipelineResult:
    scan: ScanResult
    provider_errors: tuple[tuple[str, str], ...]
    fetched: tuple[str, ...]
    fetched_series: tuple[Series, ...]


def require_scan_context(
    requests: dict[str, FetchRequest],
    target: date,
    calendar: Calendar,
    universe: Universe,
    published_at: datetime,
) -> None:
    universe.require(target)
    current = calendar.get(target)
    calendar.next(target)
    if calendar.data_mode != universe.data_mode:
        raise ValueError("mixed_fixture_live_context")
    if published_at.tzinfo is None or published_at < current.closes_at:
        raise ValueError("target_session_not_closed")
    if set(requests) != set(universe.tickers):
        raise ValueError("complete_universe_mapping_required")
    for ticker, request in requests.items():
        if request.ticker != ticker or request.end != target:
            raise ValueError("request_mapping_or_target_mismatch")


def collect_and_scan(
    provider: Provider,
    requests: dict[str, FetchRequest],
    target: date,
    calendar: Calendar,
    universe: Universe,
    published_at: datetime,
    state: ScanState,
    *,
    namespace: str = "forward",
) -> PipelineResult:
    require_scan_context(requests, target, calendar, universe, published_at)
    series: dict[str, Series] = {}
    errors = []
    for ticker in sorted(universe.tickers):
        try:
            series[ticker] = provider.fetch(requests[ticker])
        except ProviderError as error:
            errors.append((ticker, error.code))
    result = scan(series, target, calendar, universe, published_at, state, namespace=namespace)
    return PipelineResult(
        result, tuple(errors), tuple(sorted(series)), tuple(series[t] for t in sorted(series))
    )
