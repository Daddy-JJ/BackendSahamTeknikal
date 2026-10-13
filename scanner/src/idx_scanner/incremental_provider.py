"""Persisted Yahoo history with a validated ten-session overlap, never a local cache."""
import json
from dataclasses import replace
from datetime import date

from .context import quality
from .models import canonical_json


class IncrementalProvider:
    def __init__(self, provider, store, calendar, *, data_mode="live", force_full=False):
        self.provider, self.store, self.calendar = provider, store, calendar
        self.data_mode, self.force_full = data_mode, force_full
        self.raw_recovery_captures = {}

    @property
    def fetch_diagnostics(self):
        return self.provider.fetch_diagnostics

    def _capture(self, ticker, *sources):
        values = (*self.raw_recovery_captures.get(ticker, ()),
                  *getattr(self.provider, "raw_recovery_captures", {}).get(ticker, ()),
                  *sources)
        self.raw_recovery_captures[ticker] = tuple(
            {s.input_digest: s for s in values}.values())

    def _base(self, request):
        rows = self.store._request("GET", "market_series_revisions", params={
            "select": "id,input_digest", "namespace": "eq.forward",
            "data_mode": "eq." + self.data_mode, "provider": "eq.yfinance",
            "ticker": "eq." + request.ticker, "provider_symbol": "eq." + request.symbol,
            "price_basis": "eq.yahoo_provider_ohlcv_auto_adjust_false_v1",
            "bar_count": "gte.600",
            "order": "stored_at.desc,id.desc", "limit": "6",
        })
        for row in rows:
            source = self.store.load_series(row["id"], data_mode=self.data_mode,
                                            expected_input_digest=row["input_digest"])
            is_backfill = False
            for p in source.provenance:
                try:
                    if (isinstance(p, str) and
                            json.loads(p).get("kind") == "reviewed_historical_backfill_v1"):
                        is_backfill = True
                        break
                except (ValueError, TypeError, AttributeError):
                    continue
            if is_backfill:
                continue
            if (source.ticker == request.ticker and source.provider_symbol == request.symbol
                and source.bars and source.bars[0].session >= request.start
                and source.bars[-1].session <= request.end
                and quality(source, source.bars[-1].session, self.calendar) == "valid"):
                return source
        return None

    def fetch(self, request):
        base = None if self.force_full else self._base(request)
        all_days = self.calendar.historical_days + tuple(s.day for s in self.calendar.sessions)
        if base is not None:
            cutoff = base.bars[-1].session
            full_session = cutoff
            for token in base.provenance:
                item = json.loads(token)
                if item.get("kind") == "yahoo_persisted_incremental_v1":
                    full_session = date.fromisoformat(item["full_refresh_session"])
            elapsed = sum(full_session < d <= request.end for d in all_days)
            if elapsed >= 10 or len(base.bars) < 600:
                base = None
        if base is None:
            result = self.provider.fetch(request)
            self._capture(request.ticker)
            return result
        start = base.bars[-10].session
        fresh = self.provider.fetch(replace(request, start=start))
        self._capture(request.ticker, fresh)
        old = {b.session: b for b in base.bars if b.session >= start}
        new = {b.session: b for b in fresh.bars}
        fields = ("open", "high", "low", "close", "volume")
        same_overlap = all(day in new and all(getattr(bar, f) == getattr(new[day], f)
                                             for f in fields) for day, bar in old.items())
        same_actions = tuple(a for a in base.actions if a.session >= start) == tuple(
            a for a in fresh.actions if a.session <= base.bars[-1].session)
        expected = tuple(d for d in all_days if start <= d <= request.end)
        if (fresh.ticker != base.ticker or fresh.provider_symbol != base.provider_symbol
            or fresh.provider != base.provider or fresh.price_basis != base.price_basis
            or not same_overlap or not same_actions or not fresh.actions_complete
            or fresh.provider_row_issues or tuple(new) != expected
            or any(not b.valid() for b in fresh.bars)):
            result = self.provider.fetch(request)
            self._capture(request.ticker)
            return result
        result = replace(fresh,
            bars=tuple(b for b in base.bars if b.session < start) + fresh.bars,
            actions=tuple(a for a in base.actions if a.session < start) + fresh.actions,
            reconciled_actions=tuple(sorted(set(
                base.reconciled_actions + fresh.reconciled_actions))),
            provenance=fresh.provenance + (canonical_json({
                "kind": "yahoo_persisted_incremental_v1", "overlap_sessions": 10,
                "base_digest": base.input_digest, "fresh_digest": fresh.input_digest,
                "full_refresh_session": full_session.isoformat(),
            }),))
        if quality(result, request.end, self.calendar) != "valid":
            result = self.provider.fetch(request)
            self._capture(request.ticker)
        return result


def persist_provider_captures(provider, store, ticker, *, data_mode, namespace="forward"):
    """Retain rejected originals and raw short profiles before the final revision."""
    for source in getattr(provider, "raw_recovery_captures", {}).get(ticker, ()):
        store.ingest_series(source, namespace=namespace, data_mode=data_mode)
