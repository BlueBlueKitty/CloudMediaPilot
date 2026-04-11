from __future__ import annotations

from app.adapters.c115 import C115Adapter
from app.core.errors import NotFoundError
from app.schemas.models import (
    OfflineTaskResponse,
    TaskListItem,
    TaskListResponse,
    TaskStatusResponse,
)
from app.services.task_store import TaskRecord, store


class TaskService:
    def __init__(self, c115: C115Adapter) -> None:
        self.c115 = c115

    async def create_offline_task(
        self, request_id: str, source_uri: str, target_dir_id: str
    ) -> OfflineTaskResponse:
        idem_key = self.c115.make_idempotency_key(source_uri, target_dir_id)
        existing = store.get_by_idem_key(idem_key)
        if existing:
            return OfflineTaskResponse(
                request_id=request_id,
                task_id=existing.task_id,
                existing_task=True,
                status=existing.status,
            )

        upstream_task_id = await self.c115.create_offline_task(source_uri, target_dir_id)
        rec = TaskRecord(
            task_id=upstream_task_id,
            idem_key=idem_key,
            source_uri=source_uri,
            target_dir_id=target_dir_id,
            internal_state="dispatched",
            status="queued",
        )
        store.put(rec)

        return OfflineTaskResponse(
            request_id=request_id,
            task_id=rec.task_id,
            existing_task=False,
            status=rec.status,
        )

    async def get_task(self, request_id: str, task_id: str) -> TaskStatusResponse:
        rec = store.get(task_id)
        if not rec:
            raise NotFoundError("TASK_NOT_FOUND", f"task '{task_id}' not found", 404)

        status, msg = await self.c115.query_task(task_id)
        internal = rec.internal_state
        if status == "completed":
            internal = "completed"
        elif status == "running":
            internal = "dispatched"
        elif status == "failed":
            internal = "dispatch_failed"
        rec = (
            store.update_state(task_id, internal_state=internal, status=status, message=msg) or rec
        )

        return TaskStatusResponse(
            request_id=request_id,
            task_id=task_id,
            internal_state=rec.internal_state,
            status=rec.status,
            message=rec.message,
        )

    async def list_tasks(self, request_id: str, limit: int = 50) -> TaskListResponse:
        tasks = [
            TaskListItem(
                task_id=row.task_id,
                source_uri=row.source_uri,
                target_dir_id=row.target_dir_id,
                internal_state=row.internal_state,
                status=row.status,
                created_at=row.created_at,
                message=row.message,
            )
            for row in store.list_recent(limit)
        ]
        return TaskListResponse(request_id=request_id, total=len(tasks), tasks=tasks)
