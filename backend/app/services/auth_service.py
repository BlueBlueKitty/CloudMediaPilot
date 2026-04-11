from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from app.services.app_config_service import AppConfig, hash_password

_SESSION_TTL_SECONDS = 7 * 24 * 3600


def verify_password(raw_password: str, cfg: AppConfig) -> bool:
    digest = hash_password(raw_password)
    return hmac.compare_digest(digest, cfg.system_password_hash)


def issue_session_token(cfg: AppConfig) -> str:
    payload = {
        "u": cfg.system_username,
        "iat": int(time.time()),
        "exp": int(time.time()) + _SESSION_TTL_SECONDS,
    }
    payload_raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_raw).rstrip(b"=")
    signature = hmac.new(
        cfg.system_auth_secret.encode("utf-8"),
        payload_b64,
        hashlib.sha256,
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=")
    return f"{payload_b64.decode('ascii')}.{signature_b64.decode('ascii')}"


def parse_session_token(token: str, cfg: AppConfig) -> str | None:
    if not token or "." not in token:
        return None
    payload_b64, signature_b64 = token.split(".", 1)
    payload_b = payload_b64.encode("ascii")
    expected_sig = hmac.new(
        cfg.system_auth_secret.encode("utf-8"),
        payload_b,
        hashlib.sha256,
    ).digest()
    expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode("ascii")
    if not hmac.compare_digest(expected_sig_b64, signature_b64):
        return None
    padded = payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None
    if str(data.get("u") or "") != cfg.system_username:
        return None
    exp = int(data.get("exp") or 0)
    if exp <= int(time.time()):
        return None
    return cfg.system_username
