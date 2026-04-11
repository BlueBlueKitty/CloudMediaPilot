from __future__ import annotations

import httpx

from app.core.config import ProviderSettings
from app.core.errors import ProviderError
from app.schemas.models import SearchResultItem
from app.utils.media import infer_media_type


class ProwlarrAdapter:
    name = "prowlarr"

    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    def _proxy(self) -> str | None:
        if (
            self.settings.prowlarr_use_proxy
            and self.settings.system_proxy_enabled
            and self.settings.system_proxy_url
        ):
            return self.settings.system_proxy_url
        return None

    async def _resolve_magnet(self, client: httpx.AsyncClient, candidate: str) -> str | None:
        if not candidate or candidate.startswith("magnet:"):
            return candidate or None
        if "/download" not in candidate:
            return None
        try:
            resp = await client.get(candidate, follow_redirects=False)
            location = resp.headers.get("location", "")
            if location.startswith("magnet:"):
                return location
        except Exception:  # noqa: BLE001
            return None
        return None

    async def search(self, keyword: str, limit: int) -> list[SearchResultItem]:
        if self.settings.use_mock:
            rows = []
            for idx in range(min(limit, 20)):
                magnet = f"magnet:?xt=urn:btih:MOCK{idx:04d}"
                rows.append(
                    SearchResultItem(
                        source="prowlarr",
                        source_id=f"mock-{idx}",
                        title=f"{keyword} Prowlarr Mock {idx}",
                        link=magnet,
                        magnet=magnet,
                        size=(idx + 1) * 1024 * 1024 * 512,
                        media_type=infer_media_type(keyword),
                        cloud_type="magnet",
                        score=7.5,
                    )
                )
            return rows
        if not self.settings.enable_prowlarr:
            return []
        if not self.settings.prowlarr_api_key:
            raise ProviderError(
                "PROWLARR_MISSING_API_KEY",
                "Prowlarr enabled but API key is empty",
                400,
            )

        headers = {"X-Api-Key": self.settings.prowlarr_api_key}
        url = f"{self.settings.prowlarr_base_url}/api/v1/search"
        params: dict[str, str | int] = {"query": keyword, "limit": limit, "type": "search"}
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds,
                proxy=self._proxy(),
            ) as client:
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
                    magnet = (
                        row.get("magnetUrl")
                        or row.get("magnetURL")
                        or row.get("magnet")
                        or row.get("magnetUri")
                    )
                    if not magnet:
                        for key in ("downloadUrl", "guid", "guidUrl", "infoUrl", "comments"):
                            value = str(row.get(key) or "").strip()
                            if value.startswith("magnet:"):
                                magnet = value
                                break
                    magnet = str(magnet or "").strip() or None
                    if magnet and not magnet.startswith("magnet:"):
                        resolved = await self._resolve_magnet(client, magnet)
                        if resolved:
                            magnet = resolved

                    link = str(row.get("downloadUrl") or row.get("guidUrl") or row.get("infoUrl") or magnet or "")
                    out.append(
                        SearchResultItem(
                            source="prowlarr",
                            source_id=str(row.get("guid") or f"prowlarr-{idx}"),
                            title=row.get("title") or "unknown",
                            link=link,
                            magnet=magnet if magnet and magnet.startswith("magnet:") else None,
                            size=row.get("size"),
                            media_type=infer_media_type(row.get("title") or ""),
                            cloud_type="magnet",
                            score=7.5,
                        )
                    )
                return out
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("PROWLARR_ERROR", f"Prowlarr search failed: {exc}", 502) from exc

    async def check(self) -> tuple[bool, str]:
        if self.settings.use_mock:
            return True, "mock_ok"
        if not self.settings.enable_prowlarr:
            return True, "disabled"
        if not self.settings.prowlarr_api_key:
            return False, "missing_api_key"
        try:
            headers = {"X-Api-Key": self.settings.prowlarr_api_key}
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds,
                proxy=self._proxy(),
            ) as client:
                resp = await client.get(
                    f"{self.settings.prowlarr_base_url}/api/v1/health", headers=headers
                )
            return resp.status_code == 200, f"http_{resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
