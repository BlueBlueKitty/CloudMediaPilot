from __future__ import annotations

import re
from urllib.parse import urlparse

_ANIME_RE = re.compile(r"\b(anime|动漫|番剧)\b", re.IGNORECASE)
_SERIES_RE = re.compile(r"\b(s\d{1,2}e\d{1,2}|season|tv|剧集|连续剧|series)\b", re.IGNORECASE)
_MOVIE_RE = re.compile(r"\b(1080p|2160p|bluray|web[-\s]?dl|movie|电影)\b", re.IGNORECASE)


def infer_media_type(title: str) -> str:
    if _ANIME_RE.search(title):
        return "anime"
    if _SERIES_RE.search(title):
        return "series"
    if _MOVIE_RE.search(title):
        return "movie"
    return "unknown"


def infer_cloud_type(link: str, magnet: str | None = None) -> str:
    raw = (magnet or "").strip() or (link or "").strip()
    if raw.startswith("magnet:"):
        return "magnet"
    if raw.startswith("ed2k://"):
        return "ed2k"
    try:
        netloc = urlparse(raw).netloc.lower()
    except Exception:  # noqa: BLE001
        netloc = ""
    if "pan.baidu.com" in netloc:
        return "baidu"
    if "aliyundrive.com" in netloc or "alipan.com" in netloc:
        return "aliyun"
    if "pan.quark.cn" in netloc:
        return "quark"
    if "drive.uc.cn" in netloc or "pan.uc.cn" in netloc:
        return "uc"
    if "115.com" in netloc:
        return "115"
    if "mypikpak.com" in netloc or "pikpak" in netloc:
        return "pikpak"
    if "pan.xunlei.com" in netloc:
        return "xunlei"
    return "other"
