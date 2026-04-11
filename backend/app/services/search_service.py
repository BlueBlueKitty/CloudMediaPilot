from __future__ import annotations

import asyncio
import re
import time

from app.adapters.pansou import PanSouAdapter
from app.adapters.prowlarr import ProwlarrAdapter
from app.adapters.tmdb import TMDBAdapter
from app.core.errors import ProviderError
from app.schemas.models import SearchResponse, SearchResultItem, TMDBSearchContext


class SearchService:
    def __init__(self, pansou: PanSouAdapter, prowlarr: ProwlarrAdapter, tmdb: TMDBAdapter) -> None:
        self.pansou = pansou
        self.prowlarr = prowlarr
        self.tmdb = tmdb

    async def search(
        self,
        request_id: str,
        keyword: str,
        limit: int,
        tmdb_context: TMDBSearchContext | None = None,
    ) -> SearchResponse:
        started = time.perf_counter()
        partial_success = False

        source_limit = max(limit * 3, 100)
        pansou_task = asyncio.create_task(self.pansou.search(keyword, source_limit))
        prowlarr_task = asyncio.create_task(self.prowlarr.search(keyword, source_limit))

        pansou_results: list[SearchResultItem] = []
        prowlarr_results: list[SearchResultItem] = []

        for task_name, task in (("pansou", pansou_task), ("prowlarr", prowlarr_task)):
            try:
                out = await task
                if task_name == "pansou":
                    pansou_results = out
                else:
                    prowlarr_results = out
            except ProviderError:
                partial_success = True

        merged = self._dedupe(pansou_results + prowlarr_results)
        if tmdb_context:
            merged = self._precision_rank(merged, tmdb_context)
        merged = merged[:limit]

        enrich_tasks = [asyncio.create_task(self.tmdb.enrich(r.title)) for r in merged]
        enrich_results = await asyncio.gather(*enrich_tasks, return_exceptions=True)
        for row, meta in zip(merged, enrich_results, strict=False):
            if isinstance(meta, dict):
                row.tmdb_id = meta.get("tmdb_id")
                row.tmdb_title = meta.get("tmdb_title")
                row.tmdb_overview = meta.get("tmdb_overview")
                row.tmdb_poster = meta.get("tmdb_poster")
            else:
                partial_success = True

        elapsed = int((time.perf_counter() - started) * 1000)
        return SearchResponse(
            request_id=request_id,
            keyword=keyword,
            took_ms=elapsed,
            total=len(merged),
            partial_success=partial_success,
            results=merged,
        )

    @staticmethod
    def _dedupe(items: list[SearchResultItem]) -> list[SearchResultItem]:
        seen: set[str] = set()
        out: list[SearchResultItem] = []
        for row in items:
            key = row.magnet or row.link or f"{row.source}:{row.source_id}"
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
        out.sort(key=lambda x: x.score, reverse=True)
        return out

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"[^a-z0-9\u4e00-\u9fa5]+", " ", text.lower()).strip()

    @classmethod
    def _precision_rank(
        cls, items: list[SearchResultItem], context: TMDBSearchContext
    ) -> list[SearchResultItem]:
        ctx_title = cls._normalize_text(context.title)
        ctx_tokens = {x for x in ctx_title.split() if len(x) > 1}
        ctx_year = str(context.year) if context.year else None
        ranked: list[SearchResultItem] = []
        for row in items:
            norm_title = cls._normalize_text(row.title)
            tokens = {x for x in norm_title.split() if len(x) > 1}
            overlap = len(ctx_tokens & tokens)
            coverage = overlap / max(1, len(ctx_tokens))
            bonus = 0.0
            if ctx_title and ctx_title in norm_title:
                bonus += 2.0
            if ctx_year and ctx_year in norm_title:
                bonus += 1.2
            row.score = float(row.score + coverage * 3.0 + bonus)
            if coverage >= 0.2 or bonus >= 1.0:
                ranked.append(row)
        if ranked:
            ranked.sort(key=lambda x: x.score, reverse=True)
            return ranked
        items.sort(key=lambda x: x.score, reverse=True)
        return items
