"""Public-mode detector.

Answers "is this Kanfei instance running as a public droplet?" by
reading ``station_driver_type`` from ``station_config`` and comparing
it to the ``public_relay`` driver key.

The write-block middleware in ``app/main.py`` and the ``require_admin``
guest bypass in ``app/api/dependencies.py`` both call ``is_public_mode``
on every request.  A 30 s in-memory cache keeps the cost near zero
without introducing an env var (settings.py in this codebase only reads
env vars, and the operator changes driver type via the setup wizard,
not a systemd reload).

``invalidate_cache`` is called by the setup handlers that write
``station_driver_type`` so a driver-type change takes effect on the very
next request without waiting up to 30 s for the cache to expire.
"""

import time
from typing import Optional, Tuple

from ..models.database import SessionLocal
from ..models.station_config import StationConfigModel

PUBLIC_RELAY_DRIVER_TYPE = "public_relay"

_CACHE_SECONDS = 30
_cache: Optional[Tuple[float, bool]] = None


def is_public_mode() -> bool:
    """True if ``station_driver_type`` is set to the public-relay driver.

    Cached for 30 s per-worker.  Invalidated explicitly by the setup
    handlers that mutate ``station_driver_type``.
    """
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < _CACHE_SECONDS:
        return _cache[1]

    db = SessionLocal()
    try:
        row = db.query(StationConfigModel).filter_by(
            key="station_driver_type",
        ).first()
        value = row.value if row is not None else None
    finally:
        db.close()

    result = value == PUBLIC_RELAY_DRIVER_TYPE
    _cache = (now, result)
    return result


def invalidate_cache() -> None:
    """Drop the cached value so the next ``is_public_mode`` call re-reads.

    Called from the setup handlers that write ``station_driver_type``.
    """
    global _cache
    _cache = None
