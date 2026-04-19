from importlib import metadata
import os
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import Response

from app.adapters.c115 import C115Adapter
from app.adapters.douban import DoubanAdapter
from app.adapters.pansou import PanSouAdapter
from app.adapters.prowlarr import ProwlarrAdapter
from app.adapters.quark import QuarkAdapter
from app.adapters.tmdb import TMDBAdapter
from app.core.config import get_settings
from app.core.deps import (
    get_app_config_store,
    get_provider_status_service,
    get_search_service,
    get_task_service,
)
from app.schemas.models import (
    AuthLoginRequest,
    AuthUserResponse,
    C115DirListResponse,
    ConnectionTestRequest,
    ConnectionTestResponse,
    ConnectionTestResult,
    HealthResponse,
    OfflineTaskRequest,
    OfflineTaskCheckRequest,
    OfflineTaskCheckResponse,
    OfflineTaskResponse,
    TransferPrepareRequest,
    TransferPrepareResponse,
    TransferItemsRequest,
    TransferCommitRequest,
    TransferCommitResponse,
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
from app.services.app_config_service import AppConfigStore, build_provider_settings, hash_password
from app.services.auth_service import issue_session_token, parse_session_token, verify_password
from app.services.log_service import handler as memory_log_handler
from app.services.provider_status_service import ProviderStatusService
from app.services.search_service import SearchService
from app.services.task_service import TaskService
from app.utils.ids import new_request_id

router = APIRouter()

_WEBUI_INDEX = Path(__file__).resolve().parent.parent / "webui" / "index.html"
_SESSION_COOKIE = "cmp_session"


class _CheckableAdapter(Protocol):
    async def check(self) -> tuple[bool, str]: ...


def _app_version() -> str:
    env_version = os.getenv("APP_VERSION", "").strip()
    if env_version:
        return env_version
    try:
        return metadata.version("cloudmediapilot-backend")
    except metadata.PackageNotFoundError:
        return "0.1.0"


def _require_auth(request: Request, store: AppConfigStore = Depends(get_app_config_store)) -> str:
    cfg = store.get()
    token = request.cookies.get(_SESSION_COOKIE, "")
    username = parse_session_token(token, cfg)
    if not username:
        raise HTTPException(status_code=401, detail="请先登录")
    return username


@router.get("/", response_class=HTMLResponse)
async def index() -> str:
    return _WEBUI_INDEX.read_text(encoding="utf-8")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/auth/me", response_model=AuthUserResponse)
async def auth_me(request: Request, store: AppConfigStore = Depends(get_app_config_store)) -> AuthUserResponse:
    cfg = store.get()
    token = request.cookies.get(_SESSION_COOKIE, "")
    username = parse_session_token(token, cfg)
    if not username:
        return AuthUserResponse(authenticated=False, username=None)
    return AuthUserResponse(authenticated=True, username=username)


@router.post("/auth/login", response_model=AuthUserResponse)
async def auth_login(payload: AuthLoginRequest, store: AppConfigStore = Depends(get_app_config_store)) -> Response:
    cfg = store.get()
    if payload.username != cfg.system_username or not verify_password(payload.password, cfg):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = issue_session_token(cfg)
    res = JSONResponse(content=AuthUserResponse(authenticated=True, username=cfg.system_username).model_dump())
    res.set_cookie(
        key=_SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=7 * 24 * 3600,
        path="/",
    )
    return res


@router.post("/auth/logout")
async def auth_logout() -> Response:
    res = JSONResponse(content={"ok": True})
    res.delete_cookie(_SESSION_COOKIE, path="/")
    return res


@router.get("/ready", response_model=ReadyResponse)
async def ready(store: AppConfigStore = Depends(get_app_config_store)) -> ReadyResponse:
    cfg = store.get()
    checks = {
        "pansou": (not cfg.enable_pansou) or bool(cfg.pansou_base_url),
        "prowlarr": (not cfg.enable_prowlarr) or bool(cfg.prowlarr_base_url),
        "tmdb": (not cfg.enable_tmdb) or bool(cfg.tmdb_api_key),
        "c115": bool(cfg.c115_cookie),
    }
    return ReadyResponse(checks=checks)


@router.get("/tmdb/search", response_model=TMDBSearchResponse)
async def tmdb_search(
    query: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=200),
    store: AppConfigStore = Depends(get_app_config_store),
    _: str = Depends(_require_auth),
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
    timeframe: str = Query(default="week", pattern="^(day|week)$"),
    limit: int = Query(default=20, ge=1, le=200),
    store: AppConfigStore = Depends(get_app_config_store),
    _: str = Depends(_require_auth),
) -> TMDBSearchResponse:
    runtime = get_settings()
    adapter = TMDBAdapter(build_provider_settings(runtime, store.get()))
    rows = await adapter.trending(limit, timeframe=timeframe)
    return TMDBSearchResponse(
        request_id=new_request_id(),
        query="trending",
        total=len(rows),
        results=rows,
    )


@router.get("/tmdb/discover", response_model=TMDBSearchResponse)
async def tmdb_discover(
    category: str = Query(pattern="^(movie_now_playing|tv_popular|movie_popular)$"),
    limit: int = Query(default=50, ge=1, le=200),
    store: AppConfigStore = Depends(get_app_config_store),
    _: str = Depends(_require_auth),
) -> TMDBSearchResponse:
    runtime = get_settings()
    adapter = TMDBAdapter(build_provider_settings(runtime, store.get()))
    rows = await adapter.discover(category=category, limit=limit)
    return TMDBSearchResponse(
        request_id=new_request_id(),
        query=category,
        total=len(rows),
        results=rows,
    )


@router.get("/douban/hot", response_model=TMDBSearchResponse)
async def douban_hot(
    media_type: str = Query(default="movie", pattern="^(movie|tv)$"),
    tag: str = Query(default="热门", min_length=1, max_length=20),
    page_start: int = Query(default=0, ge=0, le=2000),
    page_limit: int = Query(default=50, ge=1, le=100),
    store: AppConfigStore = Depends(get_app_config_store),
    _: str = Depends(_require_auth),
) -> TMDBSearchResponse:
    runtime = get_settings()
    adapter = DoubanAdapter(build_provider_settings(runtime, store.get()))
    rows = await adapter.hot(media_type=media_type, tag=tag, start=page_start, limit=page_limit)
    return TMDBSearchResponse(
        request_id=new_request_id(),
        query=f"douban:{media_type}:{tag}",
        total=len(rows),
        results=rows,
    )


@router.get("/recommend/categories")
async def recommend_categories(_: str = Depends(_require_auth)) -> dict:
    return {
        "tmdb": [
            {"id": "trend_day", "name": "今日流行趋势"},
            {"id": "trend_week", "name": "本周流行趋势"},
            {"id": "movie_now_playing", "name": "正在热映"},
            {"id": "tv_popular", "name": "TMDB热门剧集"},
            {"id": "movie_popular", "name": "TMDB热门电影"},
        ],
        "douban": [
            {"id": "movie|热门", "name": "豆瓣热门电影"},
            {"id": "tv|热门", "name": "豆瓣热门剧集"},
            {"id": "movie|最新", "name": "豆瓣最新电影"},
            {"id": "tv|综艺", "name": "豆瓣热门综艺"},
        ],
    }


@router.get("/recommend/detail")
async def recommend_detail(
    title: str = Query(min_length=1, max_length=200),
    store: AppConfigStore = Depends(get_app_config_store),
    _: str = Depends(_require_auth),
) -> dict:
    runtime = get_settings()
    return await TMDBAdapter(build_provider_settings(runtime, store.get())).detail_by_title(title)


@router.get("/recommend/detail/by-id")
async def recommend_detail_by_id(
    tmdb_id: int = Query(ge=1),
    media_type: str = Query(default="", pattern="^(|movie|series|tv)$"),
    store: AppConfigStore = Depends(get_app_config_store),
    _: str = Depends(_require_auth),
) -> dict:
    runtime = get_settings()
    return await TMDBAdapter(build_provider_settings(runtime, store.get())).detail_by_id(
        tmdb_id=tmdb_id,
        media_type=media_type or None,
    )


@router.get("/tmdb/image")
async def tmdb_image_proxy(url: str = Query(min_length=1, max_length=1024)) -> Response:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="invalid image url")
    headers = {
        "referer": "https://movie.douban.com/" if parsed.netloc.endswith("doubanio.com") else "",
        "user-agent": "Mozilla/5.0",
    }
    headers = {k: v for k, v in headers.items() if v}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail="image fetch failed")
        content_type = resp.headers.get("content-type", "image/jpeg")
        return Response(content=resp.content, media_type=content_type)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"image proxy failed: {exc}") from exc


@router.post("/search", response_model=SearchResponse)
async def search(
    payload: SearchRequest,
    svc: SearchService = Depends(get_search_service),
    _: str = Depends(_require_auth),
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
    _: str = Depends(_require_auth),
) -> OfflineTaskResponse:
    target = payload.target_dir_id or store.get().c115_target_dir_id
    return await svc.create_offline_task(new_request_id(), payload.source_uri, target)


@router.post("/tasks/offline/check", response_model=OfflineTaskCheckResponse)
async def check_offline_task(
    payload: OfflineTaskCheckRequest,
    svc: TaskService = Depends(get_task_service),
    _: str = Depends(_require_auth),
) -> OfflineTaskCheckResponse:
    return svc.check_transfer(payload.source_uri, payload.cloud_type)


@router.post("/transfer/prepare", response_model=TransferPrepareResponse)
async def prepare_transfer(
    payload: TransferPrepareRequest,
    svc: TaskService = Depends(get_task_service),
    _: str = Depends(_require_auth),
) -> TransferPrepareResponse:
    return await svc.prepare_transfer(payload.source_uri, payload.cloud_type)


@router.post("/transfer/items", response_model=TransferPrepareResponse)
async def transfer_items(
    payload: TransferItemsRequest,
    svc: TaskService = Depends(get_task_service),
    _: str = Depends(_require_auth),
) -> TransferPrepareResponse:
    return await svc.list_transfer_items(
        payload.source_uri,
        payload.cloud_type,
        payload.parent_id,
    )


@router.post("/transfer/commit", response_model=TransferCommitResponse)
async def commit_transfer(
    payload: TransferCommitRequest,
    svc: TaskService = Depends(get_task_service),
    _: str = Depends(_require_auth),
) -> TransferCommitResponse:
    return await svc.commit_transfer(
        new_request_id(),
        payload.source_uri,
        payload.target_dir_id,
        payload.selected_ids,
        payload.cloud_type,
    )


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def task_status(
    task_id: str,
    svc: TaskService = Depends(get_task_service),
    _: str = Depends(_require_auth),
) -> TaskStatusResponse:
    return await svc.get_task(new_request_id(), task_id)


@router.get("/tasks", response_model=TaskListResponse)
async def task_list(
    limit: int = Query(default=50, ge=1, le=200),
    svc: TaskService = Depends(get_task_service),
    _: str = Depends(_require_auth),
) -> TaskListResponse:
    return await svc.list_tasks(new_request_id(), limit)


@router.get("/storage/dirs", response_model=C115DirListResponse)
async def storage_dirs(
    parent_id: str = Query(default="0", min_length=1, max_length=64),
    provider: str = Query(default="115", pattern="^(115|quark)$"),
    store: AppConfigStore = Depends(get_app_config_store),
    _: str = Depends(_require_auth),
) -> C115DirListResponse:
    runtime = get_settings()
    settings = build_provider_settings(runtime, store.get())
    if provider == "quark":
        parent_path, ancestors, items = await QuarkAdapter(settings).list_dirs(parent_id)
    else:
        parent_path, ancestors, items = await C115Adapter(settings).list_dirs(parent_id)
    return C115DirListResponse(
        request_id=new_request_id(),
        parent_id=parent_id,
        parent_path=parent_path,
        ancestors=ancestors,
        items=items,
    )


@router.get("/providers/status", response_model=ProviderStatusResponse)
async def provider_status(
    svc: ProviderStatusService = Depends(get_provider_status_service),
    _: str = Depends(_require_auth),
) -> ProviderStatusResponse:
    return await svc.get_status(new_request_id())


@router.get("/settings", response_model=SettingsResponse)
async def get_app_settings(
    store: AppConfigStore = Depends(get_app_config_store),
    _: str = Depends(_require_auth),
) -> SettingsResponse:
    cfg = store.get()
    masked = store.mask(cfg)
    masked.update(
        {
            "tmdb_api_key": cfg.tmdb_api_key,
            "prowlarr_api_key": cfg.prowlarr_api_key,
            "pansou_password": cfg.pansou_password,
            "c115_cookie": cfg.c115_cookie,
            "quark_cookie": cfg.quark_cookie,
            "tianyi_password": cfg.tianyi_password,
            "pan123_password": cfg.pan123_password,
        }
    )
    return SettingsResponse(**masked)


@router.put("/settings", response_model=SettingsResponse)
async def update_app_settings(
    payload: SettingsUpdateRequest,
    store: AppConfigStore = Depends(get_app_config_store),
    _: str = Depends(_require_auth),
) -> SettingsResponse:
    system_password_hash = None
    if payload.system_password is not None and payload.system_password.strip():
        system_password_hash = hash_password(payload.system_password.strip())

    next_cfg = store.update(
        tmdb_base_url=payload.tmdb_base_url,
        tmdb_image_base_url=payload.tmdb_image_base_url,
        tmdb_use_proxy=payload.tmdb_use_proxy,
        tmdb_api_key=payload.tmdb_api_key,
        prowlarr_base_url=payload.prowlarr_base_url,
        prowlarr_api_key=payload.prowlarr_api_key,
        prowlarr_use_proxy=payload.prowlarr_use_proxy,
        pansou_base_url=payload.pansou_base_url,
        pansou_use_proxy=payload.pansou_use_proxy,
        pansou_enable_auth=payload.pansou_enable_auth,
        pansou_username=payload.pansou_username,
        pansou_password=payload.pansou_password,
        pansou_search_path=payload.pansou_search_path,
        pansou_search_method=payload.pansou_search_method,
        pansou_cloud_types=payload.pansou_cloud_types,
        pansou_source=payload.pansou_source,
        enable_tmdb=payload.enable_tmdb,
        enable_prowlarr=payload.enable_prowlarr,
        enable_pansou=payload.enable_pansou,
        c115_base_url=payload.c115_base_url,
        c115_cookie=payload.c115_cookie,
        c115_allowed_actions=payload.c115_allowed_actions,
        c115_target_dir_id=payload.c115_target_dir_id,
        c115_target_dir_path=payload.c115_target_dir_path,
        c115_offline_dir_id=payload.c115_offline_dir_id,
        c115_offline_dir_path=payload.c115_offline_dir_path,
        c115_offline_add_path=payload.c115_offline_add_path,
        c115_offline_list_path=payload.c115_offline_list_path,
        storage_providers=payload.storage_providers,
        quark_cookie=payload.quark_cookie,
        tianyi_username=payload.tianyi_username,
        tianyi_password=payload.tianyi_password,
        pan123_username=payload.pan123_username,
        pan123_password=payload.pan123_password,
        system_username=payload.system_username,
        system_proxy_url=payload.system_proxy_url,
        system_proxy_enabled=payload.system_proxy_enabled,
        system_password_hash=system_password_hash,
    )
    masked = store.mask(next_cfg)
    masked.update(
        {
            "tmdb_api_key": next_cfg.tmdb_api_key,
            "prowlarr_api_key": next_cfg.prowlarr_api_key,
            "pansou_password": next_cfg.pansou_password,
            "c115_cookie": next_cfg.c115_cookie,
            "quark_cookie": next_cfg.quark_cookie,
            "tianyi_password": next_cfg.tianyi_password,
            "pan123_password": next_cfg.pan123_password,
        }
    )
    return SettingsResponse(**masked)


@router.get("/app/info")
async def app_info(_: str = Depends(_require_auth)) -> dict:
    return {"name": "CloudMediaPilot", "version": _app_version()}


@router.get("/logs")
async def app_logs(
    level: str = Query(default="all", pattern="^(all|debug|info|warn|warning|error)$"),
    limit: int = Query(default=300, ge=1, le=1000),
    _: str = Depends(_require_auth),
) -> dict:
    return {"items": memory_log_handler.list(level=level, limit=limit)}


@router.post("/settings/test", response_model=ConnectionTestResponse)
async def test_connections(
    payload: ConnectionTestRequest,
    store: AppConfigStore = Depends(get_app_config_store),
    _: str = Depends(_require_auth),
) -> ConnectionTestResponse:
    runtime = get_settings()
    settings = build_provider_settings(runtime, store.get())

    adapters: list[tuple[str, _CheckableAdapter]] = [
        ("tmdb", TMDBAdapter(settings)),
        ("prowlarr", ProwlarrAdapter(settings)),
        ("pansou", PanSouAdapter(settings)),
        ("c115", C115Adapter(settings)),
        ("quark", QuarkAdapter(settings)),
    ]
    if payload.provider in {"tianyi", "pan123", "proxy"}:
        if payload.provider == "tianyi":
            ok = bool(settings.tianyi_username and settings.tianyi_password)
            msg = "configured" if ok else "missing_account_or_password"
            return ConnectionTestResponse(
                request_id=new_request_id(),
                results=[ConnectionTestResult(provider="tianyi", ok=ok, message=msg)],
            )
        if payload.provider == "pan123":
            ok = bool(settings.pan123_username and settings.pan123_password)
            msg = "configured" if ok else "missing_account_or_password"
            return ConnectionTestResponse(
                request_id=new_request_id(),
                results=[ConnectionTestResult(provider="pan123", ok=ok, message=msg)],
            )
        if not settings.system_proxy_enabled or not settings.system_proxy_url:
            return ConnectionTestResponse(
                request_id=new_request_id(),
                results=[
                    ConnectionTestResult(
                        provider="proxy",
                        ok=False,
                        message="proxy_disabled_or_missing_url",
                    )
                ],
            )
        try:
            async with httpx.AsyncClient(timeout=8.0, proxy=settings.system_proxy_url) as client:
                resp = await client.get("https://www.baidu.com")
            ok = resp.status_code < 500
            msg = f"http_{resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            ok = False
            msg = str(exc)
        return ConnectionTestResponse(
            request_id=new_request_id(),
            results=[ConnectionTestResult(provider="proxy", ok=ok, message=msg)],
        )
    if payload.provider != "all":
        adapters = [row for row in adapters if row[0] == payload.provider]

    out: list[ConnectionTestResult] = []
    for name, adapter in adapters:
        ok, msg = await adapter.check()
        out.append(ConnectionTestResult(provider=name, ok=ok, message=msg))
    if payload.provider == "all":
        out.append(
            ConnectionTestResult(
                provider="tianyi",
                ok=bool(settings.tianyi_username and settings.tianyi_password),
                message=(
                    "configured"
                    if (settings.tianyi_username and settings.tianyi_password)
                    else "missing_account_or_password"
                ),
            )
        )
        out.append(
            ConnectionTestResult(
                provider="pan123",
                ok=bool(settings.pan123_username and settings.pan123_password),
                message=(
                    "configured"
                    if (settings.pan123_username and settings.pan123_password)
                    else "missing_account_or_password"
                ),
            )
        )

    return ConnectionTestResponse(request_id=new_request_id(), results=out)
