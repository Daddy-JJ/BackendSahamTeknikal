"""Cloud heartbeat failure and overlap exclusion using offline RPC doubles."""
from datetime import date

import pytest

from idx_scanner.paper_lease import PaperRuntimeLease
from idx_scanner.persistence import PersistenceError


class Store:
    def __init__(self, acquired=True, fail_heartbeat=False):
        self.calls = []
        self.acquired, self.fail_heartbeat = acquired, fail_heartbeat

    def runtime_lease(self, operation, job_id, session=None):
        self.calls.append(operation)
        if operation == "heartbeat" and self.fail_heartbeat:
            raise PersistenceError("database_transport_failed")
        return {"acquired": self.acquired}


def test_lease_releases_after_processing_exception():
    store = Store()
    with pytest.raises(ValueError, match="processing"):
        with PaperRuntimeLease(store, "job", date(2026, 10, 12)) as lease:
            assert lease.acquired
            raise ValueError("processing")
    assert store.calls == ["claim", "release"]


def test_busy_lease_neither_heartbeats_nor_releases_another_job():
    store = Store(False)
    with PaperRuntimeLease(store, "job", date(2026, 10, 12)) as lease:
        assert not lease.acquired
    assert store.calls == ["claim"]


def test_failed_heartbeat_prevents_false_success():
    store = Store(fail_heartbeat=True)
    with pytest.raises(PersistenceError, match="paper_runtime_heartbeat_failed"):
        with PaperRuntimeLease(store, "job", date(2026, 10, 12), interval_seconds=0.001) as lease:
            lease.thread.join(timeout=1)
            lease.require_healthy()
    assert store.calls == ["claim", "heartbeat", "release"]
