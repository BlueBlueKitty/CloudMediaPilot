from __future__ import annotations

from threading import RLock

from app.schemas.models import SearchProgressProvider, SearchProgressResponse


class SearchProgressStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._items: dict[str, SearchProgressResponse] = {}

    def start(self, request_id: str, keyword: str, providers: list[str]) -> None:
        with self._lock:
            self._items[request_id] = SearchProgressResponse(
                request_id=request_id,
                keyword=keyword,
                finished=False,
                providers=[
                    SearchProgressProvider(provider=provider, status="running")
                    for provider in providers
                ],
            )

    def update_provider(
        self,
        request_id: str,
        provider: str,
        *,
        status: str,
        count: int | None = None,
        message: str | None = None,
    ) -> None:
        with self._lock:
            progress = self._items.get(request_id)
            if not progress:
                return
            for item in progress.providers:
                if item.provider == provider:
                    item.status = status  # type: ignore[assignment]
                    item.count = count
                    item.message = message
                    break

    def finish(self, request_id: str) -> None:
        with self._lock:
            progress = self._items.get(request_id)
            if progress:
                progress.finished = True

    def get(self, request_id: str) -> SearchProgressResponse | None:
        with self._lock:
            progress = self._items.get(request_id)
            if not progress:
                return None
            return SearchProgressResponse.model_validate(progress.model_dump())


store = SearchProgressStore()
