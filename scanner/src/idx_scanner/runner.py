"""One-run orchestration. Provider and database IO stay outside the rule engine."""

import re
from dataclasses import dataclass
from datetime import date, datetime

from .context import Calendar, Universe
from .persistence import SupabaseScanStore
from .pipeline import PipelineResult, collect_and_scan, require_scan_context
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
) -> RunOutcome:
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", namespace):
        raise ValueError("invalid_namespace")
    require_scan_context(requests, target, calendar, universe, published_at)
    state = store.load_state(
        through_session=target, namespace=namespace, data_mode=universe.data_mode
    )
    pipeline = collect_and_scan(
        provider,
        requests,
        target,
        calendar,
        universe,
        published_at,
        state,
        namespace=namespace,
    )
    revisions = []
    for series in pipeline.fetched_series:
        receipt = store.ingest_series(series, namespace=namespace, data_mode=universe.data_mode)
        store.load_series(
            receipt["revision_id"],
            namespace=namespace,
            data_mode=universe.data_mode,
            expected_input_digest=series.input_digest,
        )
        revisions.append(receipt["revision_id"])
    publication = store.publish(pipeline.scan, namespace=namespace, data_mode=universe.data_mode)
    return RunOutcome(pipeline, tuple(revisions), publication)
