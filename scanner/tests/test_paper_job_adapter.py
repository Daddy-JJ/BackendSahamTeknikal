"""Operational job RPC is service-only and never invents successful receipts."""
import json
from datetime import date

import httpx
import pytest

from idx_scanner.paper_persistence import PaperRuntimeStore
from idx_scanner.persistence import PersistenceError, SupabaseScanStore

OWNER = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize("invalid", [False, True])
def test_health_writer_binds_owner_mode_and_checks_receipt(invalid):
    def respond(request):
        assert request.url.path == "/rest/v1/rpc/record_paper_job_v1"
        body = json.loads(request.content)
        assert body["p_owner_id"] == OWNER and body["p_data_mode"] == "fixture"
        assert body["p_session"] == "2026-10-09"
        assert body["p_failure_code"] == "database_transport_failed"
        return httpx.Response(200, json={} if invalid else {
            "contract_version": 1, "job_id": "fixture-1", "phase": "paper",
            "status": "failed", "replayed": False, "recorded_at": "2026-10-09T12:00:00Z",
        })
    with SupabaseScanStore("http://127.0.0.1", "fixture-only-key", allow_local=True,
                           transport=httpx.MockTransport(respond)) as scan:
        store = PaperRuntimeStore(scan, OWNER, "fixture")
        if invalid:
            with pytest.raises(PersistenceError, match="database_invalid_paper_job"):
                store.record_job(job_id="fixture-1", phase="paper", status="failed",
                                 session=date(2026, 10, 9),
                                 failure_code="database_transport_failed")
        else:
            assert store.record_job(job_id="fixture-1", phase="paper", status="failed",
                                    session=date(2026, 10, 9),
                                    failure_code="database_transport_failed")["status"] == "failed"
