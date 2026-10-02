"""Manual, idempotent synthetic revision proof on the allowlisted dev project."""

import argparse
from dataclasses import replace
from datetime import UTC, datetime

import httpx
from idx_scanner.fixtures import sample_market
from idx_scanner.persistence import PersistenceError, SupabaseScanStore
from smoke_dev_fixture import dev_env

NAMESPACE = "dev_market_revision_m2"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        url, key = dev_env()
        with httpx.Client(
            base_url=url + "/rest/v1/",
            headers={"apikey": key},
            timeout=20,
            follow_redirects=False,
        ) as client:
            mode = client.get("deployment_settings", params={"select": "data_mode"})
            schema = client.get(
                "market_series_revisions",
                params={"select": "bar_sessions,source_hash", "limit": 0},
            )
            if mode.status_code != 200 or mode.json() != [{"data_mode": "fixture"}]:
                raise ValueError("dev_fixture_mode_required")
            if schema.status_code != 200:
                raise ValueError("dev_revision_migrations_required")
        if not args.execute:
            print(
                "Dev revision schema available. Dry run only; --execute writes labeled fixtures."
            )
            return 0
        market, _, _ = sample_market(3)
        original = replace(
            market["DEMO-A"], fetched_at=datetime(2030, 1, 2, tzinfo=UTC)
        )
        changed = replace(
            original,
            bars=(
                replace(original.bars[0], close=original.bars[0].close + 1),
                original.bars[2],
            ),
        )
        with SupabaseScanStore(url, key) as store:
            first = store.ingest_series(
                original, namespace=NAMESPACE, data_mode="fixture"
            )
            second = store.ingest_series(
                changed, namespace=NAMESPACE, data_mode="fixture"
            )
            replay = store.ingest_series(
                original, namespace=NAMESPACE, data_mode="fixture"
            )
            if (
                first["revision_id"] == second["revision_id"]
                or replay["revision_id"] != first["revision_id"]
                or not replay["replayed"]
            ):
                raise ValueError("revision_replay_mismatch")
            for source, receipt in ((original, first), (changed, second)):
                restored = store.load_series(
                    receipt["revision_id"],
                    namespace=NAMESPACE,
                    data_mode="fixture",
                    expected_input_digest=source.input_digest,
                )
                if restored != source:
                    raise ValueError("revision_roundtrip_mismatch")
        print(
            "PASS: two fixture revisions, original/changed digests verified, original replay preserved."
        )
        print(
            "No market-provider fetch, scan publication or production write was performed."
        )
        return 0
    except (ValueError, OSError, PersistenceError, httpx.HTTPError):
        print(
            "Revision smoke could not complete. Verify dev schema/mode and local env; no credentials are printed."
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
