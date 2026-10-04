"""One-run orchestration. Provider and database IO stay outside the rule engine."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

from .context import Calendar, Universe
from .corporate_actions import DividendEvidence, reconcile_dividends
from .engine import scan
from .normalization import normalize_closed_sessions
from .persistence import SupabaseScanStore
from .pipeline import PipelineResult, fetch_series, require_scan_context
from .providers import FetchRequest, Provider


@dataclass(frozen=True)
class RunOutcome:
    pipeline: PipelineResult
    revision_ids: tuple[str, ...]
    publication: dict


def run_once(
    provider: Provider,
    store: SupabaseScanStore,
    requests: dict[str, FetchRequest],
    target: date,
    calendar: Calendar,
    universe: Universe,
    published_at: datetime,
    *,
    namespace: str = "forward",
    clock: Callable[[], datetime] | None = None,
    normalize_calendar: bool = True,
    dividend_evidence: tuple[DividendEvidence, ...] = (),
    source_revision: str | None = None,
) -> RunOutcome:
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", namespace):
        raise ValueError("invalid_namespace")
    require_scan_context(requests, target, calendar, universe, published_at)
    state = store.load_state(
        through_session=target, namespace=namespace, data_mode=universe.data_mode
    )
    series_by_ticker, errors = fetch_series(provider, requests)
    revisions = []
    prepared = {}
    for ticker in sorted(series_by_ticker):
        series = series_by_ticker[ticker]
        receipt = store.ingest_series(series, namespace=namespace, data_mode=universe.data_mode)
        store.load_series(
            receipt["revision_id"],
            namespace=namespace,
            data_mode=universe.data_mode,
            expected_input_digest=series.input_digest,
        )
        revisions.append(receipt["revision_id"])
        value = (
            normalize_closed_sessions(series, calendar, target) if normalize_calendar else series
        )
        value = reconcile_dividends(value, dividend_evidence, calendar, target)
        if value.input_digest != series.input_digest:
            receipt = store.ingest_series(value, namespace=namespace, data_mode=universe.data_mode)
            value = store.load_series(
                receipt["revision_id"],
                namespace=namespace,
                data_mode=universe.data_mode,
                expected_input_digest=value.input_digest,
            )
            revisions.append(receipt["revision_id"])
        prepared[ticker] = value
    # Timestamp after provider/database IO, so crossing next-open cannot produce
    # a falsely actionable forward signal.
    evaluated_at = clock() if clock is not None else published_at
    result = scan(
        prepared,
        target,
        calendar,
        universe,
        evaluated_at,
        state,
        namespace=namespace,
        source_revision=source_revision,
    )
    if clock is not None and evaluated_at < calendar.next(target).opens_at <= clock():
        raise ValueError("publication_window_elapsed")
    pipeline = PipelineResult(
        result,
        errors,
        tuple(sorted(series_by_ticker)),
        tuple(series_by_ticker[t] for t in sorted(series_by_ticker)),
        tuple(prepared[t] for t in sorted(prepared)),
    )
    options = {}
    if universe.data_mode == "live":
        options["publication_deadline"] = calendar.next(target).opens_at
    publication = store.publish(
        pipeline.scan, namespace=namespace, data_mode=universe.data_mode, **options
    )
    return RunOutcome(pipeline, tuple(revisions), publication)
