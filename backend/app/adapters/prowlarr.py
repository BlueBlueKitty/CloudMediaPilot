from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1

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
            if resp.status_code in {301, 302, 303, 307, 308} and location:
                resp = await client.get(location, follow_redirects=True)
            elif resp.status_code < 400 and resp.content:
                pass
            else:
                resp = await client.get(candidate, follow_redirects=True)
            text = resp.text[:4096] if resp.content else ""
            if text.startswith("magnet:"):
                return text.strip()
            if resp.content:
                info_hash = self._torrent_info_hash(resp.content)
                if info_hash:
                    return f"magnet:?xt=urn:btih:{info_hash}"
        except Exception:  # noqa: BLE001
            return None
        return None

    @staticmethod
    def _torrent_info_hash(data: bytes) -> str | None:
        key = b"4:info"
        pos = data.find(key)
        if pos < 0:
            return None
        start = pos + len(key)

        def skip(i: int) -> int:
            token = data[i : i + 1]
            if token == b"i":
                end = data.index(b"e", i)
                return end + 1
            if token == b"l":
                i += 1
                while data[i : i + 1] != b"e":
                    i = skip(i)
                return i + 1
            if token == b"d":
                i += 1
                while data[i : i + 1] != b"e":
                    i = skip(i)
                    i = skip(i)
                return i + 1
            if token.isdigit():
                colon = data.index(b":", i)
                length = int(data[i:colon])
                return colon + 1 + length
            raise ValueError("invalid bencode")

        end = skip(start)
        return sha1(data[start:end]).hexdigest().upper()

    @staticmethod
    def _source_detail(row: dict) -> str | None:
        for key in ("indexer", "indexerName", "indexer_name", "site", "tracker", "source"):
            value = str(row.get(key) or "").strip()
            if value:
                return value
        indexer_id = row.get("indexerId") or row.get("indexer_id")
        if indexer_id not in {None, ""}:
            return f"indexer-{indexer_id}"
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
                        source_detail="mock-indexer",
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

                    link = str(
                        magnet
                        if magnet and magnet.startswith("magnet:")
                        else row.get("downloadUrl") or row.get("guidUrl") or row.get("infoUrl") or ""
                    )
                    out.append(
                        SearchResultItem(
                            source="prowlarr",
                            source_id=str(row.get("guid") or f"prowlarr-{idx}"),
                            source_detail=self._source_detail(row),
                            title=row.get("title") or "unknown",
                            link=link,
                            magnet=magnet if magnet and magnet.startswith("magnet:") else None,
                            size=row.get("size"),
                            publish_time=self._parse_datetime(
                                row.get("publishDate")
                                or row.get("publish_date")
                                or row.get("indexerFlags")
                                or row.get("added")
                            ),
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
