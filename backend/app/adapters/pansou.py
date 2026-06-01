from __future__ import annotations

from datetime import datetime, timezone
import re

import httpx

from app.core.config import ProviderSettings
from app.core.errors import ProviderError
from app.schemas.models import SearchResultItem
from app.utils.media import infer_cloud_type, infer_media_type


class PanSouAdapter:
    name = "pansou"
    _EMBEDDED_LINK_PATTERNS = (
        re.compile(r"magnet:\?xt=urn:[^\s<>'\"]+", re.IGNORECASE),
        re.compile(r"ed2k://[^\s<>'\"]+", re.IGNORECASE),
        re.compile(r"https?://pan\.quark\.cn/s/[0-9A-Za-z_-]+(?:\?[^\s<>'\"]*)?", re.IGNORECASE),
        re.compile(r"https?://drive\.uc\.cn/s/[0-9A-Za-z_-]+(?:\?[^\s<>'\"]*)?", re.IGNORECASE),
        re.compile(r"https?://pan\.baidu\.com/s/[0-9A-Za-z_-]+(?:\?pwd=[0-9A-Za-z]+)?", re.IGNORECASE),
        re.compile(r"https?://(?:www\.)?(?:aliyundrive\.com|alipan\.com)/s/[0-9A-Za-z_-]+(?:\?[^\s<>'\"]*)?", re.IGNORECASE),
        re.compile(r"https?://pan\.xunlei\.com/s/[0-9A-Za-z_-]+(?:\?[^\s<>'\"]*)?", re.IGNORECASE),
        re.compile(r"https?://cloud\.189\.cn/(?:t|web/share)\S*[0-9A-Za-z]", re.IGNORECASE),
        re.compile(r"https?://(?:www\.)?(?:123pan\.com|123pan\.cn|123684\.com|123685\.com|123912\.com|123592\.com)/s/[0-9A-Za-z_-]+(?:\?[^\s<>'\"]*)?", re.IGNORECASE),
        re.compile(r"https?://(?:115\.com|anxia\.com)/s/[0-9A-Za-z_-]+(?:\?[^\s<>'\"]*)?", re.IGNORECASE),
        re.compile(r"https?://caiyun\.139\.com/[wm]/i/[0-9A-Za-z?=&_-]+", re.IGNORECASE),
        re.compile(r"https?://pan\.pikpak\.com/s/[0-9A-Za-z_-]+(?:\?[^\s<>'\"]*)?", re.IGNORECASE),
    )
    _CLOUD_TYPE_ALIASES = {
        "ali": "aliyun",
        "aliyun": "aliyun",
        "alipan": "aliyun",
        "baidu": "baidu",
        "quark": "quark",
        "tianyi": "tianyi",
        "189": "tianyi",
        "cloud189": "tianyi",
        "uc": "uc",
        "mobile": "mobile",
        "115": "115",
        "pikpak": "pikpak",
        "xunlei": "xunlei",
        "123": "123",
        "pan123": "123",
        "magnet": "magnet",
        "ed2k": "magnet",
        "other": "other",
        "others": "other",
    }

    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    def _proxy(self) -> str | None:
        if (
            self.settings.pansou_use_proxy
            and self.settings.system_proxy_enabled
            and self.settings.system_proxy_url
        ):
            return self.settings.system_proxy_url
        return None

    def _cloud_types(self) -> list[str]:
        raw = (self.settings.pansou_cloud_types or "").strip()
        if not raw:
            return []
        out: list[str] = []
        seen: set[str] = set()
        for item in raw.split(","):
            normalized = self._normalize_requested_cloud_type(item)
            if normalized and normalized not in seen:
                seen.add(normalized)
                out.append(normalized)
        return out

    @classmethod
    def _normalize_requested_cloud_type(cls, raw_type: object) -> str:
        value = str(raw_type or "").strip().lower()
        return cls._CLOUD_TYPE_ALIASES.get(value, value)

    def _source_type(self) -> str:
        source = (self.settings.pansou_source or "all").strip().lower()
        if source in {"tg", "plugin", "all"}:
            return source
        return "all"

    @staticmethod
    def _is_explicit_resource_link(raw: str) -> bool:
        value = str(raw or "").strip()
        if not value:
            return False
        lowered = value.lower()
        return (
            lowered.startswith("http://")
            or lowered.startswith("https://")
            or lowered.startswith("magnet:")
            or lowered.startswith("ed2k://")
        )

    @classmethod
    def _extract_embedded_links(cls, text: object) -> list[str]:
        raw = str(text or "")
        if not raw:
            return []
        found: list[str] = []
        seen: set[str] = set()
        for pattern in cls._EMBEDDED_LINK_PATTERNS:
            for match in pattern.findall(raw):
                link = str(match or "").strip().rstrip(".,;:|)]}>")
                if link and link not in seen:
                    seen.add(link)
                    found.append(link)
        return found

    @staticmethod
    def _parse_datetime(raw: object) -> datetime | None:
        text = str(raw or "").strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt.year <= 1971:
            return None
        return dt

    @staticmethod
    def _normalize_cloud_type(raw_type: object, fallback_url: str, fallback_magnet: str | None) -> str:
        value = str(raw_type or "").strip().lower()
        aliases = {
            "tianyi": "tianyi",
            "189": "tianyi",
            "cloud189": "tianyi",
            "123": "123",
            "pan123": "123",
            "mobile": "mobile",
            "xunlei": "xunlei",
            "quark": "quark",
            "aliyun": "aliyun",
            "alipan": "aliyun",
            "baidu": "baidu",
            "uc": "uc",
            "115": "115",
            "pikpak": "pikpak",
            "magnet": "magnet",
            "ed2k": "magnet",
            "other": "other",
            "others": "other",
        }
        if value in aliases:
            return aliases[value]
        return infer_cloud_type(fallback_url, fallback_magnet)

    @staticmethod
    def _source_detail(*rows: dict) -> str | None:
        keys = (
            "source",
            "source_name",
            "channel",
            "channel_name",
            "from",
            "site",
            "plugin",
            "plugin_name",
            "sender",
            "username",
        )
        for row in rows:
            for key in keys:
                value = str(row.get(key) or "").strip()
                if value:
                    return value
        return None

    async def _get_bearer_token(self, client: httpx.AsyncClient) -> str:
        username = self.settings.pansou_username.strip()
        password = self.settings.pansou_password.strip()
        if not username or not password:
            raise ProviderError(
                "PANSOU_AUTH_INVALID",
                "PanSou auth enabled but credentials missing",
                400,
            )

        login_url = f"{self.settings.pansou_base_url.rstrip('/')}/api/auth/login"
        resp = await client.post(login_url, json={"username": username, "password": password})
        resp.raise_for_status()
        body = resp.json() if resp.content else {}
        if not isinstance(body, dict):
            raise ProviderError("PANSOU_AUTH_INVALID", "PanSou auth response invalid", 502)

        token = body.get("token")
        if not token and isinstance(body.get("data"), dict):
            token = body["data"].get("token")
        if not token:
            raise ProviderError("PANSOU_AUTH_INVALID", "PanSou login token missing", 502)
        return str(token)

    async def _headers(self, client: httpx.AsyncClient) -> dict[str, str]:
        if not self.settings.pansou_enable_auth:
            return {}
        token = await self._get_bearer_token(client)
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _extract_rows(body: object) -> list[dict]:
        rows: object = []
        if isinstance(body, list):
            rows = body
        elif isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, dict):
                rows = data.get("results") or data.get("items") or data.get("list") or []
            elif isinstance(data, list):
                rows = data
            if not rows:
                rows = body.get("results") or body.get("items") or body.get("list") or []
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    @staticmethod
    def _extract_merged_links(body: object) -> dict[str, list[dict]]:
        merged: object = {}
        if isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, dict):
                merged = data.get("merged_by_type") or {}
            if not merged:
                merged = body.get("merged_by_type") or {}
        if not isinstance(merged, dict):
            return {}

        out: dict[str, list[dict]] = {}
        for cloud_type, rows in merged.items():
            if isinstance(rows, list):
                out[str(cloud_type).strip().lower()] = [row for row in rows if isinstance(row, dict)]
        return out

    async def _search_once(self, keyword: str, limit: int) -> list[SearchResultItem]:
        endpoint = self.settings.pansou_search_path.strip() or "/api/search"
        method = (self.settings.pansou_search_method or "POST").strip().upper()
        if method not in {"GET", "POST"}:
            raise ProviderError("PANSOU_CONFIG_ERROR", "PanSou method must be GET or POST", 400)

        url = f"{self.settings.pansou_base_url.rstrip('/')}{endpoint}"
        payload: dict[str, object] = {
            "kw": keyword,
            "src": self._source_type(),
        }
        cloud_types = self._cloud_types()
        payload["res"] = "merge" if cloud_types else "results"
        if cloud_types:
            payload["cloud_types"] = cloud_types

        timeout = self.settings.request_timeout_seconds
        if self.settings.pansou_use_proxy:
            timeout = max(timeout, 30.0)

        async with httpx.AsyncClient(timeout=timeout, proxy=self._proxy()) as client:
            headers = await self._headers(client)
            if method == "POST":
                resp = await client.post(url, json=payload, headers=headers)
            else:
                resp = await client.get(url, params=payload, headers=headers)

        resp.raise_for_status()
        allowed_cloud_types = set(cloud_types)
        body = resp.json()

        merged_links = self._extract_merged_links(body)
        if merged_links:
            out: list[SearchResultItem] = []
            for raw_cloud_type, links in merged_links.items():
                normalized_cloud_type = self._normalize_requested_cloud_type(raw_cloud_type)
                if allowed_cloud_types and normalized_cloud_type not in allowed_cloud_types:
                    continue
                for idx, link_row in enumerate(links):
                    url_value = str(link_row.get("url") or "").strip()
                    password = str(link_row.get("password") or "").strip()
                    if password and url_value and "pwd=" not in url_value and "password=" not in url_value:
                        joiner = "&" if "?" in url_value else "?"
                        url_value = f"{url_value}{joiner}pwd={password}"
                    magnet = url_value if url_value.startswith("magnet:") else None
                    title = str(link_row.get("note") or keyword).strip() or keyword
                    publish_time = self._parse_datetime(link_row.get("datetime"))
                    source_detail = str(link_row.get("source") or "").strip() or None
                    out.append(
                        SearchResultItem(
                            source="pansou",
                            source_id=f"merged-{normalized_cloud_type}-{idx}",
                            source_detail=source_detail,
                            title=title,
                            link=url_value,
                            magnet=magnet,
                            media_type=infer_media_type(title),
                            cloud_type=normalized_cloud_type,  # type: ignore[arg-type]
                            publish_time=publish_time,
                            score=7.0,
                        )
                    )
                    if len(out) >= limit:
                        return out
            return out

        rows = self._extract_rows(body)
        out: list[SearchResultItem] = []
        for idx, row in enumerate(rows):
            links = row.get("links") or []
            base_title = str(row.get("title") or row.get("name") or "unknown")
            base_source_id = str(
                row.get("unique_id")
                or row.get("message_id")
                or row.get("id")
                or row.get("sid")
                or f"pansou-{idx}"
            )
            row_time = self._parse_datetime(
                row.get("datetime") or row.get("time") or row.get("date") or row.get("created_at")
            )
            row_source_detail = self._source_detail(row)
            parsed_links: list[tuple[str, str | None, str, datetime | None, str | None]] = []
            if isinstance(links, list):
                for item in links:
                    if not isinstance(item, dict):
                        continue
                    url_value = str(item.get("url") or item.get("link") or "").strip()
                    if not url_value:
                        continue
                    magnet = url_value if url_value.startswith("magnet:") else None
                    cloud_type = self._normalize_cloud_type(item.get("type"), url_value, magnet)
                    link_time = self._parse_datetime(item.get("datetime") or item.get("time") or item.get("date"))
                    parsed_links.append(
                        (
                            url_value,
                            magnet,
                            cloud_type,
                            link_time or row_time,
                            self._source_detail(item) or row_source_detail,
                        )
                    )

            fallback_url = str(row.get("url") or row.get("link") or "").strip()
            if fallback_url and self._is_explicit_resource_link(fallback_url):
                fallback_magnet = fallback_url if fallback_url.startswith("magnet:") else None
                parsed_links.append(
                    (
                        fallback_url,
                        fallback_magnet,
                        infer_cloud_type(fallback_url, fallback_magnet),
                        row_time,
                        row_source_detail,
                    )
                )

            if not parsed_links:
                for embedded_url in self._extract_embedded_links(row.get("content") or ""):
                    embedded_magnet = embedded_url if embedded_url.startswith("magnet:") else None
                    parsed_links.append(
                        (
                            embedded_url,
                            embedded_magnet,
                            infer_cloud_type(embedded_url, embedded_magnet),
                            row_time,
                            row_source_detail,
                        )
                    )

            if not parsed_links:
                continue

            for link_idx, (
                url_value,
                magnet,
                cloud_type,
                publish_time,
                source_detail,
            ) in enumerate(parsed_links):
                if allowed_cloud_types and cloud_type not in allowed_cloud_types:
                    continue
                out.append(
                    SearchResultItem(
                        source="pansou",
                        source_id=f"{base_source_id}-{link_idx}",
                        source_detail=source_detail,
                        title=base_title,
                        link=url_value,
                        magnet=magnet,
                        media_type=infer_media_type(base_title),
                        cloud_type=cloud_type,  # type: ignore[arg-type]
                        publish_time=publish_time,
                        score=7.0,
                    )
                )
                if len(out) >= limit:
                    return out
        return out

    async def search(self, keyword: str, limit: int) -> list[SearchResultItem]:
        if self.settings.use_mock:
            rows = []
            for idx in range(min(limit, 20)):
                link = f"https://example.com/pansou/{idx}"
                rows.append(
                    SearchResultItem(
                        source="pansou",
                        source_id=f"mock-{idx}",
                        source_detail="mock",
                        title=f"{keyword} PanSou Mock {idx}",
                        link=link,
                        magnet=None,
                        media_type=infer_media_type(keyword),
                        cloud_type=infer_cloud_type(link, None),
                        score=7.0,
                    )
                )
            return rows
        if not self.settings.enable_pansou:
            return []
        try:
            return await self._search_once(keyword, limit)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("PANSOU_ERROR", f"PanSou search failed: {exc}", 502) from exc

    async def check(self) -> tuple[bool, str]:
        if self.settings.use_mock:
            return True, "mock_ok"
        if not self.settings.enable_pansou:
            return True, "disabled"
        try:
            rows = await self._search_once("test", 5)
            return True, f"ok_results_{len(rows)}"
        except ProviderError as exc:
            return False, exc.code
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
