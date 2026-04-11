from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from app.core.config import DEFAULT_REQUEST_TIMEOUT_SECONDS, ProviderSettings, Settings

_ENV_KEYS_ORDER = [
    "APP_CONFIG_MODE",
    "TMDB_BASE_URL",
    "TMDB_IMAGE_BASE_URL",
    "TMDB_USE_PROXY",
    "TMDB_API_KEY",
    "ENABLE_TMDB",
    "PROWLARR_BASE_URL",
    "PROWLARR_API_KEY",
    "PROWLARR_USE_PROXY",
    "ENABLE_PROWLARR",
    "PANSOU_BASE_URL",
    "PANSOU_USE_PROXY",
    "PANSOU_ENABLE_AUTH",
    "PANSOU_USERNAME",
    "PANSOU_PASSWORD",
    "PANSOU_SEARCH_PATH",
    "PANSOU_SEARCH_METHOD",
    "PANSOU_CLOUD_TYPES",
    "PANSOU_SOURCE",
    "ENABLE_PANSOU",
    "C115_BASE_URL",
    "C115_COOKIE",
    "C115_ALLOWED_ACTIONS",
    "C115_TARGET_DIR_ID",
    "C115_TARGET_DIR_PATH",
    "C115_OFFLINE_DIR_ID",
    "C115_OFFLINE_DIR_PATH",
    "C115_OFFLINE_ADD_PATH",
    "C115_OFFLINE_LIST_PATH",
    "STORAGE_PROVIDERS",
    "QUARK_COOKIE",
    "TIANYI_USERNAME",
    "TIANYI_PASSWORD",
    "PAN123_USERNAME",
    "PAN123_PASSWORD",
    "SYSTEM_PROXY_URL",
    "SYSTEM_PROXY_ENABLED",
    "SYSTEM_USERNAME",
    "SYSTEM_PASSWORD",
    "SYSTEM_PASSWORD_HASH",
    "SYSTEM_AUTH_SECRET",
]


@dataclass(slots=True)
class AppConfig:
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    tmdb_image_base_url: str = "https://image.tmdb.org/t/p/w500"
    tmdb_use_proxy: bool = False
    tmdb_api_key: str = ""
    enable_tmdb: bool = True

    prowlarr_base_url: str = "http://localhost:9696"
    prowlarr_api_key: str = ""
    prowlarr_use_proxy: bool = False
    enable_prowlarr: bool = True

    pansou_base_url: str = "http://localhost:805"
    pansou_use_proxy: bool = False
    pansou_enable_auth: bool = False
    pansou_username: str = ""
    pansou_password: str = ""
    pansou_search_path: str = "/api/search"
    pansou_search_method: str = "POST"
    pansou_cloud_types: str = ""
    pansou_source: str = "all"
    enable_pansou: bool = True

    c115_base_url: str = "https://lixian.115.com"
    c115_cookie: str = ""
    c115_allowed_actions: str = "create_offline_task"
    c115_target_dir_id: str = "0"
    c115_target_dir_path: str = "/"
    c115_offline_dir_id: str = "0"
    c115_offline_dir_path: str = "/"
    c115_offline_add_path: str = "/lixianssp/?ac=add_task_url"
    c115_offline_list_path: str = "/web/lixian/?ac=task_lists"
    storage_providers: str = "115,quark,tianyi,123"
    quark_cookie: str = ""
    tianyi_username: str = ""
    tianyi_password: str = ""
    pan123_username: str = ""
    pan123_password: str = ""
    system_proxy_url: str = ""
    system_proxy_enabled: bool = False
    system_username: str = "admin"
    system_password_hash: str = ""
    system_auth_secret: str = ""


def _mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 4:
        return "*" * len(secret)
    return "*" * (len(secret) - 4) + secret[-4:]


def _to_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def hash_password(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AppConfigStore:
    def __init__(self, env_path: str) -> None:
        self.env_path = Path(env_path)
        self._lock = RLock()
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.env_path.exists():
            self._write_env(self._to_env_map(AppConfig()))

    def _read_env(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if not self.env_path.exists():
            return out
        for raw in self.env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
        return out

    def _write_env(self, env_map: dict[str, str]) -> None:
        lines = [
            "# CloudMediaPilot 配置文件（由 WebUI 维护）",
            "# 仅保留关键配置；请在 WebUI 中修改，不建议手工编辑敏感字段。",
            "",
        ]
        for key in _ENV_KEYS_ORDER:
            if key in env_map:
                lines.append(f"{key}={env_map[key]}")
        lines.append("")
        self.env_path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _to_env_map(cfg: AppConfig) -> dict[str, str]:
        return {
            "APP_CONFIG_MODE": "single_config_dir",
            "TMDB_BASE_URL": cfg.tmdb_base_url,
            "TMDB_IMAGE_BASE_URL": cfg.tmdb_image_base_url,
            "TMDB_USE_PROXY": "true" if cfg.tmdb_use_proxy else "false",
            "TMDB_API_KEY": cfg.tmdb_api_key,
            "ENABLE_TMDB": "true" if cfg.enable_tmdb else "false",
            "PROWLARR_BASE_URL": cfg.prowlarr_base_url,
            "PROWLARR_API_KEY": cfg.prowlarr_api_key,
            "PROWLARR_USE_PROXY": "true" if cfg.prowlarr_use_proxy else "false",
            "ENABLE_PROWLARR": "true" if cfg.enable_prowlarr else "false",
            "PANSOU_BASE_URL": cfg.pansou_base_url,
            "PANSOU_USE_PROXY": "true" if cfg.pansou_use_proxy else "false",
            "PANSOU_ENABLE_AUTH": "true" if cfg.pansou_enable_auth else "false",
            "PANSOU_USERNAME": cfg.pansou_username,
            "PANSOU_PASSWORD": cfg.pansou_password,
            "PANSOU_SEARCH_PATH": cfg.pansou_search_path,
            "PANSOU_SEARCH_METHOD": cfg.pansou_search_method,
            "PANSOU_CLOUD_TYPES": cfg.pansou_cloud_types,
            "PANSOU_SOURCE": cfg.pansou_source,
            "ENABLE_PANSOU": "true" if cfg.enable_pansou else "false",
            "C115_BASE_URL": cfg.c115_base_url,
            "C115_COOKIE": cfg.c115_cookie,
            "C115_ALLOWED_ACTIONS": cfg.c115_allowed_actions,
            "C115_TARGET_DIR_ID": cfg.c115_target_dir_id,
            "C115_TARGET_DIR_PATH": cfg.c115_target_dir_path,
            "C115_OFFLINE_DIR_ID": cfg.c115_offline_dir_id,
            "C115_OFFLINE_DIR_PATH": cfg.c115_offline_dir_path,
            "C115_OFFLINE_ADD_PATH": cfg.c115_offline_add_path,
            "C115_OFFLINE_LIST_PATH": cfg.c115_offline_list_path,
            "STORAGE_PROVIDERS": cfg.storage_providers,
            "QUARK_COOKIE": cfg.quark_cookie,
            "TIANYI_USERNAME": cfg.tianyi_username,
            "TIANYI_PASSWORD": cfg.tianyi_password,
            "PAN123_USERNAME": cfg.pan123_username,
            "PAN123_PASSWORD": cfg.pan123_password,
            "SYSTEM_PROXY_URL": cfg.system_proxy_url,
            "SYSTEM_PROXY_ENABLED": "true" if cfg.system_proxy_enabled else "false",
            "SYSTEM_USERNAME": cfg.system_username,
            "SYSTEM_PASSWORD_HASH": cfg.system_password_hash,
            "SYSTEM_AUTH_SECRET": cfg.system_auth_secret,
        }

    def get(self) -> AppConfig:
        with self._lock:
            env = self._read_env()
            base = AppConfig()
            cfg = AppConfig(
                tmdb_base_url=env.get("TMDB_BASE_URL", base.tmdb_base_url),
                tmdb_image_base_url=env.get("TMDB_IMAGE_BASE_URL", base.tmdb_image_base_url),
                tmdb_use_proxy=_to_bool(env.get("TMDB_USE_PROXY"), base.tmdb_use_proxy),
                tmdb_api_key=env.get("TMDB_API_KEY", base.tmdb_api_key),
                enable_tmdb=_to_bool(env.get("ENABLE_TMDB"), base.enable_tmdb),
                prowlarr_base_url=env.get("PROWLARR_BASE_URL", base.prowlarr_base_url),
                prowlarr_api_key=env.get("PROWLARR_API_KEY", base.prowlarr_api_key),
                prowlarr_use_proxy=_to_bool(
                    env.get("PROWLARR_USE_PROXY"),
                    base.prowlarr_use_proxy,
                ),
                enable_prowlarr=_to_bool(env.get("ENABLE_PROWLARR"), base.enable_prowlarr),
                pansou_base_url=env.get("PANSOU_BASE_URL", base.pansou_base_url),
                pansou_use_proxy=_to_bool(env.get("PANSOU_USE_PROXY"), base.pansou_use_proxy),
                pansou_enable_auth=_to_bool(
                    env.get("PANSOU_ENABLE_AUTH"),
                    base.pansou_enable_auth,
                ),
                pansou_username=env.get("PANSOU_USERNAME", base.pansou_username),
                pansou_password=env.get("PANSOU_PASSWORD", base.pansou_password),
                pansou_search_path=env.get("PANSOU_SEARCH_PATH", base.pansou_search_path),
                pansou_search_method=env.get("PANSOU_SEARCH_METHOD", base.pansou_search_method),
                pansou_cloud_types=env.get("PANSOU_CLOUD_TYPES", base.pansou_cloud_types),
                pansou_source=env.get("PANSOU_SOURCE", base.pansou_source),
                enable_pansou=_to_bool(env.get("ENABLE_PANSOU"), base.enable_pansou),
                c115_base_url=env.get("C115_BASE_URL", base.c115_base_url),
                c115_cookie=env.get("C115_COOKIE", base.c115_cookie),
                c115_allowed_actions=env.get("C115_ALLOWED_ACTIONS", base.c115_allowed_actions),
                c115_target_dir_id=env.get("C115_TARGET_DIR_ID", base.c115_target_dir_id),
                c115_target_dir_path=env.get("C115_TARGET_DIR_PATH", base.c115_target_dir_path),
                c115_offline_dir_id=env.get("C115_OFFLINE_DIR_ID", base.c115_offline_dir_id),
                c115_offline_dir_path=env.get(
                    "C115_OFFLINE_DIR_PATH",
                    base.c115_offline_dir_path,
                ),
                c115_offline_add_path=env.get(
                    "C115_OFFLINE_ADD_PATH",
                    base.c115_offline_add_path,
                ),
                c115_offline_list_path=env.get(
                    "C115_OFFLINE_LIST_PATH",
                    base.c115_offline_list_path,
                ),
                storage_providers=env.get("STORAGE_PROVIDERS", base.storage_providers),
                quark_cookie=env.get("QUARK_COOKIE", base.quark_cookie),
                tianyi_username=env.get("TIANYI_USERNAME", base.tianyi_username),
                tianyi_password=env.get("TIANYI_PASSWORD", base.tianyi_password),
                pan123_username=env.get("PAN123_USERNAME", base.pan123_username),
                pan123_password=env.get("PAN123_PASSWORD", base.pan123_password),
                system_proxy_url=env.get("SYSTEM_PROXY_URL", base.system_proxy_url),
                system_proxy_enabled=_to_bool(
                    env.get("SYSTEM_PROXY_ENABLED"),
                    base.system_proxy_enabled,
                ),
                system_username=env.get("SYSTEM_USERNAME", base.system_username),
                system_password_hash=env.get("SYSTEM_PASSWORD_HASH", base.system_password_hash),
                system_auth_secret=env.get("SYSTEM_AUTH_SECRET", base.system_auth_secret),
            )
            plain_password = env.get("SYSTEM_PASSWORD", "").strip()
            if plain_password:
                cfg.system_password_hash = hash_password(plain_password)
            if not cfg.system_password_hash:
                cfg.system_password_hash = hash_password("admin")
            if not cfg.system_auth_secret:
                cfg.system_auth_secret = secrets.token_hex(32)
            self._write_env(self._to_env_map(cfg))
            return cfg

    def update(
        self,
        *,
        tmdb_base_url: str | None = None,
        tmdb_image_base_url: str | None = None,
        tmdb_use_proxy: bool | None = None,
        tmdb_api_key: str | None = None,
        prowlarr_base_url: str | None = None,
        prowlarr_api_key: str | None = None,
        prowlarr_use_proxy: bool | None = None,
        pansou_base_url: str | None = None,
        pansou_use_proxy: bool | None = None,
        pansou_enable_auth: bool | None = None,
        pansou_username: str | None = None,
        pansou_password: str | None = None,
        pansou_search_path: str | None = None,
        pansou_search_method: str | None = None,
        pansou_cloud_types: str | None = None,
        pansou_source: str | None = None,
        enable_tmdb: bool | None = None,
        enable_prowlarr: bool | None = None,
        enable_pansou: bool | None = None,
        c115_base_url: str | None = None,
        c115_cookie: str | None = None,
        c115_allowed_actions: str | None = None,
        c115_target_dir_id: str | None = None,
        c115_target_dir_path: str | None = None,
        c115_offline_dir_id: str | None = None,
        c115_offline_dir_path: str | None = None,
        c115_offline_add_path: str | None = None,
        c115_offline_list_path: str | None = None,
        storage_providers: str | None = None,
        quark_cookie: str | None = None,
        tianyi_username: str | None = None,
        tianyi_password: str | None = None,
        pan123_username: str | None = None,
        pan123_password: str | None = None,
        system_proxy_url: str | None = None,
        system_proxy_enabled: bool | None = None,
        system_username: str | None = None,
        system_password_hash: str | None = None,
        system_auth_secret: str | None = None,
    ) -> AppConfig:
        with self._lock:
            current = self.get()
            next_cfg = AppConfig(
                tmdb_base_url=(
                    tmdb_base_url if tmdb_base_url is not None else current.tmdb_base_url
                ),
                tmdb_image_base_url=(
                    tmdb_image_base_url
                    if tmdb_image_base_url is not None
                    else current.tmdb_image_base_url
                ),
                tmdb_use_proxy=(
                    tmdb_use_proxy if tmdb_use_proxy is not None else current.tmdb_use_proxy
                ),
                tmdb_api_key=tmdb_api_key if tmdb_api_key is not None else current.tmdb_api_key,
                enable_tmdb=enable_tmdb if enable_tmdb is not None else current.enable_tmdb,
                prowlarr_base_url=(
                    prowlarr_base_url
                    if prowlarr_base_url is not None
                    else current.prowlarr_base_url
                ),
                prowlarr_api_key=(
                    prowlarr_api_key
                    if prowlarr_api_key is not None
                    else current.prowlarr_api_key
                ),
                prowlarr_use_proxy=(
                    prowlarr_use_proxy
                    if prowlarr_use_proxy is not None
                    else current.prowlarr_use_proxy
                ),
                enable_prowlarr=(
                    enable_prowlarr
                    if enable_prowlarr is not None
                    else current.enable_prowlarr
                ),
                pansou_base_url=(
                    pansou_base_url if pansou_base_url is not None else current.pansou_base_url
                ),
                pansou_use_proxy=(
                    pansou_use_proxy if pansou_use_proxy is not None else current.pansou_use_proxy
                ),
                pansou_enable_auth=(
                    pansou_enable_auth
                    if pansou_enable_auth is not None
                    else current.pansou_enable_auth
                ),
                pansou_username=(
                    pansou_username if pansou_username is not None else current.pansou_username
                ),
                pansou_password=(
                    pansou_password if pansou_password is not None else current.pansou_password
                ),
                pansou_search_path=(
                    pansou_search_path
                    if pansou_search_path is not None
                    else current.pansou_search_path
                ),
                pansou_search_method=(
                    pansou_search_method
                    if pansou_search_method is not None
                    else current.pansou_search_method
                ),
                pansou_cloud_types=(
                    pansou_cloud_types
                    if pansou_cloud_types is not None
                    else current.pansou_cloud_types
                ),
                pansou_source=(
                    pansou_source if pansou_source is not None else current.pansou_source
                ),
                enable_pansou=(
                    enable_pansou if enable_pansou is not None else current.enable_pansou
                ),
                c115_base_url=(
                    c115_base_url if c115_base_url is not None else current.c115_base_url
                ),
                c115_cookie=c115_cookie if c115_cookie is not None else current.c115_cookie,
                c115_allowed_actions=(
                    c115_allowed_actions
                    if c115_allowed_actions is not None
                    else current.c115_allowed_actions
                ),
                c115_target_dir_id=(
                    c115_target_dir_id
                    if c115_target_dir_id is not None
                    else current.c115_target_dir_id
                ),
                c115_target_dir_path=(
                    c115_target_dir_path
                    if c115_target_dir_path is not None
                    else current.c115_target_dir_path
                ),
                c115_offline_dir_id=(
                    c115_offline_dir_id
                    if c115_offline_dir_id is not None
                    else current.c115_offline_dir_id
                ),
                c115_offline_dir_path=(
                    c115_offline_dir_path
                    if c115_offline_dir_path is not None
                    else current.c115_offline_dir_path
                ),
                c115_offline_add_path=(
                    c115_offline_add_path
                    if c115_offline_add_path is not None
                    else current.c115_offline_add_path
                ),
                c115_offline_list_path=(
                    c115_offline_list_path
                    if c115_offline_list_path is not None
                    else current.c115_offline_list_path
                ),
                storage_providers=(
                    storage_providers
                    if storage_providers is not None
                    else current.storage_providers
                ),
                quark_cookie=quark_cookie if quark_cookie is not None else current.quark_cookie,
                tianyi_username=(
                    tianyi_username if tianyi_username is not None else current.tianyi_username
                ),
                tianyi_password=(
                    tianyi_password if tianyi_password is not None else current.tianyi_password
                ),
                pan123_username=(
                    pan123_username if pan123_username is not None else current.pan123_username
                ),
                pan123_password=(
                    pan123_password if pan123_password is not None else current.pan123_password
                ),
                system_proxy_url=(
                    system_proxy_url
                    if system_proxy_url is not None
                    else current.system_proxy_url
                ),
                system_proxy_enabled=(
                    system_proxy_enabled
                    if system_proxy_enabled is not None
                    else current.system_proxy_enabled
                ),
                system_username=(
                    system_username if system_username is not None else current.system_username
                ),
                system_password_hash=(
                    system_password_hash
                    if system_password_hash is not None
                    else current.system_password_hash
                ),
                system_auth_secret=(
                    system_auth_secret
                    if system_auth_secret is not None
                    else current.system_auth_secret
                ),
            )
            self._write_env(self._to_env_map(next_cfg))
            return next_cfg

    @staticmethod
    def mask(cfg: AppConfig) -> dict[str, str | bool]:
        return {
            "tmdb_base_url": cfg.tmdb_base_url,
            "tmdb_image_base_url": cfg.tmdb_image_base_url,
            "tmdb_use_proxy": cfg.tmdb_use_proxy,
            "prowlarr_base_url": cfg.prowlarr_base_url,
            "prowlarr_use_proxy": cfg.prowlarr_use_proxy,
            "pansou_base_url": cfg.pansou_base_url,
            "pansou_use_proxy": cfg.pansou_use_proxy,
            "pansou_enable_auth": cfg.pansou_enable_auth,
            "pansou_username": cfg.pansou_username,
            "pansou_search_path": cfg.pansou_search_path,
            "pansou_search_method": cfg.pansou_search_method,
            "pansou_cloud_types": cfg.pansou_cloud_types,
            "pansou_source": cfg.pansou_source,
            "enable_tmdb": cfg.enable_tmdb,
            "enable_prowlarr": cfg.enable_prowlarr,
            "enable_pansou": cfg.enable_pansou,
            "c115_base_url": cfg.c115_base_url,
            "c115_target_dir_id": cfg.c115_target_dir_id,
            "c115_target_dir_path": cfg.c115_target_dir_path,
            "c115_offline_dir_id": cfg.c115_offline_dir_id,
            "c115_offline_dir_path": cfg.c115_offline_dir_path,
            "c115_allowed_actions": cfg.c115_allowed_actions,
            "c115_offline_add_path": cfg.c115_offline_add_path,
            "c115_offline_list_path": cfg.c115_offline_list_path,
            "storage_providers": cfg.storage_providers,
            "quark_cookie_masked": _mask_secret(cfg.quark_cookie),
            "tianyi_username": cfg.tianyi_username,
            "tianyi_password_masked": _mask_secret(cfg.tianyi_password),
            "pan123_username": cfg.pan123_username,
            "pan123_password_masked": _mask_secret(cfg.pan123_password),
            "tmdb_api_key_masked": _mask_secret(cfg.tmdb_api_key),
            "prowlarr_api_key_masked": _mask_secret(cfg.prowlarr_api_key),
            "pansou_password_masked": _mask_secret(cfg.pansou_password),
            "c115_cookie_masked": _mask_secret(cfg.c115_cookie),
            "system_proxy_url": cfg.system_proxy_url,
            "system_proxy_enabled": cfg.system_proxy_enabled,
            "system_username": cfg.system_username,
            "system_password_masked": "********" if cfg.system_password_hash else "",
            "has_tmdb_api_key": bool(cfg.tmdb_api_key),
            "has_prowlarr_api_key": bool(cfg.prowlarr_api_key),
            "has_pansou_password": bool(cfg.pansou_password),
            "has_c115_cookie": bool(cfg.c115_cookie),
            "has_system_password": bool(cfg.system_password_hash),
        }


def build_provider_settings(_runtime: Settings, app_cfg: AppConfig) -> ProviderSettings:
    return ProviderSettings(
        pansou_base_url=app_cfg.pansou_base_url,
        enable_pansou=app_cfg.enable_pansou,
        pansou_use_proxy=app_cfg.pansou_use_proxy,
        pansou_enable_auth=app_cfg.pansou_enable_auth,
        pansou_username=app_cfg.pansou_username,
        pansou_password=app_cfg.pansou_password,
        pansou_search_path=app_cfg.pansou_search_path,
        pansou_search_method=app_cfg.pansou_search_method,
        pansou_cloud_types=app_cfg.pansou_cloud_types,
        pansou_source=app_cfg.pansou_source,
        prowlarr_base_url=app_cfg.prowlarr_base_url,
        prowlarr_api_key=app_cfg.prowlarr_api_key,
        prowlarr_use_proxy=app_cfg.prowlarr_use_proxy,
        enable_prowlarr=app_cfg.enable_prowlarr,
        tmdb_base_url=app_cfg.tmdb_base_url,
        tmdb_api_key=app_cfg.tmdb_api_key,
        enable_tmdb=app_cfg.enable_tmdb,
        tmdb_image_base_url=app_cfg.tmdb_image_base_url,
        tmdb_use_proxy=app_cfg.tmdb_use_proxy,
        c115_base_url=app_cfg.c115_base_url,
        c115_cookie=app_cfg.c115_cookie,
        c115_allowed_actions=app_cfg.c115_allowed_actions,
        c115_target_dir_id=app_cfg.c115_target_dir_id,
        c115_target_dir_path=app_cfg.c115_target_dir_path,
        c115_offline_dir_id=app_cfg.c115_offline_dir_id,
        c115_offline_dir_path=app_cfg.c115_offline_dir_path,
        c115_offline_add_path=app_cfg.c115_offline_add_path,
        c115_offline_list_path=app_cfg.c115_offline_list_path,
        storage_providers=app_cfg.storage_providers,
        quark_cookie=app_cfg.quark_cookie,
        tianyi_username=app_cfg.tianyi_username,
        tianyi_password=app_cfg.tianyi_password,
        pan123_username=app_cfg.pan123_username,
        pan123_password=app_cfg.pan123_password,
        system_username=app_cfg.system_username,
        system_password_hash=app_cfg.system_password_hash,
        system_auth_secret=app_cfg.system_auth_secret,
        system_proxy_url=app_cfg.system_proxy_url,
        system_proxy_enabled=app_cfg.system_proxy_enabled,
        use_mock=_runtime.cmp_use_mock,
        request_timeout_seconds=DEFAULT_REQUEST_TIMEOUT_SECONDS,
    )
