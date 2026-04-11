from pathlib import Path
from typing import Protocol

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse

from app.adapters.c115 import C115Adapter
from app.adapters.pansou import PanSouAdapter
from app.adapters.prowlarr import ProwlarrAdapter
from app.adapters.tmdb import TMDBAdapter
from app.core.config import get_settings
from app.core.deps import (
    get_app_config_store,
    get_provider_status_service,
    get_search_service,
    get_task_service,
)
from app.schemas.models import (
    ConnectionTestRequest,
    ConnectionTestResponse,
    ConnectionTestResult,
    HealthResponse,
    OfflineTaskRequest,
    OfflineTaskResponse,
    ProviderStatusResponse,
    ReadyResponse,
    SearchRequest,
    SearchResponse,
    SettingsResponse,
    SettingsUpdateRequest,
    TaskListResponse,
    TaskStatusResponse,
    TMDBSearchResponse,
)
from app.services.app_config_service import AppConfigStore, build_provider_settings
from app.services.provider_status_service import ProviderStatusService
from app.services.search_service import SearchService
from app.services.task_service import TaskService
from app.utils.ids import new_request_id

router = APIRouter()

_WEBUI_INDEX = Path(__file__).resolve().parent.parent / "webui" / "index.html"


class _CheckableAdapter(Protocol):
    async def check(self) -> tuple[bool, str]: ...


@router.get("/", response_class=HTMLResponse)
async def index() -> str:
    return _WEBUI_INDEX.read_text(encoding="utf-8")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", response_model=ReadyResponse)
async def ready(store: AppConfigStore = Depends(get_app_config_store)) -> ReadyResponse:
    runtime = get_settings()
    cfg = store.get()
    checks = {
        "pansou": (not cfg.enable_pansou) or bool(cfg.pansou_base_url),
        "prowlarr": (not cfg.enable_prowlarr) or bool(cfg.prowlarr_base_url),
        "tmdb": (not cfg.enable_tmdb) or runtime.use_mock or bool(cfg.tmdb_api_key),
        "c115": runtime.use_mock or bool(cfg.c115_cookie),
    }
    return ReadyResponse(checks=checks)


@router.get("/tmdb/search", response_model=TMDBSearchResponse)
async def tmdb_search(
    query: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    store: AppConfigStore = Depends(get_app_config_store),
) -> TMDBSearchResponse:
    runtime = get_settings()
    adapter = TMDBAdapter(build_provider_settings(runtime, store.get()))
    rows = await adapter.search(query, limit)
    return TMDBSearchResponse(
        request_id=new_request_id(),
        query=query,
        total=len(rows),
        results=rows,
    )


@router.get("/tmdb/trending", response_model=TMDBSearchResponse)
async def tmdb_trending(
    limit: int = Query(default=20, ge=1, le=50),
    store: AppConfigStore = Depends(get_app_config_store),
) -> TMDBSearchResponse:
    runtime = get_settings()
    adapter = TMDBAdapter(build_provider_settings(runtime, store.get()))
    rows = await adapter.trending(limit)
    return TMDBSearchResponse(
        request_id=new_request_id(),
        query="trending",
        total=len(rows),
        results=rows,
    )


@router.post("/search", response_model=SearchResponse)
async def search(
    payload: SearchRequest,
    svc: SearchService = Depends(get_search_service),
) -> SearchResponse:
    return await svc.search(
        new_request_id(),
        payload.keyword,
        payload.limit,
        payload.tmdb_context,
    )


@router.post("/tasks/offline", response_model=OfflineTaskResponse)
async def create_offline_task(
    payload: OfflineTaskRequest,
    svc: TaskService = Depends(get_task_service),
    store: AppConfigStore = Depends(get_app_config_store),
) -> OfflineTaskResponse:
    target = payload.target_dir_id or store.get().c115_target_dir_id
    return await svc.create_offline_task(new_request_id(), payload.source_uri, target)


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def task_status(
    task_id: str, svc: TaskService = Depends(get_task_service)
) -> TaskStatusResponse:
    return await svc.get_task(new_request_id(), task_id)


@router.get("/tasks", response_model=TaskListResponse)
async def task_list(
    limit: int = Query(default=50, ge=1, le=200),
    svc: TaskService = Depends(get_task_service),
) -> TaskListResponse:
    return await svc.list_tasks(new_request_id(), limit)


@router.get("/providers/status", response_model=ProviderStatusResponse)
async def provider_status(
    svc: ProviderStatusService = Depends(get_provider_status_service),
) -> ProviderStatusResponse:
    return await svc.get_status(new_request_id())


@router.get("/settings", response_model=SettingsResponse)
async def get_app_settings(
    store: AppConfigStore = Depends(get_app_config_store),
) -> SettingsResponse:
    masked = store.mask(store.get())
    return SettingsResponse(**masked)


@router.put("/settings", response_model=SettingsResponse)
async def update_app_settings(
    payload: SettingsUpdateRequest,
    store: AppConfigStore = Depends(get_app_config_store),
) -> SettingsResponse:
    next_cfg = store.update(
        tmdb_base_url=payload.tmdb_base_url,
        tmdb_api_key=payload.tmdb_api_key,
        prowlarr_base_url=payload.prowlarr_base_url,
        prowlarr_api_key=payload.prowlarr_api_key,
        pansou_base_url=payload.pansou_base_url,
        enable_tmdb=payload.enable_tmdb,
        enable_prowlarr=payload.enable_prowlarr,
        enable_pansou=payload.enable_pansou,
        c115_base_url=payload.c115_base_url,
        c115_cookie=payload.c115_cookie,
        c115_allowed_actions=payload.c115_allowed_actions,
        c115_target_dir_id=payload.c115_target_dir_id,
        c115_offline_add_path=payload.c115_offline_add_path,
        c115_offline_list_path=payload.c115_offline_list_path,
    )
    return SettingsResponse(**store.mask(next_cfg))


@router.post("/settings/test", response_model=ConnectionTestResponse)
async def test_connections(
    payload: ConnectionTestRequest,
    store: AppConfigStore = Depends(get_app_config_store),
) -> ConnectionTestResponse:
    runtime = get_settings()
    settings = build_provider_settings(runtime, store.get())

    adapters: list[tuple[str, _CheckableAdapter]] = [
        ("tmdb", TMDBAdapter(settings)),
        ("prowlarr", ProwlarrAdapter(settings)),
        ("pansou", PanSouAdapter(settings)),
        ("c115", C115Adapter(settings)),
    ]
    if payload.provider != "all":
        adapters = [row for row in adapters if row[0] == payload.provider]

    out: list[ConnectionTestResult] = []
    for name, adapter in adapters:
        ok, msg = await adapter.check()
        out.append(ConnectionTestResult(provider=name, ok=ok, message=msg))

    return ConnectionTestResponse(request_id=new_request_id(), results=out)
