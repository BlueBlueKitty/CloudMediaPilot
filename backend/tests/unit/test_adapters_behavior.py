from __future__ import annotations

import pytest
from app.adapters.pansou import PanSouAdapter
from app.adapters.prowlarr import ProwlarrAdapter
from app.adapters.tmdb import TMDBAdapter
from app.core.config import ProviderSettings
from app.schemas.models import SearchResultItem
from app.services.search_service import SearchService


def _settings() -> ProviderSettings:
    return ProviderSettings(
        use_mock=False,
        request_timeout_seconds=10,
        pansou_base_url="http://localhost:805",
        enable_pansou=True,
        prowlarr_base_url="http://localhost:9696",
        prowlarr_api_key="key",
        enable_prowlarr=True,
        tmdb_base_url="https://api.themoviedb.org/3",
        tmdb_api_key="key",
        enable_tmdb=True,
        c115_base_url="https://lixian.115.com",
        c115_cookie="",
        c115_allowed_actions="create_offline_task",
        c115_target_dir_id="0",
        c115_offline_add_path="/lixianssp/?ac=add_task_url",
        c115_offline_list_path="/web/lixian/?ac=task_lists",
    )


class _Resp:
    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


@pytest.mark.asyncio
async def test_tmdb_search_supports_multi_page(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    class _Client:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        async def get(self, _url, params=None):  # type: ignore[no-untyped-def]
            page = int((params or {}).get("page", 1))
            calls.append(page)
            if page == 1:
                return _Resp(
                    {
                        "total_pages": 2,
                        "results": [
                            {
                                "id": i,
                                "title": f"A{i}",
                                "media_type": "movie",
                                "poster_path": "/x.jpg",
                            }
                            for i in range(1, 21)
                        ],
                    }
                )
            return _Resp(
                {
                    "total_pages": 2,
                    "results": [
                        {"id": i, "title": f"B{i}", "media_type": "tv", "poster_path": "/y.jpg"}
                        for i in range(21, 41)
                    ],
                }
            )

    monkeypatch.setattr("app.adapters.tmdb.httpx.AsyncClient", lambda timeout: _Client())
    out = await TMDBAdapter(_settings()).search("test", 30)
    assert len(out) == 30
    assert calls == [1, 2]
    assert all(
        row.poster_url and row.poster_url.startswith("https://image.tmdb.org/")
        for row in out
    )


@pytest.mark.asyncio
async def test_prowlarr_parses_dict_results(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Client:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        async def get(self, _url, params=None, headers=None):  # type: ignore[no-untyped-def]
            return _Resp(
                {
                    "results": [
                        {"guid": "g1", "title": "A", "downloadUrl": "https://d1"},
                        {"guid": "g2", "title": "B", "downloadUrl": "https://d2"},
                        {"guid": "g3", "title": "C", "downloadUrl": "https://d3"},
                    ]
                }
            )

    monkeypatch.setattr("app.adapters.prowlarr.httpx.AsyncClient", lambda timeout: _Client())
    out = await ProwlarrAdapter(_settings()).search("test", 50)
    assert len(out) == 3
    assert [row.source_id for row in out] == ["g1", "g2", "g3"]


@pytest.mark.asyncio
async def test_pansou_parses_wrapped_data_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Client:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        async def post(self, _url, json=None):  # type: ignore[no-untyped-def]
            return _Resp(
                {
                    "code": 0,
                    "data": {
                        "results": [
                            {"unique_id": "u1", "title": "X", "links": [{"url": "https://a"}]},
                            {
                                "unique_id": "u2",
                                "title": "Y",
                                "links": [{"url": "magnet:?xt=urn:1"}],
                            },
                            {"unique_id": "u3", "title": "Z", "content": "https://fallback"},
                        ]
                    },
                }
            )

    monkeypatch.setattr("app.adapters.pansou.httpx.AsyncClient", lambda timeout: _Client())
    out = await PanSouAdapter(_settings()).search("test", 20)
    assert len(out) == 3
    assert out[1].magnet and out[1].magnet.startswith("magnet:")
    assert out[2].link == "https://fallback"


def test_dedupe_falls_back_to_source_id_when_link_missing() -> None:
    rows = [
        SearchResultItem(
            source="pansou", source_id="x1", title="a", link="", magnet=None, score=6
        ),
        SearchResultItem(
            source="pansou", source_id="x2", title="b", link="", magnet=None, score=5
        ),
    ]
    out = SearchService._dedupe(rows)
    assert len(out) == 2
