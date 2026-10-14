"""Explicit synthetic chart export for cross-language contract tests, never production IO."""

import json
from dataclasses import asdict, replace

from .chart_artifact import ChartReceipt, build_chart_artifact
from .fixtures import sample_market
from .models import canonical_json
from .persistence import market_series_envelope


def synthetic_chart_export(owner_id: str, series_id: str, *, count=40):
    market, calendar, _ = sample_market(count)
    source = replace(next(iter(market.values())), fetched_at=calendar.sessions[count - 1].closes_at)
    receipt = ChartReceipt(series_id, "forward", "fixture", source, source.fetched_at)
    data = build_chart_artifact(receipt, calendar, observed_at=source.fetched_at)
    record = {"owner_id": owner_id, "data_mode": "fixture", "ticker": source.ticker,
              "context_kind": "latest", "context_id": None, "view": "followup",
              "revision": data["revision"], "data": data}
    return {"market_record": market_series_envelope(source, namespace="forward",
                                                    data_mode="fixture")["p_record"],
            "p_record": record, "calendar": json.loads(canonical_json(asdict(calendar)))}


def synthetic_chart_envelope(*, count=40):
    export = synthetic_chart_export("22222222-2222-4222-8222-222222222222",
                                     "11111111-1111-4111-8111-111111111111", count=count)
    data = export["p_record"]["data"]
    slots = data["sessions"]
    indicators = {key: {**value, "points": [point for point in value["points"]
                  if point["session"] in slots]} for key, value in data["indicators"].items()}
    projected = {**data, "sessions": slots,
                 "bars": [bar for bar in data["bars"] if bar["session"] in slots],
                 "gaps": [gap for gap in data["gaps"] if gap["session"] in slots],
                 "indicators": indicators, "pagination": {"window_from": slots[0],
                 "window_to": slots[-1], "returned_slots": len(slots), "limit": 250,
                 "has_more": False, "next_cursor": None}}
    return {"contract_version": "ticker-chart-v1", "success": True,
            "data": projected, "error": None}
