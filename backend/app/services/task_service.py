from __future__ import annotations

from app.adapters.c115 import C115Adapter
from app.adapters.quark import QuarkAdapter
from app.core.config import ProviderSettings
from app.core.errors import NotFoundError, ValidationError
from app.schemas.models import (
    TransferCommitResponse,
    TransferItem,
    TransferPrepareResponse,
    OfflineTaskCheckResponse,
    OfflineTaskResponse,
    TaskListItem,
    TaskListResponse,
    TaskStatusResponse,
)
from app.services.task_store import TaskRecord, store
from app.utils.media import infer_cloud_type


class TaskService:
    def __init__(self, c115: C115Adapter, quark: QuarkAdapter, settings: ProviderSettings) -> None:
        self.c115 = c115
        self.quark = quark
        self.settings = settings

    @staticmethod
    def _supports_provider(provider: str) -> bool:
        return provider in {"115", "quark", "tianyi", "123", "magnet", "ed2k"}

    def _ensure_configured(self, provider: str) -> None:
        if self.settings.use_mock:
            return
        if provider in {"magnet", "ed2k", "115"}:
            if not self.settings.c115_cookie:
                raise ValidationError("STORAGE_NOT_CONFIGURED", "115网盘未配置 Cookie", 400)
            return
        if provider == "quark":
            if not self.settings.quark_cookie:
                raise ValidationError("STORAGE_NOT_CONFIGURED", "夸克网盘未配置 Cookie", 400)
            return
        if provider == "tianyi":
            if not self.settings.tianyi_username or not self.settings.tianyi_password:
                raise ValidationError("STORAGE_NOT_CONFIGURED", "天翼云盘未配置账号密码", 400)
            raise ValidationError("STORAGE_NOT_SUPPORTED", "天翼云盘转存功能暂未接入", 400)
        if provider == "123":
            if not self.settings.pan123_username or not self.settings.pan123_password:
                raise ValidationError("STORAGE_NOT_CONFIGURED", "123网盘未配置账号密码", 400)
            raise ValidationError("STORAGE_NOT_SUPPORTED", "123网盘转存功能暂未接入", 400)
        raise ValidationError("STORAGE_NOT_SUPPORTED", "当前链接类型暂不支持转存", 400)

    def check_transfer(self, source_uri: str, preferred_cloud_type: str | None = None) -> OfflineTaskCheckResponse:
        cloud_type = (preferred_cloud_type or "").strip().lower() or infer_cloud_type(source_uri)
        if not self._supports_provider(cloud_type):
            return OfflineTaskCheckResponse(
                provider=cloud_type,
                supported=False,
                configured=False,
                message="无法识别链接对应网盘类型",
            )
        try:
            self._ensure_configured(cloud_type)
        except ValidationError as exc:
            return OfflineTaskCheckResponse(
                provider=cloud_type,
                supported=exc.code != "STORAGE_NOT_SUPPORTED",
                configured=exc.code != "STORAGE_NOT_CONFIGURED",
                message=exc.message,
            )

        default_dir_id = self.settings.c115_target_dir_id if cloud_type in {"115", "magnet", "ed2k"} else "0"
        default_dir_path = self.settings.c115_target_dir_path if cloud_type in {"115", "magnet", "ed2k"} else "/"
        return OfflineTaskCheckResponse(
            provider=cloud_type,
            supported=True,
            configured=True,
            message="ok",
            default_dir_id=default_dir_id,
            default_dir_path=default_dir_path,
        )

    async def prepare_transfer(
        self, source_uri: str, preferred_cloud_type: str | None = None
    ) -> TransferPrepareResponse:
        check = self.check_transfer(source_uri, preferred_cloud_type)
        if not check.supported or not check.configured:
            raise ValidationError("TRANSFER_NOT_READY", check.message, 400)
        provider = check.provider
        if provider in {"magnet", "ed2k"}:
            return TransferPrepareResponse(
                provider=provider,
                title="磁力任务",
                selectable=False,
                items=[],
                default_dir_id=check.default_dir_id,
                default_dir_path=check.default_dir_path,
            )
        return await self.list_transfer_items(source_uri, preferred_cloud_type, "")

    async def list_transfer_items(
        self,
        source_uri: str,
        preferred_cloud_type: str | None = None,
        parent_id: str = "",
    ) -> TransferPrepareResponse:
        check = self.check_transfer(source_uri, preferred_cloud_type)
        if not check.supported or not check.configured:
            raise ValidationError("TRANSFER_NOT_READY", check.message, 400)
        provider = check.provider
        if provider in {"magnet", "ed2k"}:
            return TransferPrepareResponse(
                provider=provider,
                title="磁力任务",
                selectable=False,
                items=[],
                default_dir_id=check.default_dir_id,
                default_dir_path=check.default_dir_path,
            )
        if provider == "115":
            rows = await self.c115.list_share_items(source_uri, parent_id)
            return TransferPrepareResponse(
                provider=provider,
                title="115分享资源",
                selectable=True,
                items=[
                    TransferItem(
                        id=x["id"],
                        name=x["name"],
                        size=x.get("size"),
                        is_dir=bool(x.get("is_dir")),
                    )
                    for x in rows
                ],
                default_dir_id=check.default_dir_id,
                default_dir_path=check.default_dir_path,
            )
        if provider == "quark":
            rows = await self.quark.list_share_items(source_uri, parent_id or "0")
            return TransferPrepareResponse(
                provider=provider,
                title="夸克分享资源",
                selectable=True,
                items=[
                    TransferItem(
                        id=x["id"],
                        name=x["name"],
                        size=x.get("size"),
                        is_dir=bool(x.get("is_dir")),
                    )
                    for x in rows
                ],
                default_dir_id="0",
                default_dir_path="/",
            )
        raise ValidationError("TRANSFER_NOT_SUPPORTED", "当前链接类型暂不支持资源选择", 400)

    async def commit_transfer(
        self,
        request_id: str,
        source_uri: str,
        target_dir_id: str,
        selected_ids: list[str],
        preferred_cloud_type: str | None = None,
    ) -> TransferCommitResponse:
        cloud_type = (preferred_cloud_type or "").strip().lower() or infer_cloud_type(source_uri)
        self._ensure_configured(cloud_type)
        if cloud_type in {"magnet", "ed2k"}:
            task = await self.create_offline_task(request_id, source_uri, target_dir_id)
            return TransferCommitResponse(request_id=request_id, task_id=task.task_id, provider=cloud_type)
        if cloud_type == "115":
            task_id = await self.c115.save_share_items(source_uri, target_dir_id, selected_ids)
            return TransferCommitResponse(request_id=request_id, task_id=task_id, provider=cloud_type)
        if cloud_type == "quark":
            task_id = await self.quark.save_selected_items(source_uri, target_dir_id, selected_ids)
            return TransferCommitResponse(request_id=request_id, task_id=task_id, provider=cloud_type)
        raise ValidationError("TRANSFER_NOT_SUPPORTED", "当前链接类型暂不支持转存", 400)

    async def create_offline_task(
        self, request_id: str, source_uri: str, target_dir_id: str
    ) -> OfflineTaskResponse:
        cloud_type = infer_cloud_type(source_uri)
        if not self._supports_provider(cloud_type):
            raise ValidationError("STORAGE_NOT_SUPPORTED", "无法识别链接对应网盘类型", 400)
        self._ensure_configured(cloud_type)

        idem_key = self.c115.make_idempotency_key(source_uri, target_dir_id)
        existing = store.get_by_idem_key(idem_key)
        if existing:
            return OfflineTaskResponse(
                request_id=request_id,
                task_id=existing.task_id,
                existing_task=True,
                status=existing.status,
            )

        if cloud_type == "quark":
            upstream_task_id = await self.quark.save_shared_file(source_uri, target_dir_id)
        else:
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
