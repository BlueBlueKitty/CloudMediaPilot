from __future__ import annotations

from hashlib import sha256
import logging
import re
from urllib.parse import parse_qs, urlparse

import httpx

from app.core.config import ProviderSettings
from app.core.errors import AuthError, ProviderError, ValidationError
from app.schemas.models import C115DirAncestor, C115DirItem, PublicTaskState

logger = logging.getLogger("provider.115")


class C115Adapter:
    name = "115"

    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    def _ensure_allowed(self, action: str) -> None:
        if action not in self.settings.allowed_actions:
            raise ValidationError(
                "C115_ACTION_NOT_ALLOWED", f"action '{action}' is not allowed", 403
            )

    def _try_p115client_add(self, source_uri: str, target_dir_id: str) -> str | None:
        try:
            from p115client import P115Client

            client = P115Client(self.settings.c115_cookie, check_for_relogin=False)
            info_hash = self._extract_magnet_hash(source_uri)
            if info_hash:
                payload = {"info_hash": info_hash, "wp_path_id": target_dir_id}
                resp = client.offline_add_torrent(payload, type="ssp")
                data = resp if isinstance(resp, dict) else {}
                nested_raw = data.get("data")
                nested = nested_raw if isinstance(nested_raw, dict) else {}
                if data.get("state") is True:
                    task_id = data.get("task_id") or nested.get("task_id") or nested.get("info_hash") or info_hash
                    return str(task_id)
                if str(data.get("errcode") or nested.get("errcode")) == "10008":
                    return str(nested.get("info_hash") or data.get("info_hash") or info_hash)

            payload = {"url": source_uri, "wp_path_id": target_dir_id}
            resp = client.offline_add_url(payload, type="ssp")
            data = resp if isinstance(resp, dict) else {}
            nested_raw = data.get("data")
            nested = nested_raw if isinstance(nested_raw, dict) else {}

            if data.get("state") is True:
                task_id = data.get("task_id") or nested.get("task_id") or nested.get("info_hash")
                return str(task_id) if task_id else None

            if str(data.get("errcode") or nested.get("errcode")) == "10008":
                info_hash = nested.get("info_hash") or data.get("info_hash")
                return str(info_hash) if info_hash else None
            return None
        except Exception:  # noqa: BLE001
            return None

    def _try_p115client_list(self) -> list[dict] | None:
        try:
            from p115client import P115Client

            client = P115Client(self.settings.c115_cookie, check_for_relogin=False)
            resp = client.offline_list({"page": 1})
            data = resp if isinstance(resp, dict) else {}
            if data.get("state") is False and str(data.get("errcode")) not in {"0", ""}:
                return None
            tasks = data.get("tasks") or data.get("data", {}).get("tasks") or []
            return tasks if isinstance(tasks, list) else None
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _json_or_error(resp: httpx.Response) -> dict:
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "115_upstream_non_json status=%s body=%s",
                resp.status_code,
                resp.text[:300],
            )
            raise ProviderError(
                "C115_UPSTREAM_ERROR",
                f"115 返回非 JSON 响应：{resp.text[:120]}",
                502,
            ) from exc
        if not isinstance(data, dict):
            raise ProviderError("C115_UPSTREAM_ERROR", "115 response is not object", 502)
        return data

    def make_idempotency_key(self, source_uri: str, target_dir_id: str) -> str:
        return sha256(f"{source_uri}|{target_dir_id}".encode()).hexdigest()

    @staticmethod
    def _extract_magnet_hash(source_uri: str) -> str | None:
        if not source_uri.startswith("magnet:"):
            return None
        parsed = urlparse(source_uri)
        values = parse_qs(parsed.query).get("xt") or []
        for value in values:
            prefix = "urn:btih:"
            if value.lower().startswith(prefix):
                raw = value[len(prefix) :].strip()
                if re.fullmatch(r"[A-Fa-f0-9]{40}", raw):
                    return raw.upper()
                if re.fullmatch(r"[A-Za-z2-7]{32}", raw):
                    return raw.upper()
        return None

    def _validate_source(self, source_uri: str) -> None:
        if not (
            source_uri.startswith("magnet:")
            or source_uri.startswith("https://")
            or source_uri.startswith("http://")
        ):
            raise ValidationError(
                "C115_INVALID_SOURCE",
                "source_uri must start with magnet:, https://, or http://",
                400,
            )

    def _offline_url(self, path: str) -> str:
        raw = (path or "").strip()
        if raw.startswith("http://") or raw.startswith("https://"):
            return raw
        base = self.settings.c115_base_url.rstrip("/")
        return f"{base}{raw}"

    def _offline_add_url_candidates(self) -> list[str]:
        # Some 115 nodes behave differently across offline endpoints.
        # Keep configured path first, then try known-compatible fallbacks.
        candidates = [
            self.settings.c115_offline_add_path,
            "/web/lixian/?ct=lixian&ac=add_task_url",
            "/web/lixian/?ac=add_task_url",
            "/lixianssp/?ac=add_task_url",
        ]
        out: list[str] = []
        for path in candidates:
            url = self._offline_url(path)
            if url not in out:
                out.append(url)
        return out

    def _offline_add_bt_candidates(self) -> list[str]:
        candidates = [
            "/lixianssp/?ac=add_task_bt",
            "/web/lixian/?ct=lixian&ac=add_task_bt",
            "/web/lixian/?ac=add_task_bt",
        ]
        out: list[str] = []
        for path in candidates:
            url = self._offline_url(path)
            if url not in out:
                out.append(url)
        return out

    @staticmethod
    def _parse_share_link(source_uri: str) -> tuple[str, str]:
        parsed = urlparse(source_uri)
        code = ""
        for pattern in (r"/s/([A-Za-z0-9]+)", r"share/([A-Za-z0-9]+)"):
            match = re.search(pattern, parsed.path)
            if match:
                code = match.group(1)
                break
        if not code:
            raise ValidationError("C115_INVALID_SHARE", "invalid 115 share link", 400)
        qs = parse_qs(parsed.query or "")
        receive = (
            (qs.get("password") or qs.get("pwd") or qs.get("receive_code") or [""])[0]
            .strip()
        )
        return code, receive

    async def create_offline_task(self, source_uri: str, target_dir_id: str) -> str:
        self._ensure_allowed("create_offline_task")
        self._validate_source(source_uri)
        if self.settings.use_mock:
            return self.make_idempotency_key(source_uri, target_dir_id)[:16]

        if not self.settings.c115_cookie:
            raise AuthError("C115_AUTH_INVALID", "missing 115 cookie", 401)

        task_from_sdk = self._try_p115client_add(source_uri, target_dir_id)
        if task_from_sdk:
            return task_from_sdk

        headers = {
            "Cookie": self.settings.c115_cookie,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
        }
        info_hash = self._extract_magnet_hash(source_uri)
        attempts: list[tuple[str, dict[str, str], str]] = []
        if info_hash:
            for bt_url in self._offline_add_bt_candidates():
                attempts.append(
                    (
                        bt_url,
                        {
                            "info_hash": info_hash,
                            "wp_path_id": target_dir_id,
                        },
                        "add_task_bt",
                    )
                )
        for add_url in self._offline_add_url_candidates():
            attempts.append(
                (
                    add_url,
                    {
                        "url": source_uri,
                        # 115 expects folder path text in savepath; passing dir-id can cause
                        # odd numeric folder naming. Use wp_path_id only.
                        "wp_path_id": target_dir_id,
                    },
                    "add_task_url",
                )
            )
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                last_error: Exception | None = None
                for idx, (url, payload, mode) in enumerate(attempts):
                    has_next = idx < len(attempts) - 1
                    resp = await client.post(url, headers=headers, data=payload)
                    try:
                        data = self._json_or_error(resp)
                    except ProviderError as exc:
                        # Some nodes return plain "decode fail!" for certain endpoints.
                        # Retry next known endpoint before failing.
                        if has_next and "decode fail" in str(exc.message).lower():
                            logger.warning("115_add_task_decode_fail_fallback mode=%s url=%s", mode, url)
                            last_error = exc
                            continue
                        raise
                    if resp.status_code == 401 or data.get("errno") in {99, 911, 20004}:
                        raise AuthError("C115_AUTH_INVALID", "115 cookie invalid or expired", 401)
                    if data.get("state") is False:
                        if has_next:
                            last_error = ProviderError(
                                "C115_UPSTREAM_ERROR",
                                f"115 add task error: {data.get('error_msg') or data.get('error')}",
                                502,
                            )
                            logger.warning(
                                "115_add_task_failed_fallback mode=%s url=%s error=%s",
                                mode,
                                url,
                                last_error,
                            )
                            continue
                        raise ProviderError(
                            "C115_UPSTREAM_ERROR",
                            f"115 error: {data.get('error_msg') or data.get('error')}",
                            502,
                        )
                    task_id = str(data.get("task_id") or data.get("info_hash") or data.get("id") or "")
                    if not task_id:
                        task_id = self.make_idempotency_key(source_uri, target_dir_id)[:16]
                    return task_id
            if last_error:
                raise last_error
            raise ProviderError("C115_UPSTREAM_ERROR", "115 create task failed with empty result", 502)
        except AuthError:
            raise
        except ValidationError:
            raise
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                "C115_UPSTREAM_ERROR", f"115 create task failed: {exc}", 502
            ) from exc

    async def query_task(self, task_id: str) -> tuple[PublicTaskState, str | None]:
        if self.settings.use_mock:
            return "completed", None
        if not self.settings.c115_cookie:
            raise AuthError("C115_AUTH_INVALID", "missing 115 cookie", 401)

        tasks_from_sdk = self._try_p115client_list()
        if tasks_from_sdk is not None:
            tasks = tasks_from_sdk
        else:
            headers = {"Cookie": self.settings.c115_cookie}
            url = f"{self.settings.c115_base_url}{self.settings.c115_offline_list_path}"
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                resp = await client.get(url, headers=headers)
            data = self._json_or_error(resp)
            tasks = data.get("tasks") or data.get("data", {}).get("tasks") or []
        try:
            for item in tasks:
                cur = str(item.get("info_hash") or item.get("task_id") or "")
                if cur == task_id:
                    st = item.get("status")
                    if st in (2, "2", "completed"):
                        return "completed", None
                    if st in (1, "1", "running"):
                        return "running", None
                    return "queued", None
            return "queued", "not found from upstream list, fallback queued"
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                "C115_UPSTREAM_ERROR", f"115 query task failed: {exc}", 502
            ) from exc

    async def check(self) -> tuple[bool, str]:
        if self.settings.use_mock:
            return True, "mock_ok"
        if not self.settings.c115_cookie:
            return False, "missing_cookie"
        try:
            tasks_from_sdk = self._try_p115client_list()
            if tasks_from_sdk is not None:
                return True, "ok"
            headers = {"Cookie": self.settings.c115_cookie}
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                resp = await client.get(
                    f"{self.settings.c115_base_url}{self.settings.c115_offline_list_path}",
                    headers=headers,
                )
            if resp.status_code == 401:
                return False, "auth_invalid"
            try:
                data = resp.json()
            except Exception:  # noqa: BLE001
                return False, f"non_json:{resp.text[:80]}"
            if isinstance(data, dict):
                if data.get("errno") in {99, 911, 20004}:
                    return False, "auth_invalid"
                if data.get("state") is False:
                    return False, str(data.get("error") or data.get("error_msg") or "state_false")
            return True, "ok"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def _parse_dir_items(self, rows: object) -> list[C115DirItem]:
        out: list[C115DirItem] = []
        if not isinstance(rows, list):
            return out
        for row in rows:
            if not isinstance(row, dict):
                continue
            ns = row.get("ns")
            ns_int = 0
            if isinstance(ns, int | float):
                ns_int = int(ns)
            elif isinstance(ns, str) and ns.isdigit():
                ns_int = int(ns)
            is_dir = bool(
                row.get("is_dir")
                or row.get("is_directory")
                or ns_int > 0
                or (row.get("fid") in {None, "", 0, "0"} and row.get("cid"))
            )
            cid = row.get("cid") or row.get("id") or row.get("fid") or row.get("file_id")
            name = row.get("n") or row.get("name") or row.get("file_name")
            if not is_dir or not cid:
                continue
            out.append(C115DirItem(id=str(cid), name=str(name or cid), is_dir=True))
        return out

    @staticmethod
    def _parse_dir_ancestors(
        path_items: object, current_id: str, parent_path: str
    ) -> list[C115DirAncestor]:
        ancestors = [C115DirAncestor(id="0", path="/")]
        if not isinstance(path_items, list):
            return ancestors if current_id in {"", "0"} else [
                *ancestors,
                C115DirAncestor(id=str(current_id), path=parent_path or "/"),
            ]

        parts: list[str] = []
        seen = {"0"}
        for row in path_items:
            if not isinstance(row, dict):
                continue
            cid = row.get("cid") or row.get("id") or row.get("file_id") or row.get("fid")
            name = str(row.get("name") or row.get("n") or "").strip("/")
            if name:
                parts.append(name)
            if cid in {None, "", 0, "0"}:
                continue
            cid_text = str(cid)
            if cid_text in seen:
                continue
            path = "/" + "/".join(parts).strip("/")
            ancestors.append(C115DirAncestor(id=cid_text, path=path or "/"))
            seen.add(cid_text)

        current_id_text = str(current_id or "0")
        if current_id_text not in seen:
            ancestors.append(C115DirAncestor(id=current_id_text, path=parent_path or "/"))
        return ancestors

    def _try_p115client_dirs(
        self, parent_id: str
    ) -> tuple[str, list[C115DirAncestor], list[C115DirItem]] | None:
        try:
            from p115client import P115Client

            client = P115Client(self.settings.c115_cookie, check_for_relogin=False)
            if hasattr(client, "fs_files"):
                resp = client.fs_files({"cid": parent_id, "show_dir": 1, "offset": 0, "limit": 200})
                data = resp if isinstance(resp, dict) else {}
                path = data.get("path") or []
                if isinstance(path, list) and path:
                    parent_path = "/" + "/".join(
                        str(x.get("name") or "")
                        for x in path
                        if isinstance(x, dict)
                    ).strip("/")
                else:
                    parent_path = "/"
                ancestors = self._parse_dir_ancestors(path, parent_id, parent_path)
                items = self._parse_dir_items(data.get("data") or data.get("files") or [])
                return parent_path, ancestors, items
        except Exception:  # noqa: BLE001
            return None
        return None

    async def list_dirs(
        self, parent_id: str = "0"
    ) -> tuple[str, list[C115DirAncestor], list[C115DirItem]]:
        if self.settings.use_mock:
            if parent_id == "0":
                return "/", [C115DirAncestor(id="0", path="/")], [
                    C115DirItem(id="100", name="媒体"),
                    C115DirItem(id="200", name="下载"),
                ]
            if parent_id == "100":
                return "/媒体", [
                    C115DirAncestor(id="0", path="/"),
                    C115DirAncestor(id="100", path="/媒体"),
                ], [
                    C115DirItem(id="101", name="movie"),
                    C115DirItem(id="102", name="tv"),
                ]
            return "/下载", [
                C115DirAncestor(id="0", path="/"),
                C115DirAncestor(id=str(parent_id), path="/下载"),
            ], [C115DirItem(id="201", name="离线任务")]
        if not self.settings.c115_cookie:
            raise AuthError("C115_AUTH_INVALID", "missing 115 cookie", 401)

        sdk_data = self._try_p115client_dirs(parent_id)
        if sdk_data is not None:
            return sdk_data

        headers = {"Cookie": self.settings.c115_cookie}
        params = {
            "aid": 1,
            "cid": parent_id,
            "o": "user_ptime",
            "asc": 1,
            "offset": 0,
            "limit": 200,
            "show_dir": 1,
            "type": 0,
            "format": "json",
            "star": 0,
            "suffix": "",
            "natsort": 0,
            "snap": 0,
            "record_open_time": 1,
            "fc_mix": 0,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                resp = await client.get(
                    "https://webapi.115.com/files",
                    params=params,
                    headers=headers,
                )
            if resp.status_code == 401:
                raise AuthError("C115_AUTH_INVALID", "115 cookie invalid or expired", 401)
            data = self._json_or_error(resp)
            if data.get("state") is False and data.get("errno") in {99, 911, 20004}:
                raise AuthError("C115_AUTH_INVALID", "115 cookie invalid or expired", 401)
            path_items = data.get("path") or []
            if isinstance(path_items, list) and path_items:
                parent_path = "/" + "/".join(
                    str(x.get("name") or "")
                    for x in path_items
                    if isinstance(x, dict)
                ).strip("/")
            else:
                parent_path = "/"
            ancestors = self._parse_dir_ancestors(path_items, parent_id, parent_path)
            items = self._parse_dir_items(data.get("data") or data.get("files") or [])
            return parent_path, ancestors, items
        except AuthError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("C115_UPSTREAM_ERROR", f"115 list dirs failed: {exc}", 502) from exc

    async def list_share_items(self, source_uri: str, parent_id: str = "") -> list[dict]:
        share_code, receive_code = self._parse_share_link(source_uri)
        if self.settings.use_mock:
            if parent_id == "m-folder":
                return [
                    {"id": "m1", "name": "电影A.mkv", "size": 12 * 1024 * 1024 * 1024, "is_dir": False},
                    {"id": "m2", "name": "字幕.ass", "size": 128 * 1024, "is_dir": False},
                ]
            return [{"id": "m-folder", "name": "电影合集", "size": None, "is_dir": True}]
        if not self.settings.c115_cookie:
            raise AuthError("C115_AUTH_INVALID", "missing 115 cookie", 401)
        headers = {"Cookie": self.settings.c115_cookie}
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                resp = await client.get(
                    "https://webapi.115.com/share/snap",
                    params={
                        "share_code": share_code,
                        "receive_code": receive_code,
                        "offset": 0,
                        "limit": 100,
                        "cid": parent_id or "",
                    },
                    headers=headers,
                )
            resp.raise_for_status()
            data = self._json_or_error(resp)
            rows = ((data.get("data") or {}).get("list") if isinstance(data, dict) else None) or []
            out: list[dict] = []
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    ns = row.get("ns")
                    ns_int = int(ns) if isinstance(ns, int | float) or (isinstance(ns, str) and ns.isdigit()) else 0
                    is_dir = bool(
                        ns_int > 0
                        or row.get("is_dir")
                        or row.get("is_directory")
                        or (row.get("fid") in {None, "", 0, "0"} and row.get("cid"))
                    )
                    fid = str((row.get("cid") if is_dir else row.get("fid")) or row.get("cid") or "").strip()
                    name = str(row.get("n") or row.get("name") or "").strip()
                    if not fid or not name:
                        continue
                    size_raw = row.get("s")
                    size = int(size_raw) if isinstance(size_raw, int | float) else None
                    out.append({"id": fid, "name": name, "size": size, "is_dir": is_dir})
            return out
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("C115_UPSTREAM_ERROR", f"115 list share items failed: {exc}", 502) from exc

    async def save_share_items(
        self, source_uri: str, target_dir_id: str, selected_ids: list[str]
    ) -> str:
        share_code, receive_code = self._parse_share_link(source_uri)
        if self.settings.use_mock:
            return self.make_idempotency_key(source_uri, target_dir_id)[:16]
        if not self.settings.c115_cookie:
            raise AuthError("C115_AUTH_INVALID", "missing 115 cookie", 401)
        ids = selected_ids or [row["id"] for row in await self.list_share_items(source_uri)]
        if not ids:
            raise ValidationError("C115_SHARE_EMPTY", "分享内容为空", 400)
        headers = {
            "Cookie": self.settings.c115_cookie,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        last_task = ""
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.request_timeout_seconds,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                for fid in ids:
                    payload = {
                        "cid": target_dir_id or "0",
                        "share_code": share_code,
                        "receive_code": receive_code,
                        "file_id": fid,
                    }
                    resp = await client.post(
                        "https://webapi.115.com/share/receive",
                        headers=headers,
                        data=payload,
                    )
                    resp.raise_for_status()
                    body = self._json_or_error(resp)
                    if body.get("state") is False:
                        raise ProviderError(
                            "C115_UPSTREAM_ERROR",
                            str(body.get("error") or body.get("error_msg") or "save share failed"),
                            502,
                        )
                    last_task = str(body.get("id") or body.get("task_id") or fid)
            return last_task or self.make_idempotency_key(source_uri, target_dir_id)[:16]
        except (ProviderError, ValidationError, AuthError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("C115_UPSTREAM_ERROR", f"115 save share failed: {exc}", 502) from exc
