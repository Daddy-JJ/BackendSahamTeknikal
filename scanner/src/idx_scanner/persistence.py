"""Supabase REST adapter. SQL owns atomic publication; no trading formulas here."""

import json
import re
import time
from collections.abc import Callable
from datetime import date, datetime
from urllib.parse import urlsplit

import httpx

from .engine import ScanResult
from .models import Candidate, Rule, ScanState, Signal, canonical_json, digest


class PersistenceError(RuntimeError):
    """Only a stable safe code is public; no URL, key or response body."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def scan_envelope(result: ScanResult, namespace: str, data_mode: str) -> dict:
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", namespace):
        raise ValueError("invalid_namespace")
    if data_mode not in ("live", "fixture"):
        raise ValueError("invalid_data_mode")
    if any(s.data_mode != data_mode for s in result.signals):
        raise ValueError("mixed_fixture_live_persistence")
    payload = json.loads(canonical_json(result))
    signals = payload.pop("signals")
    payload.update(namespace=namespace, data_mode=data_mode)
    return {"p_run": payload, "p_signals": signals}


def signal_from_snapshot(value: dict) -> Signal:
    data = dict(value)
    candidate = dict(data.pop("candidate"))
    candidate["rules"] = tuple(Rule(**r) for r in candidate["rules"])
    for field in ("pivot_date", "available_session"):
        if candidate.get(field) is not None:
            candidate[field] = date.fromisoformat(candidate[field])
    data["candidate"] = Candidate(**candidate)
    data["session"] = date.fromisoformat(data["session"])
    data["planned_entry_session"] = date.fromisoformat(data["planned_entry_session"])
    data["published_at"] = datetime.fromisoformat(data["published_at"])
    data["features"] = tuple(tuple(feature) for feature in data["features"])
    return Signal(**data)


class SupabaseScanStore:
    def __init__(
        self,
        url: str,
        service_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        allow_local: bool = False,
    ):
        parsed = urlsplit(url)
        hosted = (
            parsed.scheme == "https"
            and bool(re.fullmatch(r"[a-z0-9-]+\.supabase\.co", parsed.hostname or ""))
            and parsed.port in (None, 443)
        )
        local = (
            allow_local
            and parsed.scheme == "http"
            and parsed.hostname in ("127.0.0.1", "localhost")
        )
        if (
            not (hosted or local)
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise PersistenceError("invalid_supabase_origin")
        if not service_key or service_key.strip() != service_key:
            raise PersistenceError("missing_or_invalid_service_key")
        self._client = httpx.Client(
            base_url=url.rstrip("/") + "/rest/v1/",
            headers={"apikey": service_key},
            timeout=20,
            follow_redirects=False,
            transport=transport,
        )
        self._sleep = sleep

    def __repr__(self):
        return "SupabaseScanStore(credentials=REDACTED)"

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _request(self, method: str, path: str, **kwargs):
        for attempt in range(3):
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.TransportError:
                if attempt < 2:
                    self._sleep(0.5 * (2**attempt))
                    continue
                raise PersistenceError("database_transport_failed") from None
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                self._sleep(0.5 * (2**attempt))
                continue
            if not 200 <= response.status_code < 300:
                code = {
                    401: "database_unauthorized",
                    403: "database_forbidden",
                    409: "database_conflict",
                    429: "database_rate_limited",
                }.get(response.status_code, "database_request_failed")
                raise PersistenceError(code)
            try:
                return response.json()
            except ValueError:
                raise PersistenceError("database_invalid_response") from None
        raise PersistenceError("database_request_failed")

    def publish(self, result: ScanResult, *, namespace="forward", data_mode="live") -> dict:
        payload = scan_envelope(result, namespace, data_mode)
        response = self._request("POST", "rpc/publish_scan", json=payload)
        if (
            not isinstance(response, dict)
            or not isinstance(response.get("run_id"), str)
            or not isinstance(response.get("replayed"), bool)
        ):
            raise PersistenceError("database_invalid_response")
        return response

    def load_state(
        self, *, through_session: date, namespace="forward", data_mode="live", page_size=200
    ) -> ScanState:
        if (
            not re.fullmatch(r"[a-z0-9_-]{1,64}", namespace)
            or data_mode not in ("fixture", "live")
            or not 1 <= page_size <= 200
        ):
            raise ValueError("invalid_state_query")
        state = ScanState()
        cursor = None
        for _ in range(500):
            params = {
                "select": "id,snapshot",
                "namespace": f"eq.{namespace}",
                "data_mode": f"eq.{data_mode}",
                "session_date": f"lte.{through_session.isoformat()}",
                "order": "id.asc",
                "limit": str(page_size),
            }
            if cursor:
                params["id"] = f"gt.{cursor}"
            rows = self._request("GET", "signals", params=params)
            if not isinstance(rows, list) or len(rows) > page_size:
                raise PersistenceError("database_invalid_response")
            try:
                for row in rows:
                    signal = signal_from_snapshot(row["snapshot"])
                    if (
                        row["id"] != signal.id
                        or not re.fullmatch(r"[a-f0-9]{64}", signal.id)
                        or (cursor is not None and signal.id <= cursor)
                        or signal.session > through_session
                        or signal.data_mode != data_mode
                    ):
                        raise ValueError("invalid_snapshot_context")
                    state.signals[signal.id] = signal
                    if signal.candidate.fractal_id:
                        state.fractal_guards.add(
                            digest(
                                (
                                    namespace,
                                    signal.candidate.strategy,
                                    signal.config_hash,
                                    signal.ticker,
                                    signal.candidate.fractal_id,
                                )
                            )
                        )
                    cursor = signal.id
            except (ValueError, KeyError, TypeError):
                raise PersistenceError("database_invalid_snapshot") from None
            if len(rows) < page_size:
                return state
        raise PersistenceError("database_state_page_limit")
