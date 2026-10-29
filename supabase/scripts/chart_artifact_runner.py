"""Cloud-only chart artifact build from Supabase; dry-run unless --execute is passed."""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from idx_scanner.chart_runtime import (
    DEFAULT_MAX_REVISIONS,
    ChartArtifactStore,
    run_chart_job,
)
from idx_scanner.persistence import PersistenceError, SupabaseScanStore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ticker")
    parser.add_argument("--max-tickers", type=int, default=100)
    parser.add_argument("--max-revisions", type=int, default=DEFAULT_MAX_REVISIONS)
    args = parser.parse_args(argv)
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.is_file():
        try:
            from prepare_dev_setup import local_env

            for k, v in local_env(env_file).items():
                os.environ.setdefault(k, v)
        except (ImportError, ValueError):
            pass
    if "SUPABASE_SECRET_KEY" not in os.environ and "SUPABASE_SERVICE_ROLE_KEY" in os.environ:
        os.environ["SUPABASE_SECRET_KEY"] = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    required = ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "APP_OWNER_USER_ID")
    if any(not os.environ.get(name) for name in required):
        print(json.dumps({"status": "failed", "code": "chart_missing_environment"}))
        return 1
    try:
        with SupabaseScanStore(os.environ["SUPABASE_URL"],
                                os.environ["SUPABASE_SECRET_KEY"]) as base:
            result = run_chart_job(ChartArtifactStore(base, os.environ["APP_OWNER_USER_ID"]),
                                  observed_at=datetime.now(UTC), ticker=args.ticker,
                                  execute=args.execute, max_tickers=args.max_tickers,
                                  max_revisions=args.max_revisions)
        print(json.dumps(result, allow_nan=False))
        return 0 if result["status"] == "ready" else 1
    except PersistenceError as exc:
        print(json.dumps({"status": "failed", "code": exc.code}))
        return 1
    except (ValueError, TypeError):
        print(json.dumps({"status": "failed", "code": "chart_invalid_configuration"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
