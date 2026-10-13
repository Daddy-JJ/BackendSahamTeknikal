"""Import independently reviewed, exact Yahoo captures; offline dry-run by default.

This operator imports source revisions only. It never publishes signals, fills a
trade, modifies a paper book, or substitutes EODHD prices into Yahoo history.
"""
import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from idx_scanner.config_io import load_calendar, load_requests
from idx_scanner.context import Calendar, quality
from idx_scanner.models import Bar, Series, canonical_json
from idx_scanner.paper_persistence import PaperRuntimeStore
from idx_scanner.persistence import PersistenceError, SupabaseScanStore, series_from_revision
from idx_scanner.reviewed_backfill import ReviewedBackfill, parse_reviewed_backfill_manifest

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "data"
PRODUCTION_URL = "https://hcjfxbynqzsaidlwvdfx.supabase.co"
IMPORT_VERSION = "reviewed_backfill_import_v1"
REFERENCE_VERSION = "independent_ohlcv_reference_v1"
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_CANDIDATES = 100
OHLCV = ("open", "high", "low", "close", "volume")
HASH = re.compile(r"[a-f0-9]{64}")


@dataclass(frozen=True)
class ImportCandidate:
    series: Series
    record: ReviewedBackfill
    capture_sha256: str
    capture_index: int


@dataclass(frozen=True)
class PreparedImport:
    candidates: tuple[ImportCandidate, ...]
    plan_sha256: str
    manifest_sha256: str


def _fail(code="invalid_reviewed_backfill_import"):
    raise ValueError(code)


def _pairs(values):
    if len({key for key, _ in values}) != len(values):
        _fail("duplicate_json_keys")
    return dict(values)


def _json(raw):
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=lambda _: _fail("nonfinite_json_value"))
    except (UnicodeError, json.JSONDecodeError):
        _fail("invalid_json_document")


def _path(value, root):
    if not isinstance(value, (str, Path)) or not str(value):
        _fail("invalid_backfill_data_path")
    value = Path(value)
    result = (value if value.is_absolute() else root / value).resolve()
    if (result == root or not result.is_relative_to(root) or result.suffix != ".json"
            or any(part.startswith(".env") for part in result.parts)):
        _fail("invalid_backfill_data_path")
    return result


def _document(value, root):
    path = _path(value, root)
    try:
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_FILE_BYTES:
            _fail("invalid_backfill_document_size")
        content = path.read_bytes()
        if len(content) > MAX_FILE_BYTES:
            _fail("invalid_backfill_document_size")
        return _json(content), sha256(content).hexdigest()
    except OSError:
        _fail("backfill_document_unavailable")


def _exact_object(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail()


def _decimal(value):
    if type(value) not in (int, float, str):
        _fail("invalid_reference_price")
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        _fail("invalid_reference_price")
    if not result.is_finite():
        _fail("invalid_reference_price")
    return result


def _reference(payload):
    keys = ("version", "exchange", "timezone", "session", "volume_unit", "source_url", "rows")
    _exact_object(payload, keys)
    if (payload["version"] != REFERENCE_VERSION or payload["exchange"] != "XIDX"
            or payload["timezone"] != "Asia/Jakarta" or payload["volume_unit"] != "shares"
            or type(payload["rows"]) is not list or not 0 < len(payload["rows"]) <= 100):
        _fail("invalid_independent_reference")
    day = date.fromisoformat(payload["session"])
    rows = {}
    for row in payload["rows"]:
        _exact_object(row, ("ticker", *OHLCV))
        ticker = row["ticker"]
        if (not isinstance(ticker, str) or not re.fullmatch(r"[A-Z0-9_-]{1,20}", ticker)
                or ticker in rows):
            _fail("invalid_reference_ticker")
        values = {key: _decimal(row[key]) for key in OHLCV}
        if (min(values[key] for key in OHLCV[:4]) <= 0 or values["volume"] < 0
                or not values["low"] <= min(values["open"], values["close"])
                <= max(values["open"], values["close"]) <= values["high"]):
            _fail("invalid_reference_ohlcv")
        rows = {**rows, ticker: values}
    return day, payload["source_url"], rows


def _capture(raw, source_digest):
    expected = {field.name for field in fields(Series)}
    if type(raw) is not dict or set(raw) not in (expected, expected - {"provenance"}):
        _fail("invalid_capture_series")
    if type(raw["bars"]) is not list or not raw["bars"]:
        _fail("empty_capture_series")
    for bar in raw["bars"]:
        _exact_object(bar, {field.name for field in fields(Bar)})
        if any(type(bar[key]) not in (int, float) for key in OHLCV):
            _fail("invalid_capture_numeric_tokens")
    try:
        return series_from_revision({
            "metadata_source": canonical_json({key: value for key, value in raw.items()
                                               if key not in ("bars", "fetched_at",
                                                              "provider_version")}),
            "bar_sources": [canonical_json(bar) for bar in raw["bars"]],
            "fetched_at": raw["fetched_at"], "provider_version": raw["provider_version"],
            "input_digest": source_digest,
        })
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
        _fail("capture_digest_or_source_mismatch")


def _validate_source(source, record, calendar, now):
    identity = ("ticker", "provider_symbol", "provider", "price_basis", "provider_version")
    if any(getattr(source, key) != getattr(record, key) for key in identity):
        _fail("capture_identity_mismatch")
    if (source.fetched_at is None or source.fetched_at.tzinfo is None
            or not calendar.get(record.session).closes_at <= source.fetched_at
            <= record.reference.reviewed_at <= now
            or any(action.session > record.session for action in source.actions)
            or any(issue.session > record.session for issue in source.provider_row_issues)
            or any(day > record.session for day in source.provider_missing_sessions)
            or quality(source, record.session, calendar) != "valid"):
        _fail("capture_invalid_historical_context")


def _candidate(capture, records, references, root, calendar, now):
    _exact_object(capture, ("path", "index", "file_sha256", "ticker", "session",
                            "source_input_digest"))
    if (type(capture["index"]) is not int or capture["index"] < 0
            or not isinstance(capture["file_sha256"], str)
            or HASH.fullmatch(capture["file_sha256"]) is None):
        _fail("invalid_capture_identity")
    key = capture["ticker"], date.fromisoformat(capture["session"])
    record = records.get(key)
    if record is None or capture["source_input_digest"] != record.source_input_digest:
        _fail("capture_not_in_reviewed_manifest")
    payload, file_hash = _document(capture["path"], root)
    if (file_hash != capture["file_sha256"] or type(payload) is not list
            or not 0 < len(payload) <= 20 or capture["index"] >= len(payload)):
        _fail("capture_checksum_or_index_mismatch")
    source = _capture(payload[capture["index"]], record.source_input_digest)
    _validate_source(source, record, calendar, now)
    reference = references.get(record.reference.document_sha256)
    if reference is None:
        _fail("independent_reference_document_missing")
    day, url, rows = reference
    if day != record.session or url != record.reference.source_url or record.ticker not in rows:
        _fail("independent_reference_context_mismatch")
    bar = source.bars[-1]
    if any(_decimal(getattr(bar, key)) != rows[record.ticker][key] for key in OHLCV):
        _fail("independent_reference_ohlcv_conflict")
    return ImportCandidate(source, record, file_hash, capture["index"])


def prepare_import(plan_path, *, data_root=DATA_ROOT, calendar: Calendar, now=None):
    """Fully validate all evidence before obtaining a writer; never repair numbers."""
    root = Path(data_root).resolve()
    now = now or datetime.now(UTC)
    if calendar.data_mode != "live" or now.tzinfo is None:
        _fail("invalid_import_context")
    payload, plan_hash = _document(plan_path, root)
    _exact_object(payload, ("version", "manifest_path", "reference_documents", "captures"))
    if (payload["version"] != IMPORT_VERSION or type(payload["captures"]) is not list
            or not 0 < len(payload["captures"]) <= MAX_CANDIDATES
            or type(payload["reference_documents"]) is not list
            or not 0 < len(payload["reference_documents"]) <= MAX_CANDIDATES):
        _fail("invalid_backfill_import_plan")
    manifest, manifest_hash = _document(payload["manifest_path"], root)
    records = {(value.ticker, value.session): value
               for value in parse_reviewed_backfill_manifest(manifest)}
    references = {}
    for path in payload["reference_documents"]:
        document, checksum = _document(path, root)
        if checksum in references:
            _fail("duplicate_reference_document")
        references = {**references, checksum: _reference(document)}
    candidates = tuple(_candidate(value, records, references, root, calendar, now)
                       for value in payload["captures"])
    keys = {(value.record.ticker, value.record.session) for value in candidates}
    if len(keys) != len(candidates) or keys != set(records):
        _fail("incomplete_or_duplicate_import_plan")
    used_references = {value.record.reference.document_sha256 for value in candidates}
    if used_references != set(references):
        _fail("unexpected_reference_document")
    return PreparedImport(candidates, plan_hash, manifest_hash)


def _preflight(store, owner_id):
    try:
        if str(UUID(owner_id)) != owner_id:
            _fail("invalid_import_owner")
    except (TypeError, AttributeError):
        _fail("invalid_import_owner")
    store.require_live_schema()
    rows = store._request("GET", "app_members", params={
        "select": "role,enabled", "user_id": "eq." + owner_id,
    })
    if rows != [{"role": "owner", "enabled": True}]:
        raise PersistenceError("reviewed_backfill_owner_inactive")
    PaperRuntimeStore(store, owner_id, "live").load()


def _readback(store, source, record, response):
    if (type(response) is not dict or type(response.get("replayed")) is not bool
            or not isinstance(response.get("revision_id"), str)):
        raise PersistenceError("reviewed_backfill_invalid_ingest_response")
    saved = store.load_series(response["revision_id"], namespace="forward", data_mode="live",
                              expected_input_digest=source.input_digest)
    # Retry preserves the first DB observation time rather than overriding it.
    if (saved.input_digest != source.input_digest
            or saved.provider_version != source.provider_version
            or saved.fetched_at is None or saved.fetched_at.tzinfo is None
            or saved.fetched_at > record.reference.reviewed_at
            or (not response["replayed"] and saved != source)):
        raise PersistenceError("reviewed_backfill_readback_mismatch")
    return saved


def import_prepared(prepared, store=None, *, owner_id=None, execute=False):
    """Only validated source revisions are written; a failure remains visible."""
    if not isinstance(prepared, PreparedImport) or not prepared.candidates:
        _fail("empty_prepared_import")
    report = {"status": "dry_run_validated", "candidates": len(prepared.candidates),
              "ingested": 0, "replayed": 0, "production_write_attempted": False}
    if not execute:
        return report
    _preflight(store, owner_id)
    report = {**report, "status": "imported", "production_write_attempted": True}
    for candidate in prepared.candidates:
        response = store.ingest_series(candidate.series, namespace="forward", data_mode="live")
        _readback(store, candidate.series, candidate.record, response)
        report = {**report, "ingested": report["ingested"] + 1,
                  "replayed": report["replayed"] + int(response["replayed"])}
    return report


def _runtime_env():
    from prepare_dev_setup import local_env
    values = local_env(ROOT / ".env") if (ROOT / ".env").is_file() else {}
    names = ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "APP_OWNER_USER_ID")
    result = {key: os.environ.get(key, values.get(key, "")) for key in names}
    if (result["SUPABASE_URL"].rstrip("/") != PRODUCTION_URL
            or not result["SUPABASE_SECRET_KEY"]):
        _fail("production_runtime_configuration_missing_or_mismatched")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = _path(args.receipt or f"reviewed-backfill/import-{uuid4().hex}.json", DATA_ROOT)
        if receipt.exists():
            _fail("backfill_receipt_already_exists")
        calendar = load_calendar(ROOT / "config/live/idx-calendar-2024-2026.json")
        prepared = prepare_import(args.plan, data_root=DATA_ROOT, calendar=calendar)
        requests = load_requests(
            ROOT / "config/reference/yfinance-kompas100-verified-mappings.json",
            "yfinance", date(2024, 1, 1), datetime.now(UTC).date())
        if any(value.series.ticker not in requests or value.series.provider_symbol
               != requests[value.series.ticker].symbol for value in prepared.candidates):
            _fail("reviewed_backfill_mapping_unverified")
        if args.execute:
            env = _runtime_env()
            with SupabaseScanStore(PRODUCTION_URL, env["SUPABASE_SECRET_KEY"]) as store:
                report = import_prepared(prepared, store, owner_id=env["APP_OWNER_USER_ID"],
                                         execute=True)
        else:
            report = import_prepared(prepared)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        private = {**report, "plan_sha256": prepared.plan_sha256,
                   "manifest_sha256": prepared.manifest_sha256,
                   "records": [{"ticker": value.record.ticker,
                                "session": str(value.record.session),
                                "input_digest": value.series.input_digest,
                                "capture_sha256": value.capture_sha256,
                                "capture_index": value.capture_index,
                                "fetched_at": value.series.fetched_at.isoformat()}
                               for value in prepared.candidates]}
        with receipt.open("x", encoding="utf-8") as target:
            target.write(canonical_json(private) + "\n")
        print(json.dumps(report))
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, PersistenceError) as error:
        code = error.code if isinstance(error, PersistenceError) else "backfill_import_rejected"
        print(json.dumps({"status": "failed", "code": code}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
