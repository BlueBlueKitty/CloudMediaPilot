from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock

from app.schemas.models import PublicTaskState, TaskState


@dataclass
class TaskRecord:
    task_id: str
    idem_key: str
    source_uri: str
    target_dir_id: str
    internal_state: TaskState
    status: PublicTaskState
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    message: str | None = None


class TaskStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._by_task_id: dict[str, TaskRecord] = {}
        self._by_idem_key: dict[str, str] = {}

    def get_by_idem_key(self, idem_key: str) -> TaskRecord | None:
        with self._lock:
            task_id = self._by_idem_key.get(idem_key)
            if not task_id:
                return None
            return self._by_task_id.get(task_id)

    def put(self, record: TaskRecord) -> None:
        with self._lock:
            self._by_task_id[record.task_id] = record
            self._by_idem_key[record.idem_key] = record.task_id

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._by_task_id.get(task_id)

    def list_recent(self, limit: int = 50) -> list[TaskRecord]:
        with self._lock:
            rows = sorted(
                self._by_task_id.values(),
                key=lambda x: x.created_at,
                reverse=True,
            )
            return rows[:limit]

    def update_state(
        self,
        task_id: str,
        *,
        internal_state: TaskState | None = None,
        status: PublicTaskState | None = None,
        message: str | None = None,
    ) -> TaskRecord | None:
        with self._lock:
            record = self._by_task_id.get(task_id)
            if not record:
                return None
            if internal_state is not None:
                record.internal_state = internal_state
            if status is not None:
                record.status = status
            if message is not None:
                record.message = message
            return record


store = TaskStore()
