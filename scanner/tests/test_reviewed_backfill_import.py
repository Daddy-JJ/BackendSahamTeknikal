"""Operator boundaries: no source acceptance or writes without reviewed evidence."""
import importlib.util
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest

from idx_scanner.fixtures import sample_market
from idx_scanner.models import canonical_json
from idx_scanner.paper_research import MODEL_VERSION
from idx_scanner.persistence import PersistenceError
from idx_scanner.reviewed_backfill import BACKFILL_VERSION, YAHOO_BASIS

SCRIPT = (Path(__file__).resolve().parents[2]
          / "supabase/scripts/import_reviewed_historical_ohlcv.py")
spec = importlib.util.spec_from_file_location("reviewed_backfill_import", SCRIPT)
operator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = operator
spec.loader.exec_module(operator)
OWNER = "12345678-1234-4234-8234-123456789012"
REVISION = "87654321-4321-4321-8321-210987654321"
NOW = datetime(2030, 1, 3, tzinfo=UTC)


def write(path, value):
    content = canonical_json(value).encode()
    path.write_bytes(content)
    return sha256(content).hexdigest()


@pytest.fixture
def evidence(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    values, calendar, _ = sample_market(3)
    source = replace(values["DEMO-A"], ticker="ADRO", provider_symbol="ADRO.JK",
                     provider="yfinance", price_basis=YAHOO_BASIS,
                     provider_version="1.7.0", fetched_at=NOW)
    day = source.bars[-1].session
    reference = {"version": "independent_ohlcv_reference_v1", "exchange": "XIDX",
                 "timezone": "Asia/Jakarta", "session": str(day), "volume_unit": "shares",
                 "source_url": "https://www.idx.co.id/data/stock-summary/",
                 "rows": [{"ticker": source.ticker,
                           **{key: getattr(source.bars[-1], key)
                              for key in ("open", "high", "low", "close", "volume")}}]}
    reference_hash = write(data / "reference.json", reference)
    manifest = {"version": BACKFILL_VERSION, "data_mode": "live", "records": [{
        "ticker": source.ticker, "provider_symbol": source.provider_symbol,
        "session": str(day), "provider": source.provider, "price_basis": source.price_basis,
        "provider_version": source.provider_version, "source_input_digest": source.input_digest,
        "reference": {"source_url": reference["source_url"],
                      "document_sha256": reference_hash, "reviewed_at": NOW.isoformat()}}]}
    write(data / "manifest.json", manifest)
    capture_hash = write(data / "capture.json", [source])
    plan = {"version": "reviewed_backfill_import_v1", "manifest_path": "manifest.json",
            "reference_documents": ["reference.json"], "captures": [{
                "path": "capture.json", "index": 0, "file_sha256": capture_hash,
                "ticker": source.ticker, "session": str(day),
                "source_input_digest": source.input_digest}]}
    write(data / "plan.json", plan)
    return data, source, replace(calendar, data_mode="live"), plan, manifest, reference


class Store:
    def __init__(self):
        self.calls = []
        self.sources = {}
        self.enabled = True
        self.runtime = {"owner_id": OWNER, "data_mode": "live", "model_version": MODEL_VERSION,
                        "revision": 4, "book": {"trades": {}, "experiments": {}},
                        "evaluations": {}, "activated_at": "2029-01-01T00:00:00+00:00"}

    def require_live_schema(self):
        self.calls.append("schema")

    def _request(self, method, path, **kwargs):
        self.calls.append(path)
        if path == "app_members":
            return [{"role": "owner", "enabled": self.enabled}]
        if path == "rpc/load_paper_runtime_v1":
            assert kwargs["json"] == {"p_owner_id": OWNER, "p_data_mode": "live"}
            return self.runtime
        raise AssertionError("unexpected endpoint " + path)

    def ingest_series(self, source, **kwargs):
        assert kwargs == {"namespace": "forward", "data_mode": "live"}
        self.calls.append("ingest")
        replayed = source.input_digest in self.sources
        self.sources = {**self.sources, source.input_digest: source}
        return {"revision_id": REVISION, "replayed": replayed}

    def load_series(self, revision_id, **kwargs):
        assert UUID(revision_id)
        self.calls.append("readback")
        return self.sources[kwargs["expected_input_digest"]]


def load(evidence):
    data, _, calendar, *_ = evidence
    return operator.prepare_import(data / "plan.json", data_root=data, calendar=calendar, now=NOW)


def test_default_dry_run_preserves_exact_source_and_performs_no_database_io(evidence):
    prepared = load(evidence)
    store = Store()
    report = operator.import_prepared(prepared, store, owner_id=OWNER)
    assert report == {"status": "dry_run_validated", "candidates": 1, "ingested": 0,
                      "replayed": 0, "production_write_attempted": False}
    assert prepared.candidates[0].series == evidence[1]
    assert store.calls == []


def test_execute_checks_active_owner_model_and_reuses_digest_revision_on_retry(evidence):
    prepared, store = load(evidence), Store()
    first = operator.import_prepared(prepared, store, owner_id=OWNER, execute=True)
    second = operator.import_prepared(prepared, store, owner_id=OWNER, execute=True)
    assert first["ingested"] == 1 and first["replayed"] == 0
    assert second["ingested"] == 1 and second["replayed"] == 1
    assert len(store.sources) == 1
    assert store.sources[evidence[1].input_digest].fetched_at == NOW
    assert store.calls == ["schema", "app_members", "rpc/load_paper_runtime_v1", "ingest",
                           "readback"] * 2


@pytest.mark.parametrize("change", ["hash", "price", "volume", "date", "url", "duplicate",
                                   "basis", "digest", "capture_index", "empty", "unknown"])
def test_all_evidence_is_checked_before_any_write(evidence, change):
    data, source, _, plan, manifest, reference = evidence
    if change == "hash":
        reference["rows"][0]["close"] = 999
        write(data / "reference.json", reference)
    elif change in ("price", "volume", "date", "url", "duplicate"):
        if change == "price":
            reference["rows"][0]["close"] += 1
        elif change == "volume":
            reference["rows"][0]["volume"] += 1
        elif change == "date":
            reference["session"] = "2026-10-09"
        elif change == "url":
            reference["source_url"] = "https://finance.yahoo.com/"
        else:
            reference["rows"] *= 2
        manifest["records"][0]["reference"]["document_sha256"] = write(
            data / "reference.json", reference)
        write(data / "manifest.json", manifest)
    elif change == "basis":
        manifest["records"][0]["price_basis"] = "eodhd_adjusted"
        write(data / "manifest.json", manifest)
    elif change == "digest":
        plan["captures"][0]["source_input_digest"] = "0" * 64
    elif change == "capture_index":
        plan["captures"][0]["index"] = True
    elif change == "empty":
        plan["captures"] = []
    else:
        plan["provider"] = "eodhd"
    write(data / "plan.json", plan)
    with pytest.raises(ValueError):
        load(evidence)


@pytest.mark.parametrize("path", ["../outside.json", ".env.production-operator.local", "no.txt"])
def test_file_paths_are_confined_to_ignored_json_data(evidence, path):
    data, _, _, plan, *_ = evidence
    plan["manifest_path"] = path
    write(data / "plan.json", plan)
    with pytest.raises(ValueError):
        load(evidence)


def test_duplicate_json_keys_and_nonfinite_capture_rejected(evidence):
    data = evidence[0]
    (data / "plan.json").write_text('{"version":"a","version":"b"}')
    with pytest.raises(ValueError):
        load(evidence)


@pytest.mark.parametrize("context", ["disabled", "wrong_model", "wrong_mode", "bad_owner"])
def test_preflight_failure_never_ingests(evidence, context):
    prepared, store = load(evidence), Store()
    owner = OWNER
    if context == "disabled":
        store.enabled = False
    elif context == "wrong_model":
        store.runtime = {**store.runtime, "model_version": "legacy"}
    elif context == "wrong_mode":
        store.runtime = {**store.runtime, "data_mode": "fixture"}
    else:
        owner = "invalid"
    with pytest.raises((ValueError, PersistenceError)):
        operator.import_prepared(prepared, store, owner_id=owner, execute=True)
    assert "ingest" not in store.calls


def test_readback_must_match_source_exactly(evidence):
    prepared, store = load(evidence), Store()
    store.load_series = lambda *_args, **_kwargs: replace(evidence[1], provider_version="different")
    with pytest.raises(PersistenceError, match="reviewed_backfill_readback_mismatch"):
        operator.import_prepared(prepared, store, owner_id=OWNER, execute=True)


def test_safe_cli_summary_does_not_include_prices_digests_owner_or_raw_errors(evidence):
    report = operator.import_prepared(load(evidence), Store(), owner_id=OWNER)
    output = json.dumps(report)
    for private in (OWNER, evidence[1].input_digest, "provider_symbol", "reference", "close"):
        assert private not in output


def test_later_candidate_failure_rejects_complete_plan_before_any_ingest(evidence):
    data, source, _, plan, manifest, reference = evidence
    second = replace(source, ticker="INDY", provider_symbol="INDY.JK")
    reference["rows"] = [*reference["rows"], {**reference["rows"][0], "ticker": "INDY"}]
    checksum = write(data / "reference.json", reference)
    first_record = {**manifest["records"][0], "reference": {
        **manifest["records"][0]["reference"], "document_sha256": checksum}}
    manifest["records"] = [first_record, {**first_record, "ticker": second.ticker,
        "provider_symbol": second.provider_symbol, "source_input_digest": second.input_digest}]
    write(data / "manifest.json", manifest)
    checksum = write(data / "second.json", [second])
    plan["captures"] = [*plan["captures"], {**plan["captures"][0], "path": "second.json",
        "ticker": "INDY", "source_input_digest": second.input_digest,
        "file_sha256": "0" * 64}]
    write(data / "plan.json", plan)
    store = Store()
    with pytest.raises(ValueError, match="checksum"):
        operator.import_prepared(load(evidence), store, owner_id=OWNER, execute=True)
    assert store.calls == []


@pytest.mark.parametrize("change", ["duplicate_bar", "invalid_bar", "future_fetch",
                                   "wrong_identity", "source_tokens", "float_volume"])
def test_source_or_reference_integrity_rejects_even_rehashed_evidence(evidence, change):
    data, source, _, plan, manifest, reference = evidence
    if change == "duplicate_bar":
        source = replace(source, bars=(*source.bars, source.bars[-1]))
    elif change == "invalid_bar":
        source = replace(source, bars=(*source.bars[:-1], replace(source.bars[-1], close=1)))
    elif change == "future_fetch":
        source = replace(source, fetched_at=NOW + timedelta(seconds=1))
    elif change == "wrong_identity":
        source = replace(source, provider_symbol="INDY.JK")
    elif change == "float_volume":
        reference["rows"][0]["volume"] = "1.5"
        manifest["records"][0]["reference"]["document_sha256"] = write(
            data / "reference.json", reference)
    raw = json.loads(canonical_json(source))
    if change == "source_tokens":
        raw["bars"][-1]["close"] = str(raw["bars"][-1]["close"])
    plan["captures"][0] = {**plan["captures"][0], "file_sha256": write(
        data / "capture.json", [raw]), "source_input_digest": source.input_digest}
    manifest["records"][0]["source_input_digest"] = source.input_digest
    write(data / "plan.json", plan)
    write(data / "manifest.json", manifest)
    with pytest.raises(ValueError):
        load(evidence)


def test_reference_decimal_tokens_are_compared_without_rounding(evidence):
    data, _, _, _, manifest, reference = evidence
    reference["rows"][0] = {key: str(value) if key != "ticker" else value
                            for key, value in reference["rows"][0].items()}
    manifest["records"][0]["reference"]["document_sha256"] = write(
        data / "reference.json", reference)
    write(data / "manifest.json", manifest)
    assert len(load(evidence).candidates) == 1


def test_missing_oversized_non_json_symlink_and_duplicate_reference_files_rejected(evidence):
    data, _, _, plan, *_ = evidence
    plan["reference_documents"] = ["reference.json", "reference.json"]
    write(data / "plan.json", plan)
    with pytest.raises(ValueError, match="duplicate_reference"):
        load(evidence)
    with pytest.raises(ValueError, match="size"):
        operator._document("absent.json", data)
    (data / "big.json").write_bytes(b"x" * (operator.MAX_FILE_BYTES + 1))
    with pytest.raises(ValueError, match="size"):
        operator._document("big.json", data)
    (data / "broken.json").write_bytes(b"\xff")
    with pytest.raises(ValueError, match="invalid_json"):
        operator._document("broken.json", data)
    (data / "infinite.json").write_text('{"value": NaN}')
    with pytest.raises(ValueError, match="nonfinite"):
        operator._document("infinite.json", data)


def test_replayed_import_keeps_prior_database_observation_time(evidence):
    prepared, store = load(evidence), Store()
    prior = replace(evidence[1], fetched_at=NOW - timedelta(seconds=30))
    store.sources = {prior.input_digest: prior}
    original_ingest = store.ingest_series
    def preserve_prior(source, **kwargs):
        result = original_ingest(source, **kwargs)
        store.sources = {prior.input_digest: prior}
        return result
    store.ingest_series = preserve_prior
    result = operator.import_prepared(prepared, store, owner_id=OWNER, execute=True)
    assert result["replayed"] == 1
    assert store.sources[prior.input_digest].fetched_at == prior.fetched_at


def test_cli_dry_run_and_execute_only_emit_operational_counts(evidence, monkeypatch, capsys):
    data, _, calendar, *_ = evidence
    monkeypatch.setattr(operator, "DATA_ROOT", data)
    monkeypatch.setattr(operator, "load_calendar", lambda _: calendar)
    class Clock(datetime):
        @classmethod
        def now(cls, _timezone=None):
            return NOW
    monkeypatch.setattr(operator, "datetime", Clock)
    class Request:
        symbol = "ADRO.JK"
    monkeypatch.setattr(operator, "load_requests", lambda *_: {"ADRO": Request()})
    assert operator.main(["--plan", str(data / "plan.json"),
                          "--receipt", "dry-run.json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run_validated"
    private = json.loads((data / "dry-run.json").read_text())
    assert private["records"][0]["input_digest"] == evidence[1].input_digest
    store = Store()
    store.__enter__ = lambda: store
    store.__exit__ = lambda *_: None
    class Context:
        def __enter__(self):
            return store
        def __exit__(self, *_):
            return None
    monkeypatch.setattr(operator, "SupabaseScanStore", lambda *_: Context())
    monkeypatch.setattr(operator, "_runtime_env", lambda: {
        "APP_OWNER_USER_ID": OWNER, "SUPABASE_SECRET_KEY": "test-not-real"})
    assert operator.main(["--plan", str(data / "plan.json"),
                          "--receipt", "executed.json", "--execute"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "imported"
    assert "ingest" in store.calls


def test_cli_invalid_plan_or_receipt_never_uses_credentials(evidence, monkeypatch, capsys):
    data = evidence[0]
    monkeypatch.setattr(operator, "DATA_ROOT", data)
    monkeypatch.setattr(operator, "load_calendar", lambda _: evidence[2])
    monkeypatch.setattr(operator, "_runtime_env", lambda: pytest.fail("must not read env"))
    assert operator.main(["--plan", "absent.json", "--execute"]) == 1
    assert json.loads(capsys.readouterr().err) == {
        "status": "failed", "code": "backfill_import_rejected"}
    assert operator.main(["--plan", str(data / "plan.json"), "--receipt", "../secret.json",
                          "--execute"]) == 1
    assert "backfill_import_rejected" in capsys.readouterr().err


def test_runtime_env_requires_exact_project_and_service_key(evidence, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    monkeypatch.setattr(operator, "ROOT", evidence[0])
    for name in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "APP_OWNER_USER_ID"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="configuration"):
        operator._runtime_env()
    monkeypatch.setenv("SUPABASE_URL", "https://other-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-not-real")
    with pytest.raises(ValueError, match="configuration"):
        operator._runtime_env()
    monkeypatch.setenv("SUPABASE_URL", operator.PRODUCTION_URL)
    monkeypatch.setenv("APP_OWNER_USER_ID", OWNER)
    assert operator._runtime_env()["APP_OWNER_USER_ID"] == OWNER
