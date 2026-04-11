from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_prefix="CMP_", extra="ignore"
    )

    app_name: str = "CloudMediaPilot"
    env: str = "dev"
    use_mock: bool = True
    request_timeout_seconds: float = 10.0

    # runtime-only settings
    config_db_path: str = "data/cloudmediapilot.db"


@dataclass(slots=True)
class ProviderSettings:
    use_mock: bool
    request_timeout_seconds: float

    pansou_base_url: str
    enable_pansou: bool
    prowlarr_base_url: str
    prowlarr_api_key: str
    enable_prowlarr: bool
    tmdb_base_url: str
    tmdb_api_key: str
    enable_tmdb: bool

    c115_base_url: str
    c115_cookie: str
    c115_allowed_actions: str
    c115_target_dir_id: str
    c115_offline_add_path: str
    c115_offline_list_path: str

    @property
    def allowed_actions(self) -> set[str]:
        return {x.strip() for x in self.c115_allowed_actions.split(",") if x.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
