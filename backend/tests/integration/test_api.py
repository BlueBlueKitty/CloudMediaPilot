from pathlib import Path

from app.core.config import get_settings
from app.core.deps import get_app_config_store
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _reset_runtime_config_db() -> None:
    get_settings.cache_clear()
    get_app_config_store.cache_clear()


def _prepare_config_db(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / "config" / ".env"
    monkeypatch.setenv("CONFIG_ENV_PATH", str(env_path))
    monkeypatch.setenv("CMP_USE_MOCK", "true")
    _reset_runtime_config_db()


def _login() -> None:
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200


def test_health_ready() -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200


def test_tmdb_search_resources_and_task_roundtrip(monkeypatch, tmp_path) -> None:
    _prepare_config_db(monkeypatch, tmp_path)
    _login()

    tm = client.get("/tmdb/search", params={"query": "fight club", "limit": 5})
    assert tm.status_code == 200
    tm_data = tm.json()
    assert tm_data["total"] >= 1

    sr = client.post("/search", json={"keyword": "fight club", "limit": 5})
    assert sr.status_code == 200
    sdata = sr.json()
    assert sdata["total"] >= 1

    tr = client.post(
        "/tasks/offline",
        json={"source_uri": "magnet:?xt=urn:btih:ABCDE", "target_dir_id": "0"},
    )
    assert tr.status_code == 200
    tdata = tr.json()
    assert tdata["task_id"]

    gr = client.get(f"/tasks/{tdata['task_id']}")
    assert gr.status_code == 200
    gdata = gr.json()
    assert gdata["status"] in {"queued", "running", "completed", "failed"}

    ls = client.get("/tasks", params={"limit": 10})
    assert ls.status_code == 200
    assert ls.json()["total"] >= 1


def test_idempotency_replay(monkeypatch, tmp_path) -> None:
    _prepare_config_db(monkeypatch, tmp_path)
    _login()

    payload = {"source_uri": "magnet:?xt=urn:btih:SAME", "target_dir_id": "0"}
    r1 = client.post("/tasks/offline", json=payload)
    r2 = client.post("/tasks/offline", json=payload)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["task_id"] == r2.json()["task_id"]
    assert r2.json()["existing_task"] is True


def test_offline_task_uses_default_target_dir_from_settings(monkeypatch, tmp_path) -> None:
    _prepare_config_db(monkeypatch, tmp_path)
    _login()
    client.put("/settings", json={"c115_target_dir_id": "12345"})

    source_uri = "magnet:?xt=urn:btih:DEFAULT-DIR"
    r = client.post("/tasks/offline", json={"source_uri": source_uri})
    assert r.status_code == 200
    task_id = r.json()["task_id"]

    # mock mode下 task_id 来自 source + target 的哈希，显式目录应产生不同ID
    r_explicit = client.post(
        "/tasks/offline",
        json={"source_uri": source_uri, "target_dir_id": "0"},
    )
    assert r_explicit.status_code == 200
    assert r_explicit.json()["task_id"] != task_id

    r2 = client.post("/tasks/offline", json={"source_uri": source_uri})
    assert r2.status_code == 200
    assert r2.json()["task_id"] == task_id
    assert r2.json()["existing_task"] is True


def test_transfer_share_items_can_be_browsed_recursively(monkeypatch, tmp_path) -> None:
    _prepare_config_db(monkeypatch, tmp_path)
    _login()

    source_uri = "https://115.com/s/mockcode?password=abcd"
    root = client.post(
        "/transfer/prepare",
        json={"source_uri": source_uri, "cloud_type": "115"},
    )
    assert root.status_code == 200
    root_items = root.json()["items"]
    assert root_items
    assert root_items[0]["is_dir"] is True

    child = client.post(
        "/transfer/items",
        json={
            "source_uri": source_uri,
            "cloud_type": "115",
            "parent_id": root_items[0]["id"],
        },
    )
    assert child.status_code == 200
    child_items = child.json()["items"]
    assert child_items
    assert all(item["is_dir"] is False for item in child_items)


def test_storage_dirs_returns_ancestors_for_saved_child_dir(monkeypatch, tmp_path) -> None:
    _prepare_config_db(monkeypatch, tmp_path)
    _login()

    response = client.get("/storage/dirs", params={"provider": "115", "parent_id": "100"})

    assert response.status_code == 200
    data = response.json()
    assert data["parent_path"] == "/媒体"
    assert data["ancestors"] == [
        {"id": "0", "path": "/"},
        {"id": "100", "path": "/媒体"},
    ]


def test_settings_masked_and_update(monkeypatch, tmp_path) -> None:
    _prepare_config_db(monkeypatch, tmp_path)
    _login()

    g1 = client.get("/settings")
    assert g1.status_code == 200
    assert g1.json()["has_tmdb_api_key"] is False

    upd = client.put(
        "/settings",
        json={
            "tmdb_base_url": "https://api.themoviedb.org/3",
            "tmdb_api_key": "abcd1234",
            "prowlarr_base_url": "http://localhost:9696",
            "prowlarr_api_key": "pkey0001",
            "pansou_base_url": "http://localhost:805",
            "c115_base_url": "https://lixian.115.com",
            "c115_cookie": "cookie-sample-ijkl",
            "c115_allowed_actions": "create_offline_task",
            "c115_target_dir_id": "0",
            "c115_offline_add_path": "/lixianssp/?ac=add_task_url",
            "c115_offline_list_path": "/web/lixian/?ac=task_lists",
        },
    )
    assert upd.status_code == 200
    data = upd.json()
    assert data["has_tmdb_api_key"] is True
    assert data["tmdb_api_key_masked"].endswith("1234")
    assert data["tmdb_api_key_masked"] != "abcd1234"
    assert data["has_c115_cookie"] is True
    assert data["c115_cookie_masked"].endswith("ijkl")

    test = client.post("/settings/test", json={"provider": "all"})
    assert test.status_code == 200
    assert len(test.json()["results"]) == 7


def test_transfer_commit_skips_filtered_share_files(monkeypatch, tmp_path) -> None:
    _prepare_config_db(monkeypatch, tmp_path)
    _login()

    async def fake_tree(self, source_uri, selected_ids=None):  # type: ignore[no-untyped-def]
        return [
            {"id": "f1", "name": "正片.mkv", "path": "/正片.mkv", "size": 100 * 1024 * 1024, "is_dir": False},
            {
                "id": "f2",
                "name": "电影港 地址发布页 www.dygang.me 收藏不迷路.txt",
                "path": "/电影港 地址发布页 www.dygang.me 收藏不迷路.txt",
                "size": 16,
                "is_dir": False,
            },
        ]

    async def fake_save(self, source_uri, target_dir_id, selected_ids):  # type: ignore[no-untyped-def]
        assert selected_ids == ["f1"]
        return "save-1"

    monkeypatch.setattr("app.adapters.c115.C115Adapter.list_share_tree", fake_tree)
    monkeypatch.setattr("app.adapters.c115.C115Adapter.save_share_items", fake_save)

    response = client.post(
        "/transfer/commit",
        json={
            "source_uri": "https://115.com/s/mockcode?password=abcd",
            "target_dir_id": "0",
            "selected_ids": [],
            "cloud_type": "115",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == "save-1"
    assert data["kept_count"] == 1
    assert data["skipped_count"] == 1
    assert data["skipped_rules_summary"]


def test_cleanup_preview_and_execute_local(monkeypatch, tmp_path) -> None:
    _prepare_config_db(monkeypatch, tmp_path)
    _login()

    root = tmp_path / "library"
    root.mkdir(parents=True, exist_ok=True)
    trash = root / "电影港 地址发布页 www.dygang.me 收藏不迷路.txt"
    keep = root / "正片.mkv"
    trash.write_text("ad", encoding="utf-8")
    keep.write_text("movie", encoding="utf-8")

    update = client.put(
        "/settings",
        json={
            "resource_cleanup_local_roots": str(root),
            "resource_filter_enabled": True,
            "resource_filter_rules": '[{"id":"txt","name":"文本","enabled":true,"glob":"*.txt","min_size_bytes":null,"max_size_bytes":null,"applies_to":"both"}]',
        },
    )
    assert update.status_code == 200

    preview = client.post("/cleanup/preview", json={"provider": "local", "local_root": str(root)})
    assert preview.status_code == 200
    preview_data = preview.json()
    assert preview_data["total_matches"] == 1
    assert preview_data["items"][0]["name"].endswith(".txt")

    execute = client.post("/cleanup/execute", json={"preview_token": preview_data["preview_token"]})
    assert execute.status_code == 200
    execute_data = execute.json()
    assert execute_data["deleted_count"] == 1
    assert not trash.exists()
    assert keep.exists()
