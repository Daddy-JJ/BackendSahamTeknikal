"""Versioned Supabase paper runtime; service credentials remain in scan store."""
from datetime import date, datetime
from uuid import UUID

from .paper_research import MODEL_VERSION
from .persistence import PersistenceError, SupabaseScanStore


class PaperRuntimeStore:
    def __init__(self, store: SupabaseScanStore, owner_id: str, data_mode: str = "live"):
        if str(UUID(owner_id)) != owner_id or data_mode not in ("live", "fixture"):
            raise ValueError("invalid_paper_owner_context")
        self.store, self.owner_id, self.data_mode = store, owner_id, data_mode

    def _rpc(self, name: str, **kwargs):
        return self.store._request("POST", "rpc/" + name, json={
            "p_owner_id": self.owner_id, "p_data_mode": self.data_mode, **kwargs,
        })

    def _runtime(self, response):
        try:
            if (not isinstance(response, dict) or response["owner_id"] != self.owner_id
                or response["data_mode"] != self.data_mode
                or response["model_version"] != MODEL_VERSION
                or type(response["revision"]) is not int or response["revision"] < 0
                or not isinstance(response["book"], dict)
                or not isinstance(response["book"]["trades"], dict)
                or not isinstance(response["book"]["experiments"], dict)
                or not isinstance(response["evaluations"], dict)
                or datetime.fromisoformat(response["activated_at"]).tzinfo is None):
                raise ValueError("invalid_paper_runtime")
            return response
        except (KeyError, TypeError, ValueError):
            raise PersistenceError("database_invalid_paper_runtime") from None

    def initialize(self):
        return self._runtime(self._rpc("init_paper_model_v1"))

    def load(self):
        return self._runtime(self._rpc("load_paper_runtime_v1"))

    def commit(self, *, revision: int, request_id: str, session: date,
               book: dict, evaluations: dict, source_run_id: str | None = None):
        result = self._rpc(
            "commit_paper_session_v1", p_expected_revision=revision,
            p_request_id=request_id, p_session=session.isoformat(),
            p_book=book, p_evaluations=evaluations, p_source_run_id=source_run_id,
        )
        if (not isinstance(result, dict) or type(result.get("revision")) is not int
            or not isinstance(result.get("replayed"), bool)):
            raise PersistenceError("database_invalid_paper_commit")
        return result

    def committed_signals(self, through: date, activation: datetime):
        state = self.store.load_state(through_session=through, data_mode=self.data_mode)
        return sorted((s for s in state.signals.values()
                       if s.cohort == "forward" and s.published_at >= activation
                       and s.candidate.execution_eligible), key=lambda s: (s.session, s.id))

    def record_job(self, *, job_id: str, phase: str, status: str, session: date,
                   failure_code: str | None = None, context: dict | None = None):
        response = self._rpc(
            "record_paper_job_v1", p_job_id=job_id, p_phase=phase, p_status=status,
            p_session=session.isoformat(), p_failure_code=failure_code,
            p_context=context or {},
        )
        if (not isinstance(response, dict) or response.get("contract_version") != 1
            or response.get("job_id") != job_id or response.get("phase") != phase
            or response.get("status") != status or not isinstance(response.get("replayed"), bool)):
            raise PersistenceError("database_invalid_paper_job")
        return response
