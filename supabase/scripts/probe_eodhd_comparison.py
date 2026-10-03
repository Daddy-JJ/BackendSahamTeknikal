"""Read-only EODHD coverage discovery; secrets and HTTP response bodies never logged.

Does not change the scanner provider, publish signals or connect to Supabase.
Discovery is bounded to two GET requests and stops on missing Indonesia coverage.
"""

import argparse
import hashlib
import json
import os
import re
from datetime import UTC, date, datetime

import httpx
from idx_scanner.config_io import load_calendar
from idx_scanner.models import canonical_json
from idx_scanner.normalization import normalize_closed_sessions
from idx_scanner.providers import EODHDProvider, FetchRequest, ProviderError
from prepare_dev_setup import ROOT, local_env

CANDIDATES = ("BBCA", "BRPT", "AMMN", "BUMI", "EMAS")
REVIEWED_NAMES = {
    "BBCA": "Bank Central Asia Tbk",
    "BRPT": "Barito Pacific Tbk",
    "AMMN": "PT Amman Mineral Internasional",
    "BUMI": "Bumi Resources Tbk",
    "EMAS": "PT Merdeka Gold Resources Tbk",
}


def compare(client, token):
    # Identity reviewed against the checksum-verified Yahoo capture. No suffix inference.
    from publish_first_live_hold_run import captured_series

    discovery = json.loads(
        (ROOT / "data/eodhd-coverage-discovery-20261002.json").read_text()
    )
    rows = {r["Code"]: r for r in discovery.get("candidate_identities", [])}
    if not all(
        rows.get(t, {}).get("Name") == REVIEWED_NAMES[t]
        and rows[t].get("Exchange") == "JK"
        and rows[t].get("Currency") == "IDR"
        and rows[t].get("Type") == "Common Stock"
        for t in CANDIDATES
    ):
        raise ValueError("reviewed_provider_identities_required")
    yahoo = captured_series()
    calendar = load_calendar(ROOT / "config/live/idx-calendar-2024-2026.json")
    target = date(2026, 10, 2)
    report = {
        "purpose": "separate_provider_comparison_not_signal_or_ca_approval",
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "production_write": False,
        "provider_changed": False,
        "scheduler_enabled": False,
        "yahoo_price_basis": "yahoo_provider_ohlcv_auto_adjust_false_v1",
        "eodhd_price_basis": "eodhd_unadjusted_ohlc_v1",
        "volume_basis_equivalence_verified": False,
        "results": [],
        "http_requests": 0,
    }

    class BoundedClient:
        def get(self, *args, **kwargs):
            if report["http_requests"] >= 15:
                raise ProviderError("comparison_request_budget_exhausted")
            report["http_requests"] += 1
            return client.get(*args, **kwargs)

    provider = EODHDProvider(token, BoundedClient())
    folder = ROOT / "data/eodhd-comparison-20261002"
    folder.mkdir(parents=True, exist_ok=True)
    for ticker in CANDIDATES:
        result = {
            "ticker": ticker,
            "identity_reviewed": True,
            "provider_symbol": ticker + ".JK",
        }
        try:
            series = provider.fetch(
                FetchRequest(ticker, ticker + ".JK", date(2024, 1, 1), target, True)
            )
        except ProviderError as exc:
            result["status"] = exc.code
            report["results"].append(result)
            # Do not consume more budget after entitlement, rate or request failure.
            break
        raw = canonical_json(series).encode()
        (folder / (ticker + ".json")).write_bytes(raw)
        value = normalize_closed_sessions(series, calendar, target)
        baseline = normalize_closed_sessions(yahoo[ticker], calendar, target)
        by_day = {b.session: b for b in value.bars}
        old = {b.session: b for b in baseline.bars}
        common = sorted(set(old) & set(by_day))
        price_differences = [
            d
            for d in common
            if any(
                getattr(old[d], k) != getattr(by_day[d], k)
                for k in ("open", "high", "low", "close")
            )
        ]
        open_days = set(calendar.historical_days) | {s.day for s in calendar.sessions}
        result.update(
            status="adapter_fetched_comparison_only",
            raw_sha256=hashlib.sha256(raw).hexdigest(),
            input_digest=series.input_digest,
            first_bar=value.bars[0].session.isoformat(),
            latest_bar=value.bars[-1].session.isoformat(),
            requested_history_complete=value.bars[0].session
            <= baseline.bars[0].session,
            target_fresh=value.bars[-1].session == target,
            bars=len(value.bars),
            matched_sessions=len(common),
            ohlc_differing_sessions=len(price_differences),
            max_close_relative_difference=max(
                (abs(by_day[d].close / old[d].close - 1) for d in common), default=None
            ),
            zero_volume_open_sessions=[
                b.session.isoformat()
                for b in value.bars
                if b.volume == 0 and b.session in open_days
            ],
            yahoo_zero_volume_open_count=sum(b.volume == 0 for b in baseline.bars),
            yahoo_zero_volume_matched_sessions=[
                d.isoformat() for d in common if old[d].volume == 0
            ],
            yahoo_zero_volume_outside_comparison=[
                d.isoformat()
                for d in sorted(old)
                if old[d].volume == 0 and d not in by_day
            ],
            missing_known_open_count=sum(
                d not in by_day
                for d in open_days
                if value.bars[0].session <= d <= target
            ),
            corporate_actions=json.loads(canonical_json(series.actions)),
            yahoo_corporate_actions=json.loads(canonical_json(baseline.actions)),
            dividend_or_split_reconciliation_approved=False,
        )
        report["results"].append(result)
    report["price_comparison_completed"] = len(report["results"]) == len(
        CANDIDATES
    ) and all(
        r["status"] == "adapter_fetched_comparison_only" for r in report["results"]
    )
    report["status"] = (
        "comparison_completed_review_required"
        if report["price_comparison_completed"]
        else "comparison_blocked"
    )
    return report


def discover(client, token):
    report = {
        "purpose": "eodhd_comparison_coverage_discovery",
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "production_write": False,
        "provider_changed": False,
        "scheduler_enabled": False,
        "http_requests": 0,
        "price_comparison_completed": False,
    }

    def get(endpoint):
        report["http_requests"] += 1
        try:
            response = client.get(
                "https://eodhd.com/api/" + endpoint,
                params={"api_token": token, "fmt": "json"},
                timeout=30,
                follow_redirects=False,
            )
        except httpx.TransportError:
            report["status"] = "transport_failed"
            return None
        report["last_http_status"] = response.status_code
        if response.status_code != 200:
            report["status"] = (
                "auth_or_entitlement_denied"
                if response.status_code in (401, 403)
                else "request_failed"
            )
            return None
        try:
            data = response.json()
            if not isinstance(data, list) or any(not isinstance(r, dict) for r in data):
                raise ValueError()
        except (ValueError, TypeError):
            report["status"] = "invalid_provider_payload"
            return None
        report["last_payload_sha256"] = hashlib.sha256(response.content).hexdigest()
        return data

    exchanges = get("exchanges-list/")
    if exchanges is None:
        return report
    report["supported_exchange_count"] = len(exchanges)
    matches = [
        r
        for r in exchanges
        if r.get("CountryISO2") == "ID"
        or r.get("Currency") == "IDR"
        or "indonesia" in str(r.get("Country", "")).lower()
        or "jakarta" in str(r.get("Name", "")).lower()
    ]
    report["indonesia_exchanges"] = [
        {
            k: r.get(k)
            for k in ("Code", "Name", "CountryISO2", "Currency", "OperatingMIC")
        }
        for r in matches
    ]
    if not matches:
        report["status"] = "blocked_indonesia_exchange_not_in_supported_list"
        return report
    if len(matches) != 1 or not re.fullmatch(
        r"[A-Z0-9_-]{1,12}", matches[0].get("Code", "")
    ):
        report["status"] = "blocked_exchange_identity_ambiguous"
        return report
    rows = get("exchange-symbol-list/" + matches[0]["Code"])
    if rows is None:
        return report
    report["candidate_identities"] = [
        {k: r.get(k) for k in ("Code", "Name", "Currency", "Exchange", "Type", "ISIN")}
        for r in rows
        if r.get("Code") in CANDIDATES
    ]
    report["status"] = "identities_pending_review_before_price_requests"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Reviewed five-symbol comparison, at most 15 GETs",
    )
    args = parser.parse_args()
    token = os.environ.get("EODHD_API_TOKEN") or local_env(ROOT / ".env").get(
        "EODHD_API_TOKEN"
    )
    if not token or token.lower() == "demo":
        print(json.dumps({"status": "credentials_missing", "production_write": False}))
        return
    with httpx.Client() as client:
        report = compare(client, token) if args.compare else discover(client, token)
    path = ROOT / (
        "data/eodhd-comparison-20261002.json"
        if args.compare
        else "data/eodhd-coverage-discovery-20261002.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
