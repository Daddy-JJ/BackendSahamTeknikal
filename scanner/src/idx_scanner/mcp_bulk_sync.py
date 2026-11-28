"""
Redeveloped Max Trade MCP Bulk Synchronizer & v2 Screener Pipeline.

Pulls complete market data directly from Max Trade MCP without truncation:
1. All 11 IDX Sectors + market_cap + free_float_pct via run_fundamental_screening
2. Multi-year EOD OHLCV history (2023-01-02 to latest) via chunked get_eod_bulk_history signed CSVs
3. IHSG full OHLCV history via get_ihsg_history
4. Complete market-wide Broksum + Quadrants + Confidence/Alignment across ALL 831 tickers
   via VPS run_flexible_screening (bypassing the 128 KiB single-call truncation cap)
5. Runs technical_rules (FRACTAL_BREAKOUT, MACD_EMA200, G_ACC),
   Smart Money Scoring (3 factors), Regime Detection, IHSG Contributors/Draggers,
   11 Sector Snapshots, and Win Rate Evaluation across 2026 history, then upserts into Supabase.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import logging
import os
import time
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from idx_scanner.smart_money import (
    compute_ihsg_contributors,
    compute_smart_money_score,
    sector_to_slug,
)
from idx_scanner.technical_rules import (
    Bar,
    classify_ihsg_regime,
    classify_stock_regime,
    compute_pivot_points,
    detect_ticker_signals_history,
    ema_series,
    supertrend_series,
)

logger = logging.getLogger("mcp_bulk_sync")

DEFAULT_MCP_URL = "https://eod.maxlong.my.id/mcp"

IDX_SECTORS = [
    "Basic Materials",
    "Consumer Cyclicals",
    "Consumer Non-Cyclicals",
    "Energy",
    "Financials",
    "Healthcare",
    "Industrials",
    "Infrastructures",
    "Properties & Real Estate",
    "Technology",
    "Transportation & Logistic",
]


def load_local_envs() -> Dict[str, str]:
    """Load backend/.env and backend/.env.production-operator.local if present."""
    env_map: Dict[str, str] = {}
    root = Path(__file__).resolve().parents[3]  # backend/
    for fname in (".env", ".env.production-operator.local"):
        fpath = root / fname
        if fpath.is_file():
            for line in fpath.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env_map.setdefault(k.strip(), v.strip())
                os.environ.setdefault(k.strip(), v.strip())
    return env_map


class McpClient:
    def __init__(self, url: Optional[str] = None, token: Optional[str] = None):
        load_local_envs()
        self.url = url or os.getenv("MAX_TRADE_MCP_URL") or DEFAULT_MCP_URL
        self.token = (token or os.getenv("MAX_TRADE_MCP_TOKEN") or "").strip()
        if not self.token:
            raise RuntimeError("MAX_TRADE_MCP_TOKEN is not configured in environment.")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

    async def call_tool(
        self,
        client: httpx.AsyncClient,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: float = 45.0,
    ) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        last_exc: Optional[Exception] = None
        for attempt in range(4):
            try:
                resp = await client.post(self.url, headers=self._headers(), json=payload, timeout=timeout)
                if resp.status_code in (429, 502, 503, 504) and attempt < 3:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                resp.raise_for_status()
                text = resp.text
                if text.startswith("event:") or text.startswith("data:"):
                    for line in text.splitlines():
                        if line.startswith("data:"):
                            raw = line[5:].strip()
                            if not raw or raw == "[DONE]":
                                continue
                            return self._unwrap_rpc_result(tool_name, json.loads(raw))
                return self._unwrap_rpc_result(tool_name, resp.json())
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                if attempt < 3 and (status_code is None or status_code in (429, 502, 503, 504)):
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                raise
        raise RuntimeError(f"MCP retries exhausted for {tool_name}: {last_exc}")

    @staticmethod
    def _unwrap_rpc_result(tool_name: str, payload: Dict[str, Any]) -> Any:
        if "error" in payload:
            raise RuntimeError(f"MCP error {tool_name}: {payload['error']}")
        res = payload.get("result", {})
        content = res.get("content", [])
        if content and content[0].get("type") == "text":
            txt = content[0].get("text", "")
            if res.get("isError"):
                raise RuntimeError(f"MCP tool error {tool_name}: {txt[:300]}")
            try:
                return json.loads(txt)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"MCP non-JSON response from {tool_name}: {txt[:240]}"
                ) from exc
        if res.get("isError"):
            raise RuntimeError(f"MCP tool error {tool_name}: {res}")
        return res


def apply_supabase_migration() -> None:
    """Apply pending SQL migration via Supabase CLI (`supabase db push --remote`)."""
    load_local_envs()
    backend_dir = Path(__file__).resolve().parents[3]
    sql_path = (
        backend_dir
        / "supabase"
        / "migrations"
        / "20261128125100_redevelop_screener_v2.sql"
    )
    import subprocess
    proc = subprocess.run(
        ["npx", "--yes", "supabase", "db", "push", "--workdir", str(backend_dir), "--remote", "--include-all", "--yes"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"supabase db push failed ({proc.returncode}): {proc.stderr or proc.stdout}")
    logger.info("Applied migration cleanly via Supabase CLI: %s", sql_path.name)


async def fetch_all_ticker_fundamentals(
    client: httpx.AsyncClient, mcp: McpClient
) -> Dict[str, Dict[str, Any]]:
    """Fetch sector, market_cap, and free_float_pct for all IDX tickers via run_fundamental_screening."""
    master: Dict[str, Dict[str, Any]] = {}

    async def fetch_sector(sec: str) -> None:
        offset = 0
        while True:
            res = await mcp.call_tool(
                client,
                "run_fundamental_screening",
                {
                    "sectors": [sec],
                    "filterGroups": [{"rules": [{"metric": "market_cap", "op": "gte", "value": 0}]}],
                    "columns": ["market_cap", "free_float_pct"],
                    "limit": 40,
                    "offset": offset,
                },
            )
            recs = res.get("records") or []
            for r in recs:
                t = str(r.get("ticker") or "").upper().strip()
                if not t:
                    continue
                vals = r.get("values") or {}
                mcap = vals.get("market_cap")
                ff = vals.get("free_float_pct")
                sec_name = str(r.get("sector") or sec)
                master[t] = {
                    "ticker": t,
                    "sector": sec_name,
                    "sector_slug": sector_to_slug(sec_name),
                    "market_cap": float(mcap) if mcap is not None else None,
                    "free_float_pct": float(ff) if ff is not None else None,
                    "weight_proxy": (
                        float(mcap) * (float(ff) / 100.0 if ff and float(ff) > 0 else 0.50)
                        if mcap
                        else None
                    ),
                }
            pag = res.get("pagination") or {}
            next_off = pag.get("nextOffset")
            if next_off is None or not recs:
                break
            offset = int(next_off)

    # Fetch each official IDX sector concurrently (bounded)
    await asyncio.gather(*[fetch_sector(s) for s in IDX_SECTORS])
    logger.info("Loaded fundamental sector & cap metadata for %d tickers.", len(master))
    return master


async def fetch_ihsg_bars(client: httpx.AsyncClient, mcp: McpClient, total_bars: int = 960) -> List[Bar]:
    """Fetch full chronological IHSG history up to total_bars using descending pagination."""
    all_recs: List[Dict[str, Any]] = []
    end_date: Optional[str] = None
    while len(all_recs) < total_bars:
        args: Dict[str, Any] = {"limit": 500, "order": "desc"}
        if end_date:
            args["endDate"] = end_date
        res = await mcp.call_tool(client, "get_ihsg_history", args)
        recs = res.get("records") or []
        if not recs:
            break
        all_recs.extend(recs)
        if not res.get("hasMore") or not res.get("nextEndDate"):
            break
        end_date = str(res["nextEndDate"])

    by_date: Dict[str, Bar] = {}
    for r in all_recs:
        d = str(r.get("date") or "")
        if not d:
            continue
        b = Bar(
            date=d,
            open=float(r.get("open") or r.get("close") or 0),
            high=float(r.get("high") or r.get("close") or 0),
            low=float(r.get("low") or r.get("close") or 0),
            close=float(r.get("close") or 0),
            volume=float(r.get("volume") or 0),
            trade_value=float(r.get("tradeValue") or 0),
            nbsa=float(r.get("nbsa") or 0),
        )
        if b.valid():
            by_date[d] = b
    ordered = [by_date[d] for d in sorted(by_date)]
    logger.info("Fetched %d valid IHSG daily bars (%s .. %s).", len(ordered), ordered[0].date if ordered else "-", ordered[-1].date if ordered else "-")
    return ordered


async def fetch_eod_bulk_all_tickers(
    client: httpx.AsyncClient,
    mcp: McpClient,
    earliest_date: str,
    latest_date: str,
    trading_dates: Optional[List[str]] = None,
) -> Dict[str, List[Bar]]:
    """
    Download complete EOD OHLCV CSV across all IDX tickers in <=250 trading day chunks
    from earliest_date to latest_date using verified IDX trading dates.
    """
    windows: List[Tuple[str, str]] = []
    filtered_dates = sorted(
        d for d in (trading_dates or []) if earliest_date <= d <= latest_date
    )
    if filtered_dates:
        chunk_size = 240
        for idx in range(0, len(filtered_dates), chunk_size):
            chunk = filtered_dates[idx : idx + chunk_size]
            windows.append((chunk[0], chunk[-1]))
    else:
        from datetime import timedelta

        end_dt = date.fromisoformat(latest_date)
        earliest_dt = date.fromisoformat(earliest_date)
        cur_end = end_dt
        while cur_end >= earliest_dt:
            cur_start = max(earliest_dt, cur_end - timedelta(days=340))
            windows.append((cur_start.isoformat(), cur_end.isoformat()))
            cur_end = cur_start - timedelta(days=1)
        windows.sort()

    bars_by_ticker: Dict[str, Dict[str, Bar]] = defaultdict(dict)

    async def download_window(s_date: str, e_date: str) -> None:
        meta = await mcp.call_tool(
            client,
            "get_eod_bulk_history",
            {"startDate": s_date, "endDate": e_date, "minRecords": 1},
            timeout=60.0,
        )
        dl_url = meta.get("downloadUrl")
        if not dl_url:
            logger.warning("No downloadUrl for window %s..%s", s_date, e_date)
            return
        csv_resp = await client.get(dl_url, timeout=90.0)
        csv_resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(csv_resp.text))
        for row in reader:
            d = (row.get("<date>") or row.get("date") or "").strip()
            t = (row.get("<ticker>") or row.get("ticker") or "").strip().upper()
            if not d or not t or t == "IHSG":
                continue
            try:
                b = Bar(
                    date=d,
                    open=float(row.get("<open>") or row.get("open") or 0),
                    high=float(row.get("<high>") or row.get("high") or 0),
                    low=float(row.get("<low>") or row.get("low") or 0),
                    close=float(row.get("<close>") or row.get("close") or 0),
                    volume=float(row.get("<volume>") or row.get("volume") or 0),
                    trade_value=float(row.get("<valuasi>") or row.get("tradeValue") or 0),
                    nbsa=float(row.get("<nbsa>") or row.get("nbsa") or 0),
                )
                if b.valid():
                    bars_by_ticker[t][d] = b
            except (TypeError, ValueError):
                continue

    for s_date, e_date in windows:
        logger.info("Downloading EOD bulk CSV window %s .. %s ...", s_date, e_date)
        await download_window(s_date, e_date)

    final_bars = {
        t: [by_d[d] for d in sorted(by_d)] for t, by_d in bars_by_ticker.items() if by_d
    }
    logger.info("Loaded EOD history for %d tickers.", len(final_bars))
    return final_bars


FLEX_BROKSUM_SCRIPT = r"""
import csv, gzip, json
from collections import defaultdict

with open('/job/input/manifest.json') as f:
    manifest = json.load(f)

dates = sorted(manifest.get('broksumDates') or manifest.get('dates') or [])
target_date = manifest.get('endDate') or (dates[-1] if dates else '')

eod_by_dt = {}
eod_prev = defaultdict(list)
with open('/job/input/eod.csv', newline='') as f:
    for row in csv.DictReader(f):
        t = (row.get('ticker') or '').strip().upper()
        d = (row.get('date') or '').strip()
        if not t or not d:
            continue
        c = float(row.get('close') or 0)
        eod_prev[t].append((d, c, float(row.get('tradeValue') or 0), float(row.get('nbsa') or 0)))
        if d == target_date:
            eod_by_dt[t] = (c, float(row.get('tradeValue') or 0), float(row.get('nbsa') or 0))

chg_by_t = {}
for t, seq in eod_prev.items():
    seq.sort(key=lambda x: x[0])
    if len(seq) >= 2 and seq[-1][0] == target_date and seq[-2][1] > 0:
        chg_by_t[t] = round((seq[-1][1] - seq[-2][1]) / seq[-2][1] * 100.0, 2)
    else:
        chg_by_t[t] = 0.0

# Track broker aggregates per (date, ticker)
dt_stats = defaultdict(lambda: {'f': 0.0, 'g': 0.0, 'l': 0.0, 'tot': 0.0, 'brokers': defaultdict(lambda: [0.0, 0.0, 0.0, 'LOCAL'])})

with gzip.open('/job/input/broksum.jsonl.gz', 'rt', encoding='utf-8') as f:
    for line in f:
        r = json.loads(line)
        d = r.get('date')
        t = str(r.get('ticker') or '').upper()
        if not d or not t:
            continue
        b = r.get('broker') or {}
        code = str(b.get('code') or '')
        grp = str(r.get('investorGroup') or 'LOCAL').upper()
        val = float(r.get('value') or 0.0)
        vol = float(r.get('volume') or 0.0)
        side = str(r.get('transactionType') or '').upper()
        signed = val if side == 'BUY' else -val
        st = dt_stats[(d, t)]
        st['tot'] += val
        if grp == 'FOREIGN':
            st['f'] += signed
        elif grp == 'GOVERNMENT':
            st['g'] += signed
        else:
            st['l'] += signed
        br = st['brokers'][code]
        br[0] += signed
        br[1] += (val if side == 'BUY' else 0.0)
        br[2] += (vol if side == 'BUY' else 0.0)
        br[3] = grp

# Also compute 20D/10D bandar_value history for target_date alignment check
bandar_hist = defaultdict(list)
records = []
# Emit full latest-date metrics for ALL tickers AND historical compact markers for signal days
for (d, t), st in sorted(dt_stats.items()):
    sorted_b = sorted(st['brokers'].items(), key=lambda x: x[1][0], reverse=True)
    top_buy = [x for x in sorted_b if x[1][0] > 0][:3]
    top_sell = [x for x in sorted_b if x[1][0] < 0][-3:]
    top_sell.reverse()
    buy_sum = sum(x[1][0] for x in top_buy)
    sell_sum = sum(abs(x[1][0]) for x in top_sell)
    bandar_val = buy_sum - sell_sum
    turnover = st['tot'] / 2.0 if st['tot'] > 0 else 0.0
    acc_pct = round(buy_sum / turnover * 100.0, 2) if turnover > 0 else 0.0
    dist_pct = round(sell_sum / turnover * 100.0, 2) if turnover > 0 else 0.0
    smart_net = round(st['f'] + st['g'])
    conc_pct = round((top_buy[0][1][0] / turnover * 100.0), 2) if top_buy and turnover > 0 else 0.0

    # Weighted bandar avg cost across top 3 buyers
    cost_val = sum(x[1][1] for x in top_buy)
    cost_vol = sum(x[1][2] for x in top_buy) * 100.0
    avg_cost = round(cost_val / cost_vol, 2) if cost_vol > 0 else 0.0

    if bandar_val > 0 and acc_pct >= 20:
        label = 'STRONG_ACCUMULATION' if conc_pct >= 15 or st['f'] > 0 else 'ACCUMULATION'
    elif bandar_val < 0 and dist_pct >= 20:
        label = 'DISTRIBUTION'
    else:
        label = 'MIXED_NEUTRAL'

    # Confidence heuristic aligned with MCP component agreement & concentration
    conf = min(95.0, round(30.0 + min(30.0, conc_pct * 1.2) + (20.0 if (st['f'] > 0 and bandar_val > 0) or (st['f'] < 0 and bandar_val < 0) else 0.0) + min(15.0, abs(acc_pct - dist_pct) * 0.5), 1))

    bandar_hist[t].append((d, bandar_val))

    if d == target_date:
        c_val = eod_by_dt.get(t, (0.0, turnover, 0.0))[0]
        chg = chg_by_t.get(t, 0.0)
        q = ('markup_akumulasi' if smart_net >= 0 else 'markup_distribusi') if chg >= 0 else ('markdown_akumulasi' if smart_net >= 0 else 'markdown_distribusi')
        records.append({
            'kind': 'latest',
            'd': d,
            't': t,
            'c': c_val,
            'chg': chg,
            'tv': round(turnover),
            'fn': round(st['f']),
            'gn': round(st['g']),
            'sn': smart_net,
            'bv': round(bandar_val),
            'bc': avg_cost,
            'acc': acc_pct,
            'dist': dist_pct,
            'conc': conc_pct,
            'conf': conf,
            'lbl': label,
            'q': q,
            'tb': ','.join(x[0] for x in top_buy[:2])
        })

# Attach recent 10D MA of bandarValue for latest rows
for rec in records:
    seq = [x[1] for x in bandar_hist.get(rec['t'], [])[-10:]]
    rec['bv_ma10'] = round(sum(seq) / len(seq)) if seq else 0

print(json.dumps({
    'summary': {'target_date': target_date, 'latest_count': len(records)},
    'records': records
}))
"""


async def _run_and_collect_flex_job(
    client: httpx.AsyncClient,
    mcp: McpClient,
    tool_args: Dict[str, Any],
    max_polls: int = 60,
    raise_on_fail: bool = True,
) -> List[Dict[str, Any]]:
    """Submit a run_flexible_screening job, poll until COMPLETED, and paginate all rows."""
    job: Dict[str, Any] = {}
    for q_attempt in range(8):
        try:
            job = await mcp.call_tool(client, "run_flexible_screening", tool_args, timeout=30.0)
            break
        except RuntimeError as exc:
            if "queue is full" in str(exc).lower() and q_attempt < 7:
                await asyncio.sleep(5.0)
                continue
            if raise_on_fail:
                raise
            logger.warning("Flexible screening submit error: %s", exc)
            return []

    job_id = job.get("jobId")
    if not job_id:
        if raise_on_fail:
            raise RuntimeError(f"Failed to submit flexible screening job: {job}")
        return []

    res: Dict[str, Any] = {}
    for _ in range(max_polls):
        await asyncio.sleep(max(1.5, float(res.get("pollAfterSeconds") or 2.0)))
        res = await mcp.call_tool(client, "get_flexible_screening", {"jobId": job_id, "limit": 40, "offset": 0})
        status = str(res.get("status") or "").upper()
        if status == "COMPLETED":
            break
        if status in ("FAILED", "ERROR", "CANCELLED"):
            logger.warning("Flexible screening job %s %s: %s", job_id, status, res.get("error") or res)
            if raise_on_fail:
                raise RuntimeError(f"Flexible screening job failed: {res.get('error') or res}")
            return []
    else:
        if raise_on_fail:
            raise TimeoutError(f"Timed out polling flexible screening job {job_id} (last status={res.get('status')}).")
        return []

    all_records: List[Dict[str, Any]] = list(res.get("records") or [])
    total = int(res.get("totalMatches") or res.get("totalRecords") or len(all_records))
    next_off = (res.get("pagination") or {}).get("nextOffset")
    while next_off is not None and len(all_records) < total:
        page = await mcp.call_tool(
            client,
            "get_flexible_screening",
            {"jobId": job_id, "limit": 40, "offset": int(next_off)},
        )
        recs = page.get("records") or []
        if not recs:
            break
        all_records.extend(recs)
        next_off = (page.get("pagination") or {}).get("nextOffset")
    return all_records


async def fetch_full_market_broksum_via_vps(
    client: httpx.AsyncClient, mcp: McpClient, start_date: str, end_date: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Run VPS flexible screening over broksum + eod for end_date (with 15D window for MA10 alignment),
    returning FULL coverage (~831 tickers) without 37-row truncation. Also fetches paginated MaX Screener.
    """
    all_records = await _run_and_collect_flex_job(
        client,
        mcp,
        {
            "name": f"sahamteknikal_full_broksum_{end_date}",
            "datasets": ["eod", "broksum"],
            "startDate": start_date,
            "endDate": end_date,
            "code": FLEX_BROKSUM_SCRIPT,
        },
        max_polls=60,
        raise_on_fail=True,
    )

    # Fetch active signals from get_screener_max (filtered to signals only so pagination is compact)
    max_sig_res = await mcp.call_tool(
        client, "get_screener_max", {"filter": "signals", "limit": 200, "sort": "score_desc"}
    )
    max_signals = max_sig_res.get("records") or []
    logger.info(
        "Fetched full VPS Broksum for %d tickers + %d active MaX Screener signals.",
        len(all_records),
        len(max_signals),
    )
    return all_records, max_signals


async def enrich_candidates_with_live_broksum_signals(
    client: httpx.AsyncClient, mcp: McpClient, tickers: List[str], cutoff_date: str
) -> Dict[str, Dict[str, Any]]:
    """Fetch exact MCP get_broksum_signal (confidence, foreignFlow, alignment) for active candidates."""
    sem = asyncio.Semaphore(10)
    out: Dict[str, Dict[str, Any]] = {}

    async def one(t: str) -> None:
        async with sem:
            try:
                sig = await mcp.call_tool(
                    client,
                    "get_broksum_signal",
                    {"ticker": t, "startDate": cutoff_date, "endDate": cutoff_date},
                    timeout=15.0,
                )
                fac = await mcp.call_tool(
                    client,
                    "get_bandarmology_factors",
                    {"ticker": t, "endDate": cutoff_date},
                    timeout=15.0,
                )
                latest_fac = (fac or {}).get("latest") or {}
                out[t] = {
                    "confidence": (sig or {}).get("confidence"),
                    "label": (sig or {}).get("label"),
                    "score": (sig or {}).get("score"),
                    "evidence": (sig or {}).get("evidence") or {},
                    "summary": (sig or {}).get("summary") or {},
                    "bandar_value": latest_fac.get("bandarValue"),
                    "bandar_value_ma10": latest_fac.get("bandarValueMa10"),
                    "bandar_avg_cost": None,
                }
                buyers = latest_fac.get("topNetBuyers") or []
                tot_v = sum(float(b.get("buyValue") or 0) for b in buyers)
                tot_l = sum(float(b.get("buyVolume") or 0) for b in buyers) * 100.0
                if tot_l > 0:
                    out[t]["bandar_avg_cost"] = round(tot_v / tot_l, 2)
            except Exception as exc:
                logger.debug("Enrich failed for %s: %s", t, exc)

    await asyncio.gather(*[one(t) for t in sorted(set(tickers))])
    return out


async def supabase_upsert(
    client: httpx.AsyncClient, table: str, rows: List[Dict[str, Any]], on_conflict: str, batch_size: int = 200
) -> None:
    if not rows:
        return
    supa_url = os.environ["SUPABASE_URL"]
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_SECRET_KEY"]
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    endpoint = f"{supa_url}/rest/v1/{table}?on_conflict={on_conflict}"
    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        resp = await client.post(endpoint, headers=headers, json=chunk, timeout=45.0)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Supabase upsert {table} failed ({resp.status_code}): {resp.text[:300]}")


FLEX_HISTORY_ENRICH_TEMPLATE = r"""
import gzip, json
from collections import defaultdict

RAW_BY_DATE = __TARGET_BY_DATE__
TARGET_BY_DATE = {d: set(ts.split(',')) for d, ts in RAW_BY_DATE.items() if ts}
TARGET_TICKERS = {t for ts in TARGET_BY_DATE.values() for t in ts}

dt_stats = defaultdict(lambda: {'f': 0.0, 'g': 0.0, 'tot': 0.0, 'brokers': defaultdict(lambda: [0.0, 0.0, 0.0])})

with gzip.open('/job/input/broksum.jsonl.gz', 'rt', encoding='utf-8') as f:
    for line in f:
        r = json.loads(line)
        d = r.get('date')
        day_tickers = TARGET_BY_DATE.get(d)
        if not day_tickers:
            continue
        t = str(r.get('ticker') or '').upper()
        if t not in day_tickers:
            continue
        b = r.get('broker') or {}
        code = str(b.get('code') or '')
        grp = str(r.get('investorGroup') or 'LOCAL').upper()
        val = float(r.get('value') or 0.0)
        vol = float(r.get('volume') or 0.0)
        side = str(r.get('transactionType') or '').upper()
        signed = val if side == 'BUY' else -val
        st = dt_stats[(d, t)]
        st['tot'] += val
        if grp == 'FOREIGN':
            st['f'] += signed
        elif grp == 'GOVERNMENT':
            st['g'] += signed
        br = st['brokers'][code]
        br[0] += signed
        br[1] += (val if side == 'BUY' else 0.0)
        br[2] += (vol if side == 'BUY' else 0.0)

records = []
for (d, t), st in sorted(dt_stats.items()):
    sorted_b = sorted(st['brokers'].items(), key=lambda x: x[1][0], reverse=True)
    top_buy = [x for x in sorted_b if x[1][0] > 0][:3]
    top_sell = [x for x in sorted_b if x[1][0] < 0][-3:]
    buy_sum = sum(x[1][0] for x in top_buy)
    sell_sum = sum(abs(x[1][0]) for x in top_sell)
    bandar_val = buy_sum - sell_sum
    turnover = st['tot'] / 2.0 if st['tot'] > 0 else 0.0
    acc_pct = round(buy_sum / turnover * 100.0, 2) if turnover > 0 else 0.0
    dist_pct = round(sell_sum / turnover * 100.0, 2) if turnover > 0 else 0.0
    smart_net = round(st['f'] + st['g'])
    conc_pct = round((top_buy[0][1][0] / turnover * 100.0), 2) if top_buy and turnover > 0 else 0.0
    cost_val = sum(x[1][1] for x in top_buy)
    cost_vol = sum(x[1][2] for x in top_buy) * 100.0
    avg_cost = round(cost_val / cost_vol, 2) if cost_vol > 0 else 0.0
    if bandar_val > 0 and acc_pct >= 20:
        label = 'STRONG_ACCUMULATION' if conc_pct >= 15 or st['f'] > 0 else 'ACCUMULATION'
    elif bandar_val < 0 and dist_pct >= 20:
        label = 'DISTRIBUTION'
    else:
        label = 'MIXED_NEUTRAL'
    conf = min(95.0, round(30.0 + min(30.0, conc_pct * 1.2) + (20.0 if (st['f'] > 0 and bandar_val > 0) or (st['f'] < 0 and bandar_val < 0) else 0.0) + min(15.0, abs(acc_pct - dist_pct) * 0.5), 1))
    records.append({
        'd': d, 't': t, 'fn': round(st['f']), 'gn': round(st['g']), 'sn': smart_net,
        'bv': round(bandar_val), 'bc': avg_cost, 'acc': acc_pct, 'dist': dist_pct,
        'conc': conc_pct, 'conf': conf, 'lbl': label,
    })

print(json.dumps({'summary': {'matched': len(records)}, 'records': records}))
"""


async def fetch_historical_broksum_for_pairs(
    client: httpx.AsyncClient, mcp: McpClient, pairs: List[Tuple[str, str]]
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Fetch exact historical broksum stats from VPS packed compactly by date (keeps queue <= 1 job)."""
    if not pairs:
        return {}
    by_date: Dict[str, set[str]] = defaultdict(set)
    for d, t in pairs:
        by_date[str(d)].add(str(t).upper())

    # Pack date-keyed ticker sets up to ~22KB and <= 4000 pairs per VPS job (stays below offset 5000 cap)
    batches: List[Dict[str, str]] = []
    cur_batch: Dict[str, str] = {}
    cur_chars = 2
    cur_pairs = 0
    for d in sorted(by_date):
        dt_list = sorted(by_date[d])
        joined = ",".join(dt_list)
        entry_len = len(d) + len(joined) + 6
        if cur_batch and (cur_chars + entry_len > 22000 or cur_pairs + len(dt_list) > 4000):
            batches.append(cur_batch)
            cur_batch = {}
            cur_chars = 2
            cur_pairs = 0
        cur_batch[d] = joined
        cur_chars += entry_len
        cur_pairs += len(dt_list)
    if cur_batch:
        batches.append(cur_batch)

    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for idx, batch in enumerate(batches):
        s_date = min(batch)
        e_date = max(batch)
        code = FLEX_HISTORY_ENRICH_TEMPLATE.replace("__TARGET_BY_DATE__", json.dumps(batch))
        recs = await _run_and_collect_flex_job(
            client,
            mcp,
            {
                "name": f"sahamteknikal_hist_broksum_{idx}",
                "datasets": ["broksum"],
                "startDate": s_date,
                "endDate": e_date,
                "code": code,
            },
            max_polls=90,
            raise_on_fail=False,
        )
        for r in recs:
            out[(str(r["d"]), str(r["t"]))] = r
    logger.info("Enriched %d historical signal (date, ticker) pairs with genuine Broksum across %d jobs.", len(out), len(batches))
    return out


async def run_full_sync(
    backfill_eod: bool = True,
    min_signal_date: str = "2026-05-06",
    skip_eod_cache: bool = False,
) -> Dict[str, Any]:
    load_local_envs()
    mcp = McpClient()
    t0 = time.time()

    async with httpx.AsyncClient() as client:
        status = await mcp.call_tool(client, "get_service_status", {})
        eod_meta = status["eod"]
        latest_date = str(eod_meta["latestDate"])
        # Always fetch full available history (>=600 bars needed for MACD+EMA200)
        earliest_eod = str(eod_meta["earliestDate"])
        from datetime import timedelta

        start_broksum_15d = (date.fromisoformat(latest_date) - timedelta(days=25)).isoformat()

        # Fetch IHSG bars first to lock onto verified IDX trading dates
        ihsg_bars = await fetch_ihsg_bars(client, mcp, total_bars=960)
        trading_dates = [b.date for b in ihsg_bars]

        # Parallel independent fetches
        master_task = fetch_all_ticker_fundamentals(client, mcp)
        eod_task = fetch_eod_bulk_all_tickers(
            client, mcp, earliest_eod, latest_date, trading_dates=trading_dates
        )
        vps_task = fetch_full_market_broksum_via_vps(client, mcp, start_broksum_15d, latest_date)

        master_by_ticker, bars_by_ticker, (latest_broksum_rows, max_signals) = await asyncio.gather(
            master_task, eod_task, vps_task
        )

        broksum_by_t = {str(r["t"]): r for r in latest_broksum_rows}

        # 1. IHSG Chart + EMA 21/50/200 + Supertrend + Pivots + Regime
        ihsg_closes = [b.close for b in ihsg_bars]
        ihsg_e21 = ema_series(ihsg_closes, 21)
        ihsg_e50 = ema_series(ihsg_closes, 50)
        ihsg_e200 = ema_series(ihsg_closes, 200)
        ihsg_st = supertrend_series(ihsg_bars, 10, 3.0)
        ihsg_last = ihsg_bars[-1]
        ihsg_prev = ihsg_bars[-2] if len(ihsg_bars) > 1 else ihsg_last
        ihsg_pivots = compute_pivot_points(ihsg_prev)

        # Latest cross-section breadth from full EOD bars on latest_date
        snapshot_records: List[Dict[str, Any]] = []
        gainers = losers = unchanged = 0
        tot_vol = tot_val = 0.0
        for t, seq in bars_by_ticker.items():
            if not seq or seq[-1].date != latest_date:
                continue
            cur = seq[-1]
            prv = seq[-2] if len(seq) > 1 else cur
            chg_pct = ((cur.close - prv.close) / prv.close * 100.0) if prv.close > 0 else 0.0
            if chg_pct > 0:
                gainers += 1
            elif chg_pct < 0:
                losers += 1
            else:
                unchanged += 1
            tot_vol += cur.volume
            tot_val += cur.trade_value
            snapshot_records.append({
                "ticker": t,
                "close": cur.close,
                "previousClose": prv.close,
                "changePercent": chg_pct,
                "tradeValue": cur.trade_value,
                "nbsa": cur.nbsa,
            })

        ihsg_chg = round(ihsg_last.close - ihsg_prev.close, 2)
        ihsg_chg_pct = round((ihsg_chg / ihsg_prev.close * 100.0), 2) if ihsg_prev.close > 0 else 0.0
        ihsg_regime = classify_ihsg_regime(
            ihsg_last.close,
            ihsg_e21[-1] if ihsg_e21 else None,
            ihsg_e50[-1] if ihsg_e50 else None,
            int(ihsg_st[-1]["direction"]) if ihsg_st else 0,
            gainers,
            losers,
        )

        # Slice latest 320 bars for IHSG chart payload
        slice_idx = max(0, len(ihsg_bars) - 320)
        ihsg_chart_data = {
            "pivots": ihsg_pivots,
            "bars": [
                {
                    "time": ihsg_bars[i].date,
                    "open": ihsg_bars[i].open,
                    "high": ihsg_bars[i].high,
                    "low": ihsg_bars[i].low,
                    "close": ihsg_bars[i].close,
                    "volume": ihsg_bars[i].volume,
                    "ema21": round(ihsg_e21[i], 2),
                    "ema50": round(ihsg_e50[i], 2),
                    "ema200": round(ihsg_e200[i], 2),
                    "supertrend": ihsg_st[i]["value"],
                    "supertrend_dir": ihsg_st[i]["direction"],
                }
                for i in range(slice_idx, len(ihsg_bars))
            ],
        }

        # 2. IHSG Contributors & Draggers
        contributors = compute_ihsg_contributors(
            snapshot_records, master_by_ticker, ihsg_prev.close, top_n=15
        )

        # 3. Run technical rules across all tickers from min_signal_date to latest_date
        raw_signals: List[Dict[str, Any]] = []
        stock_regimes: Dict[str, Tuple[str, str]] = {}

        for t, seq in bars_by_ticker.items():
            if len(seq) < 10:
                continue
            closes_t = [x.close for x in seq]
            e21_t = ema_series(closes_t, 21)
            e50_t = ema_series(closes_t, 50)
            b_info = broksum_by_t.get(t) or {}
            acc_flag = "ACCUMULATION" in str(b_info.get("lbl") or "") or float(b_info.get("sn") or 0) > 0
            dist_flag = "DISTRIBUTION" in str(b_info.get("lbl") or "") or float(b_info.get("sn") or 0) < 0
            stock_regimes[t] = classify_stock_regime(
                seq[-1].close, e21_t[-1], e50_t[-1], acc_flag, dist_flag
            )

            # Provide latest broksum summary map so today's G_ACC checks live broksum
            bmap = {latest_date: {
                "label": b_info.get("lbl"),
                "smart_money_net": b_info.get("sn"),
                "foreign_net": b_info.get("fn"),
                "bandar_avg_cost": b_info.get("bc"),
            }} if b_info else {}
            raw_signals.extend(
                detect_ticker_signals_history(t, seq, broksum_by_date=bmap, min_signal_date=min_signal_date)
            )

        # Merge today's MaX Screener active G_ACC signals only (strictly 3 core strategies)
        seen_keys = {(s["date"], s["ticker"], s["signal_type"]) for s in raw_signals}
        for ms in max_signals:
            t = str(ms.get("ticker") or "").upper()
            d = str(ms.get("date") or latest_date)
            sig_raw = str(ms.get("signal") or "").upper().replace(" ", "_")
            sig_type = "G_ACC" if sig_raw in ("G_ACC", "G_ACCUMULATION") else sig_raw
            if sig_type != "G_ACC":
                continue
            if (d, t, sig_type) in seen_keys or t not in bars_by_ticker:
                continue
            sl = ms.get("stopLoss")
            tp1 = ms.get("tp1")
            tp2 = ms.get("tp2")
            price = float(ms.get("price") or bars_by_ticker[t][-1].close)
            reg_tuple = stock_regimes.get(t, ("CONSOLIDATING", "TUNGGU BREAKOUT"))
            risk = (price - float(sl)) if sl and price > float(sl) else None
            raw_signals.append({
                "date": d,
                "ticker": t,
                "signal_type": sig_type,
                "signal_source": "max_screener",
                "entry_price": price,
                "stop_loss": float(sl) if sl else None,
                "tp1": float(tp1) if tp1 else None,
                "tp2": float(tp2) if tp2 else None,
                "rr_tp1": round((float(tp1) - price) / risk, 2) if risk and tp1 else None,
                "rr_tp2": round((float(tp2) - price) / risk, 2) if risk and tp2 else None,
                "regime": reg_tuple[0],
                "regime_action": reg_tuple[1],
                "rule_checklist": {"max_score": ms.get("score"), "rvol": ms.get("rvol"), "rsi": ms.get("rsi")},
                "notes": str(ms.get("logicNotes") or ""),
                "eval_tp1_status": "pending",
                "eval_tp2_status": "pending",
                "eval_up_5d_status": "pending",
                "eval_up_10d_status": "pending",
                "eval_up_latest_status": "pending",
                "evaluated_until_date": latest_date,
            })

        # Enrich LATEST_DATE signals with exact real-time MCP get_broksum_signal confidence
        # AND enrich historical signal pairs via VPS broksum lookup so Smart Money 3/3 filter works historically!
        latest_signal_tickers = sorted({s["ticker"] for s in raw_signals if s["date"] == latest_date})
        hist_pairs = [(s["date"], s["ticker"]) for s in raw_signals if s["date"] != latest_date and s["date"] >= "2025-12-01"]
        live_enrichment, hist_broksum_map = await asyncio.gather(
            enrich_candidates_with_live_broksum_signals(client, mcp, latest_signal_tickers, latest_date),
            fetch_historical_broksum_for_pairs(client, mcp, hist_pairs),
        )

        # Build final signal DB rows with Smart Money 3-Factor Score
        active_signals_by_ticker: Dict[str, List[str]] = defaultdict(list)
        signal_rows_for_db: List[Dict[str, Any]] = []

        for s in raw_signals:
            t = s["ticker"]
            meta = master_by_ticker.get(t) or {}
            b_vps = broksum_by_t.get(t) or {}
            b_hist = hist_broksum_map.get((s["date"], t))
            live_sig = live_enrichment.get(t) if s["date"] == latest_date else None

            if live_sig and live_sig.get("confidence") is not None:
                ev = live_sig.get("evidence") or {}
                summ = live_sig.get("summary") or {}
                conf = float(live_sig["confidence"])
                lbl = live_sig.get("label")
                f_net = float(summ.get("foreignNetValue") or b_vps.get("fn") or 0.0)
                s_net = float(b_vps.get("sn") or f_net)
                b_val = live_sig.get("bandar_value")
                b_ma10 = live_sig.get("bandar_value_ma10")
                b_cost = live_sig.get("bandar_avg_cost") or b_vps.get("bc")
                acc_share = ev.get("accumulationSharePct")
                dist_share = ev.get("distributionSharePct")
            elif s["date"] == latest_date:
                conf = float(b_vps.get("conf") or 0.0)
                lbl = b_vps.get("lbl")
                f_net = float(b_vps.get("fn") or 0.0)
                s_net = float(b_vps.get("sn") or 0.0)
                b_val = b_vps.get("bv")
                b_ma10 = b_vps.get("bv_ma10")
                b_cost = b_vps.get("bc")
                acc_share = b_vps.get("acc")
                dist_share = b_vps.get("dist")
            elif b_hist:
                conf = float(b_hist.get("conf") or 0.0)
                lbl = b_hist.get("lbl")
                f_net = float(b_hist.get("fn") or 0.0)
                s_net = float(b_hist.get("sn") or 0.0)
                b_val = b_hist.get("bv")
                b_ma10 = None
                b_cost = b_hist.get("bc")
                acc_share = b_hist.get("acc")
                dist_share = b_hist.get("dist")
            else:
                conf = 0.0
                lbl = None
                f_net = 0.0
                s_net = 0.0
                b_val = None
                b_ma10 = None
                b_cost = None
                acc_share = None
                dist_share = None

            t_bars = bars_by_ticker[t]
            cur_bar = next((x for x in t_bars if x.date == s["date"]), t_bars[-1])
            idx_cur = t_bars.index(cur_bar)
            prv_bar = t_bars[idx_cur - 1] if idx_cur > 0 else cur_bar
            chg_pct = ((cur_bar.close - prv_bar.close) / prv_bar.close * 100.0) if prv_bar.close > 0 else 0.0
            if s["date"] != latest_date and f_net == 0.0 and not b_hist:
                f_net = cur_bar.nbsa
                s_net = cur_bar.nbsa

            sm = compute_smart_money_score(
                confidence_pct=conf,
                broksum_label=lbl,
                accumulation_share_pct=acc_share,
                distribution_share_pct=dist_share,
                foreign_net_value=f_net,
                price_change_pct=chg_pct,
                smart_money_net=s_net,
                bandar_value=b_val,
                bandar_value_ma10=b_ma10,
                close_price=cur_bar.close,
                bandar_avg_cost=b_cost,
            )

            if s["date"] == latest_date:
                active_signals_by_ticker[t].append(s["signal_type"])

            signal_rows_for_db.append({
                "signal_date": s["date"],
                "ticker": t,
                "sector": meta.get("sector") or "Other",
                "sector_slug": meta.get("sector_slug") or "other",
                "signal_type": s["signal_type"],
                "signal_source": s.get("signal_source", "engine_v2"),
                "close_price": cur_bar.close,
                "change_pct": round(chg_pct, 2),
                "entry_price": s["entry_price"],
                "stop_loss": s["stop_loss"],
                "tp1": s["tp1"],
                "tp2": s["tp2"],
                "rr_tp1": s["rr_tp1"],
                "rr_tp2": s["rr_tp2"],
                "regime": s["regime"],
                "regime_action": s["regime_action"],
                "smart_money_score": sm["score"],
                "smart_money_label": sm["label"],
                "smart_money_factors": sm["factors"],
                "rule_checklist": s["rule_checklist"],
                "notes": s.get("notes", ""),
                "eval_tp1_status": s["eval_tp1_status"],
                "eval_tp2_status": s["eval_tp2_status"],
                "eval_up_5d_status": s["eval_up_5d_status"],
                "eval_up_10d_status": s["eval_up_10d_status"],
                "eval_up_latest_status": s["eval_up_latest_status"],
                "evaluated_until_date": s["evaluated_until_date"],
            })

        # 4. Full Market Quadrant Map (ALL 831/602+ tickers — ZERO Top-8 truncation!)
        q_stocks: Dict[str, List[Dict[str, Any]]] = {
            "markup_akumulasi": [],
            "markup_distribusi": [],
            "markdown_akumulasi": [],
            "markdown_distribusi": [],
        }
        for row in latest_broksum_rows:
            t = str(row["t"])
            q_id = str(row["q"])
            meta = master_by_ticker.get(t) or {}
            reg_tuple = stock_regimes.get(t, ("CONSOLIDATING", "TUNGGU BREAKOUT"))
            sm_row = compute_smart_money_score(
                confidence_pct=row.get("conf"),
                broksum_label=row.get("lbl"),
                accumulation_share_pct=row.get("acc"),
                distribution_share_pct=row.get("dist"),
                foreign_net_value=row.get("fn"),
                price_change_pct=float(row.get("chg") or 0),
                smart_money_net=float(row.get("sn") or 0),
                bandar_value=row.get("bv"),
                bandar_value_ma10=row.get("bv_ma10"),
                close_price=float(row.get("c") or 0),
                bandar_avg_cost=row.get("bc"),
            )
            q_stocks[q_id].append({
                "ticker": t,
                "sector": meta.get("sector") or "Other",
                "sector_slug": meta.get("sector_slug") or "other",
                "close": row["c"],
                "change_percent": row["chg"],
                "turnover": row["tv"],
                "smart_money_net": row["sn"],
                "foreign_net": row["fn"],
                "bandar_value": row["bv"],
                "bandar_cost": row["bc"],
                "regime": reg_tuple[0],
                "regime_action": reg_tuple[1],
                "smart_money_score": sm_row["score"],
                "smart_money_label": sm_row["label"],
                "active_signals": active_signals_by_ticker.get(t, []),
            })

        for q_id in q_stocks:
            q_stocks[q_id].sort(key=lambda x: abs(float(x["smart_money_net"])), reverse=True)

        quadrant_summary = {
            "counts": {k: len(v) for k, v in q_stocks.items()},
            "stocks_by_quadrant": q_stocks,
        }

        # 5. Build 11 Sector Heatmap + Full Sector Snapshots (index chart & all sector stocks)
        stocks_by_sector: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        snap_by_t = {r["ticker"]: r for r in snapshot_records}

        for t, s_rec in snap_by_t.items():
            meta = master_by_ticker.get(t) or {}
            sec_name = meta.get("sector") or "Other"
            b_vps = broksum_by_t.get(t) or {}
            reg_tuple = stock_regimes.get(t, ("CONSOLIDATING", "TUNGGU BREAKOUT"))
            sm_row = compute_smart_money_score(
                confidence_pct=b_vps.get("conf"),
                broksum_label=b_vps.get("lbl"),
                accumulation_share_pct=b_vps.get("acc"),
                distribution_share_pct=b_vps.get("dist"),
                foreign_net_value=b_vps.get("fn") or s_rec.get("nbsa"),
                price_change_pct=float(s_rec["changePercent"]),
                smart_money_net=float(b_vps.get("sn") or 0),
                bandar_value=b_vps.get("bv"),
                bandar_value_ma10=b_vps.get("bv_ma10"),
                close_price=float(s_rec["close"]),
                bandar_avg_cost=b_vps.get("bc"),
            )
            stocks_by_sector[sec_name].append({
                "ticker": t,
                "sector": sec_name,
                "sector_slug": sector_to_slug(sec_name),
                "close": s_rec["close"],
                "change_pct": round(float(s_rec["changePercent"]), 2),
                "turnover": round(float(s_rec["tradeValue"])),
                "market_cap": meta.get("market_cap"),
                "free_float_pct": meta.get("free_float_pct"),
                "smart_money_net": round(float(b_vps.get("sn") or 0)),
                "foreign_net": round(float(b_vps.get("fn") or s_rec.get("nbsa") or 0)),
                "quadrant": b_vps.get("q") or "neutral",
                "regime": reg_tuple[0],
                "regime_action": reg_tuple[1],
                "smart_money_score": sm_row["score"],
                "smart_money_label": sm_row["label"],
                "active_signals": active_signals_by_ticker.get(t, []),
            })

        # Compute equal-weighted Base-100 sector chart over last 180 dates
        ref_dates = [b.date for b in ihsg_bars[-180:]]
        sector_heatmap: List[Dict[str, Any]] = []
        sector_snapshot_rows: List[Dict[str, Any]] = []

        for sec_name, sec_stocks in stocks_by_sector.items():
            if sec_name == "Other" and len(sec_stocks) < 3:
                continue
            slug = sector_to_slug(sec_name)
            sec_g = sum(1 for x in sec_stocks if x["change_pct"] > 0)
            sec_l = sum(1 for x in sec_stocks if x["change_pct"] < 0)
            sec_u = sum(1 for x in sec_stocks if x["change_pct"] == 0)
            tot_tv = sum(x["turnover"] for x in sec_stocks)
            tot_sm = sum(x["smart_money_net"] for x in sec_stocks)
            tot_fn = sum(x["foreign_net"] for x in sec_stocks)
            tot_mcap = sum(float(x["market_cap"] or 0) for x in sec_stocks)

            equal_chg = sum(x["change_pct"] for x in sec_stocks) / max(1, len(sec_stocks))
            w_num = sum(x["change_pct"] * float(x["market_cap"] or 1e9) for x in sec_stocks)
            w_den = sum(float(x["market_cap"] or 1e9) for x in sec_stocks)
            weighted_chg = (w_num / w_den) if w_den > 0 else equal_chg

            top_gainer = max(sec_stocks, key=lambda x: x["change_pct"])
            top_loser = min(sec_stocks, key=lambda x: x["change_pct"])

            # Synthetic equal-weight sector index from ref_dates
            sec_tickers = [x["ticker"] for x in sec_stocks if x["ticker"] in bars_by_ticker]
            date_returns: Dict[str, List[float]] = defaultdict(list)
            date_turnover: Dict[str, float] = defaultdict(float)
            ref_set = set(ref_dates)
            for st_t in sec_tickers:
                seq = bars_by_ticker[st_t]
                for idx in range(1, len(seq)):
                    d_str = seq[idx].date
                    if d_str not in ref_set:
                        continue
                    prev_c = seq[idx - 1].close
                    if prev_c > 0:
                        date_returns[d_str].append((seq[idx].close - prev_c) / prev_c * 100.0)
                    date_turnover[d_str] += seq[idx].trade_value

            idx_val = 100.0
            raw_series: List[Dict[str, Any]] = []
            for d_str in ref_dates:
                rets = date_returns.get(d_str)
                avg_r = (sum(rets) / len(rets)) if rets else 0.0
                idx_val = idx_val * (1.0 + avg_r / 100.0)
                raw_series.append({
                    "time": d_str,
                    "close": round(idx_val, 2),
                    "change_pct": round(avg_r, 2),
                    "volume": round(date_turnover.get(d_str, 0.0)),
                })

            idx_closes = [p["close"] for p in raw_series]
            sec_e21 = ema_series(idx_closes, 21)
            sec_e50 = ema_series(idx_closes, 50)
            for i, p in enumerate(raw_series):
                p["ema21"] = round(sec_e21[i], 2)
                p["ema50"] = round(sec_e50[i], 2)

            summary_obj = {
                "sector": sec_name,
                "slug": slug,
                "stocks_count": len(sec_stocks),
                "gainers": sec_g,
                "losers": sec_l,
                "unchanged": sec_u,
                "equal_change_pct": round(equal_chg, 2),
                "weighted_change_pct": round(weighted_chg, 2),
                "total_turnover": round(tot_tv),
                "total_market_cap": round(tot_mcap),
                "smart_money_net": round(tot_sm),
                "foreign_net": round(tot_fn),
                "top_gainer": {
                    "ticker": top_gainer["ticker"],
                    "change_pct": top_gainer["change_pct"],
                    "close": top_gainer["close"],
                },
                "top_loser": {
                    "ticker": top_loser["ticker"],
                    "change_pct": top_loser["change_pct"],
                    "close": top_loser["close"],
                },
            }
            sector_heatmap.append(summary_obj)
            sector_snapshot_rows.append({
                "session_date": latest_date,
                "sector_slug": slug,
                "sector_name": sec_name,
                "summary": summary_obj,
                "chart_series": raw_series,
                "stocks": sorted(sec_stocks, key=lambda x: x["turnover"], reverse=True),
            })

        sector_heatmap.sort(key=lambda x: x["total_turnover"], reverse=True)

        # 6. Persist everything cleanly into Supabase Postgres
        logger.info("Upserting master (%d), EOD cache (%d), signals (%d), sectors (%d) to Supabase...",
                    len(master_by_ticker), len(bars_by_ticker), len(signal_rows_for_db), len(sector_snapshot_rows))

        master_rows = list(master_by_ticker.values())
        await supabase_upsert(client, "idx_ticker_master", master_rows, "ticker", batch_size=250)

        eod_cache_rows = (
            []
            if skip_eod_cache
            else [
                {
                    "ticker": t,
                    "latest_date": seq[-1].date,
                    "bar_count": len(seq),
                    "bars_json": [
                        [b.date, b.open, b.high, b.low, b.close, b.volume, b.trade_value, b.nbsa]
                        for b in seq
                    ],
                    "updated_at": datetime.now(UTC).isoformat(),
                }
                for t, seq in bars_by_ticker.items()
                if seq
            ]
        )
        if eod_cache_rows:
            await supabase_upsert(client, "idx_eod_bars_cache", eod_cache_rows, "ticker", batch_size=50)

        dashboard_row = {
            "session_date": latest_date,
            "ihsg_close": ihsg_last.close,
            "ihsg_change": ihsg_chg,
            "ihsg_change_pct": ihsg_chg_pct,
            "market_regime": ihsg_regime,
            "breadth": {
                "gainers": gainers,
                "losers": losers,
                "unchanged": unchanged,
                "total_tickers": gainers + losers + unchanged,
                "total_volume": round(tot_vol),
                "total_turnover": round(tot_val),
                "ad_ratio": round(gainers / max(1, losers), 2),
                "smart_money_net": round(sum(float(r.get("sn") or 0) for r in latest_broksum_rows)),
                "foreign_net": round(sum(float(r.get("fn") or 0) for r in latest_broksum_rows)),
            },
            "ihsg_chart_data": ihsg_chart_data,
            "contributors": contributors,
            "sector_heatmap": sector_heatmap,
            "quadrant_summary": quadrant_summary,
        }
        await supabase_upsert(client, "daily_market_dashboard", [dashboard_row], "session_date", batch_size=1)
        await supabase_upsert(client, "daily_sector_snapshots", sector_snapshot_rows, "session_date,sector_slug", batch_size=5)
        supa_url = os.environ["SUPABASE_URL"]
        supa_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_SECRET_KEY"]
        del_resp = await client.delete(
            f"{supa_url}/rest/v1/daily_screening_signals?signal_type=not.in.(FRACTAL_BREAKOUT,MACD_EMA200,G_ACC)",
            headers={"apikey": supa_key, "Authorization": f"Bearer {supa_key}"},
            timeout=30.0,
        )
        if del_resp.status_code not in (200, 204):
            raise RuntimeError(f"Failed pruning deprecated signal types ({del_resp.status_code}): {del_resp.text[:200]}")
        await supabase_upsert(client, "daily_screening_signals", signal_rows_for_db, "signal_date,ticker,signal_type", batch_size=250)

        elapsed = round(time.time() - t0, 2)
        logger.info("Full v2 sync completed in %.2fs! Signals indexed: %d.", elapsed, len(signal_rows_for_db))
        return {
            "session_date": latest_date,
            "tickers_master": len(master_rows),
            "tickers_eod": len(eod_cache_rows),
            "signals": len(signal_rows_for_db),
            "sectors": len(sector_snapshot_rows),
            "elapsed_sec": elapsed,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="SahamTeknikal v2 Max Trade MCP Full Sync")
    parser.add_argument("--apply-migration", action="store_true", help="Apply SQL migration first")
    parser.add_argument("--incremental", action="store_true", help="Fetch only 1Y EOD instead of 2023+ backfill")
    parser.add_argument("--skip-eod-cache", action="store_true", help="Skip uploading idx_eod_bars_cache payloads")
    parser.add_argument("--min-signal-date", type=str, default="2026-05-06", help="Earliest signal archive date for Win Rate")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if args.apply_migration:
        apply_supabase_migration()
    res = asyncio.run(
        run_full_sync(
            backfill_eod=not args.incremental,
            min_signal_date=args.min_signal_date,
            skip_eod_cache=args.skip_eod_cache,
        )
    )
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
