"""GET /api/station - Station type, connection status, diagnostics.
   POST /api/station/sync-time - Sync station clock to computer time.

All hardware operations are proxied to the logger daemon via IPC.
"""

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter

from ..ipc.dependencies import get_ipc_client

logger = logging.getLogger(__name__)
router = APIRouter()

AUTO_SYNC_THRESHOLD_SECONDS = 5


def _format_station_time(t: dict | None) -> str | None:
    """Format station time dict as a display string."""
    if t is None:
        return None
    time_str = f"{t['hour']:02d}:{t['minute']:02d}:{t['second']:02d}"
    if t.get("year"):
        return f"{time_str} {t['month']:02d}/{t['day']:02d}/{t['year']}"
    return f"{time_str} {t['month']:02d}/{t['day']:02d}"


def _station_time_to_datetime(t: dict) -> datetime:
    """Build a datetime from a station time dict for drift comparison."""
    now = datetime.now()
    year = t.get("year") or now.year
    return datetime(year, t["month"], t["day"], t["hour"], t["minute"], t["second"])


_DEGRADED_RESPONSE = {
    "type_code": -1,
    "type_name": "Not connected",
    "connected": False,
    "link_revision": "unknown",
    "poll_interval": 0,
    "station_time": None,
}


@router.get("/station")
async def get_station():
    """Return station information and diagnostics."""
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "status"})
    except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
        return _DEGRADED_RESPONSE

    if not result.get("ok"):
        return _DEGRADED_RESPONSE

    data = result["data"]

    # Read station clock and auto-sync if drifted
    station_time = None
    if data.get("connected"):
        try:
            # Longer timeout — serial lock may be held by archive sync
            time_result = await client.send_command(
                {"cmd": "read_station_time"}, timeout=20.0,
            )
            if time_result.get("ok") and time_result["data"] is not None:
                t = time_result["data"]
                station_time = _format_station_time(t)

                # Auto-sync if drift exceeds threshold
                station_dt = _station_time_to_datetime(t)
                drift = abs((datetime.now() - station_dt).total_seconds())
                if drift > AUTO_SYNC_THRESHOLD_SECONDS:
                    logger.info(
                        "Station clock drift %.1fs exceeds %ds threshold, auto-syncing",
                        drift, AUTO_SYNC_THRESHOLD_SECONDS,
                    )
                    sync_result = await client.send_command({"cmd": "sync_station_time"})
                    if sync_result.get("ok") and sync_result["data"].get("success"):
                        station_time = datetime.now().strftime("%H:%M:%S %m/%d")
                        logger.info("Auto-sync complete")
            else:
                logger.warning(
                    "Station time IPC returned ok=%s data=%s",
                    time_result.get("ok"), time_result.get("data"),
                )
        except Exception as exc:
            logger.warning("Failed to read station time via IPC: %s", exc)

    return {
        "type_code": data.get("type_code", -1),
        "type_name": data.get("type_name", "Unknown"),
        "connected": data.get("connected", False),
        "link_revision": data.get("link_revision", "unknown"),
        "poll_interval": data.get("poll_interval", 0),
        "last_poll": data.get("last_poll"),
        "uptime_seconds": data.get("uptime_seconds", 0),
        "crc_errors": data.get("crc_errors", 0),
        "timeouts": data.get("timeouts", 0),
        "station_time": station_time,
    }


@router.post("/station/sync-time")
async def sync_station_time():
    """Sync station clock to computer time."""
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "sync_station_time"})
        if result.get("ok"):
            return {"status": "ok", **result["data"]}
        return {"status": "error", "message": result.get("error", "Unknown error")}
    except (ConnectionRefusedError, OSError):
        return {"status": "error", "message": "Logger daemon not running"}
