from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.core.config import ProviderSettings
from app.core.errors import ProviderError
from app.schemas.models import SearchResultItem
from app.utils.media import infer_cloud_type, infer_media_type


class PanSouAdapter:
    name = "pansou"

    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    async def search(self, keyword: str, limit: int) -> list[SearchResultItem]:
        if self.settings.use_mock:
            return [
                SearchResultItem(
                    source="pansou",
                    source_id=f"ps-mock-{idx + 1}",
                    title=f"{keyword} 1080p {idx + 1}",
                    link=f"https://example.com/pansou/item/{idx + 1}",
                    magnet=f"magnet:?xt=urn:btih:PANSOU{idx + 1}",
                    publish_time=datetime.now(UTC),
                    size=(idx + 1) * 1024 * 1024 * 1024,
                    media_type=infer_media_type(f"{keyword} 1080p"),
                    cloud_type="magnet",
                    score=8.5 - idx * 0.2,
                )
                for idx in range(min(limit, 10))
            ]

        if not self.settings.enable_pansou:
            return []
        url = f"{self.settings.pansou_base_url}/api/search"
        payload = {"kw": keyword, "res": "results"}
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                resp = await client.post(url, json=payload)
            resp.raise_for_status()
            body = resp.json()
            data = body.get("data", {}) if isinstance(body, dict) else {}
            if isinstance(data, dict):
                rows = data.get("results")
                if rows is None:
                    rows = data.get("items")
            elif isinstance(data, list):
                rows = data
            else:
                rows = None
            if rows is None and isinstance(body, dict):
                rows = body.get("results") or body.get("items")
            if not isinstance(rows, list):
                rows = []
            rows = rows[:limit]
            out: list[SearchResultItem] = []
            for idx, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                links = row.get("links") or []
                first_url = ""
                magnet = None
                if isinstance(links, list):
                    for item in links:
                        if not isinstance(item, dict):
                            continue
                        url_value = str(item.get("url") or "").strip()
                        if not url_value:
                            continue
                        if not first_url:
                            first_url = url_value
                        if url_value.startswith("magnet:"):
                            magnet = url_value
                            break
                if not first_url:
                    first_url = str(row.get("content") or "").strip()
                out.append(
                    SearchResultItem(
                        source="pansou",
                        source_id=row.get("unique_id") or f"pansou-{idx}",
                        title=row.get("title") or "unknown",
                        link=first_url,
                        magnet=magnet,
                        media_type=infer_media_type(row.get("title") or ""),
                        cloud_type=infer_cloud_type(first_url, magnet),
                        score=7.0,
                    )
                )
            return out
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("PANSOU_ERROR", f"PanSou search failed: {exc}", 502) from exc

    async def check(self) -> tuple[bool, str]:
        if self.settings.use_mock:
            return True, "mock"
        if not self.settings.enable_pansou:
            return True, "disabled"
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                resp = await client.get(f"{self.settings.pansou_base_url}/api/health")
            return resp.status_code == 200, f"http_{resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
