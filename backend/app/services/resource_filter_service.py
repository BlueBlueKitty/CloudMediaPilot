from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
import json
from pathlib import Path

from app.core.config import ProviderSettings
from app.schemas.models import ResourceFilterRule


DEFAULT_RULES: list[dict[str, object]] = [
    {
        "id": "doc-text-files",
        "name": "文档和文本文件",
        "enabled": True,
        "glob": "*.txt",
        "min_size_bytes": None,
        "max_size_bytes": None,
        "applies_to": "both",
    },
    {
        "id": "doc-word-files",
        "name": "Word 文档",
        "enabled": True,
        "glob": "*.docx",
        "min_size_bytes": None,
        "max_size_bytes": None,
        "applies_to": "both",
    },
    {
        "id": "ad-video-mp4",
        "name": "广告视频-mp4",
        "enabled": True,
        "glob": "*.mp4",
        "min_size_mb": None,
        "max_size_mb": 5,
        "applies_to": "both",
    },
    {
        "id": "ad-video-mkv",
        "name": "广告视频-mkv",
        "enabled": True,
        "glob": "*.mkv",
        "min_size_mb": None,
        "max_size_mb": 5,
        "applies_to": "both",
    },
]


@dataclass(slots=True)
class FilterMatch:
    rule_id: str
    rule_name: str


@dataclass(slots=True)
class ResourceEntry:
    id: str
    name: str
    path: str
    provider: str
    size: int | None = None
    is_dir: bool = False


class ResourceFilterService:
    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    @staticmethod
    def default_rules() -> list[ResourceFilterRule]:
        return [ResourceFilterRule.model_validate(row) for row in DEFAULT_RULES]

    def rules(self) -> list[ResourceFilterRule]:
        raw = (self.settings.resource_filter_rules or "").strip()
        if not raw:
            return self.default_rules()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return self.default_rules()
        if not isinstance(parsed, list):
            return self.default_rules()
        out: list[ResourceFilterRule] = []
        for row in parsed:
            try:
                out.append(ResourceFilterRule.model_validate(row))
            except Exception:
                continue
        return out or self.default_rules()

    def local_roots(self) -> list[str]:
        raw = (self.settings.resource_cleanup_local_roots or "").strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        values: list[str]
        if isinstance(parsed, list):
            values = [str(x).strip() for x in parsed]
        else:
            values = [line.strip() for line in raw.splitlines()]
        out: list[str] = []
        seen: set[str] = set()
        for item in values:
            if not item:
                continue
            resolved = str(Path(item).expanduser())
            if resolved not in seen:
                seen.add(resolved)
                out.append(resolved)
        return out

    def match(self, entry: ResourceEntry, *, operation: str) -> FilterMatch | None:
        if not self.settings.resource_filter_enabled:
            return None
        rel_candidates = {
            entry.name.lower(),
            entry.path.lower().lstrip("/"),
        }
        for rule in self.rules():
            if not rule.enabled:
                continue
            if rule.applies_to not in {operation, "both"}:
                continue
            if entry.size is not None:
                if rule.min_size_mb is not None and entry.size < rule.min_size_mb * 1024 * 1024:
                    continue
                if rule.max_size_mb is not None and entry.size > rule.max_size_mb * 1024 * 1024:
                    continue
            matched = False
            pattern = rule.glob.lower()
            for candidate in rel_candidates:
                if fnmatch(candidate, pattern):
                    matched = True
                    break
            if matched:
                return FilterMatch(rule_id=rule.id, rule_name=rule.name)
        return None
