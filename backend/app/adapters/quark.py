from __future__ import annotations

import re
import time
from urllib.parse import urlparse

import httpx

from app.core.config import ProviderSettings
from app.core.errors import AuthError, ProviderError, ValidationError
from app.schemas.models import C115DirAncestor, C115DirItem


class QuarkAdapter:
    name = "quark"

    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    @staticmethod
    def _extract_pwd_id(source_uri: str) -> str:
        parsed = urlparse(source_uri)
        match = re.search(r"/s/([A-Za-z0-9_-]+)", parsed.path)
        if not match:
            raise ValidationError("QUARK_INVALID_LINK", "invalid quark share url", 400)
        return match.group(1)

    @staticmethod
    def _extract_passcode(source_uri: str) -> str:
        parsed = urlparse(source_uri)
        query = parsed.query or ""
        for key in ("pwd=", "passcode=", "password="):
            pos = query.find(key)
            if pos >= 0:
                return query[pos + len(key) :].split("&", 1)[0].strip()
        return ""

    @staticmethod
    def _encode_item_id(fid: str, token: str) -> str:
        return f"{fid}::{token}" if token else fid

    @staticmethod
    def _decode_item_id(item_id: str) -> tuple[str, str]:
        fid, sep, token = item_id.partition("::")
        return fid, token if sep else ""

    async def _share_context(self, source_uri: str, parent_id: str = "0") -> tuple[str, str, list[dict]]:
        pwd_id = self._extract_pwd_id(source_uri)
        passcode = self._extract_passcode(source_uri)
        parent_fid, _ = self._decode_item_id(parent_id or "0")
        headers = {
            "cookie": self.settings.quark_cookie,
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0",
        }
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            token_resp = await client.post(
                "https://drive-h.quark.cn/1/clouddrive/share/sharepage/token",
                params={"pr": "ucpro", "fr": "pc", "uc_param_str": "", "__t": int(time.time() * 1000)},
                headers=headers,
                json={"pwd_id": pwd_id, "passcode": passcode},
            )
            token_resp.raise_for_status()
            token_body = token_resp.json() if token_resp.content else {}
            stoken = (token_body.get("data") or {}).get("stoken") if isinstance(token_body, dict) else None
            if not stoken:
                raise ProviderError("QUARK_UPSTREAM_ERROR", "quark stoken missing", 502)

            detail_resp = await client.get(
                "https://drive-h.quark.cn/1/clouddrive/share/sharepage/detail",
                params={
                    "pr": "ucpro",
                    "fr": "pc",
                    "uc_param_str": "",
                    "pwd_id": pwd_id,
                    "stoken": stoken,
                    "pdir_fid": parent_fid or "0",
                    "_page": "1",
                    "_size": "200",
                    "_fetch_banner": "0",
                    "_fetch_share": "1",
                    "_fetch_total": "1",
                    "__t": int(time.time() * 1000),
                },
                headers=headers,
            )
            detail_resp.raise_for_status()
            detail_body = detail_resp.json() if detail_resp.content else {}
            rows = ((detail_body.get("data") or {}).get("list") if isinstance(detail_body, dict) else None) or []
            return pwd_id, str(stoken), rows if isinstance(rows, list) else []

    async def save_shared_file(self, source_uri: str, target_dir_id: str) -> str:
        if self.settings.use_mock:
            return f"quark-{target_dir_id or '0'}"
        if not self.settings.quark_cookie:
            raise AuthError("QUARK_AUTH_INVALID", "missing quark cookie", 401)

        pwd_id = self._extract_pwd_id(source_uri)
        headers = {
            "cookie": self.settings.quark_cookie,
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0",
        }

        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                token_resp = await client.post(
                    "https://drive-h.quark.cn/1/clouddrive/share/sharepage/token",
                    params={"pr": "ucpro", "fr": "pc", "uc_param_str": "", "__t": int(time.time() * 1000)},
                    headers=headers,
                    json={"pwd_id": pwd_id, "passcode": ""},
                )
                token_resp.raise_for_status()
                token_body = token_resp.json() if token_resp.content else {}
                stoken = (token_body.get("data") or {}).get("stoken") if isinstance(token_body, dict) else None
                if not stoken:
                    raise ProviderError("QUARK_UPSTREAM_ERROR", "quark stoken missing", 502)

                detail_resp = await client.get(
                    "https://drive-h.quark.cn/1/clouddrive/share/sharepage/detail",
                    params={
                        "pr": "ucpro",
                        "fr": "pc",
                        "uc_param_str": "",
                        "pwd_id": pwd_id,
                        "stoken": stoken,
                        "pdir_fid": "0",
                        "_page": "1",
                        "_size": "50",
                        "_fetch_banner": "0",
                        "_fetch_share": "1",
                        "_fetch_total": "1",
                        "__t": int(time.time() * 1000),
                    },
                    headers=headers,
                )
                detail_resp.raise_for_status()
                detail_body = detail_resp.json() if detail_resp.content else {}
                rows = ((detail_body.get("data") or {}).get("list") if isinstance(detail_body, dict) else None) or []
                fid_list: list[str] = []
                fid_token_list: list[str] = []
                if isinstance(rows, list):
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        fid = str(row.get("fid") or "").strip()
                        token = str(row.get("share_fid_token") or "").strip()
                        if fid and token:
                            fid_list.append(fid)
                            fid_token_list.append(token)
                if not fid_list:
                    raise ProviderError("QUARK_UPSTREAM_ERROR", "quark share has no savable files", 502)

                save_resp = await client.post(
                    "https://drive-h.quark.cn/1/clouddrive/share/sharepage/save",
                    params={"pr": "ucpro", "fr": "pc", "uc_param_str": "", "__t": int(time.time() * 1000)},
                    headers=headers,
                    json={
                        "fid_list": fid_list,
                        "fid_token_list": fid_token_list,
                        "to_pdir_fid": target_dir_id or "0",
                        "pwd_id": pwd_id,
                        "stoken": stoken,
                        "pdir_fid": "0",
                        "scene": "link",
                    },
                )
                save_resp.raise_for_status()
                save_body = save_resp.json() if save_resp.content else {}
                if isinstance(save_body, dict) and str(save_body.get("status")) not in {"200", "0"}:
                    message = str(save_body.get("message") or "quark save failed")
                    raise ProviderError("QUARK_UPSTREAM_ERROR", message, 502)
                return f"quark-{pwd_id}-{target_dir_id or '0'}"
        except (ProviderError, ValidationError, AuthError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("QUARK_UPSTREAM_ERROR", f"quark save failed: {exc}", 502) from exc

    async def list_share_items(self, source_uri: str, parent_id: str = "0") -> list[dict]:
        if self.settings.use_mock:
            if parent_id.startswith("qdir"):
                return [
                    {"id": "qf1::qt1", "name": "资源A.mp4", "size": 2 * 1024 * 1024 * 1024, "is_dir": False},
                    {"id": "qf2::qt2", "name": "资源B.srt", "size": 3 * 1024 * 1024, "is_dir": False},
                ]
            return [
                {"id": "qdir::qdt", "name": "资源目录", "size": None, "is_dir": True},
            ]
        if not self.settings.quark_cookie:
            raise AuthError("QUARK_AUTH_INVALID", "missing quark cookie", 401)
        _, _, rows = await self._share_context(source_uri, parent_id)
        out: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            fid = str(row.get("fid") or "").strip()
            name = str(row.get("file_name") or "").strip()
            token = str(row.get("share_fid_token") or "").strip()
            if not fid or not name or not token:
                continue
            size_raw = row.get("size")
            size = int(size_raw) if isinstance(size_raw, int | float) else None
            is_dir = int(row.get("file_type") or 1) == 0
            out.append({"id": self._encode_item_id(fid, token), "name": name, "size": size, "is_dir": is_dir})
        return out

    async def save_selected_items(
        self, source_uri: str, target_dir_id: str, selected_ids: list[str]
    ) -> str:
        if self.settings.use_mock:
            return f"quark-{target_dir_id or '0'}"
        if not self.settings.quark_cookie:
            raise AuthError("QUARK_AUTH_INVALID", "missing quark cookie", 401)
        pwd_id, stoken, rows = await self._share_context(source_uri)
        by_id: dict[str, tuple[str, str]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            fid = str(row.get("fid") or "").strip()
            token = str(row.get("share_fid_token") or "").strip()
            name = str(row.get("file_name") or fid)
            if fid and token:
                by_id[fid] = (token, name)
        chosen = selected_ids or list(by_id.keys())
        if not chosen:
            raise ValidationError("QUARK_SHARE_EMPTY", "分享内容为空", 400)
        fid_list: list[str] = []
        fid_token_list: list[str] = []
        for raw_id in chosen:
            fid, inline_token = self._decode_item_id(raw_id)
            token_name = by_id.get(fid)
            if inline_token:
                fid_list.append(fid)
                fid_token_list.append(inline_token)
                continue
            if not token_name:
                continue
            fid_list.append(fid)
            fid_token_list.append(token_name[0])
        if not fid_list:
            raise ValidationError("QUARK_SHARE_EMPTY", "未选择可转存资源", 400)
        headers = {
            "cookie": self.settings.quark_cookie,
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0",
        }
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            save_resp = await client.post(
                "https://drive-h.quark.cn/1/clouddrive/share/sharepage/save",
                params={"pr": "ucpro", "fr": "pc", "uc_param_str": "", "__t": int(time.time() * 1000)},
                headers=headers,
                json={
                    "fid_list": fid_list,
                    "fid_token_list": fid_token_list,
                    "to_pdir_fid": target_dir_id or "0",
                    "pwd_id": pwd_id,
                    "stoken": stoken,
                    "pdir_fid": "0",
                    "scene": "link",
                },
            )
        save_resp.raise_for_status()
        save_body = save_resp.json() if save_resp.content else {}
        if isinstance(save_body, dict) and str(save_body.get("status")) not in {"200", "0"}:
            message = str(save_body.get("message") or "quark save failed")
            raise ProviderError("QUARK_UPSTREAM_ERROR", message, 502)
        return f"quark-{pwd_id}-{target_dir_id or '0'}"

    async def check(self) -> tuple[bool, str]:
        if self.settings.use_mock:
            return True, "mock_ok"
        if not self.settings.quark_cookie:
            return False, "missing_cookie"
        try:
            headers = {"cookie": self.settings.quark_cookie, "user-agent": "Mozilla/5.0"}
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                resp = await client.get(
                    "https://drive-h.quark.cn/1/clouddrive/file/sort",
                    params={
                        "pr": "ucpro",
                        "fr": "pc",
                        "uc_param_str": "",
                        "pdir_fid": "0",
                        "_page": "1",
                        "_size": "1",
                        "_fetch_total": "false",
                        "_fetch_sub_dirs": "0",
                    },
                    headers=headers,
                )
            return resp.status_code == 200, f"http_{resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    async def list_dirs(
        self, parent_id: str = "0"
    ) -> tuple[str, list[C115DirAncestor], list[C115DirItem]]:
        if self.settings.use_mock:
            if parent_id == "0":
                return "/", [C115DirAncestor(id="0", path="/")], [
                    C115DirItem(id="q100", name="电影"),
                    C115DirItem(id="q200", name="剧集"),
                ]
            if parent_id == "q100":
                return "/电影", [
                    C115DirAncestor(id="0", path="/"),
                    C115DirAncestor(id="q100", path="/电影"),
                ], [C115DirItem(id="q101", name="华语")]
            return "/剧集", [
                C115DirAncestor(id="0", path="/"),
                C115DirAncestor(id=str(parent_id), path="/剧集"),
            ], [C115DirItem(id="q201", name="美剧")]
        if not self.settings.quark_cookie:
            raise AuthError("QUARK_AUTH_INVALID", "missing quark cookie", 401)

        headers = {
            "cookie": self.settings.quark_cookie,
            "accept": "application/json, text/plain, */*",
            "user-agent": "Mozilla/5.0",
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                resp = await client.get(
                    "https://drive-h.quark.cn/1/clouddrive/file/sort",
                    params={
                        "pr": "ucpro",
                        "fr": "pc",
                        "uc_param_str": "",
                        "pdir_fid": parent_id or "0",
                        "_page": "1",
                        "_size": "100",
                        "_fetch_total": "false",
                        "_fetch_sub_dirs": "1",
                        "_sort": "",
                        "__t": int(time.time() * 1000),
                    },
                    headers=headers,
                )
            resp.raise_for_status()
            body = resp.json() if resp.content else {}
            rows = ((body.get("data") or {}).get("list") if isinstance(body, dict) else None) or []
            out: list[C115DirItem] = []
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    fid = str(row.get("fid") or "").strip()
                    name = str(row.get("file_name") or "").strip()
                    if not fid or not name:
                        continue
                    if int(row.get("file_type") or 1) != 0:
                        continue
                    out.append(C115DirItem(id=fid, name=name, is_dir=True))
            parent_path = "/" if parent_id in {"0", ""} else f"/{parent_id}"
            ancestors = [C115DirAncestor(id="0", path="/")]
            if parent_id not in {"0", ""}:
                ancestors.append(C115DirAncestor(id=parent_id, path=parent_path))
            return parent_path, ancestors, out
        except (ProviderError, AuthError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("QUARK_UPSTREAM_ERROR", f"quark list dirs failed: {exc}", 502) from exc
