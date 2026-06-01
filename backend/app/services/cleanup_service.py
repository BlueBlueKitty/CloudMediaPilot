from __future__ import annotations

import asyncio
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
import logging
from pathlib import Path
import re
import secrets
import time

from app.adapters.c115 import C115Adapter
from app.adapters.quark import QuarkAdapter
from app.core.config import ProviderSettings
from app.core.errors import ValidationError
from app.schemas.models import (
    CleanupExecuteResponse,
    CleanupMatchedItem,
    CleanupPreviewResponse,
    CleanupRuleStat,
)
from app.services.resource_filter_service import ResourceEntry, ResourceFilterService


@dataclass(slots=True)
class _PreviewPayload:
    provider: str
    items: list[CleanupMatchedItem]
    created_at: float


_PREVIEW_STORE: dict[str, _PreviewPayload] = {}
_PREVIEW_TTL_SECONDS = 900
logger = logging.getLogger("cleanup")


class CleanupService:
    def __init__(
        self,
        c115: C115Adapter,
        quark: QuarkAdapter,
        settings: ProviderSettings,
        filter_service: ResourceFilterService,
    ) -> None:
        self.c115 = c115
        self.quark = quark
        self.settings = settings
        self.filter_service = filter_service

    @staticmethod
    def _prune_preview_store() -> None:
        now = time.time()
        expired = [key for key, value in _PREVIEW_STORE.items() if now - value.created_at > _PREVIEW_TTL_SECONDS]
        for key in expired:
            _PREVIEW_STORE.pop(key, None)

    async def _walk_115(self, parent_id: str, parent_path: str | None = None) -> list[ResourceEntry]:
        path, _ancestors, rows = await self.c115.list_storage_entries(parent_id or "0")
        base_path = parent_path or path or "/"
        logger.info("cleanup_scan_dir provider=115 path=%s", base_path)
        out: list[ResourceEntry] = []
        for row in rows:
            entry_path = f"{base_path.rstrip('/')}/{row['name']}".replace("//", "/")
            if row.get("is_dir"):
                out.extend(await self._walk_115(str(row["id"]), entry_path))
                continue
            out.append(
                ResourceEntry(
                    id=str(row["id"]),
                    name=str(row["name"]),
                    path=entry_path,
                    provider="115",
                    size=row.get("size"),
                    is_dir=False,
                )
            )
        return out

    async def _walk_quark(self, parent_id: str, parent_path: str | None = None) -> list[ResourceEntry]:
        path, _ancestors, rows = await self.quark.list_storage_entries(parent_id or "0")
        base_path = parent_path or path or "/"
        logger.info("cleanup_scan_dir provider=quark path=%s", base_path)
        out: list[ResourceEntry] = []
        for row in rows:
            entry_path = f"{base_path.rstrip('/')}/{row['name']}".replace("//", "/")
            if row.get("is_dir"):
                out.extend(await self._walk_quark(str(row["id"]), entry_path))
                continue
            out.append(
                ResourceEntry(
                    id=str(row["id"]),
                    name=str(row["name"]),
                    path=entry_path,
                    provider="quark",
                    size=row.get("size"),
                    is_dir=False,
                )
            )
        return out

    def _allowed_local_roots(self) -> list[Path]:
        return [Path(item).resolve() for item in self.filter_service.local_roots()]

    def _walk_local_gen(self, requested_root: str | None):
        """Generator that yields (log_msg_or_None, ResourceEntry_or_None) during scan."""
        roots = self._allowed_local_roots()
        if not roots:
            raise ValidationError("LOCAL_ROOTS_EMPTY", "请先配置本地扫描根目录", 400)
        chosen: list[Path]
        if requested_root:
            target = Path(requested_root).resolve()
            if not any(target == root or target.is_relative_to(root) for root in roots):
                raise ValidationError("LOCAL_ROOT_INVALID", "选择的本地根目录不在允许列表中", 400)
            chosen = [target]
        else:
            chosen = roots
        # Pre-compute relevant extensions from enabled rules for early skip
        relevant_exts: set[str] = set()
        can_skip_by_ext = True
        for rule in self.filter_service.rules():
            if not rule.enabled:
                continue
            if rule.applies_to not in {"cleanup", "both"}:
                continue
            glob_lower = rule.glob.lower()
            match = re.search(r"(\.[a-z0-9]{1,16})$", glob_lower)
            if match:
                relevant_exts.add(match.group(1))
            else:
                # Any rule without a clear extension suffix makes ext-only
                # skipping unsafe; keep full scan to avoid missing matches.
                can_skip_by_ext = False
                break
        for root in chosen:
            if not root.exists():
                continue
            root_str = str(root)
            root_name = root.name
            yield (f"cleanup_scan_dir provider=local path={root}", None)
            dirs = [root_str]
            while dirs:
                dir_path = dirs.pop()
                if dir_path != root_str:
                    yield (f"cleanup_scan_dir provider=local path={dir_path}", None)
                try:
                    with os.scandir(dir_path) as it:
                        for entry in it:
                            try:
                                if entry.is_dir(follow_symlinks=False):
                                    dirs.append(entry.path)
                                elif entry.is_file(follow_symlinks=False):
                                    if can_skip_by_ext and relevant_exts:
                                        _dot = entry.name.rfind(".")
                                        if _dot >= 0:
                                            ext = entry.name[_dot:].lower()
                                        else:
                                            ext = ""
                                        if ext not in relevant_exts:
                                            continue
                                    size = entry.stat().st_size
                                    rel = os.path.relpath(entry.path, root_str)
                                    posix_rel = rel.replace("\\", "/")
                                    yield (None, ResourceEntry(
                                        id=entry.path,
                                        name=entry.name,
                                        path=f"/{root_name}/{posix_rel}",
                                        provider="local",
                                        size=size,
                                        is_dir=False,
                                    ))
                            except (OSError, ValueError):
                                continue
                except PermissionError:
                    continue

    def _walk_local(self, requested_root: str | None) -> list[ResourceEntry]:
        out: list[ResourceEntry] = []
        for log_msg, entry_or_none in self._walk_local_gen(requested_root):
            if entry_or_none is not None:
                out.append(entry_or_none)
        return out

    async def _entries_for_provider(self, provider: str, parent_id: str | None, local_root: str | None) -> list[ResourceEntry]:
        if provider == "115":
            return await self._walk_115(parent_id or "0")
        if provider == "quark":
            return await self._walk_quark(parent_id or "0")
        if provider == "local":
            return await asyncio.to_thread(self._walk_local, local_root)
        raise ValidationError("CLEANUP_PROVIDER_UNSUPPORTED", "不支持的清理目标", 400)

    async def stream_local_preview(self, request_id: str, local_root: str):
        """Async generator that yields SSE events: logs, real-time matches, then final result."""
        from asyncio import Queue as _Queue

        queue: _Queue[tuple[str | None, ResourceEntry | None] | None] = _Queue()

        def _run():
            try:
                for log_msg, entry in self._walk_local_gen(local_root):
                    queue.put_nowait((log_msg, entry))
            except ValidationError as exc:
                queue.put_nowait(("error", str(exc)))
            finally:
                queue.put_nowait(None)

        loop = asyncio.get_event_loop()
        scan_task = loop.run_in_executor(None, _run)

        preview_token = secrets.token_hex(12)
        yield ("start", preview_token)
        matched: list[CleanupMatchedItem] = []
        stats_count: Counter[tuple[str, str]] = Counter()
        stats_size: defaultdict[tuple[str, str], int] = defaultdict(int)
        total_size = 0
        completed = False

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                log_msg, entry = item
                if log_msg == "error":
                    yield ("error", entry)
                    return
                if log_msg:
                    yield ("log", log_msg)
                if entry is not None:
                    match = self.filter_service.match(entry, operation="cleanup")
                    if match:
                        matched_item = CleanupMatchedItem(
                            id=entry.id, path=entry.path, name=entry.name, size=entry.size,
                            rule_id=match.rule_id, rule_name=match.rule_name, provider="local",
                        )
                        matched.append(matched_item)
                        yield ("match", matched_item.model_dump_json())
                        key = (match.rule_id, match.rule_name)
                        stats_count[key] += 1
                        stats_size[key] += entry.size or 0
                        total_size += entry.size or 0

            await scan_task
            completed = True
        finally:
            # Always save whatever we matched so far (supports stop-and-cleanup)
            rules = [
                CleanupRuleStat(rule_id=rule_id, rule_name=rule_name, count=count, total_size=stats_size[(rule_id, rule_name)])
                for (rule_id, rule_name), count in stats_count.items()
            ]
            _PREVIEW_STORE[preview_token] = _PreviewPayload(provider="local", items=matched, created_at=time.time())

        result = CleanupPreviewResponse(
            request_id=request_id, provider="local", preview_token=preview_token,
            total_matches=len(matched), total_size=total_size,
            rules=sorted(rules, key=lambda x: (-x.count, x.rule_name)), items=matched,
        )
        yield ("result", result.model_dump_json())

    async def preview(
        self,
        request_id: str,
        provider: str,
        parent_id: str | None = None,
        local_root: str | None = None,
    ) -> CleanupPreviewResponse:
        self._prune_preview_store()
        entries = await self._entries_for_provider(provider, parent_id, local_root)
        matched: list[CleanupMatchedItem] = []
        stats_count: Counter[tuple[str, str]] = Counter()
        stats_size: defaultdict[tuple[str, str], int] = defaultdict(int)
        total_size = 0
        for entry in entries:
            match = self.filter_service.match(entry, operation="cleanup")
            if not match:
                continue
            item = CleanupMatchedItem(
                id=entry.id,
                path=entry.path,
                name=entry.name,
                size=entry.size,
                rule_id=match.rule_id,
                rule_name=match.rule_name,
                provider=provider,
            )
            matched.append(item)
            key = (match.rule_id, match.rule_name)
            stats_count[key] += 1
            stats_size[key] += entry.size or 0
            total_size += entry.size or 0
        rules = [
            CleanupRuleStat(rule_id=rule_id, rule_name=rule_name, count=count, total_size=stats_size[(rule_id, rule_name)])
            for (rule_id, rule_name), count in stats_count.items()
        ]
        preview_token = secrets.token_hex(12)
        _PREVIEW_STORE[preview_token] = _PreviewPayload(provider=provider, items=matched, created_at=time.time())
        return CleanupPreviewResponse(
            request_id=request_id,
            provider=provider,
            preview_token=preview_token,
            total_matches=len(matched),
            total_size=total_size,
            rules=sorted(rules, key=lambda x: (-x.count, x.rule_name)),
            items=matched,
        )

    def _delete_local(self, items: list[CleanupMatchedItem]) -> tuple[int, int]:
        roots = self._allowed_local_roots()
        deleted = 0
        deleted_size = 0
        for item in items:
            path = Path(item.id).resolve()
            if not any(path.is_relative_to(root) for root in roots):
                continue
            if not path.exists() or not path.is_file():
                continue
            size = path.stat().st_size
            path.unlink()
            deleted += 1
            deleted_size += size
        return deleted, deleted_size

    async def execute(self, request_id: str, preview_token: str, selected_ids: list[str] | None = None) -> CleanupExecuteResponse:
        self._prune_preview_store()
        payload = _PREVIEW_STORE.pop(preview_token, None)
        if payload is None:
            raise ValidationError("CLEANUP_PREVIEW_EXPIRED", "预览已失效，请重新扫描", 400)
        items = [item for item in payload.items if selected_ids is None or item.id in selected_ids]
        ids = [item.id for item in items]
        total_size = sum(item.size or 0 for item in items)
        if payload.provider == "115":
            deleted = await self.c115.delete_files(ids)
            return CleanupExecuteResponse(request_id=request_id, provider="115", deleted_count=deleted, deleted_size=total_size)
        if payload.provider == "quark":
            deleted = await self.quark.delete_files(ids)
            return CleanupExecuteResponse(request_id=request_id, provider="quark", deleted_count=deleted, deleted_size=total_size)
        deleted, deleted_size = self._delete_local(items)
        return CleanupExecuteResponse(request_id=request_id, provider="local", deleted_count=deleted, deleted_size=deleted_size)
