from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import logging
import sys
from threading import RLock

_MAX_LOGS = 1000


class MemoryLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self._rows: deque[dict[str, str]] = deque(maxlen=_MAX_LOGS)
        self._lock = RLock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            row = {
                "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record),
            }
            with self._lock:
                self._rows.append(row)
        except Exception:  # noqa: BLE001
            return

    def list(self, level: str = "all", limit: int = 300) -> list[dict[str, str]]:
        min_level = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "warn": logging.WARNING,
            "error": logging.ERROR,
        }.get(level.lower(), 0)
        with self._lock:
            rows = list(self._rows)
        if min_level:
            rows = [r for r in rows if logging._nameToLevel.get(r["level"], 0) >= min_level]
        return rows[-limit:]


handler = MemoryLogHandler()
handler.setFormatter(logging.Formatter("%(message)s"))
console_handler = logging.StreamHandler(stream=sys.stdout)
console_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if handler not in root.handlers:
        root.addHandler(handler)
    if console_handler not in root.handlers:
        root.addHandler(console_handler)
    logging.getLogger("uvicorn.access").disabled = False
    logging.getLogger("httpx").setLevel(logging.WARNING)
