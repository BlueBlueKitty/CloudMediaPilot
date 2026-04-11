from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.core.config import ProviderSettings
from app.core.errors import ProviderError
from app.schemas.models import SearchResultItem
from app.utils.media import infer_cloud_type, infer_media_type


class ProwlarrAdapter:
    name = "prowlarr"

    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    async def search(self, keyword: str, limit: int) -> list[SearchResultItem]:
        if self.settings.use_mock:
            return [
                SearchResultItem(
                    source="prowlarr",
                    source_id=f"pr-mock-{idx + 1}",
                    title=f"{keyword} WEB-DL {idx + 1}",
                    link=f"https://example.com/prowlarr/item/{idx + 1}",
                    magnet=f"magnet:?xt=urn:btih:PROWLARR{idx + 1}",
                    publish_time=datetime.now(UTC),
                    size=(idx + 1) * 1024 * 1024 * 1024,
                    media_type=infer_media_type(f"{keyword} WEB-DL"),
                    cloud_type="magnet",
                    score=8.0 - idx * 0.2,
                )
                for idx in range(min(limit, 10))
            ]

        if not self.settings.enable_prowlarr:
            return []
        if not self.settings.prowlarr_api_key:
            return []

        headers = {"X-Api-Key": self.settings.prowlarr_api_key}
        url = f"{self.settings.prowlarr_base_url}/api/v1/search"
        params: dict[str, str | int] = {"query": keyword, "limit": limit, "type": "search"}
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, list):
                rows = payload
            elif isinstance(payload, dict):
                rows = payload.get("results") or payload.get("data") or []
            else:
                rows = []
            rows = rows[:limit]
            out: list[SearchResultItem] = []
            for idx, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                magnet = row.get("magnetUrl")
                link = row.get("infoUrl") or row.get("downloadUrl") or row.get("guidUrl") or ""
                out.append(
                    SearchResultItem(
                        source="prowlarr",
                        source_id=str(row.get("guid") or f"prowlarr-{idx}"),
                        title=row.get("title") or "unknown",
                        link=link,
                        magnet=magnet,
                        size=row.get("size"),
                        media_type=infer_media_type(row.get("title") or ""),
                        cloud_type=infer_cloud_type(link, magnet),
                        score=7.5,
                    )
                )
            return out
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("PROWLARR_ERROR", f"Prowlarr search failed: {exc}", 502) from exc

    async def check(self) -> tuple[bool, str]:
        if self.settings.use_mock:
            return True, "mock"
        if not self.settings.enable_prowlarr:
            return True, "disabled"
        if not self.settings.prowlarr_api_key:
            return False, "missing_api_key"
        try:
            headers = {"X-Api-Key": self.settings.prowlarr_api_key}
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                resp = await client.get(
                    f"{self.settings.prowlarr_base_url}/api/v1/health", headers=headers
                )
            return resp.status_code == 200, f"http_{resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
