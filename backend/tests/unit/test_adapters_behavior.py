from __future__ import annotations

from dataclasses import replace
import sys
import types

import httpx
import pytest
from app.adapters.c115 import C115Adapter
from app.adapters.pansou import PanSouAdapter
from app.adapters.prowlarr import ProwlarrAdapter
from app.adapters.tmdb import TMDBAdapter
from app.core.config import ProviderSettings
from app.schemas.models import SearchResultItem
from app.services.resource_filter_service import ResourceFilterService
from app.services.search_service import SearchService
from app.services.task_service import TaskService


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
        pansou_search_limit_enabled=True,
        pansou_search_limit=500,
        prowlarr_base_url="http://localhost:9696",
        prowlarr_api_key="key",
        prowlarr_use_proxy=False,
        enable_prowlarr=True,
        prowlarr_search_limit_enabled=True,
        prowlarr_search_limit=100,
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
        resource_filter_enabled=True,
        resource_filter_rules="",
        resource_cleanup_local_roots="",
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


class _FakeTMDB:
    async def enrich(self, _title: str) -> dict[str, object]:  # type: ignore[override]
        return {}


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
                        {
                            "guid": "g1",
                            "title": "A",
                            "downloadUrl": "https://d1",
                            "indexer": "SiteA",
                        },
                        {"guid": "g2", "title": "B", "downloadUrl": "https://d2"},
                        {"guid": "g3", "title": "C", "downloadUrl": "https://d3"},
                    ]
                }
            )

    monkeypatch.setattr("app.adapters.prowlarr.httpx.AsyncClient", lambda **kwargs: _Client())
    out = await ProwlarrAdapter(_settings()).search("test", 50)
    assert len(out) == 3
    assert [row.source_id for row in out] == ["g1", "g2", "g3"]
    assert out[0].source_detail == "SiteA"


@pytest.mark.asyncio
async def test_prowlarr_resolve_download_url_from_download_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Client:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        async def get(self, url, params=None, headers=None, follow_redirects=False):  # type: ignore[no-untyped-def]
            if "download?x=1" in url:
                resp = types.SimpleNamespace(
                    status_code=301,
                    headers={"location": "magnet:?xt=urn:btih:ABC123"},
                    content=b"",
                    text="",
                )
                return resp
            raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr("app.adapters.prowlarr.httpx.AsyncClient", lambda **kwargs: _Client())
    resolved = await ProwlarrAdapter(_settings()).resolve_download_url(
        "http://localhost:9696/15/download?x=1"
    )
    assert resolved == "magnet:?xt=urn:btih:ABC123"


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
                            {
                                "unique_id": "u1",
                                "title": "X",
                                "source": "tg-channel",
                                "links": [{"url": "https://a"}],
                            },
                            {
                                "unique_id": "u2",
                                "title": "Y",
                                "links": [{"url": "magnet:?xt=urn:1", "source": "plugin-a"}],
                            },
                            {
                                "unique_id": "u3",
                                "title": "Z",
                                "content": "夸克：https://pan.quark.cn/s/fallback",
                            },
                        ]
                    },
                }
            )

    monkeypatch.setattr("app.adapters.pansou.httpx.AsyncClient", lambda **kwargs: _Client())
    out = await PanSouAdapter(_settings()).search("test", 20)
    assert len(out) == 3
    assert out[0].source_detail == "tg-channel"
    assert out[1].source_detail == "plugin-a"
    assert out[1].magnet and out[1].magnet.startswith("magnet:")
    assert out[2].link == "https://pan.quark.cn/s/fallback"


@pytest.mark.asyncio
async def test_pansou_extracts_embedded_links_from_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
                            {
                                "unique_id": "u1",
                                "title": "Embed",
                                "content": "夸克：https://pan.quark.cn/s/abc123 百度：https://pan.baidu.com/s/xyz789?pwd=abcd",
                                "source": "tg-channel",
                                "links": [{"url": "", "type": "other"}],
                            }
                        ]
                    },
                }
            )

    monkeypatch.setattr("app.adapters.pansou.httpx.AsyncClient", lambda **kwargs: _Client())
    out = await PanSouAdapter(_settings()).search("test", 20)
    assert len(out) == 2
    assert {row.cloud_type for row in out} == {"quark", "baidu"}
    assert all(row.link.startswith("https://") for row in out)


@pytest.mark.asyncio
async def test_pansou_drops_plain_text_rows_without_real_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
                            {
                                "unique_id": "u1",
                                "title": "Plain Text",
                                "content": "这是一段没有任何网盘链接的介绍文本",
                                "links": [{"url": "", "type": "other"}],
                            }
                        ]
                    },
                }
            )

    monkeypatch.setattr("app.adapters.pansou.httpx.AsyncClient", lambda **kwargs: _Client())
    out = await PanSouAdapter(_settings()).search("test", 20)
    assert out == []


@pytest.mark.asyncio
async def test_pansou_filters_results_by_configured_cloud_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_payload: dict[str, object] = {}

    class _Client:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        async def post(self, _url, json=None, headers=None):  # type: ignore[no-untyped-def]
            captured_payload.update(json or {})
            return _Resp(
                {
                    "code": 0,
                    "data": {
                        "merged_by_type": {
                            "quark": [
                                {
                                    "url": "https://pan.quark.cn/s/abc",
                                    "password": "",
                                    "note": "Only Quark",
                                    "source": "tg:movie",
                                }
                            ]
                        }
                    },
                }
            )

    monkeypatch.setattr("app.adapters.pansou.httpx.AsyncClient", lambda **kwargs: _Client())
    settings = replace(_settings(), pansou_cloud_types="quark")
    out = await PanSouAdapter(settings).search("test", 20)
    assert captured_payload["cloud_types"] == ["quark"]
    assert captured_payload["res"] == "merge"
    assert len(out) == 1
    assert out[0].cloud_type == "quark"
    assert out[0].title == "Only Quark"
    assert out[0].source_detail == "tg:movie"


@pytest.mark.asyncio
async def test_pansou_merges_ed2k_into_magnet_for_requested_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_payload: dict[str, object] = {}

    class _Client:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        async def post(self, _url, json=None, headers=None):  # type: ignore[no-untyped-def]
            captured_payload.update(json or {})
            return _Resp(
                {
                    "code": 0,
                    "data": {
                        "merged_by_type": {
                            "115": [
                                {
                                    "url": "https://115.com/s/abc",
                                    "password": "",
                                    "note": "115 Result",
                                }
                            ],
                            "ed2k": [
                                {
                                    "url": "ed2k://|file|demo.mkv|123|HASH|/",
                                    "password": "",
                                    "note": "ed2k Result",
                                }
                            ],
                        }
                    },
                }
            )

    monkeypatch.setattr("app.adapters.pansou.httpx.AsyncClient", lambda **kwargs: _Client())
    settings = replace(_settings(), pansou_cloud_types="115,magnet,ed2k")
    out = await PanSouAdapter(settings).search("test", 20)
    assert captured_payload["cloud_types"] == ["115", "magnet"]
    assert captured_payload["res"] == "merge"
    assert [row.cloud_type for row in out] == ["115", "magnet"]
    assert out[1].magnet is None
    assert out[1].link.startswith("ed2k://")


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
async def test_search_service_caps_prowlarr_limit() -> None:
    captured: dict[str, tuple[str, int]] = {}
    settings = _settings()
    settings.pansou_search_limit = 321
    settings.prowlarr_search_limit = 45

    class _PanSou:
        def __init__(self, settings: ProviderSettings) -> None:
            self.settings = settings

        async def search(self, keyword: str, limit: int) -> list[SearchResultItem]:
            captured["pansou"] = (keyword, limit)
            return []

    class _Prowlarr:
        def __init__(self, settings: ProviderSettings) -> None:
            self.settings = settings

        async def search(self, keyword: str, limit: int) -> list[SearchResultItem]:
            captured["prowlarr"] = (keyword, limit)
            return []

    svc = SearchService(_PanSou(settings), _Prowlarr(settings), _FakeTMDB())  # type: ignore[arg-type]
    out = await svc.search("req-1", "蜘蛛侠", 20)

    assert out.total == 0
    assert captured["pansou"] == ("蜘蛛侠", 321)
    assert captured["prowlarr"] == ("蜘蛛侠", 45)


@pytest.mark.asyncio
async def test_search_service_omits_provider_limit_when_search_caps_disabled() -> None:
    captured: dict[str, tuple[str, int | None]] = {}
    settings = _settings()
    settings.pansou_search_limit_enabled = False
    settings.prowlarr_search_limit_enabled = False

    class _PanSou:
        def __init__(self, settings: ProviderSettings) -> None:
            self.settings = settings

        async def search(self, keyword: str, limit: int | None) -> list[SearchResultItem]:
            captured["pansou"] = (keyword, limit)
            return []

    class _Prowlarr:
        def __init__(self, settings: ProviderSettings) -> None:
            self.settings = settings

        async def search(self, keyword: str, limit: int | None) -> list[SearchResultItem]:
            captured["prowlarr"] = (keyword, limit)
            return []

    class _TMDBMustNotRun:
        async def enrich(self, _title: str) -> dict[str, object]:
            raise AssertionError("tmdb enrich should not run after search")

    svc = SearchService(_PanSou(settings), _Prowlarr(settings), _TMDBMustNotRun())  # type: ignore[arg-type]
    out = await svc.search("req-2", "蜘蛛侠", 77)

    assert out.total == 0
    assert captured["pansou"] == ("蜘蛛侠", None)
    assert captured["prowlarr"] == ("蜘蛛侠", None)


@pytest.mark.asyncio
async def test_task_service_resolves_prowlarr_download_url_on_offline_create() -> None:
    settings = _settings()
    settings.c115_cookie = "cookie"
    captured: dict[str, str] = {}

    class _C115:
        def make_idempotency_key(self, source_uri: str, target_dir_id: str) -> str:
            captured["idem_source"] = source_uri
            return f"{source_uri}|{target_dir_id}"

        async def create_offline_task(self, source_uri: str, target_dir_id: str) -> str:
            captured["offline_source"] = source_uri
            captured["offline_target"] = target_dir_id
            return "task-123"

    class _Quark:
        async def save_shared_file(self, source_uri: str, target_dir_id: str) -> str:
            raise AssertionError("should not call quark")

    class _Prowlarr:
        async def resolve_download_url(self, source_uri: str) -> str | None:
            captured["resolve_source"] = source_uri
            return "magnet:?xt=urn:btih:ABC123"

    svc = TaskService(
        _C115(),  # type: ignore[arg-type]
        _Quark(),  # type: ignore[arg-type]
        _Prowlarr(),  # type: ignore[arg-type]
        settings,
        ResourceFilterService(settings),
    )
    out = await svc.create_offline_task(
        "req-1",
        "http://localhost:9696/15/download?x=1",
        "0",
        "magnet",
    )

    assert out.task_id == "task-123"
    assert captured["resolve_source"] == "http://localhost:9696/15/download?x=1"
    assert captured["idem_source"] == "magnet:?xt=urn:btih:ABC123"
    assert captured["offline_source"] == "magnet:?xt=urn:btih:ABC123"


@pytest.mark.asyncio
async def test_task_service_rejects_unresolved_prowlarr_download_url() -> None:
    settings = _settings()
    settings.c115_cookie = "cookie"

    class _C115:
        def make_idempotency_key(self, source_uri: str, target_dir_id: str) -> str:
            return f"{source_uri}|{target_dir_id}"

        async def create_offline_task(self, source_uri: str, target_dir_id: str) -> str:
            raise AssertionError("should not reach 115")

    class _Quark:
        async def save_shared_file(self, source_uri: str, target_dir_id: str) -> str:
            raise AssertionError("should not call quark")

    class _Prowlarr:
        async def resolve_download_url(self, source_uri: str) -> str | None:
            return None

    svc = TaskService(
        _C115(),  # type: ignore[arg-type]
        _Quark(),  # type: ignore[arg-type]
        _Prowlarr(),  # type: ignore[arg-type]
        settings,
        ResourceFilterService(settings),
    )

    with pytest.raises(Exception) as exc:
        await svc.create_offline_task(
            "req-1",
            "http://localhost:9696/15/download?x=1",
            "0",
            "magnet",
        )
    assert "Prowlarr 下载链接解析磁力失败" in str(exc.value)


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


@pytest.mark.asyncio
async def test_c115_delete_files_falls_back_to_app_sdk_on_405(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, list[str]]] = []

    class _Client:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def fs_delete(self, payload):  # type: ignore[no-untyped-def]
            batch = list(payload)
            calls.append(("web", batch))
            raise RuntimeError("115 risk control 405")

        def fs_delete_app(self, payload):  # type: ignore[no-untyped-def]
            batch = list(payload)
            calls.append(("app", batch))
            return {"state": True}

    monkeypatch.setitem(sys.modules, "p115client", types.SimpleNamespace(P115Client=_Client))
    settings = _settings()
    settings.c115_cookie = "cookie"
    deleted = await C115Adapter(settings).delete_files(["1", "2"])
    assert deleted == 2
    assert calls == [("web", ["1", "2"]), ("app", ["1", "2"])]


@pytest.mark.asyncio
async def test_c115_delete_files_http_fallback_retries_comma_payload_after_405(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "p115client", None)

    class _Resp405:
        status_code = 405
        text = "blocked"

        def json(self):  # type: ignore[no-untyped-def]
            raise ValueError("non-json")

    class _RespOk:
        status_code = 200
        text = '{"state": true}'

        def json(self):  # type: ignore[no-untyped-def]
            return {"state": True}

    class _Client:
        def __init__(self) -> None:
            self.payloads: list[dict[str, str]] = []

        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        async def post(self, _url, headers=None, data=None):  # type: ignore[no-untyped-def]
            assert isinstance(data, dict)
            self.payloads.append(data)
            if "fid[0]" in data:
                return _Resp405()
            return _RespOk()

    fake = _Client()
    monkeypatch.setattr("app.adapters.c115.httpx.AsyncClient", lambda **kwargs: fake)
    settings = _settings()
    settings.c115_cookie = "cookie"
    deleted = await C115Adapter(settings).delete_files(["10", "20"])
    assert deleted == 2
    assert fake.payloads[0] == {"fid[0]": "10", "fid[1]": "20"}
    assert fake.payloads[1] == {"fid": "10,20"}


@pytest.mark.asyncio
async def test_c115_delete_files_chunks_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    class _Client:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def fs_delete(self, payload):  # type: ignore[no-untyped-def]
            batch = list(payload)
            calls.append(batch)
            return {"state": True}

        def fs_delete_app(self, payload):  # type: ignore[no-untyped-def]
            raise AssertionError("app fallback should not be used")

    monkeypatch.setitem(sys.modules, "p115client", types.SimpleNamespace(P115Client=_Client))
    monkeypatch.setattr(C115Adapter, "_delete_batch_size", 2)
    settings = _settings()
    settings.c115_cookie = "cookie"
    deleted = await C115Adapter(settings).delete_files(["1", "2", "3", "4", "5"])
    assert deleted == 5
    assert calls == [["1", "2"], ["3", "4"], ["5"]]
