from __future__ import annotations

import asyncio
import httpx

from app.core.config import ProviderSettings
from app.core.errors import ProviderError
from app.schemas.models import TMDBSearchItem


class TMDBAdapter:
    name = "tmdb"

    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    def _proxy(self) -> str | None:
        if not self.settings.tmdb_use_proxy:
            return None
        if self.settings.system_proxy_enabled and self.settings.system_proxy_url:
            return self.settings.system_proxy_url
        return None

    def _trust_env(self) -> bool:
        # Default path: use runtime/system proxy env.
        # Opt-in TMDB proxy path: only use configured proxy URL.
        return not self.settings.tmdb_use_proxy

    def _base_urls(self) -> list[str]:
        base = self.settings.tmdb_base_url.rstrip("/")
        out = [base]
        if "api.themoviedb.org" in base:
            out.append(base.replace("api.themoviedb.org", "api.tmdb.org"))
        elif "api.tmdb.org" in base:
            out.append(base.replace("api.tmdb.org", "api.themoviedb.org"))
        dedup: list[str] = []
        for row in out:
            if row not in dedup:
                dedup.append(row)
        return dedup

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        params: dict[str, str | int],
    ) -> dict:
        last_exc: Exception | None = None
        for base in self._base_urls():
            url = f"{base}{endpoint}"
            for attempt in range(2):
                try:
                    resp = await client.get(url, params=params)
                    if resp.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                        await asyncio.sleep(0.25)
                        continue
                    resp.raise_for_status()
                    try:
                        data = resp.json()
                    except Exception:
                        data = {}
                    if not isinstance(data, dict):
                        raise ProviderError("TMDB_ERROR", "TMDB response is not object", 502)
                    return data
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code if exc.response else 0
                    if status in {429, 500, 502, 503, 504} and attempt == 0:
                        await asyncio.sleep(0.25)
                        continue
                    if status in {401, 403}:
                        raise
                    last_exc = exc
                    break
                except (httpx.ConnectError, httpx.ReadTimeout, httpx.ProxyError, httpx.RemoteProtocolError) as exc:
                    if attempt == 0:
                        await asyncio.sleep(0.25)
                        continue
                    last_exc = exc
                    break
        if last_exc:
            raise last_exc
        raise ProviderError("TMDB_ERROR", "TMDB request failed", 502)

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
                follow_redirects=True,
                trust_env=self._trust_env(),
            ) as client:
                for page in range(1, max_page + 1):
                    params = {
                        "api_key": self.settings.tmdb_api_key,
                        "query": query,
                        "language": "zh-CN",
                        "page": page,
                    }
                    payload = await self._get_json(client, "/search/multi", params)
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

    async def detail_by_title(self, title: str) -> dict:
        rows = await self.search(title, limit=5)
        if not rows:
            return {}
        wanted = "".join(title.lower().split())
        top = next((row for row in rows if "".join(row.title.lower().split()) == wanted), rows[0])
        if self.settings.use_mock or not self.settings.tmdb_api_key:
            return top.model_dump()
        try:
            data = await self.detail_by_id(top.tmdb_id, top.media_type)
            if data:
                return data
        except Exception:  # noqa: BLE001
            pass
        return top.model_dump()

    async def detail_by_id(self, tmdb_id: int, media_type: str | None = None) -> dict:
        if self.settings.use_mock or not self.settings.tmdb_api_key:
            return {}
        media_candidates: list[str] = []
        raw = str(media_type or "").lower().strip()
        if raw in {"movie"}:
            media_candidates = ["movie"]
        elif raw in {"series", "tv"}:
            media_candidates = ["tv"]
        else:
            media_candidates = ["movie", "tv"]
        params = {"api_key": self.settings.tmdb_api_key, "language": "zh-CN", "append_to_response": "credits"}
        last_exc: Exception | None = None
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds,
                proxy=self._proxy(),
                follow_redirects=True,
                trust_env=self._trust_env(),
            ) as client:
                for media in media_candidates:
                    try:
                        body = await self._get_json(client, f"/{media}/{tmdb_id}", params)
                        data = self._detail_from_body(body)
                        raw_poster = data.get("poster_url")
                        data["poster_url"] = self._build_poster_url(raw_poster)
                        return data
                    except httpx.HTTPStatusError as exc:
                        if exc.response is not None and exc.response.status_code == 404:
                            last_exc = exc
                            continue
                        raise
                    except Exception as exc:  # noqa: BLE001
                        last_exc = exc
                        continue
        except Exception:
            if last_exc:
                raise last_exc
            raise
        return {}

    @staticmethod
    def _detail_from_body(body: dict) -> dict:
        genres = [str(x.get("name")) for x in body.get("genres") or [] if isinstance(x, dict) and x.get("name")]
        crew = ((body.get("credits") or {}).get("crew") or []) if isinstance(body, dict) else []
        cast_rows = ((body.get("credits") or {}).get("cast") or []) if isinstance(body, dict) else []
        director = next((str(x.get("name")) for x in crew if isinstance(x, dict) and x.get("job") in {"Director", "Creator"} and x.get("name")), None)
        cast = [str(x.get("name")) for x in cast_rows[:4] if isinstance(x, dict) and x.get("name")]
        date_text = str(body.get("release_date") or body.get("first_air_date") or "")
        year = int(date_text[:4]) if len(date_text) >= 4 and date_text[:4].isdigit() else None
        countries = body.get("origin_country") or []
        country = str(countries[0]) if isinstance(countries, list) and countries else None
        data = {
            "tmdb_id": int(body.get("id") or 0),
            "title": str(body.get("title") or body.get("name") or ""),
            "year": year,
            "media_type": "series" if str(body.get("name") or "") and not body.get("title") else "movie",
            "rating": body.get("vote_average"),
            "overview": str(body.get("overview") or ""),
            "poster_url": body.get("poster_path"),
            "country": country,
            "language": str(body.get("original_language") or "").upper() or None,
            "episodes": int(body.get("number_of_episodes")) if isinstance(body.get("number_of_episodes"), int) else None,
        }
        data.update({"genres": genres, "director": director, "cast": cast})
        return data

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
                follow_redirects=True,
                trust_env=self._trust_env(),
            ) as client:
                await self._get_json(client, "/configuration", params)
            return True, "http_200"
        except httpx.HTTPStatusError as exc:  # noqa: PERF203
            return False, f"http_{exc.response.status_code if exc.response else 0}"
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
            follow_redirects=True,
            trust_env=self._trust_env(),
        ) as client:
            for page in range(1, max_page + 1):
                req_params = dict(params)
                req_params["page"] = page
                payload = await self._get_json(client, endpoint, req_params)
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
