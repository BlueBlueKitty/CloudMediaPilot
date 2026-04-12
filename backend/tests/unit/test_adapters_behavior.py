from __future__ import annotations

import httpx
import pytest
from app.adapters.c115 import C115Adapter
from app.adapters.pansou import PanSouAdapter
from app.adapters.prowlarr import ProwlarrAdapter
from app.adapters.tmdb import TMDBAdapter
from app.core.config import ProviderSettings
from app.schemas.models import SearchResultItem
from app.services.search_service import SearchService


def _settings() -> ProviderSettings:
    return ProviderSettings(
        pansou_base_url="http://localhost:805",
        enable_pansou=True,
        pansou_use_proxy=False,
        pansou_enable_auth=False,
        pansou_username="",
        pansou_password="",
        pansou_search_path="/api/search",
        pansou_search_method="POST",
        pansou_cloud_types="",
        pansou_source="all",
        prowlarr_base_url="http://localhost:9696",
        prowlarr_api_key="key",
        prowlarr_use_proxy=False,
        enable_prowlarr=True,
        tmdb_base_url="https://api.themoviedb.org/3",
        tmdb_api_key="key",
        enable_tmdb=True,
        tmdb_image_base_url="https://image.tmdb.org/t/p/w500",
        tmdb_use_proxy=False,
        c115_base_url="https://lixian.115.com",
        c115_cookie="",
        c115_allowed_actions="create_offline_task",
        c115_target_dir_id="0",
        c115_target_dir_path="/",
        c115_offline_dir_id="0",
        c115_offline_dir_path="/",
        c115_offline_add_path="/lixianssp/?ac=add_task_url",
        c115_offline_list_path="/web/lixian/?ac=task_lists",
        storage_providers="115,quark,tianyi,123",
        quark_cookie="",
        tianyi_username="",
        tianyi_password="",
        pan123_username="",
        pan123_password="",
        system_username="admin",
        system_password_hash="",
        system_auth_secret="secret",
        system_proxy_url="",
        system_proxy_enabled=False,
        request_timeout_seconds=10,
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

    monkeypatch.setattr("app.adapters.tmdb.httpx.AsyncClient", lambda **kwargs: _Client())
    out = await TMDBAdapter(_settings()).search("test", 30)
    assert len(out) == 30
    assert calls == [1, 2]
    assert all(
        row.poster_url and row.poster_url.startswith("https://image.tmdb.org/")
        for row in out
    )


@pytest.mark.asyncio
async def test_tmdb_search_fallbacks_to_alt_domain_when_primary_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Client:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        async def get(self, url, params=None):  # type: ignore[no-untyped-def]
            if "api.themoviedb.org" in url:
                raise httpx.ConnectError("primary_down")
            return _Resp(
                {
                    "total_pages": 1,
                    "results": [
                        {
                            "id": 1,
                            "title": "Fallback OK",
                            "media_type": "movie",
                            "poster_path": "/x.jpg",
                        }
                    ],
                }
            )

    monkeypatch.setattr("app.adapters.tmdb.httpx.AsyncClient", lambda **kwargs: _Client())
    out = await TMDBAdapter(_settings()).search("fallback", 5)
    assert len(out) == 1
    assert out[0].title == "Fallback OK"


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

    monkeypatch.setattr("app.adapters.prowlarr.httpx.AsyncClient", lambda **kwargs: _Client())
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

        async def post(self, _url, json=None, headers=None):  # type: ignore[no-untyped-def]
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

    monkeypatch.setattr("app.adapters.pansou.httpx.AsyncClient", lambda **kwargs: _Client())
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


@pytest.mark.asyncio
async def test_c115_magnet_falls_back_to_add_task_url_when_bt_decode_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RespText:
        status_code = 200
        text = "decode fail!"
        content = b"decode fail!"

        def json(self):  # type: ignore[no-untyped-def]
            raise ValueError("non-json")

    class _RespJson:
        status_code = 200
        text = '{"state": true, "task_id": "task-123"}'
        content = b'{"state": true, "task_id": "task-123"}'

        def json(self):  # type: ignore[no-untyped-def]
            return {"state": True, "task_id": "task-123"}

    class _Client:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        async def post(self, url, headers=None, data=None):  # type: ignore[no-untyped-def]
            self.calls.append(url)
            if "ac=add_task_bt" in url:
                return _RespText()
            return _RespJson()

    fake = _Client()
    monkeypatch.setattr("app.adapters.c115.httpx.AsyncClient", lambda **kwargs: fake)
    settings = _settings()
    settings.c115_cookie = "cookie"
    task_id = await C115Adapter(settings).create_offline_task(
        "magnet:?xt=urn:btih:13C51508AE25C8F2368FA260FC63478183D5A234",
        "0",
    )
    assert task_id == "task-123"
    assert len(fake.calls) >= 2
    assert "ac=add_task_bt" in fake.calls[0]
    assert any("ac=add_task_url" in call for call in fake.calls)


@pytest.mark.asyncio
async def test_c115_add_task_url_falls_back_when_first_endpoint_decode_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RespText:
        status_code = 200
        text = "decode fail!"
        content = b"decode fail!"

        def json(self):  # type: ignore[no-untyped-def]
            raise ValueError("non-json")

    class _RespJson:
        status_code = 200
        text = '{"state": true, "task_id": "task-456"}'
        content = b'{"state": true, "task_id": "task-456"}'

        def json(self):  # type: ignore[no-untyped-def]
            return {"state": True, "task_id": "task-456"}

    class _Client:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        async def post(self, url, headers=None, data=None):  # type: ignore[no-untyped-def]
            self.calls.append(url)
            if "ac=add_task_bt" in url:
                return _RespJson()
            if "lixianssp/?ac=add_task_url" in url:
                return _RespText()
            if "web/lixian/?ct=lixian&ac=add_task_url" in url:
                return _RespJson()
            return _RespText()

    fake = _Client()
    monkeypatch.setattr("app.adapters.c115.httpx.AsyncClient", lambda **kwargs: fake)
    settings = _settings()
    settings.c115_cookie = "cookie"
    settings.c115_offline_add_path = "/lixianssp/?ac=add_task_url"
    task_id = await C115Adapter(settings).create_offline_task(
        "https://example.com/file.torrent",
        "0",
    )
    assert task_id == "task-456"
    assert len(fake.calls) >= 2
    assert "lixianssp/?ac=add_task_url" in fake.calls[0]
    assert "web/lixian/?ct=lixian&ac=add_task_url" in fake.calls[1]


@pytest.mark.asyncio
async def test_c115_add_task_url_payload_uses_wp_path_id_without_savepath(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RespJson:
        status_code = 200
        text = '{"state": true, "task_id": "task-789"}'
        content = b'{"state": true, "task_id": "task-789"}'

        def json(self):  # type: ignore[no-untyped-def]
            return {"state": True, "task_id": "task-789"}

    class _Client:
        def __init__(self) -> None:
            self.last_data = None

        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        async def post(self, url, headers=None, data=None):  # type: ignore[no-untyped-def]
            self.last_data = data
            return _RespJson()

    fake = _Client()
    monkeypatch.setattr("app.adapters.c115.httpx.AsyncClient", lambda **kwargs: fake)
    settings = _settings()
    settings.c115_cookie = "cookie"
    task_id = await C115Adapter(settings).create_offline_task(
        "https://example.com/file.torrent",
        "3322179626497351548",
    )
    assert task_id == "task-789"
    assert isinstance(fake.last_data, dict)
    assert fake.last_data.get("wp_path_id") == "3322179626497351548"
    assert "savepath" not in fake.last_data
