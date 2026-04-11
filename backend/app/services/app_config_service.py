from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import ProviderSettings, Settings


@dataclass(slots=True)
class AppConfig:
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    tmdb_api_key: str = ""
    prowlarr_base_url: str = "http://localhost:9696"
    prowlarr_api_key: str = ""
    pansou_base_url: str = "http://localhost:805"
    enable_tmdb: bool = True
    enable_prowlarr: bool = True
    enable_pansou: bool = True

    c115_base_url: str = "https://lixian.115.com"
    c115_cookie: str = ""
    c115_allowed_actions: str = "create_offline_task"
    c115_target_dir_id: str = "0"
    c115_offline_add_path: str = "/lixianssp/?ac=add_task_url"
    c115_offline_list_path: str = "/web/lixian/?ac=task_lists"


def _mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 4:
        return "*" * len(secret)
    return "*" * (len(secret) - 4) + secret[-4:]


class AppConfigStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_column(self, conn: sqlite3.Connection, name: str, ddl: str) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(app_config)").fetchall()}
        if name not in columns:
            conn.execute(f"ALTER TABLE app_config ADD COLUMN {ddl}")

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    tmdb_base_url TEXT NOT NULL,
                    tmdb_api_key TEXT NOT NULL,
                    prowlarr_base_url TEXT NOT NULL,
                    prowlarr_api_key TEXT NOT NULL,
                    pansou_base_url TEXT NOT NULL,
                    enable_tmdb INTEGER NOT NULL DEFAULT 1,
                    enable_prowlarr INTEGER NOT NULL DEFAULT 1,
                    enable_pansou INTEGER NOT NULL DEFAULT 1,
                    c115_base_url TEXT NOT NULL,
                    c115_cookie TEXT NOT NULL,
                    c115_allowed_actions TEXT NOT NULL,
                    c115_target_dir_id TEXT NOT NULL,
                    c115_offline_add_path TEXT NOT NULL,
                    c115_offline_list_path TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            self._ensure_column(
                conn,
                "enable_tmdb",
                "enable_tmdb INTEGER NOT NULL DEFAULT 1",
            )
            self._ensure_column(
                conn,
                "enable_prowlarr",
                "enable_prowlarr INTEGER NOT NULL DEFAULT 1",
            )
            self._ensure_column(
                conn,
                "enable_pansou",
                "enable_pansou INTEGER NOT NULL DEFAULT 1",
            )
            self._ensure_column(
                conn,
                "c115_base_url",
                "c115_base_url TEXT NOT NULL DEFAULT 'https://lixian.115.com'",
            )
            self._ensure_column(conn, "c115_cookie", "c115_cookie TEXT NOT NULL DEFAULT ''")
            self._ensure_column(
                conn,
                "c115_allowed_actions",
                "c115_allowed_actions TEXT NOT NULL DEFAULT 'create_offline_task'",
            )
            self._ensure_column(
                conn,
                "c115_target_dir_id",
                "c115_target_dir_id TEXT NOT NULL DEFAULT '0'",
            )
            self._ensure_column(
                conn,
                "c115_offline_add_path",
                "c115_offline_add_path TEXT NOT NULL DEFAULT '/lixianssp/?ac=add_task_url'",
            )
            self._ensure_column(
                conn,
                "c115_offline_list_path",
                "c115_offline_list_path TEXT NOT NULL DEFAULT '/web/lixian/?ac=task_lists'",
            )

            conn.execute(
                """
                INSERT INTO app_config (
                    id, tmdb_base_url, tmdb_api_key,
                    prowlarr_base_url, prowlarr_api_key,
                    pansou_base_url,
                    enable_tmdb, enable_prowlarr, enable_pansou,
                    c115_base_url, c115_cookie, c115_allowed_actions,
                    c115_target_dir_id, c115_offline_add_path, c115_offline_list_path,
                    updated_at
                )
                SELECT
                    1,
                    'https://api.themoviedb.org/3',
                    '',
                    'http://localhost:9696',
                    '',
                    'http://localhost:805',
                    1,
                    1,
                    1,
                    'https://lixian.115.com',
                    '',
                    'create_offline_task',
                    '0',
                    '/lixianssp/?ac=add_task_url',
                    '/web/lixian/?ac=task_lists',
                    ?
                WHERE NOT EXISTS (SELECT 1 FROM app_config WHERE id = 1)
                """,
                (datetime.now(UTC).isoformat(),),
            )

    def get(self) -> AppConfig:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM app_config WHERE id = 1").fetchone()
        if not row:
            return AppConfig()
        return AppConfig(
            tmdb_base_url=row["tmdb_base_url"],
            tmdb_api_key=row["tmdb_api_key"],
            prowlarr_base_url=row["prowlarr_base_url"],
            prowlarr_api_key=row["prowlarr_api_key"],
            pansou_base_url=row["pansou_base_url"],
            enable_tmdb=bool(row["enable_tmdb"]),
            enable_prowlarr=bool(row["enable_prowlarr"]),
            enable_pansou=bool(row["enable_pansou"]),
            c115_base_url=row["c115_base_url"],
            c115_cookie=row["c115_cookie"],
            c115_allowed_actions=row["c115_allowed_actions"],
            c115_target_dir_id=row["c115_target_dir_id"],
            c115_offline_add_path=row["c115_offline_add_path"],
            c115_offline_list_path=row["c115_offline_list_path"],
        )

    def update(
        self,
        *,
        tmdb_base_url: str | None = None,
        tmdb_api_key: str | None = None,
        prowlarr_base_url: str | None = None,
        prowlarr_api_key: str | None = None,
        pansou_base_url: str | None = None,
        enable_tmdb: bool | None = None,
        enable_prowlarr: bool | None = None,
        enable_pansou: bool | None = None,
        c115_base_url: str | None = None,
        c115_cookie: str | None = None,
        c115_allowed_actions: str | None = None,
        c115_target_dir_id: str | None = None,
        c115_offline_add_path: str | None = None,
        c115_offline_list_path: str | None = None,
    ) -> AppConfig:
        current = self.get()
        next_cfg = AppConfig(
            tmdb_base_url=tmdb_base_url if tmdb_base_url is not None else current.tmdb_base_url,
            tmdb_api_key=tmdb_api_key if tmdb_api_key is not None else current.tmdb_api_key,
            prowlarr_base_url=prowlarr_base_url
            if prowlarr_base_url is not None
            else current.prowlarr_base_url,
            prowlarr_api_key=prowlarr_api_key
            if prowlarr_api_key is not None
            else current.prowlarr_api_key,
            pansou_base_url=(
                pansou_base_url if pansou_base_url is not None else current.pansou_base_url
            ),
            enable_tmdb=enable_tmdb if enable_tmdb is not None else current.enable_tmdb,
            enable_prowlarr=(
                enable_prowlarr if enable_prowlarr is not None else current.enable_prowlarr
            ),
            enable_pansou=enable_pansou if enable_pansou is not None else current.enable_pansou,
            c115_base_url=c115_base_url if c115_base_url is not None else current.c115_base_url,
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
        )

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE app_config
                SET tmdb_base_url = ?,
                    tmdb_api_key = ?,
                    prowlarr_base_url = ?,
                    prowlarr_api_key = ?,
                    pansou_base_url = ?,
                    enable_tmdb = ?,
                    enable_prowlarr = ?,
                    enable_pansou = ?,
                    c115_base_url = ?,
                    c115_cookie = ?,
                    c115_allowed_actions = ?,
                    c115_target_dir_id = ?,
                    c115_offline_add_path = ?,
                    c115_offline_list_path = ?,
                    updated_at = ?
                WHERE id = 1
                """,
                (
                    next_cfg.tmdb_base_url,
                    next_cfg.tmdb_api_key,
                    next_cfg.prowlarr_base_url,
                    next_cfg.prowlarr_api_key,
                    next_cfg.pansou_base_url,
                    1 if next_cfg.enable_tmdb else 0,
                    1 if next_cfg.enable_prowlarr else 0,
                    1 if next_cfg.enable_pansou else 0,
                    next_cfg.c115_base_url,
                    next_cfg.c115_cookie,
                    next_cfg.c115_allowed_actions,
                    next_cfg.c115_target_dir_id,
                    next_cfg.c115_offline_add_path,
                    next_cfg.c115_offline_list_path,
                    datetime.now(UTC).isoformat(),
                ),
            )
        return next_cfg

    @staticmethod
    def mask(cfg: AppConfig) -> dict[str, str | bool]:
        return {
            "tmdb_base_url": cfg.tmdb_base_url,
            "prowlarr_base_url": cfg.prowlarr_base_url,
            "pansou_base_url": cfg.pansou_base_url,
            "enable_tmdb": cfg.enable_tmdb,
            "enable_prowlarr": cfg.enable_prowlarr,
            "enable_pansou": cfg.enable_pansou,
            "c115_base_url": cfg.c115_base_url,
            "c115_target_dir_id": cfg.c115_target_dir_id,
            "c115_allowed_actions": cfg.c115_allowed_actions,
            "c115_offline_add_path": cfg.c115_offline_add_path,
            "c115_offline_list_path": cfg.c115_offline_list_path,
            "tmdb_api_key_masked": _mask_secret(cfg.tmdb_api_key),
            "prowlarr_api_key_masked": _mask_secret(cfg.prowlarr_api_key),
            "c115_cookie_masked": _mask_secret(cfg.c115_cookie),
            "has_tmdb_api_key": bool(cfg.tmdb_api_key),
            "has_prowlarr_api_key": bool(cfg.prowlarr_api_key),
            "has_c115_cookie": bool(cfg.c115_cookie),
        }


def build_provider_settings(runtime: Settings, app_cfg: AppConfig) -> ProviderSettings:
    return ProviderSettings(
        use_mock=runtime.use_mock,
        request_timeout_seconds=runtime.request_timeout_seconds,
        pansou_base_url=app_cfg.pansou_base_url,
        enable_pansou=app_cfg.enable_pansou,
        prowlarr_base_url=app_cfg.prowlarr_base_url,
        prowlarr_api_key=app_cfg.prowlarr_api_key,
        enable_prowlarr=app_cfg.enable_prowlarr,
        tmdb_base_url=app_cfg.tmdb_base_url,
        tmdb_api_key=app_cfg.tmdb_api_key,
        enable_tmdb=app_cfg.enable_tmdb,
        c115_base_url=app_cfg.c115_base_url,
        c115_cookie=app_cfg.c115_cookie,
        c115_allowed_actions=app_cfg.c115_allowed_actions,
        c115_target_dir_id=app_cfg.c115_target_dir_id,
        c115_offline_add_path=app_cfg.c115_offline_add_path,
        c115_offline_list_path=app_cfg.c115_offline_list_path,
    )
