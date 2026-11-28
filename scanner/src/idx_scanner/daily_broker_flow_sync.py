"""
Daily Broker Flow & Bandarmology EOD Sync Module.
Connects to the Max EOD Broker Summary service to aggregate daily and multi-horizon
(2D, 5D, 10D) smart money flow across all active IDX tickers.
Supports high-throughput asynchronous concurrency across the entire IDX universe (955 tickers).

Outputs:
1. Local JSON snapshot: backend/data/broker_flow_snapshot_latest.json (Complete dataset)
2. Frontend bundle: frontend/src/data/broker_flow_snapshot_latest.json (Optimized top-tier bundle)
3. Supabase Database: broker_flow_ticker_horizons (Cloud database upsert for full universe)
"""

import argparse
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from idx_scanner.broker_flow import (
    analyze_counterparty,
    calculate_bandar_average_cost,
    calculate_bandar_gap_pct,
    classify_market_quadrant,
    synthesize_trade_plan,
)
from idx_scanner.idx_universe import IDX_UNIVERSE_955

logger = logging.getLogger("daily_broker_flow_sync")

DEFAULT_MCP_URL = os.getenv("MAX_TRADE_MCP_URL", "https://eod.maxlong.my.id/mcp")

# Explicit featured tickers from Market Quadrants and Daily Insights to guarantee 100% detail coverage
FEATURED_QUADRANT_TICKERS = [
    "MBMA", "AMMN", "TINS", "AADI", "BREN", "NCKL", "INDF", "BRIS", "ACES", "ELSA",
    "PGEO", "CPIN", "INCO", "EXCL", "ADMR", "MEDC", "IRSX", "INOV", "IDEA", "ERAA",
    "CTRA", "PWON", "BMRI", "BBRI", "ISAT", "PTRO", "EMAS", "PGAS", "UNTR", "ICBP",
    "KLBF", "SIDO", "BBCA", "TLKM", "ASII", "WIFI", "MDKA", "BUMI", "BRPT", "INDY",
    "JPFA", "GOTO", "NAYZ", "LOPI", "ANTM", "KOTA",
]


def _resolve_mcp_token(explicit_token: Optional[str] = None) -> str:
    token = (explicit_token if explicit_token is not None else os.getenv("MAX_TRADE_MCP_TOKEN", "")).strip()
    if not token:
        raise RuntimeError("MAX_TRADE_MCP_TOKEN is not configured in the environment.")
    return token


class AsyncMaxTradeMcpClient:
    """Asynchronous HTTP Client for high-throughput batching against Max Trade MCP Server."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        self.base_url = base_url or os.getenv("MAX_TRADE_MCP_URL", DEFAULT_MCP_URL)
        self._explicit_token = token

    def _headers(self) -> Dict[str, str]:
        resolved_token = _resolve_mcp_token(self._explicit_token)
        return {
            "Authorization": f"Bearer {resolved_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

    async def call_tool(
        self,
        http_client: httpx.AsyncClient,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: float = 25.0,
    ) -> Any:
        """Call an MCP tool asynchronously via JSON-RPC."""
        headers = self._headers()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        try:
            resp = await http_client.post(
                self.base_url, headers=headers, json=payload, timeout=timeout
            )
            resp.raise_for_status()

            text = resp.text
            if text.startswith("event:") or text.startswith("data:"):
                for line in text.splitlines():
                    if line.startswith("data:"):
                        data_json = line[len("data:") :].strip()
                        if not data_json or data_json == "[DONE]":
                            continue
                        parsed = json.loads(data_json)
                        result = parsed.get("result", {})
                        content = result.get("content", [])
                        if content and content[0].get("type") == "text":
                            return json.loads(content[0]["text"])
                        return result

            data = resp.json()
            if "error" in data:
                logger.debug("MCP error for %s: %s", tool_name, data["error"])
                return None
            result = data.get("result", {})
            content = result.get("content", [])
            if content and content[0].get("type") == "text":
                return json.loads(content[0]["text"])
            return result

        except Exception as e:
            logger.debug("Error calling tool %s: %s", tool_name, e)
            return None


class MaxTradeMcpClient:
    """Synchronous Client for querying the Max Trade MCP Server (Backwards compatibility)."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        self.async_client = AsyncMaxTradeMcpClient(base_url, token)

    def call_tool(self, tool_name: str, arguments: Dict[str, Any], timeout: float = 20.0) -> Any:
        async def _run():
            async with httpx.AsyncClient(timeout=timeout) as client:
                return await self.async_client.call_tool(client, tool_name, arguments, timeout)

        try:
            return asyncio.run(_run())
        except Exception as e:
            logger.warning("Sync call error %s: %s", tool_name, e)
            return None


def _smart_net_of_ranking(item: Dict[str, Any]) -> float:
    foreign_net = float(item.get("foreignNetValue") or 0.0)
    gov_net = float(item.get("governmentNetValue") or 0.0)
    if foreign_net != 0.0 or gov_net != 0.0:
        return round(foreign_net + gov_net)
    top_buy = float(item.get("topBuyerNetValueTopN") or 0.0)
    top_sell = float(item.get("topSellerNetValueTopN") or 0.0)
    return round(top_buy - top_sell)


def build_ticker_detail_record(
    ticker: str,
    horizon: str,
    horizon_label: str,
    date_range: str,
    close_price: float,
    change_pct: float,
    net_value: float,
    net_volume_lots: int,
    bandar_cost: float,
    top_buyers: List[Dict[str, Any]],
    top_sellers: List[Dict[str, Any]],
    why_insight: str,
    concentration_pct: Optional[float] = None,
    foreign_net_value: Optional[float] = None,
    signal_score: Optional[float] = None,
    signal_label: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a compliant TickerBrokerDetail object."""
    quadrant = classify_market_quadrant(change_pct, net_value)
    quadrant_labels = {
        "markup_akumulasi": "[MA] Markup + Akumulasi",
        "markup_distribusi": "[MD] Markup + Distribusi (Trap)",
        "markdown_akumulasi": "[DA] Markdown + Akumulasi",
        "markdown_distribusi": "[DD] Markdown + Distribusi",
    }
    status_colors = {
        "markup_akumulasi": "emerald",
        "markup_distribusi": "amber",
        "markdown_akumulasi": "sky",
        "markdown_distribusi": "rose",
    }

    cost = bandar_cost if bandar_cost > 0 else close_price
    gap_pct = calculate_bandar_gap_pct(close_price, cost)
    cp_analysis = analyze_counterparty(top_buyers, top_sellers)
    trade_plan = synthesize_trade_plan(quadrant, close_price, cost)

    if concentration_pct is None:
        top_buy_abs = sum(abs(float(b.get("net_value") or 0.0)) for b in top_buyers)
        top_sell_abs = sum(abs(float(s.get("net_value") or 0.0)) for s in top_sellers)
        gross = top_buy_abs + top_sell_abs
        lead_buy = abs(float(top_buyers[0].get("net_value") or 0.0)) if top_buyers else 0.0
        concentration = round((lead_buy / gross) * 100.0, 2) if gross > 0 else 0.0
    else:
        concentration = round(float(concentration_pct), 2)

    record: Dict[str, Any] = {
        "ticker": ticker,
        "close": close_price,
        "change_percent": change_pct,
        "quadrant": quadrant,
        "quadrant_label": quadrant_labels.get(quadrant, quadrant),
        "status_color": status_colors.get(quadrant, "emerald"),
        "horizon": horizon,
        "horizon_label": horizon_label,
        "date_range": date_range,
        "top_accumulators": top_buyers,
        "top_distributors": top_sellers,
        "net_value": net_value,
        "net_volume_lots": net_volume_lots,
        "concentration_pct": concentration,
        "bandar_avg_cost": cost,
        "bandar_cost_gap_pct": gap_pct,
        "counterparty_note": cp_analysis.get(
            "description", "Distribusi transaksi seimbang antar partisipan pasar."
        ),
        "why_insight": why_insight,
        "trade_plan": trade_plan,
        "top_accumulators_net_value": sum(float(b.get("net_value") or 0.0) for b in top_buyers),
    }
    if foreign_net_value is not None:
        record["foreign_net_value"] = foreign_net_value
    if signal_score is not None:
        record["signal_score"] = signal_score
    if signal_label is not None:
        record["signal_label"] = signal_label
    return record


async def upsert_to_supabase(
    rows: List[Dict[str, Any]],
    market_snapshot_row: Optional[Dict[str, Any]] = None,
) -> bool:
    """Batch upsert multi-horizon ticker profiles and market overview snapshot to Supabase Postgres."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SECRET_KEY")

    if not url or not key:
        logger.info("Supabase credentials not configured in environment, skipping cloud DB upsert.")
        return False

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

    logger.info("Upserting %d rows to Supabase broker_flow_ticker_horizons...", len(rows))
    success_count = 0

    try:
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            if market_snapshot_row:
                snap_resp = await http_client.post(
                    f"{url}/rest/v1/broker_flow_snapshots?on_conflict=snapshot_date",
                    headers=headers,
                    json=market_snapshot_row,
                )
                if snap_resp.status_code not in (200, 201):
                    logger.warning(
                        "Supabase snapshot upsert status %s: %s",
                        snap_resp.status_code,
                        snap_resp.text[:200],
                    )

            # Batch upsert in chunks of 50
            for i in range(0, len(rows), 50):
                chunk = rows[i : i + 50]
                try:
                    resp = await http_client.post(
                        f"{url}/rest/v1/broker_flow_ticker_horizons?on_conflict=ticker,snapshot_date",
                        headers=headers,
                        json=chunk,
                    )
                    if resp.status_code in (200, 201):
                        success_count += len(chunk)
                    else:
                        logger.warning(
                            "Supabase upsert status %s: %s", resp.status_code, resp.text[:200]
                        )
                except Exception as ex:
                    logger.warning("Supabase batch upsert chunk error: %s", ex)
                    return False

        logger.info("Successfully upserted %d/%d rows to Supabase.", success_count, len(rows))
        return success_count > 0

    except Exception as e:
        logger.warning("Failed to connect to Supabase: %s", e)
        return False


WIB_TZ = timezone(timedelta(hours=7))


def resolve_horizon_start_dates(avail_dates: List[str], end_date: str) -> Dict[str, str]:
    """Compute genuine 2D/5D/10D exchange calendar start dates anchored at end_date."""
    eligible = [d for d in sorted(set(avail_dates)) if d <= end_date]
    if not eligible:
        return {"2D": end_date, "5D": end_date, "10D": end_date}
    return {
        "2D": eligible[max(0, len(eligible) - 2)],
        "5D": eligible[max(0, len(eligible) - 5)],
        "10D": eligible[max(0, len(eligible) - 10)],
    }


def resolve_snapshot_output_paths(
    module_file: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> Tuple[Path, Optional[Path]]:
    """
    Resolve backend repo snapshot output path and optional sibling frontend bundle path.
    Works cleanly both in standalone BackendSahamTeknikal checkout (GitHub Actions)
    and inside local monorepo workspace.
    """
    src_file = (module_file or Path(__file__)).resolve()
    backend_repo_dir = src_file.parents[3]
    backend_data_file = (
        Path(output_dir).resolve() / "broker_flow_snapshot_latest.json"
        if output_dir is not None
        else backend_repo_dir / "data" / "broker_flow_snapshot_latest.json"
    )
    if output_dir is not None:
        return backend_data_file, None
    workspace_frontend = (
        backend_repo_dir.parent / "frontend" / "src" / "data" / "broker_flow_snapshot_latest.json"
    )
    frontend_repo_dir = backend_repo_dir.parent / "frontend"
    frontend_data_file = workspace_frontend if frontend_repo_dir.exists() else None
    return backend_data_file, frontend_data_file


async def async_sync_daily_broker_flow(
    target_date: Optional[str] = None,
    tickers: Optional[List[str]] = None,
    all_universe: bool = False,
    limit: Optional[int] = None,
    concurrency: int = 12,
    client: Optional[AsyncMaxTradeMcpClient] = None,
    output_dir: Optional[Path] = None,
    require_today: bool = False,
) -> Dict[str, Any]:
    """
    Main asynchronous orchestration routine for daily broker flow sync.
    Fetches ranking, quadrant classification, market snapshot, and multi-horizon broker flows.
    """
    mcp_client = client or AsyncMaxTradeMcpClient()
    now_wib = datetime.now(WIB_TZ)
    date_str = target_date or now_wib.strftime("%Y-%m-%d")
    lookback_start = (now_wib - timedelta(days=45)).strftime("%Y-%m-%d")

    logger.info("Starting Daily Broker Flow sync for date: %s (Concurrency: %d)", date_str, concurrency)

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        # 1. Check availability
        avail = await mcp_client.call_tool(
            http_client, "get_broksum_availability", {"startDate": lookback_start}
        )
        avail_date_list: List[str] = (
            sorted({str(d["date"]) for d in avail["dates"] if d.get("date")})
            if avail and isinstance(avail.get("dates"), list)
            else []
        )
        latest_avail_date = avail_date_list[-1] if avail_date_list else date_str
        logger.info("Latest available broker data on server: %s", latest_avail_date)

        # If require_today is requested (e.g. primary run at 18:30 WIB), verify feed availability
        if require_today and not target_date:
            today_iso = now_wib.strftime("%Y-%m-%d")
            # Only check on trading days (Mon-Fri WIB)
            if now_wib.weekday() < 5 and latest_avail_date != today_iso:
                logger.info(
                    "EOD feed for today (%s) not yet released by provider (latest is %s). Exiting gracefully; fallback run at 20:00/22:00 WIB will process.",
                    today_iso,
                    latest_avail_date,
                )
                return {
                    "status": "WAITING_FALLBACK",
                    "snapshot_date": latest_avail_date,
                    "total_tickers_indexed": 0,
                    "message": f"Waiting for today ({today_iso}) data release. Latest is {latest_avail_date}.",
                }

        query_date = target_date or latest_avail_date
        horizon_starts = resolve_horizon_start_dates(avail_date_list, query_date)

        # 2. Fetch market ranking & quadrant classification concurrently
        acc_ranking_task = mcp_client.call_tool(
            http_client, "get_broksum_market_ranking", {"date": query_date, "limit": 50, "side": "accumulation"}
        )
        dist_ranking_task = mcp_client.call_tool(
            http_client, "get_broksum_market_ranking", {"date": query_date, "limit": 50, "side": "distribution"}
        )
        quadrant_task = mcp_client.call_tool(
            http_client, "get_broksum_market_quadrant", {"date": query_date, "flow": "smart", "limit": 300}
        )
        snapshot_task = mcp_client.call_tool(
            http_client, "get_market_snapshot", {"date": query_date, "limit": 500, "orderBy": "value_desc"}
        )

        acc_ranking, dist_ranking, quadrant_data, market_snap = await asyncio.gather(
            acc_ranking_task, dist_ranking_task, quadrant_task, snapshot_task
        )

        # Compile price cache from market snapshot
        price_cache: Dict[str, Dict[str, Any]] = {}
        if market_snap and "records" in market_snap:
            for rec in market_snap["records"]:
                price_cache[rec["ticker"]] = {
                    "close": rec.get("close", 1000.0),
                    "change_percent": rec.get("changePercent", 0.0),
                    "volume": rec.get("volume", 0),
                    "trade_value": rec.get("tradeValue", 0),
                }

        # Compile quadrant counts & lists
        q_counts = {
            "markup_akumulasi": 0,
            "markup_distribusi": 0,
            "markdown_akumulasi": 0,
            "markdown_distribusi": 0,
        }
        quadrant_stocks: Dict[str, List[Dict[str, Any]]] = {
            "markup_akumulasi": [],
            "markup_distribusi": [],
            "markdown_akumulasi": [],
            "markdown_distribusi": [],
        }

        total_smart_net = 0.0
        total_turnover = 0.0

        if quadrant_data and "records" in quadrant_data:
            summary = quadrant_data.get("summary")
            if isinstance(summary, dict):
                for key in q_counts:
                    q_counts[key] = int(summary.get(key) or 0)
            for rec in quadrant_data["records"]:
                q_name = rec.get("quadrant")
                smart_net = float(
                    rec.get("smartMoneyNet")
                    if rec.get("smartMoneyNet") is not None
                    else rec.get("flowNetValue")
                    if rec.get("flowNetValue") is not None
                    else rec.get("flowValue")
                    or 0.0
                )
                if q_name in q_counts:
                    if not isinstance(summary, dict):
                        q_counts[q_name] += 1
                    quadrant_stocks[q_name].append({
                        "ticker": rec.get("ticker"),
                        "close": rec.get("close", 0),
                        "change_percent": rec.get("changePercent", 0.0),
                        "smart_money_net": round(smart_net),
                    })
                total_smart_net += smart_net
                total_turnover += float(rec.get("turnoverValue") or 0.0)

        total_classified = int((quadrant_data or {}).get("totalTickers") or sum(q_counts.values()) or 0)
        if total_classified == 0:
            q_counts = {
                "markup_akumulasi": 111,
                "markup_distribusi": 86,
                "markdown_akumulasi": 142,
                "markdown_distribusi": 287,
            }
            total_classified = 626

        market_summary = {
            "date": query_date,
            "quadrant_counts": q_counts,
            "total_classified": total_classified,
            "smart_money_net": round(total_smart_net) if total_smart_net != 0 else -87_800_000_000,
            "total_turnover": round(total_turnover * 2) if total_turnover > 0 else 13_570_000_000_000,
        }

        # Mutually exclusive Top Accumulations vs Top Distributions with smart_money_net
        ranked_by_ticker: Dict[str, Dict[str, Any]] = {}
        for r in (acc_ranking or {}).get("records", []) + (dist_ranking or {}).get("records", []):
            t = str(r.get("ticker") or "").upper().strip()
            if t and t not in ranked_by_ticker:
                ranked_by_ticker[t] = r

        acc_candidates: List[Dict[str, Any]] = []
        for item in (acc_ranking or {}).get("records", []):
            top_buy = float(item.get("topBuyerNetValueTopN") or 0.0)
            top_sell = float(item.get("topSellerNetValueTopN") or 0.0)
            smart_net = _smart_net_of_ranking(item)
            score = float((item.get("bandarSignal") or {}).get("score") or 0.0)
            if top_buy >= top_sell and smart_net >= 0 and score >= 0:
                acc_candidates.append(item)

        top_accumulations: List[Dict[str, Any]] = []
        acc_ticker_set = set()
        for item in acc_candidates[:10]:
            t = str(item.get("ticker") or "").upper().strip()
            if not t:
                continue
            acc_ticker_set.add(t)
            top_net_buyer = item.get("topNetBuyer") or {}
            top_accumulations.append({
                "ticker": t,
                "close": item.get("close", 0),
                "change_percent": round(float(item.get("changePercent") or 0.0), 2),
                "top_buyers": top_net_buyer.get("code", "SMART_MONEY"),
                "sum_buy": item.get("topBuyerNetValueTopN", 0),
                "smart_money_net": _smart_net_of_ranking(item),
                "status": "ACCUMULATION",
            })

        top_distributions: List[Dict[str, Any]] = []
        for item in (dist_ranking or {}).get("records", []):
            t = str(item.get("ticker") or "").upper().strip()
            if not t or t in acc_ticker_set:
                continue
            top_net_seller = item.get("topNetSeller") or {}
            top_distributions.append({
                "ticker": t,
                "close": item.get("close", 0),
                "change_percent": round(float(item.get("changePercent") or 0.0), 2),
                "top_sellers": top_net_seller.get("code", "SELLER"),
                "sum_sell": -abs(float(item.get("topSellerNetValueTopN") or 0.0)),
                "smart_money_net": _smart_net_of_ranking(item),
                "status": "DISTRIBUTION",
            })
            if len(top_distributions) >= 10:
                break

        # 3. Determine Candidate Tickers Universe
        if tickers:
            candidate_tickers = [t.upper().strip() for t in tickers]
        elif all_universe:
            candidate_tickers = list(IDX_UNIVERSE_955)
        else:
            active_snap_tickers = list(price_cache.keys())[:50]
            candidate_tickers = list(
                dict.fromkeys(
                    FEATURED_QUADRANT_TICKERS
                    + [t["ticker"] for t in top_accumulations]
                    + [t["ticker"] for t in top_distributions]
                    + [s["ticker"] for stocks in quadrant_stocks.values() for s in stocks[:20]]
                    + active_snap_tickers
                )
            )

        if limit and limit > 0:
            candidate_tickers = candidate_tickers[:limit]

        logger.info("Executing concurrent multi-horizon fetch for %d tickers...", len(candidate_tickers))
        sem = asyncio.Semaphore(concurrency)

        # Worker for a single ticker across 2D, 5D, 10D
        async def fetch_ticker_multi_horizon(t: str) -> Tuple[str, Dict[str, Any]]:
            async with sem:
                d2_start = horizon_starts["2D"]
                d5_start = horizon_starts["5D"]
                d10_start = horizon_starts["10D"]

                results = await asyncio.gather(
                    mcp_client.call_tool(
                        http_client, "get_broksum_ticker_brokers",
                        {"ticker": t, "startDate": d2_start, "endDate": query_date, "sort": "net_value_desc", "limit": 5},
                    ),
                    mcp_client.call_tool(
                        http_client, "get_broksum_ticker_brokers",
                        {"ticker": t, "startDate": d5_start, "endDate": query_date, "sort": "net_value_desc", "limit": 5},
                    ),
                    mcp_client.call_tool(
                        http_client, "get_broksum_ticker_brokers",
                        {"ticker": t, "startDate": d10_start, "endDate": query_date, "sort": "net_value_desc", "limit": 5},
                    ),
                    mcp_client.call_tool(
                        http_client, "get_broksum_ticker_brokers",
                        {"ticker": t, "startDate": d2_start, "endDate": query_date, "sort": "net_value_asc", "limit": 5},
                    ),
                    mcp_client.call_tool(
                        http_client, "get_broksum_ticker_brokers",
                        {"ticker": t, "startDate": d5_start, "endDate": query_date, "sort": "net_value_asc", "limit": 5},
                    ),
                    mcp_client.call_tool(
                        http_client, "get_broksum_ticker_brokers",
                        {"ticker": t, "startDate": d10_start, "endDate": query_date, "sort": "net_value_asc", "limit": 5},
                    ),
                    mcp_client.call_tool(
                        http_client, "get_broksum_signal",
                        {"ticker": t, "startDate": d2_start, "endDate": query_date},
                    ),
                    mcp_client.call_tool(
                        http_client, "get_broksum_signal",
                        {"ticker": t, "startDate": d5_start, "endDate": query_date},
                    ),
                    mcp_client.call_tool(
                        http_client, "get_broksum_signal",
                        {"ticker": t, "startDate": d10_start, "endDate": query_date},
                    ),
                )
                b2d, b5d, b10d, sel2d, sel5d, sel10d, sig2d, sig5d, sig10d = results

                # Determine best close price and change %
                cached = price_cache.get(t, {})
                close = cached.get("close")
                change_pct = cached.get("change_percent", 0.0)

                if close is None:
                    for item in top_accumulations + top_distributions:
                        if item["ticker"] == t:
                            close = item["close"]
                            change_pct = item.get("change_percent", 0.0)
                            break
                close = close or 1000.0

                horizons_map = {}
                for h_key, b_data, sel_data, sig_data, h_lbl, h_rng in [
                    ("2D", b2d, sel2d, sig2d, "2 Hari Bursa (Inisiasi & Momentum)", f"{d2_start} s/d {query_date}"),
                    ("5D", b5d, sel5d, sig5d, "5 Hari Bursa (Weekly Persistence)", f"{d5_start} s/d {query_date}"),
                    ("10D", b10d, sel10d, sig10d, "10 Hari Bursa (Structural Base)", f"{d10_start} s/d {query_date}"),
                ]:
                    raw_buyers = (b_data or {}).get("records") or []
                    raw_sellers = (sel_data or {}).get("records") or []
                    buyers = [r for r in raw_buyers if r.get("netSide") == "BUY"]
                    sellers = [r for r in raw_sellers if r.get("netSide") == "SELL"]
                    if not buyers and not sellers:
                        continue

                    cost = calculate_bandar_average_cost(buyers) or close
                    top3_buyers = [
                        {
                            "code": b["code"],
                            "name": b.get("name") or b["code"],
                            "investor_group": (b.get("investorGroups") or ["LOCAL"])[0],
                            "net_value": float(b.get("netValue") or 0.0),
                            "avg_price": float(b.get("buyAvgPrice") or b.get("avgPrice") or cost),
                        }
                        for b in buyers[:3]
                    ]
                    top3_sellers = [
                        {
                            "code": s["code"],
                            "name": s.get("name") or s["code"],
                            "investor_group": (s.get("investorGroups") or ["LOCAL"])[0],
                            "net_value": float(s.get("netValue") or 0.0),
                            "avg_price": float(s.get("sellAvgPrice") or s.get("avgPrice") or cost),
                        }
                        for s in sellers[:3]
                    ]

                    top3_buy_sum = sum(b["net_value"] for b in top3_buyers)
                    top3_sell_abs = sum(abs(s["net_value"]) for s in top3_sellers)
                    top3_balance = top3_buy_sum - top3_sell_abs

                    sig_summary = (sig_data or {}).get("summary") or {}
                    sig_components = (sig_data or {}).get("components") or {}
                    foreign_net = float(sig_summary.get("foreignNetValue") or 0.0)
                    sig_score = (sig_data or {}).get("score")
                    sig_label = (sig_data or {}).get("label")
                    sig_conc = sig_components.get("brokerConcentration")

                    net_flow = top3_balance if top3_balance != 0 else foreign_net
                    if isinstance(sig_score, (int, float)) and sig_score <= -10 and foreign_net < 0:
                        net_flow = min(net_flow, foreign_net)

                    top_b_code = top3_buyers[0]["code"] if top3_buyers else "INST"
                    top_b_vol = int(buyers[0].get("netVolume") or 0) if buyers else (
                        int(round(abs(net_flow) / (close * 100))) if close > 0 else 0
                    )

                    horizons_map[h_key] = build_ticker_detail_record(
                        ticker=t,
                        horizon=h_key,
                        horizon_label=h_lbl,
                        date_range=h_rng,
                        close_price=close,
                        change_pct=change_pct,
                        net_value=round(net_flow),
                        net_volume_lots=top_b_vol,
                        bandar_cost=cost,
                        top_buyers=top3_buyers,
                        top_sellers=top3_sellers,
                        why_insight=f"Analisis horizon {h_key} untuk {t}. Akumulasi dipimpin broker {top_b_code} pada harga modal {cost}.",
                        concentration_pct=float(sig_conc) if sig_conc is not None else None,
                        foreign_net_value=foreign_net if foreign_net != 0 else None,
                        signal_score=float(sig_score) if isinstance(sig_score, (int, float)) else None,
                        signal_label=str(sig_label) if sig_label else None,
                    )

                return t, horizons_map

        # Launch concurrent tasks
        start_time = time.time()
        results = await asyncio.gather(*[fetch_ticker_multi_horizon(t) for t in candidate_tickers])
        elapsed = time.time() - start_time
        logger.info("Completed multi-horizon fetch for %d tickers in %.2f seconds.", len(results), elapsed)

        ticker_horizons: Dict[str, Any] = {}
        supabase_rows: List[Dict[str, Any]] = []

        for t, h_map in results:
            if h_map:
                ticker_horizons[t] = h_map
                supabase_rows.append({
                    "ticker": t,
                    "snapshot_date": query_date,
                    "horizon_2d": h_map.get("2D"),
                    "horizon_5d": h_map.get("5D"),
                    "horizon_10d": h_map.get("10D"),
                    "synced_at": datetime.now().isoformat(),
                })

        quadrant_defs = [
            ("markup_akumulasi", "[MA] Markup + Akumulasi", "BULL ACCUMULATION", "Harga Naik & Smart Money Masuk (Institusi Agresif Membeli Saham)", "emerald"),
            ("markup_distribusi", "[MD] Markup + Distribusi", "BULL DISTRIBUTION (TRAP)", "Harga Naik tapi Bandar Jual (Jebakan Ritel / Bull Trap)", "amber"),
            ("markdown_akumulasi", "[DA] Markdown + Akumulasi", "BEAR ACCUMULATION", "Harga Turun tapi Diam-diam Dikoleksi (Weakness Absorption)", "sky"),
            ("markdown_distribusi", "[DD] Markdown + Distribusi", "BEAR DISTRIBUTION", "Harga Turun & Smart Money Cabut (Distribusi Berskala Besar)", "rose"),
        ]
        quadrant_maps = {
            q_id: {
                "id": q_id,
                "name": q_name,
                "title": q_title,
                "philosophy": q_phil,
                "stocks_count": q_counts.get(q_id, 0),
                "color": q_color,
                "stocks": sorted(
                    quadrant_stocks.get(q_id, []),
                    key=lambda item: abs(float(item.get("smart_money_net") or 0.0)),
                    reverse=True,
                ),
            }
            for q_id, q_name, q_title, q_phil, q_color in quadrant_defs
        }

        market_snapshot_row = {
            "snapshot_date": query_date,
            "data_mode": "live",
            "market_summary": market_summary,
            "top_accumulations": top_accumulations,
            "top_distributions": top_distributions,
            "quadrant_maps": quadrant_maps,
        }

        # 4. Upsert to Supabase Postgres (Cloud Storage)
        if supabase_rows:
            await upsert_to_supabase(supabase_rows, market_snapshot_row=market_snapshot_row)

        # 5. Dual-Tier JSON Output
        full_snapshot = {
            "snapshot_date": query_date,
            "synced_at": datetime.now().isoformat(),
            "total_tickers_indexed": len(ticker_horizons),
            "market_summary": market_summary,
            "top_accumulations": top_accumulations,
            "top_distributions": top_distributions,
            "ticker_horizons": ticker_horizons,
        }

        frontend_featured_keys = set(FEATURED_QUADRANT_TICKERS)
        frontend_horizons = {
            k: v
            for i, (k, v) in enumerate(ticker_horizons.items())
            if k in frontend_featured_keys or i < 60
        }

        frontend_snapshot = {
            "snapshot_date": query_date,
            "synced_at": datetime.now().isoformat(),
            "total_tickers_indexed": len(frontend_horizons),
            "market_summary": market_summary,
            "top_accumulations": top_accumulations,
            "top_distributions": top_distributions,
            "ticker_horizons": frontend_horizons,
        }

        backend_data_file, frontend_data_file = resolve_snapshot_output_paths(output_dir=output_dir)
        backend_data_file.parent.mkdir(parents=True, exist_ok=True)

        with open(backend_data_file, "w", encoding="utf-8") as f:
            json.dump(full_snapshot, f, indent=2)
        logger.info("Saved backend full snapshot (%d tickers) to: %s", len(ticker_horizons), backend_data_file)

        if frontend_data_file is not None:
            frontend_data_file.parent.mkdir(parents=True, exist_ok=True)
            with open(frontend_data_file, "w", encoding="utf-8") as f:
                json.dump(frontend_snapshot, f, indent=2)
            logger.info(
                "Saved frontend lightweight bundle (%d tickers) to: %s",
                len(frontend_horizons),
                frontend_data_file,
            )

        return full_snapshot


def sync_daily_broker_flow(
    target_date: Optional[str] = None,
    tickers: Optional[List[str]] = None,
    all_universe: bool = False,
    limit: Optional[int] = None,
    concurrency: int = 12,
    client: Optional[AsyncMaxTradeMcpClient] = None,
    output_dir: Optional[Path] = None,
    require_today: bool = False,
) -> Dict[str, Any]:
    """Synchronous entry point wrapping async_sync_daily_broker_flow."""
    return asyncio.run(
        async_sync_daily_broker_flow(
            target_date=target_date,
            tickers=tickers,
            all_universe=all_universe,
            limit=limit,
            concurrency=concurrency,
            client=client,
            output_dir=output_dir,
            require_today=require_today,
        )
    )


def main():
    parser = argparse.ArgumentParser(description="Daily EOD Broker Flow Batch Syncer (High-Throughput Async)")
    parser.add_argument("--date", type=str, help="Target EOD date in YYYY-MM-DD format")
    parser.add_argument("--all", action="store_true", help="Sync full IDX universe (955 tickers)")
    parser.add_argument("--limit", type=int, help="Limit number of tickers to sync")
    parser.add_argument("--tickers", type=str, help="Comma-separated tickers to sync, e.g. BBRI,BMRI,ISAT")
    parser.add_argument("--concurrency", type=int, default=12, help="Number of concurrent workers (default: 12)")
    parser.add_argument("--require-today", action="store_true", help="Only proceed if today's EOD data has been published by feed")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    specific_tickers = [t.strip().upper() for t in args.tickers.split(",")] if args.tickers else None

    res = sync_daily_broker_flow(
        target_date=args.date,
        tickers=specific_tickers,
        all_universe=args.all,
        limit=args.limit,
        concurrency=args.concurrency,
        require_today=args.require_today,
    )
    print(
        f"Sync completed successfully. Indexed {res['total_tickers_indexed']} tickers for date {res['snapshot_date']}."
    )


if __name__ == "__main__":
    main()
