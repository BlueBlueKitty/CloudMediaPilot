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
    source_detail: str | None = None
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
        "tianyi",
        "123",
        "uc",
        "115",
        "pikpak",
        "mobile",
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
    warnings: list[str] = Field(default_factory=list)
    results: list[SearchResultItem]


class TMDBSearchItem(BaseModel):
    tmdb_id: int
    title: str
    year: int | None = None
    media_type: Literal["movie", "series", "person", "unknown"] = "unknown"
    rating: float | None = None
    overview: str = ""
    poster_url: str | None = None
    country: str | None = None
    language: str | None = None
    episodes: int | None = None
    genres: list[str] = Field(default_factory=list)
    director: str | None = None
    cast: list[str] = Field(default_factory=list)


class TMDBSearchResponse(BaseModel):
    request_id: str
    query: str
    total: int
    results: list[TMDBSearchItem]


class OfflineTaskRequest(BaseModel):
    source_uri: str = Field(min_length=1)
    target_dir_id: str | None = None


class OfflineTaskCheckRequest(BaseModel):
    source_uri: str = Field(min_length=1)
    cloud_type: str | None = None


class OfflineTaskCheckResponse(BaseModel):
    provider: str
    supported: bool
    configured: bool
    message: str
    default_dir_id: str | None = None
    default_dir_path: str | None = None


class OfflineTaskResponse(BaseModel):
    request_id: str
    task_id: str
    existing_task: bool
    status: PublicTaskState


class TransferPrepareRequest(BaseModel):
    source_uri: str = Field(min_length=1)
    cloud_type: str | None = None


class TransferItemsRequest(BaseModel):
    source_uri: str = Field(min_length=1)
    cloud_type: str | None = None
    parent_id: str = ""


class TransferItem(BaseModel):
    id: str
    name: str
    size: int | None = None
    is_dir: bool = False


class TransferPrepareResponse(BaseModel):
    provider: str
    title: str
    selectable: bool = False
    items: list[TransferItem] = Field(default_factory=list)
    default_dir_id: str | None = None
    default_dir_path: str | None = None


class TransferCommitRequest(BaseModel):
    source_uri: str = Field(min_length=1)
    target_dir_id: str = Field(min_length=1)
    selected_ids: list[str] = Field(default_factory=list)
    cloud_type: str | None = None


class TransferCommitResponse(BaseModel):
    request_id: str
    task_id: str
    provider: str


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
    tmdb_image_base_url: str
    tmdb_use_proxy: bool
    tmdb_api_key_masked: str
    tmdb_api_key: str = ""
    has_tmdb_api_key: bool

    prowlarr_base_url: str
    prowlarr_use_proxy: bool
    prowlarr_api_key_masked: str
    prowlarr_api_key: str = ""
    has_prowlarr_api_key: bool

    pansou_base_url: str
    pansou_use_proxy: bool
    pansou_enable_auth: bool
    pansou_username: str
    pansou_search_path: str
    pansou_search_method: str
    pansou_cloud_types: str
    pansou_source: str
    pansou_password_masked: str
    pansou_password: str = ""
    has_pansou_password: bool
    enable_tmdb: bool
    enable_prowlarr: bool
    enable_pansou: bool

    c115_base_url: str
    c115_cookie_masked: str
    c115_cookie: str = ""
    has_c115_cookie: bool
    c115_allowed_actions: str
    c115_target_dir_id: str
    c115_target_dir_path: str
    c115_offline_dir_id: str
    c115_offline_dir_path: str
    c115_offline_add_path: str
    c115_offline_list_path: str
    storage_providers: str
    quark_cookie_masked: str
    quark_cookie: str = ""
    tianyi_username: str
    tianyi_password_masked: str
    tianyi_password: str = ""
    pan123_username: str
    pan123_password_masked: str
    pan123_password: str = ""

    system_username: str
    system_proxy_url: str
    system_proxy_enabled: bool
    system_password_masked: str
    system_password: str = ""
    has_system_password: bool


class SettingsUpdateRequest(BaseModel):
    tmdb_base_url: str | None = None
    tmdb_image_base_url: str | None = None
    tmdb_use_proxy: bool | None = None
    tmdb_api_key: str | None = None

    prowlarr_base_url: str | None = None
    prowlarr_api_key: str | None = None
    prowlarr_use_proxy: bool | None = None

    pansou_base_url: str | None = None
    pansou_use_proxy: bool | None = None
    pansou_enable_auth: bool | None = None
    pansou_username: str | None = None
    pansou_password: str | None = None
    pansou_search_path: str | None = None
    pansou_search_method: str | None = None
    pansou_cloud_types: str | None = None
    pansou_source: str | None = None
    enable_tmdb: bool | None = None
    enable_prowlarr: bool | None = None
    enable_pansou: bool | None = None

    c115_base_url: str | None = None
    c115_cookie: str | None = None
    c115_allowed_actions: str | None = None
    c115_target_dir_id: str | None = None
    c115_target_dir_path: str | None = None
    c115_offline_dir_id: str | None = None
    c115_offline_dir_path: str | None = None
    c115_offline_add_path: str | None = None
    c115_offline_list_path: str | None = None
    storage_providers: str | None = None
    quark_cookie: str | None = None
    tianyi_username: str | None = None
    tianyi_password: str | None = None
    pan123_username: str | None = None
    pan123_password: str | None = None

    system_username: str | None = None
    system_proxy_url: str | None = None
    system_proxy_enabled: bool | None = None
    system_password: str | None = None


class ConnectionTestRequest(BaseModel):
    provider: Literal[
        "tmdb",
        "prowlarr",
        "pansou",
        "c115",
        "quark",
        "tianyi",
        "pan123",
        "proxy",
        "all",
    ] = "all"


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


class AuthLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class AuthUserResponse(BaseModel):
    authenticated: bool
    username: str | None = None


class C115DirItem(BaseModel):
    id: str
    name: str
    is_dir: bool = True


class C115DirAncestor(BaseModel):
    id: str
    path: str


class C115DirListResponse(BaseModel):
    request_id: str
    parent_id: str
    parent_path: str
    ancestors: list[C115DirAncestor] = Field(default_factory=list)
    items: list[C115DirItem]
