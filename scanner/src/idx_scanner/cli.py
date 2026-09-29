"""CLI for deterministic fixture output and explicit live provider connectivity probes."""

import argparse
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

import httpx

from .demo import demo_snapshot
from .models import canonical_json
from .persistence import PersistenceError
from .providers import FetchRequest, ProviderError, make_provider
from .run_command import add_run_parser, execute_run


def main() -> int:
    parser = argparse.ArgumentParser(prog="idx-scanner")
    commands = parser.add_subparsers(dest="command", required=True)
    fixture = commands.add_parser(
        "demo", help="Generate deterministic synthetic engine/UI snapshot"
    )
    fixture.add_argument("--output", type=Path)
    probe = commands.add_parser("fetch", help="Live provider probe only; not a published scan")
    probe.add_argument("--provider", choices=("yfinance", "eodhd"), required=True)
    probe.add_argument("--ticker", required=True)
    probe.add_argument("--symbol", required=True)
    probe.add_argument("--mapping-verified", action="store_true", required=True)
    probe.add_argument("--start", type=date.fromisoformat, required=True)
    probe.add_argument("--end", type=date.fromisoformat, required=True)
    probe.add_argument("--output", type=Path, required=True)
    add_run_parser(commands)
    args = parser.parse_args()
    try:
        if args.command == "run":
            payload = execute_run(args)
            print(canonical_json(payload))
            return 0 if payload["status"] in ("preflight_passed", "complete") else 3
        if args.command == "demo":
            payload = demo_snapshot()
        else:
            request = FetchRequest(
                args.ticker, args.symbol, args.start, args.end, args.mapping_verified
            )
            with httpx.Client() as client:
                series = make_provider(args.provider, client).fetch(request)
            payload = {
                "data_mode": "live",
                "purpose": "provider_probe_not_published_signal",
                "series": asdict(series),
                "input_digest": series.input_digest,
            }
        output = canonical_json(payload) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding="utf-8")
            print(f"Wrote {args.output} ({payload['data_mode']})")
        else:
            print(output, end="")
        return 0
    except (ProviderError, PersistenceError) as exc:
        print(canonical_json({"error": exc.code, "fallback": False}), file=sys.stderr)
        return 2
    except (ValueError, OSError, KeyError, TypeError):
        print(canonical_json({"error": "invalid_configuration_or_output_path"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
