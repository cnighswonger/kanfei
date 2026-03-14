"""In-memory ring buffer for recent WARNING+ log entries.

Provides a custom logging.Handler backed by collections.deque so the
web UI can display recent warnings/errors without touching the database.
"""

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Optional


class _BufferHandler(logging.Handler):
    """Captures log records into a bounded deque."""

    def __init__(self, maxlen: int = 1000):
        super().__init__(level=logging.WARNING)
        self._buf: deque[dict] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._buf.append({
                "timestamp": datetime.fromtimestamp(
                    record.created, tz=timezone.utc
                ).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record),
            })
        except Exception:
            self.handleError(record)

    def get_entries(
        self,
        level: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return newest-first entries, optionally filtered by min level."""
        min_level = logging.WARNING
        if level:
            min_level = getattr(logging, level.upper(), logging.WARNING)

        result = [
            e for e in reversed(self._buf)
            if logging.getLevelName(e["level"]) >= min_level
        ]
        return result[:limit]


# Module-level singleton
log_buffer = _BufferHandler()


def install() -> None:
    """Attach the buffer handler to the root logger."""
    logging.getLogger().addHandler(log_buffer)
