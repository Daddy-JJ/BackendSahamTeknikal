"""Build and persist chart artifacts for active signal tickers only."""
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Load local .env
env_file = Path(__file__).resolve().parents[2] / ".env"
if env_file.is_file():
    try:
        from prepare_dev_setup import local_env
        for k, v in local_env(env_file).items():
            os.environ.setdefault(k, v)
    except Exception:
        pass

if "SUPABASE_SECRET_KEY" not in os.environ and "SUPABASE_SERVICE_ROLE_KEY" in os.environ:
    os.environ["SUPABASE_SECRET_KEY"] = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

required = ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "APP_OWNER_USER_ID")
if any(not os.environ.get(name) for name in required):
    print("Missing environment variables", file=sys.stderr)
    sys.exit(1)

from idx_scanner.chart_runtime import ChartArtifactStore, run_chart_job
from idx_scanner.persistence import SupabaseScanStore

def main():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SECRET_KEY"]
    owner_id = os.environ["APP_OWNER_USER_ID"]

    with SupabaseScanStore(url, key) as base:
        # Fetch tickers with active signals
        resp = base._client.get(
            f"{url}/rest/v1/signals?select=ticker",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
            }
        )
        if resp.status_code != 200:
            print(f"Failed to fetch signals: {resp.status_code} {resp.text}", file=sys.stderr)
            sys.exit(1)
        
        tickers = sorted(list(set(row["ticker"] for row in resp.json())))
        print(f"Found {len(tickers)} distinct tickers with signals: {', '.join(tickers)}")

        store = ChartArtifactStore(base, owner_id)
        now = datetime.now(UTC)
        total_prepared = 0
        total_written = 0

        for idx, t in enumerate(tickers, 1):
            try:
                res = run_chart_job(
                    store,
                    observed_at=now,
                    ticker=t,
                    execute=True,
                    max_revisions=250,
                )
                prep = res.get("prepared", 0)
                writ = res.get("written", 0)
                total_prepared += prep
                total_written += writ
                print(f"[{idx}/{len(tickers)}] {t}: prepared={prep}, written={writ}")
            except Exception as e:
                print(f"[{idx}/{len(tickers)}] {t}: ERROR: {e}")

        print(f"\nCompleted! Total prepared={total_prepared}, total written={total_written}")

if __name__ == "__main__":
    main()
