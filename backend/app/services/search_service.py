from __future__ import annotations

import asyncio
import json
import logging
import re
import time

from app.adapters.pansou import PanSouAdapter
from app.adapters.prowlarr import ProwlarrAdapter
from app.core.errors import ProviderError
from app.schemas.models import (
    SearchFilterRule,
    SearchResponse,
    SearchResultItem,
    TMDBSearchContext,
)
from app.services.search_progress_service import store as search_progress_store

logger = logging.getLogger("resource_search")

DEFAULT_SEARCH_FILTER_RULES: list[dict[str, object]] = []


class SearchService:
    def __init__(self, pansou: PanSouAdapter, prowlarr: ProwlarrAdapter, tmdb: object) -> None:
        self.pansou = pansou
        self.prowlarr = prowlarr
        self.tmdb = tmdb

    async def search(
        self,
        request_id: str,
        keyword: str,
        limit: int | None,
        tmdb_context: TMDBSearchContext | None = None,
    ) -> SearchResponse:
        started = time.perf_counter()
        partial_success = False
        warnings: list[str] = []
        logger.info("search_started title=%s limit=%s", keyword, limit)
        active_providers = [
            provider
            for provider, enabled in (
                ("pansou", self.pansou.settings.enable_pansou),
                ("prowlarr", self.prowlarr.settings.enable_prowlarr),
            )
            if enabled
        ]
        search_progress_store.start(request_id, keyword, active_providers)

        pansou_limit = (
            max(1, self.pansou.settings.pansou_search_limit)
            if self.pansou.settings.pansou_search_limit_enabled
            else None
        )
        prowlarr_limit = (
            max(1, self.prowlarr.settings.prowlarr_search_limit)
            if self.prowlarr.settings.prowlarr_search_limit_enabled
            else None
        )
        pansou_task = asyncio.create_task(self.pansou.search(keyword, pansou_limit))
        prowlarr_task = asyncio.create_task(self.prowlarr.search(keyword, prowlarr_limit))

        pansou_results: list[SearchResultItem] = []
        prowlarr_results: list[SearchResultItem] = []
        for task_name, task in (("pansou", pansou_task), ("prowlarr", prowlarr_task)):
            try:
                out = await task
                logger.info(
                    "search_provider_succeeded provider=%s title=%s count=%s",
                    task_name,
                    keyword,
                    len(out),
                )
                search_progress_store.update_provider(
                    request_id, task_name, status="succeeded", count=len(out)
                )
                if task_name == "pansou":
                    pansou_results = out
                else:
                    prowlarr_results = out
            except ProviderError as exc:
                partial_success = True
                warnings.append(f"{task_name}:{exc.message}")
                logger.error(
                    "search_provider_failed provider=%s title=%s error=%s",
                    task_name,
                    keyword,
                    exc.message,
                )
                search_progress_store.update_provider(
                    request_id, task_name, status="failed", message=exc.message
                )

        merged = self._dedupe(pansou_results + prowlarr_results)
        total_before_search_filter = len(merged)
        filtered_count = total_before_search_filter
        merged = self._filter_search_results(merged)
        filtered_count -= len(merged)
        total_after_search_filter = len(merged)
        if filtered_count > 0:
            logger.info(
                "search_filtered_adult title=%s filtered_count=%s",
                keyword,
                filtered_count,
            )
        if tmdb_context:
            merged = self._precision_rank(merged, tmdb_context)
        if limit is not None:
            merged = merged[:limit]

        elapsed = int((time.perf_counter() - started) * 1000)
        search_progress_store.finish(request_id)
        logger.info(
            "search_finished title=%s provider=all total_results=%s took_ms=%s",
            keyword,
            len(merged),
            elapsed,
        )
        return SearchResponse(
            request_id=request_id,
            keyword=keyword,
            took_ms=elapsed,
            total=len(merged),
            total_before_search_filter=total_before_search_filter,
            search_filter_removed=filtered_count,
            total_after_search_filter=total_after_search_filter,
            partial_success=partial_success,
            warnings=warnings,
            results=merged,
        )

    @staticmethod
    def _dedupe(items: list[SearchResultItem]) -> list[SearchResultItem]:
        seen: set[str] = set()
        out: list[SearchResultItem] = []
        for row in items:
            uri = (row.magnet or row.link or "").strip()
            if uri:
                key = uri.lower()
            elif row.source_id:
                key = f"{row.source}:{row.source_id}"
            else:
                key = f"{row.source}:{row.title}"
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
        out.sort(key=lambda x: x.score, reverse=True)
        return out

    def _search_filter_rules(self) -> list[SearchFilterRule]:
        raw = (self.pansou.settings.search_filter_rules or "").strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        out: list[SearchFilterRule] = []
        for row in parsed:
            try:
                out.append(SearchFilterRule.model_validate(row))
            except Exception:
                continue
        return out

    def _matches_search_filter(self, row: SearchResultItem) -> bool:
        if row.cloud_type != "magnet":
            return False
        text = " ".join(
            part.strip()
            for part in (row.title or "", row.source_detail or "", row.link or "", row.magnet or "")
            if part and part.strip()
        )
        if not text:
            return False
        folded_text = text.casefold()
        for rule in self._search_filter_rules():
            if not rule.enabled:
                continue
            if rule.match_mode == "keyword":
                tokens = [
                    token.strip().casefold()
                    for token in re.split(r"[,，]", rule.pattern.strip())
                    if token.strip()
                ]
                if tokens and all(token in folded_text for token in tokens):
                    return True
                continue
            try:
                if re.search(rule.pattern, text, re.IGNORECASE):
                    return True
            except re.error:
                continue
        return False

    def _filter_search_results(self, items: list[SearchResultItem]) -> list[SearchResultItem]:
        if not self.pansou.settings.search_filter_enabled:
            return items
        return [row for row in items if not self._matches_search_filter(row)]

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
