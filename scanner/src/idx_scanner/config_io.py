"""Strict file imports. Never infer exchange holidays from weekdays."""

import csv
import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from .context import Calendar, Session, Universe
from .providers import FetchRequest


def _provenance(data: dict) -> None:
    if data.get("data_mode") not in ("live", "fixture") or not data.get("version"):
        raise ValueError("invalid_config_metadata")
    if data["data_mode"] == "live":
        if urlparse(data.get("source", "")).scheme != "https":
            raise ValueError("live_source_https_required")
        date.fromisoformat(data["published_date"])
        if not re.fullmatch(r"[0-9a-f]{64}", data.get("source_checksum", "")):
            raise ValueError("live_source_checksum_required")


def load_calendar(path: Path) -> Calendar:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    _provenance(data)
    sessions = tuple(
        Session(
            date.fromisoformat(s["day"]),
            datetime.fromisoformat(s["opens_at"]),
            datetime.fromisoformat(s["closes_at"]),
        )
        for s in data["sessions"]
    )
    return Calendar(
        sessions,
        data["version"],
        data["source"],
        data["data_mode"],
        tuple(date.fromisoformat(day) for day in data.get("historical_days", [])),
        tuple(date.fromisoformat(day) for day in data.get("closed_days", [])),
    )


def load_universe(metadata_path: Path, csv_path: Path) -> Universe:
    data = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    _provenance(data)
    with csv_path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows or any(
        set(row) != {"ticker"} or not re.fullmatch(r"[A-Z0-9_-]{1,20}", row["ticker"])
        for row in rows
    ):
        raise ValueError("invalid_universe_csv")
    return Universe(
        tuple(row["ticker"] for row in rows),
        data["version"],
        date.fromisoformat(data["effective_from"]),
        date.fromisoformat(data["effective_to"]),
        data["source"],
        data["data_mode"],
    )


def load_requests(path: Path, provider: str, start: date, end: date) -> dict[str, FetchRequest]:
    if provider not in ("yfinance", "eodhd"):
        raise ValueError("explicit_provider_required")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    result = {}
    for row in data:
        if row["ticker"] in result or row["verified"] is not True:
            raise ValueError("duplicate_or_unverified_mapping")
        if not row.get("source"):
            raise ValueError("mapping_source_required")
        result[row["ticker"]] = FetchRequest(row["ticker"], row[provider], start, end, True)
    return result
