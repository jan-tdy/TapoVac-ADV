"""A small bounded ring buffer of this integration's own log records, for the sidebar page's
Log tab. Pure logging.Handler, no Home Assistant imports, so it is easy to unit test and cheap
to keep attached for the life of the process.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

#: everything under this logger name (custom_components.tapo_rv30, custom_components.tapo_rv30.tpap, ...)
LOGGER_NAME = "custom_components.tapo_rv30"
MAX_RECORDS = 500


class RingBufferHandler(logging.Handler):
    """Keeps the last `capacity` formatted log records in memory, newest last."""

    def __init__(self, capacity: int = MAX_RECORDS) -> None:
        super().__init__()
        self.capacity = capacity
        self._records: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._next_id = 1

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:  # pragma: no cover - formatting itself should not crash logging
            message = record.getMessage()
        self._records.append({
            "id": self._next_id,
            "time": record.created,
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        })
        self._next_id += 1

    def list(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Records newest first, at most `limit` of them (default: all kept)."""
        out = list(reversed(self._records))
        return out[:limit] if limit else out

    def clear(self) -> None:
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)


def human_time(epoch: float) -> str:
    """A record's timestamp as a local HH:MM:SS, for a quick glance in the UI."""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))


def install(capacity: int = MAX_RECORDS) -> RingBufferHandler:
    """Attach (once) a RingBufferHandler to this integration's logger namespace and return it.
    Safe to call more than once: a handler already installed on that logger is reused."""
    logger = logging.getLogger(LOGGER_NAME)
    for existing in logger.handlers:
        if isinstance(existing, RingBufferHandler):
            return existing
    handler = RingBufferHandler(capacity)
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return handler


def uninstall(handler: RingBufferHandler | None) -> None:
    """Detach a handler installed by install(), if it is still attached."""
    if handler is None:
        return
    logging.getLogger(LOGGER_NAME).removeHandler(handler)
