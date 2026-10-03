"""Cross-runtime persistence proof; synthetic inputs only."""

import json
import sys
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scanner/src"))
from idx_scanner.fixtures import sample_market
from idx_scanner.models import CorporateAction, ProviderRowIssue, canonical_json
from idx_scanner.normalization import normalize_closed_sessions
from idx_scanner.persistence import market_series_envelope, series_from_revision

if sys.argv[1] == "setup":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from prepare_dev_market_setup import render_setup

    print(render_setup("11111111-1111-4111-8111-111111111111"))
    sys.exit(0)

series, _, _ = sample_market(3)
original = series["DEMO-A"]
source = replace(
    original,
    fetched_at=datetime(2030, 1, 2, tzinfo=UTC),
    bars=(
        replace(
            original.bars[0], open=1e20, high=1e20, low=1e-7, close=100.0, volume=-0.0
        ),
        replace(original.bars[1], volume=100),
    ),
    actions=(CorporateAction(date(2024, 1, 2), "dividend", "1.0"),),
    provider_missing_sessions=(date(2024, 1, 4),),
    provider_row_issues=(
        ProviderRowIssue(
            date(2024, 1, 4), "incomplete_ohlcv", (("volume", 1e20), ("close", None))
        ),
    ),
)
if "normalized" in sys.argv[1]:
    values, calendar, _ = sample_market(5)
    original = values["DEMO-A"]
    from datetime import timedelta

    closed = original.bars[3].session + timedelta(days=1)
    raw = replace(
        original,
        bars=tuple(
            sorted(
                original.bars
                + (
                    replace(
                        original.bars[0],
                        session=closed,
                        open=100,
                        high=100,
                        low=100,
                        close=100,
                        volume=0,
                    ),
                ),
                key=lambda b: b.session,
            )
        ),
        fetched_at=datetime(2030, 1, 2, tzinfo=UTC),
    )
    source = (
        raw
        if sys.argv[1].endswith("_raw")
        else normalize_closed_sessions(
            raw, replace(calendar, closed_days=(closed,)), original.bars[-1].session
        )
    )
if sys.argv[1].startswith("encode"):
    print(
        canonical_json(
            market_series_envelope(source, namespace="roundtrip", data_mode="fixture")[
                "p_record"
            ]
        )
    )
else:
    restored = series_from_revision(json.load(sys.stdin))
    assert restored.input_digest == source.input_digest
    assert canonical_json(restored) == canonical_json(source)
    print("digest_verified")
