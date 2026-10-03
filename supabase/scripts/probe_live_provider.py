"""Read-only Yahoo identity and adapter probe; never publishes a scan."""

import argparse
import contextlib
import hashlib
import io
import json
from dataclasses import asdict
from datetime import UTC, date, datetime
from importlib.metadata import version
from pathlib import Path

import yfinance as yf
from idx_scanner.models import canonical_json
from idx_scanner.providers import FetchRequest, ProviderError, YFinanceProvider

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = ("BBCA", "BBRI", "BMRI", "TLKM", "ASII")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 10, 1))
    parser.add_argument("--start", type=date.fromisoformat, default=date(2023, 9, 1))
    parser.add_argument("--all-universe", action="store_true")
    args = parser.parse_args()
    end = args.end
    if args.start > end:
        parser.error("start must precede end")
    candidates = CANDIDATES
    if args.all_universe:
        reference = json.loads(
            (ROOT / "config/reference/kompas100-2026-08-source.json").read_text()
        )
        candidates = tuple(reference["tickers"])
        if len(candidates) != 100 or len(set(candidates)) != 100:
            raise ValueError("invalid_reference_universe")
    folder = (
        ROOT
        / "data"
        / (
            f"live-universe-{end.isoformat()}"
            if args.all_universe
            else "live-provider-20261002"
        )
    )
    folder.mkdir(parents=True, exist_ok=True)
    report = {
        "purpose": "provider_probe_not_published_signal",
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "provider": "yfinance",
        "provider_version": version("yfinance"),
        "requested_end": end.isoformat(),
        "requested_start": args.start.isoformat(),
        "expected_tickers": len(candidates),
        "calendar_freshness_verified": False,
        "cross_section_complete": False,
        "production_write": False,
        "scheduler_enabled": False,
        "results": [],
    }
    for ticker in candidates:
        symbol = ticker + ".JK"  # Candidate only until provider identity agrees.
        result = {
            "ticker": ticker,
            "candidate_symbol": symbol,
            "mapping_verified": False,
        }
        try:
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                info = yf.Ticker(symbol).get_info()
            identity = {
                k: info.get(k)
                for k in ("symbol", "exchange", "currency", "quoteType", "longName")
            }
            if not (
                identity["symbol"] == symbol
                and identity["exchange"] == "JKT"
                and identity["currency"] == "IDR"
                and identity["quoteType"] == "EQUITY"
                and identity["longName"]
            ):
                result["status"] = "provider_identity_unverified"
            else:
                result.update(
                    mapping_verified=True,
                    identity=identity,
                    source=f"https://finance.yahoo.com/quote/{symbol}/",
                )
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    series = YFinanceProvider().fetch(
                        FetchRequest(
                            ticker,
                            symbol,
                            args.start,
                            end,
                            True,
                        )
                    )
                raw = canonical_json(asdict(series)).encode()
                (folder / f"{ticker}.json").write_bytes(raw)
                if not series.bars:
                    raise ProviderError("no_complete_bars")
                result.update(
                    status="adapter_fetch_passed_quality_not_certified",
                    valid_bars=len(series.bars),
                    first_bar=str(series.bars[0].session),
                    latest_complete_bar=str(series.bars[-1].session),
                    missing_rows=len(series.provider_missing_sessions),
                    row_issues=len(series.provider_row_issues),
                    corporate_actions=len(series.actions),
                    corporate_actions_reconciled=False,
                    input_digest=series.input_digest,
                    raw_sha256=hashlib.sha256(raw).hexdigest(),
                )
        except ProviderError as error:
            result["status"] = error.code
        except Exception:  # noqa: BLE001 -- provider errors must not expose transport credentials.
            result["status"] = "provider_identity_or_probe_failed"
        report["results"].append(result)
        (folder / "evidence.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        if args.all_universe and len(report["results"]) % 10 == 0:
            print(
                json.dumps(
                    {"processed": len(report["results"]), "total": len(candidates)}
                ),
                flush=True,
            )
    (folder / "evidence.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    if args.all_universe:
        print(
            json.dumps(
                {
                    "evidence_path": str(folder / "evidence.json"),
                    "processed": len(report["results"]),
                    "mapping_verified": sum(
                        x["mapping_verified"] for x in report["results"]
                    ),
                    "adapter_fetch_passed": sum(
                        x["status"] == "adapter_fetch_passed_quality_not_certified"
                        for x in report["results"]
                    ),
                    "production_write": False,
                }
            )
        )
    else:
        print(json.dumps(report, indent=2))
    return int(
        any(
            x["status"] != "adapter_fetch_passed_quality_not_certified"
            for x in report["results"]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
