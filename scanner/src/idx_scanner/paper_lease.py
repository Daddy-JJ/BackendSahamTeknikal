"""Cloud lease and bounded heartbeat; no laptop process is part of runtime state."""
from threading import Event, Thread

from .persistence import PersistenceError


class PaperRuntimeLease:
    def __init__(self, store, job_id, session, *, interval_seconds=60):
        self.store, self.job_id, self.session = store, job_id, session
        self.interval_seconds = interval_seconds
        self.stop = Event()
        self.failure = None
        self.acquired = False
        self.thread = None

    def __enter__(self):
        self.acquired = self.store.runtime_lease("claim", self.job_id, self.session)["acquired"]
        if self.acquired:
            self.thread = Thread(target=self._heartbeat, name="paper-lease", daemon=True)
            self.thread.start()
        return self

    def _heartbeat(self):
        while not self.stop.wait(self.interval_seconds):
            try:
                if not self.store.runtime_lease("heartbeat", self.job_id)["acquired"]:
                    raise PersistenceError("paper_runtime_lease_lost")
            except (PersistenceError, ValueError):
                self.failure = PersistenceError("paper_runtime_heartbeat_failed")
                return

    def require_healthy(self):
        if self.failure is not None:
            raise self.failure

    def __exit__(self, exc_type, exc, traceback):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=65)
        if self.acquired:
            self.store.runtime_lease("release", self.job_id)
        if exc is None:
            self.require_healthy()
