from __future__ import annotations

import re
import logging

import httpx

from app.core.config import ProviderSettings
from app.core.errors import ProviderError
from app.schemas.models import TMDBSearchItem

_DOUBAN_COOKIE = (
    'll="118282"; bid=StA6AQFsAWQ; '
    "_pk_id.100001.4cf6=6448be57b1b5ca7e.1723172321.; "
    "_vwo_uuid_v2=DC15B8183560FF1E538FFE1D480723310|c08e2d213ecb5510005f90a6ff332121; "
    "__utmv=30149280.6282; douban-fav-remind=1; "
    "_pk_ses.100001.4cf6=1; ap_v=0,6.0; "
    "__utma=30149280.859303574.1723448979.1739167503.1739176523.42; "
    "__utmb=30149280.0.10.1739176523; "
    "__utma=223695111.1882744177.1723448979.1739167503.42; "
    "__utmb=223695111.0.10.1739176523"
)
logger = logging.getLogger("provider.douban")


class DoubanAdapter:
    name = "douban"

    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    @staticmethod
    def _extract_year(title: str, url: str) -> int | None:
        for text in (title or "", url or ""):
            match = re.search(r"(19|20)\d{2}", text)
            if match:
                return int(match.group(0))
        return None

    @staticmethod
    def _normalize_cover(raw: object) -> str | None:
        cover = str(raw or "").strip()
        if not cover:
            return None
        if cover.startswith("//"):
            return "https:" + cover
        if cover.startswith(("http://", "https://")):
            return cover
        return None

    async def hot(self, media_type: str, tag: str, start: int, limit: int) -> list[TMDBSearchItem]:
        if self.settings.use_mock:
            return self._mock(media_type, tag, start, limit)

        params = {
            "type": media_type,
            "tag": tag,
            "page_start": max(0, start),
            "page_limit": max(1, min(limit, 100)),
        }
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "priority": "u=1, i",
            "sec-ch-ua": '"Not A(Brand";v="8", "Chromium";v="132", "Microsoft Edge";v="132"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-requested-with": "XMLHttpRequest",
            "referer": "https://movie.douban.com/",
            "referrer-policy": "unsafe-url",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0"
            ),
            # CloudSaver 带完整浏览器头和豆瓣访问 cookie；短 cookie 容易拿到缺字段响应。
            "cookie": _DOUBAN_COOKIE,
        }
        url = "https://movie.douban.com/j/search_subjects"
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            try:
                payload = resp.json() if resp.content else {}
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "douban_non_json status=%s body=%s",
                    resp.status_code,
                    resp.text[:300],
                )
                raise ProviderError("DOUBAN_ERROR", "Douban 返回非 JSON 响应", 502) from exc
            subjects = payload.get("subjects") if isinstance(payload, dict) else []
            if not isinstance(subjects, list):
                subjects = []
            out: list[TMDBSearchItem] = []
            for row in subjects:
                if not isinstance(row, dict):
                    continue
                douban_id = row.get("id")
                if not douban_id:
                    continue
                title = str(row.get("title") or "unknown")
                subject_url = str(row.get("url") or "")
                out.append(
                    TMDBSearchItem(
                        tmdb_id=int(douban_id),
                        title=title,
                        media_type="movie" if media_type == "movie" else "series",
                        rating=float(row.get("rate")) if str(row.get("rate") or "").replace(".", "", 1).isdigit() else None,
                        overview=str(row.get("episodes_info") or ("新上架" if row.get("is_new") else "")),
                        poster_url=self._normalize_cover(row.get("cover")),
                        year=self._extract_year(title, subject_url),
                        episodes=None,
                    )
                )
            return out
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("DOUBAN_ERROR", f"Douban hot failed: {exc}", 502) from exc

    def _mock(self, media_type: str, tag: str, start: int, limit: int) -> list[TMDBSearchItem]:
        out: list[TMDBSearchItem] = []
        for idx in range(limit):
            seq = start + idx + 1
            out.append(
                TMDBSearchItem(
                    tmdb_id=900000 + seq,
                    title=f"豆瓣{tag}{seq}",
                    media_type="movie" if media_type == "movie" else "series",
                    rating=7.0 + (idx % 20) / 10.0,
                    overview="",
                    poster_url=None,
                    year=2020 + (seq % 5),
                    episodes=12 if media_type != "movie" else None,
                )
            )
        return out
