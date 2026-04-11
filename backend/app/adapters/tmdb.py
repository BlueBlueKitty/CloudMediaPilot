from __future__ import annotations

import httpx

from app.core.config import ProviderSettings
from app.schemas.models import TMDBSearchItem


class TMDBAdapter:
    name = "tmdb"

    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    async def search(self, query: str, limit: int) -> list[TMDBSearchItem]:
        if self.settings.use_mock:
            return self._mock_rows(query, limit)

        if not self.settings.enable_tmdb or not self.settings.tmdb_api_key:
            return []
        try:
            max_page = max(1, (limit + 19) // 20)
            raw_rows: list[dict] = []
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                for page in range(1, max_page + 1):
                    params = {
                        "api_key": self.settings.tmdb_api_key,
                        "query": query,
                        "language": "zh-CN",
                        "page": page,
                    }
                    resp = await client.get(
                        f"{self.settings.tmdb_base_url}/search/multi",
                        params=params,
                    )
                    resp.raise_for_status()
                    payload = resp.json()
                    page_rows = payload.get("results") or []
                    if not isinstance(page_rows, list) or not page_rows:
                        break
                    raw_rows.extend([row for row in page_rows if isinstance(row, dict)])
                    total_pages = int(payload.get("total_pages") or page)
                    if len(raw_rows) >= limit or page >= total_pages:
                        break

            out: list[TMDBSearchItem] = []
            for row in raw_rows[:limit]:
                mid = row.get("id")
                if not mid:
                    continue
                date_text = row.get("release_date") or row.get("first_air_date") or ""
                year = None
                if date_text and len(date_text) >= 4 and date_text[:4].isdigit():
                    year = int(date_text[:4])
                upstream_media_type = row.get("media_type")
                if upstream_media_type in {"movie", "series", "person"}:
                    media_type = upstream_media_type
                elif upstream_media_type == "tv":
                    media_type = "series"
                else:
                    media_type = "unknown"
                poster_path = row.get("poster_path")
                poster_url: str | None = None
                if isinstance(poster_path, str) and poster_path:
                    if poster_path.startswith("http://") or poster_path.startswith("https://"):
                        poster_url = poster_path
                    elif poster_path.startswith("/"):
                        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
                out.append(
                    TMDBSearchItem(
                        tmdb_id=int(mid),
                        title=row.get("title") or row.get("name") or "unknown",
                        year=year,
                        media_type=media_type,
                        rating=row.get("vote_average"),
                        overview=row.get("overview") or "",
                        poster_url=poster_url,
                    )
                )
            return out
        except Exception:  # noqa: BLE001
            return []

    async def trending(self, limit: int) -> list[TMDBSearchItem]:
        if self.settings.use_mock:
            return self._mock_rows("热门", limit)
        if not self.settings.enable_tmdb or not self.settings.tmdb_api_key:
            return []
        params = {
            "api_key": self.settings.tmdb_api_key,
            "language": "zh-CN",
            "page": 1,
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                resp = await client.get(
                    f"{self.settings.tmdb_base_url}/trending/all/week",
                    params=params,
                )
            resp.raise_for_status()
            rows = resp.json().get("results") or []
            return self._convert_rows(rows, limit)
        except Exception:  # noqa: BLE001
            return []

    async def enrich(self, title: str) -> dict:
        rows = await self.search(title, limit=1)
        if not rows:
            return {}
        top = rows[0]
        return {
            "tmdb_id": top.tmdb_id,
            "tmdb_title": top.title,
            "tmdb_overview": top.overview,
            "tmdb_poster": top.poster_url,
        }

    async def check(self) -> tuple[bool, str]:
        if self.settings.use_mock:
            return True, "mock"
        if not self.settings.enable_tmdb:
            return True, "disabled"
        if not self.settings.tmdb_api_key:
            return False, "missing_api_key"
        params = {"api_key": self.settings.tmdb_api_key}
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                resp = await client.get(
                    f"{self.settings.tmdb_base_url}/configuration", params=params
                )
            return resp.status_code == 200, f"http_{resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def _mock_rows(self, query: str, limit: int) -> list[TMDBSearchItem]:
        samples = [
            ("Inception", 2010, "movie", 8.4),
            ("Interstellar", 2014, "movie", 8.5),
            ("Breaking Bad", 2008, "series", 8.9),
            ("The Dark Knight", 2008, "movie", 8.5),
            ("Game of Thrones", 2011, "series", 8.4),
        ]
        out: list[TMDBSearchItem] = []
        for idx, (title, year, media_type, rating) in enumerate(samples[:limit]):
            display_title = title if query in {"", "热门"} else f"{title} · {query}"
            out.append(
                TMDBSearchItem(
                    tmdb_id=1000 + idx,
                    title=display_title,
                    year=year,
                    media_type=media_type,  # type: ignore[arg-type]
                    rating=rating,
                    overview=f"{title} mock overview",
                    poster_url=f"https://image.tmdb.org/t/p/w500/mock-{idx + 1}.jpg",
                )
            )
        return out

    def _convert_rows(self, rows: list, limit: int) -> list[TMDBSearchItem]:
        out: list[TMDBSearchItem] = []
        for row in rows[:limit]:
            if not isinstance(row, dict):
                continue
            mid = row.get("id")
            if not mid:
                continue
            date_text = row.get("release_date") or row.get("first_air_date") or ""
            year = (
                int(date_text[:4])
                if isinstance(date_text, str) and date_text[:4].isdigit()
                else None
            )
            upstream_media_type = row.get("media_type")
            if upstream_media_type in {"movie", "series", "person"}:
                media_type = upstream_media_type
            elif upstream_media_type == "tv":
                media_type = "series"
            else:
                media_type = "unknown"
            poster_path = row.get("poster_path") or row.get("profile_path")
            poster_url: str | None = None
            if isinstance(poster_path, str) and poster_path:
                if poster_path.startswith(("http://", "https://")):
                    poster_url = poster_path
                elif poster_path.startswith("/"):
                    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
            out.append(
                TMDBSearchItem(
                    tmdb_id=int(mid),
                    title=row.get("title") or row.get("name") or "unknown",
                    year=year,
                    media_type=media_type,
                    rating=row.get("vote_average"),
                    overview=row.get("overview") or "",
                    poster_url=poster_url,
                )
            )
        return out
