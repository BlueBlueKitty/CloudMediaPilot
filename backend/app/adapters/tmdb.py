from __future__ import annotations

import httpx

from app.core.config import ProviderSettings
from app.core.errors import ProviderError
from app.schemas.models import TMDBSearchItem


class TMDBAdapter:
    name = "tmdb"

    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    def _proxy(self) -> str | None:
        if (
            self.settings.tmdb_use_proxy
            and self.settings.system_proxy_enabled
            and self.settings.system_proxy_url
        ):
            return self.settings.system_proxy_url
        return None

    async def search(self, query: str, limit: int) -> list[TMDBSearchItem]:
        if self.settings.use_mock:
            return self._mock_rows(query, limit)
        if not self.settings.enable_tmdb:
            return []
        if not self.settings.tmdb_api_key:
            raise ProviderError("TMDB_MISSING_API_KEY", "TMDB enabled but API key is empty", 400)
        try:
            max_page = max(1, (limit + 19) // 20)
            raw_rows: list[dict] = []
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds,
                proxy=self._proxy(),
            ) as client:
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

            return self._convert_rows(raw_rows, limit)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("TMDB_ERROR", f"TMDB search failed: {exc}", 502) from exc

    async def trending(self, limit: int, timeframe: str = "week") -> list[TMDBSearchItem]:
        if self.settings.use_mock:
            return self._mock_rows(timeframe, limit)
        if not self.settings.enable_tmdb:
            return []
        if not self.settings.tmdb_api_key:
            raise ProviderError("TMDB_MISSING_API_KEY", "TMDB enabled but API key is empty", 400)
        params = {
            "api_key": self.settings.tmdb_api_key,
            "language": "zh-CN",
        }
        try:
            rows = await self._fetch_paged_rows(
                f"/trending/all/{timeframe}",
                limit,
                params,
            )
            return self._convert_rows(rows, limit)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("TMDB_ERROR", f"TMDB trending failed: {exc}", 502) from exc

    async def discover(self, category: str, limit: int) -> list[TMDBSearchItem]:
        if self.settings.use_mock:
            return self._mock_rows(category, limit)
        if not self.settings.enable_tmdb:
            return []
        if not self.settings.tmdb_api_key:
            raise ProviderError("TMDB_MISSING_API_KEY", "TMDB enabled but API key is empty", 400)

        endpoint = ""
        params: dict[str, str | int] = {
            "api_key": self.settings.tmdb_api_key,
            "language": "zh-CN",
        }
        if category == "movie_now_playing":
            endpoint = "/movie/now_playing"
            params["region"] = "CN"
        elif category == "tv_popular":
            endpoint = "/tv/popular"
        elif category == "movie_popular":
            endpoint = "/movie/popular"
        else:
            raise ProviderError("TMDB_CATEGORY_INVALID", f"unsupported category: {category}", 400)

        try:
            rows = await self._fetch_paged_rows(endpoint, limit, params)
            return self._convert_rows(rows, limit)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("TMDB_ERROR", f"TMDB discover failed: {exc}", 502) from exc

    async def enrich(self, title: str) -> dict:
        try:
            rows = await self.search(title, limit=1)
        except Exception:  # noqa: BLE001
            return {}
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
            return True, "mock_ok"
        if not self.settings.enable_tmdb:
            return True, "disabled"
        if not self.settings.tmdb_api_key:
            return False, "missing_api_key"
        params = {"api_key": self.settings.tmdb_api_key}
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds,
                proxy=self._proxy(),
            ) as client:
                resp = await client.get(
                    f"{self.settings.tmdb_base_url}/configuration", params=params
                )
            return resp.status_code == 200, f"http_{resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    async def _fetch_paged_rows(
        self,
        endpoint: str,
        limit: int,
        params: dict[str, str | int],
    ) -> list[dict]:
        max_page = max(1, (limit + 19) // 20)
        raw_rows: list[dict] = []
        async with httpx.AsyncClient(
            timeout=self.settings.request_timeout_seconds,
            proxy=self._proxy(),
        ) as client:
            for page in range(1, max_page + 1):
                req_params = dict(params)
                req_params["page"] = page
                resp = await client.get(f"{self.settings.tmdb_base_url}{endpoint}", params=req_params)
                resp.raise_for_status()
                payload = resp.json()
                page_rows = payload.get("results") or []
                if not isinstance(page_rows, list) or not page_rows:
                    break
                raw_rows.extend([row for row in page_rows if isinstance(row, dict)])
                total_pages = int(payload.get("total_pages") or page)
                if len(raw_rows) >= limit or page >= total_pages:
                    break
        return raw_rows

    def _mock_rows(self, query: str, limit: int) -> list[TMDBSearchItem]:
        samples = [
            ("Inception", 2010, "movie", 8.4, "/qmDpIHrmpJINaRKAfWQfftjCdyi.jpg", "US", "en"),
            ("Interstellar", 2014, "movie", 8.5, "/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg", "US", "en"),
            ("Breaking Bad", 2008, "series", 8.9, "/ztkUQFLlC19CCMYHW9o1zWhJRNq.jpg", "US", "en"),
            ("The Dark Knight", 2008, "movie", 8.5, "/qJ2tW6WMUDux911r6m7haRef0WH.jpg", "US", "en"),
            (
                "Game of Thrones",
                2011,
                "series",
                8.4,
                "/1XS1oqL89opfnbLl8WnZY1O1uJx.jpg",
                "US",
                "en",
            ),
        ]
        out: list[TMDBSearchItem] = []
        for idx, (title, year, media_type, rating, poster_path, country, language) in enumerate(
            samples[:limit]
        ):
            out.append(
                TMDBSearchItem(
                    tmdb_id=1000 + idx,
                    title=title,
                    year=year,
                    media_type=media_type,  # type: ignore[arg-type]
                    rating=rating,
                    overview=f"{title} mock overview",
                    poster_url=self._build_poster_url(poster_path),
                    country=country,
                    language=language.upper(),
                    episodes=10 + idx if media_type == "series" else None,
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
            poster_url = self._build_poster_url(poster_path)
            countries = row.get("origin_country")
            country = None
            if isinstance(countries, list) and countries:
                country = str(countries[0])
            language = row.get("original_language")
            episodes = row.get("number_of_episodes") or row.get("episode_count")
            out.append(
                TMDBSearchItem(
                    tmdb_id=int(mid),
                    title=row.get("title") or row.get("name") or "unknown",
                    year=year,
                    media_type=media_type,
                    rating=row.get("vote_average"),
                    overview=row.get("overview") or "",
                    poster_url=poster_url,
                    country=country,
                    language=str(language).upper() if language else None,
                    episodes=int(episodes) if isinstance(episodes, int | float) else None,
                )
            )
        return out

    def _build_poster_url(self, poster_path: object) -> str | None:
        if not isinstance(poster_path, str) or not poster_path:
            return None
        if poster_path.startswith(("http://", "https://")):
            return poster_path
        if poster_path.startswith("/"):
            return f"{self.settings.tmdb_image_base_url}{poster_path}"
        return None
