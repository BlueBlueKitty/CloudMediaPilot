#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath("backend"))
from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


def must(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"[FAIL] {msg}")


def run_mock(client: TestClient) -> None:
    must(client.get("/health").status_code == 200, "health")
    must(client.get("/ready").status_code == 200, "ready")
    s = client.post("/search", json={"keyword": "test", "limit": 5})
    must(s.status_code == 200, "search")
    t = client.post(
        "/tasks/offline", json={"source_uri": "magnet:?xt=urn:btih:SMOKE", "target_dir_id": "0"}
    )
    must(t.status_code == 200 and bool(t.json().get("task_id")), "task create with task_id")
    task_id = t.json()["task_id"]
    g = client.get(f"/tasks/{task_id}")
    must(g.status_code == 200, "task query")


def run_connectivity(client: TestClient) -> None:
    must(client.get("/health").status_code == 200, "health")
    r = client.get("/providers/status")
    must(r.status_code == 200, "providers status")
    providers = r.json().get("providers", [])
    must(bool(providers), "providers list not empty")
    names = {x.get("name"): x.get("ok") for x in providers}
    must("pansou" in names and "prowlarr" in names and "tmdb" in names and "c115" in names, "provider names")


def run_action(client: TestClient) -> None:
    settings = get_settings()
    if not settings.c115_cookie:
        raise SystemExit("[FAIL] missing CMP_C115_COOKIE for smoke-real-action")

    source_uri = os.getenv(
        "CMP_SMOKE_SOURCE_URI",
        "magnet:?xt=urn:btih:4a3f5e08bcef825718eda30637230585e3330599"
        "&dn=ubuntu-24.04.1-desktop-amd64.iso",
    )
    must(bool(source_uri), "source uri exists")

    payload = {"source_uri": source_uri, "target_dir_id": "0"}
    t1 = client.post("/tasks/offline", json=payload)
    must(t1.status_code == 200, "task create")
    task_id = t1.json().get("task_id")
    must(bool(task_id), "task_id exists")

    g = client.get(f"/tasks/{task_id}")
    must(g.status_code == 200, "task query")
    status = g.json().get("status")
    must(status in {"queued", "running", "completed", "failed"}, "task status readable")

    t2 = client.post("/tasks/offline", json=payload)
    must(t2.status_code == 200 and t2.json().get("existing_task") is True, "idempotency replay")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "mock"
    client = TestClient(app)
    if mode == "mock":
        run_mock(client)
    elif mode == "connectivity":
        run_connectivity(client)
    elif mode == "action":
        run_action(client)
    else:
        raise SystemExit(f"unknown mode: {mode}")
    print(f"[OK] smoke-{mode}")


if __name__ == "__main__":
    main()
