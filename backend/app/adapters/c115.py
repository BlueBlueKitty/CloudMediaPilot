from __future__ import annotations

from hashlib import sha256

import httpx

from app.core.config import ProviderSettings
from app.core.errors import AuthError, ProviderError, ValidationError
from app.schemas.models import PublicTaskState


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
            raise ProviderError(
                "C115_UPSTREAM_ERROR",
                f"115 non-json response: {resp.text[:120]}",
                502,
            ) from exc
        if not isinstance(data, dict):
            raise ProviderError("C115_UPSTREAM_ERROR", "115 response is not object", 502)
        return data

    def make_idempotency_key(self, source_uri: str, target_dir_id: str) -> str:
        return sha256(f"{source_uri}|{target_dir_id}".encode()).hexdigest()

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
        }
        payload = {
            "url": source_uri,
            "savepath": target_dir_id,
            "wp_path_id": target_dir_id,
        }
        url = f"{self.settings.c115_base_url}{self.settings.c115_offline_add_path}"
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                resp = await client.post(url, headers=headers, data=payload)
            data = self._json_or_error(resp)
            if resp.status_code == 401 or data.get("errno") in {99, 911, 20004}:
                raise AuthError("C115_AUTH_INVALID", "115 cookie invalid or expired", 401)
            if data.get("state") is False:
                raise ProviderError(
                    "C115_UPSTREAM_ERROR",
                    f"115 error: {data.get('error_msg') or data.get('error')}",
                    502,
                )
            task_id = str(data.get("task_id") or data.get("info_hash") or data.get("id") or "")
            if not task_id:
                task_id = self.make_idempotency_key(source_uri, target_dir_id)[:16]
            return task_id
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
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
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
            return True, "mock"
        if not self.settings.c115_cookie:
            return False, "missing_cookie"
        try:
            tasks_from_sdk = self._try_p115client_list()
            if tasks_from_sdk is not None:
                return True, "ok"
            headers = {"Cookie": self.settings.c115_cookie}
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
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
