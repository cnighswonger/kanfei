"""Per-command rate limiter for bot integrations.

Shared by all bot adapters to enforce consistent cooldown behavior:
- Same command repeated: 5s cooldown (prevents spam)
- Different command from same source: 1s debounce
"""

import time

# Default cooldown values (seconds).
DEFAULT_SAME_CMD = 5
DEFAULT_DIFF_CMD = 1


class RateLimiter:
    """Tracks per-source, per-command timestamps and enforces cooldowns."""

    def __init__(self, same_cmd: float = DEFAULT_SAME_CMD,
                 diff_cmd: float = DEFAULT_DIFF_CMD) -> None:
        self._same_cmd = same_cmd
        self._diff_cmd = diff_cmd
        self._timestamps: dict[tuple[str, str], float] = {}

    def is_limited(self, source_id: str, command: str = "") -> bool:
        """Check if a command from a source is rate-limited.

        Returns True if the command should be dropped.
        Records the timestamp if not limited.
        """
        now = time.monotonic()
        key = (source_id, command)

        # Same command cooldown
        last_same = self._timestamps.get(key, 0.0)
        if now - last_same < self._same_cmd:
            return True

        # Cross-command debounce
        for (sid, _), ts in self._timestamps.items():
            if sid == source_id and now - ts < self._diff_cmd:
                return True

        self._timestamps[key] = now
        return False
