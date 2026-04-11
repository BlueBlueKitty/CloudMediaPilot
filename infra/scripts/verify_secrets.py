#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
BLOCKED = [
    re.compile(r"\bUID=[^;\s]+;\s*CID=[^;\s]+;\s*SEID=[^;\s]+"),
    re.compile(r"(?i)prowlarr_api_key\s*=\s*[\"'][^\"']{6,}[\"']"),
    re.compile(r"(?i)tmdb_api_key\s*=\s*[\"'][^\"']{6,}[\"']"),
]
SKIP_DIRS = {".git", ".omx", "ref_repos", "__pycache__"}
ALLOW_FILES = {"key.txt", ".env", ".env.example"}


def should_skip(path: pathlib.Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def main() -> None:
    failures: list[str] = []
    if (ROOT / "key.txt").exists():
        print("[WARN] key.txt exists locally; keep it out of VCS/images.")
    for file in ROOT.rglob("*"):
        if not file.is_file() or should_skip(file):
            continue
        if file.name in ALLOW_FILES:
            continue
        if file.suffix in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".lock", ".pyc"}:
            continue
        text = file.read_text(errors="ignore")
        for pattern in BLOCKED:
            if pattern.search(text):
                failures.append(f"{file}: matched {pattern.pattern}")
    if failures:
        print("[FAIL] secret verify failed")
        for f in failures:
            print(" -", f)
        raise SystemExit(1)
    print("[OK] secret verify passed")


if __name__ == "__main__":
    main()
