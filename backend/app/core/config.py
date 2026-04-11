from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_REQUEST_TIMEOUT_SECONDS = 15.0


class Settings(BaseSettings):
    _root_dir = Path(__file__).resolve().parents[3]
    _config_dir = _root_dir / "config"
    _config_env = _config_dir / ".env"
    model_config = SettingsConfigDict(
        env_file=(str(_config_env),),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    config_env_path: str = str(_config_env)
    cmp_use_mock: bool = False


@dataclass(slots=True)
class ProviderSettings:
    pansou_base_url: str
    enable_pansou: bool
    pansou_use_proxy: bool
    pansou_enable_auth: bool
    pansou_username: str
    pansou_password: str
    pansou_search_path: str
    pansou_search_method: str
    pansou_cloud_types: str
    pansou_source: str
    prowlarr_base_url: str
    prowlarr_api_key: str
    prowlarr_use_proxy: bool
    enable_prowlarr: bool
    tmdb_base_url: str
    tmdb_api_key: str
    enable_tmdb: bool
    tmdb_image_base_url: str
    tmdb_use_proxy: bool

    c115_base_url: str
    c115_cookie: str
    c115_allowed_actions: str
    c115_target_dir_id: str
    c115_target_dir_path: str
    c115_offline_dir_id: str
    c115_offline_dir_path: str
    c115_offline_add_path: str
    c115_offline_list_path: str
    storage_providers: str
    quark_cookie: str
    tianyi_username: str
    tianyi_password: str
    pan123_username: str
    pan123_password: str
    system_username: str
    system_password_hash: str
    system_auth_secret: str
    system_proxy_url: str
    system_proxy_enabled: bool
    use_mock: bool = False
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS

    @property
    def allowed_actions(self) -> set[str]:
        return {x.strip() for x in self.c115_allowed_actions.split(",") if x.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
