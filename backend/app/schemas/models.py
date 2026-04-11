from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TaskState = Literal[
    "created",
    "searching",
    "enriched",
    "pending_dispatch",
    "dispatched",
    "completed",
    "search_failed",
    "enrich_failed",
    "dispatch_failed",
    "partial_success",
]
PublicTaskState = Literal["queued", "running", "completed", "failed"]


class TMDBSearchContext(BaseModel):
    tmdb_id: int | None = None
    title: str
    year: int | None = None
    media_type: Literal["movie", "series", "person", "unknown"] = "unknown"


class SearchRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=50, ge=1, le=500)
    tmdb_context: TMDBSearchContext | None = None


class SearchResultItem(BaseModel):
    source: Literal["pansou", "prowlarr"]
    source_id: str
    title: str
    link: str
    magnet: str | None = None
    publish_time: datetime | None = None
    size: int | None = None
    media_type: Literal["movie", "series", "anime", "unknown"] = "unknown"
    cloud_type: Literal[
        "magnet",
        "baidu",
        "aliyun",
        "quark",
        "uc",
        "115",
        "pikpak",
        "xunlei",
        "ed2k",
        "other",
    ] = "other"
    score: float = 0.0
    tmdb_id: int | None = None
    tmdb_title: str | None = None
    tmdb_overview: str | None = None
    tmdb_poster: str | None = None


class SearchResponse(BaseModel):
    request_id: str
    keyword: str
    took_ms: int
    total: int
    partial_success: bool = False
    results: list[SearchResultItem]


class TMDBSearchItem(BaseModel):
    tmdb_id: int
    title: str
    year: int | None = None
    media_type: Literal["movie", "series", "person", "unknown"] = "unknown"
    rating: float | None = None
    overview: str = ""
    poster_url: str | None = None


class TMDBSearchResponse(BaseModel):
    request_id: str
    query: str
    total: int
    results: list[TMDBSearchItem]


class OfflineTaskRequest(BaseModel):
    source_uri: str = Field(min_length=1)
    target_dir_id: str | None = None


class OfflineTaskResponse(BaseModel):
    request_id: str
    task_id: str
    existing_task: bool
    status: PublicTaskState


class TaskStatusResponse(BaseModel):
    request_id: str
    task_id: str
    internal_state: TaskState
    status: PublicTaskState
    message: str | None = None


class TaskListItem(BaseModel):
    task_id: str
    source_uri: str
    target_dir_id: str
    internal_state: TaskState
    status: PublicTaskState
    created_at: datetime
    message: str | None = None


class TaskListResponse(BaseModel):
    request_id: str
    total: int
    tasks: list[TaskListItem]


class ProviderStatusItem(BaseModel):
    name: str
    ok: bool
    message: str
    latency_ms: int | None = None


class ProviderStatusResponse(BaseModel):
    request_id: str
    providers: list[ProviderStatusItem]


class SettingsResponse(BaseModel):
    tmdb_base_url: str
    tmdb_api_key_masked: str
    has_tmdb_api_key: bool

    prowlarr_base_url: str
    prowlarr_api_key_masked: str
    has_prowlarr_api_key: bool

    pansou_base_url: str
    enable_tmdb: bool
    enable_prowlarr: bool
    enable_pansou: bool

    c115_base_url: str
    c115_cookie_masked: str
    has_c115_cookie: bool
    c115_allowed_actions: str
    c115_target_dir_id: str
    c115_offline_add_path: str
    c115_offline_list_path: str


class SettingsUpdateRequest(BaseModel):
    tmdb_base_url: str | None = None
    tmdb_api_key: str | None = None

    prowlarr_base_url: str | None = None
    prowlarr_api_key: str | None = None

    pansou_base_url: str | None = None
    enable_tmdb: bool | None = None
    enable_prowlarr: bool | None = None
    enable_pansou: bool | None = None

    c115_base_url: str | None = None
    c115_cookie: str | None = None
    c115_allowed_actions: str | None = None
    c115_target_dir_id: str | None = None
    c115_offline_add_path: str | None = None
    c115_offline_list_path: str | None = None


class ConnectionTestRequest(BaseModel):
    provider: Literal["tmdb", "prowlarr", "pansou", "c115", "all"] = "all"


class ConnectionTestResult(BaseModel):
    provider: str
    ok: bool
    message: str


class ConnectionTestResponse(BaseModel):
    request_id: str
    results: list[ConnectionTestResult]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    status: Literal["ready"] = "ready"
    checks: dict[str, bool]
