"""GET /api/station - Station type, connection status, diagnostics.
   POST /api/station/sync-time - Sync station clock to computer time.

All hardware operations are proxied to the logger daemon via IPC.
"""

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..ipc.dependencies import get_ipc_client
from .dependencies import require_admin

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
async def sync_station_time(_admin=Depends(require_admin)):
    """Sync station clock to computer time."""
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "sync_station_time"})
        if result.get("ok"):
            return {"status": "ok", **result["data"]}
        return {"status": "error", "message": result.get("error", "Unknown error")}
    except (ConnectionRefusedError, OSError):
        return {"status": "error", "message": "Logger daemon not running"}


# --------------- Driver catalog ---------------

DRIVER_CATALOG = [
    {
        "type": "legacy",
        "name": "Davis Weather Monitor / Wizard",
        "connection": "serial",
        "description": "Legacy serial protocol for Weather Monitor II, Wizard III, Wizard II, Perception II, GroWeather, Energy, Health stations.",
        "config_fields": ["serial_port", "baud_rate"],
    },
    {
        "type": "vantage",
        "name": "Davis Vantage Pro / Pro2 / Vue",
        "connection": "serial",
        "description": "Serial protocol for Vantage Pro1, Pro2, and Vue consoles via RS-232 or USB adapter.",
        "config_fields": ["serial_port"],
    },
    {
        "type": "weatherlink_ip",
        "name": "Davis WeatherLink IP (6555)",
        "connection": "network",
        # Said "Vantage protocol over TCP" until #247.  The driver wraps
        # LinkDriver (legacy WRD/WWR), not VantageDriver — corrected here
        # to match the code.  Which of the two was wrong is still open.
        "description": "Legacy WeatherLink protocol over TCP for the WeatherLink IP data logger.",
        "config_fields": ["weatherlink_ip", "weatherlink_port"],
    },
    {
        "type": "weatherlink_live",
        "name": "Davis WeatherLink Live (6100)",
        "connection": "network",
        "description": "HTTP + UDP for the WeatherLink Live device.",
        "config_fields": ["weatherlink_ip"],
    },
    {
        "type": "ecowitt",
        "name": "Ecowitt / Fine Offset",
        "connection": "network",
        "description": "TCP LAN API for Ecowitt gateways (GW1000, GW2000, HP2551) and Fine Offset branded variants (Froggit, Bresser, Sainlogic, etc.).",
        "config_fields": ["ecowitt_ip"],
    },
    {
        "type": "tempest",
        "name": "WeatherFlow Tempest",
        "connection": "udp",
        "description": "Local UDP broadcast from the Tempest hub. No cloud account needed.",
        "config_fields": ["tempest_hub_sn"],
    },
    {
        "type": "ambient",
        "name": "Ambient Weather",
        "connection": "http_push",
        "description": "HTTP push from Ambient Weather stations (WS-2902, WS-5000) or any Fine Offset station with Ecowitt firmware.",
        "config_fields": ["ambient_listen_port"],
    },
]


@router.get("/station/drivers")
def get_driver_catalog():
    """Return the list of supported station drivers with metadata."""
    return DRIVER_CATALOG


@router.get("/station/signal-quality")
async def get_signal_quality(_admin=Depends(require_admin)):
    """Console reception diagnostics — how well it is hearing the sensors.

    The counters reset at station midnight, so a single reading is a
    since-midnight total rather than a rate.  Two readings apart give the
    rate; that is the caller's job, not ours.

    Read-only, but admin-gated like the other station endpoints: it holds
    the serial lock briefly, and on a single-master port that is enough to
    stall a poll.
    """
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "signal_quality"}, timeout=20.0)
        if result.get("ok"):
            return result["data"]
        detail = result.get("error", "Failed")
        # Same split as force-archive (#219): a station that cannot do this
        # is a 501, anything else is a transient fault.  A command that did
        # not run must not look like one that did.
        raise HTTPException(
            status_code=501 if "does not support" in detail else 503,
            detail=detail,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Station did not respond in time (serial port busy?)",
        )
    except (ConnectionRefusedError, OSError):
        raise HTTPException(status_code=503, detail="Logger daemon not running")


# --------------- Barometer calibration ---------------
#
# Vantage only.  Legacy stations calibrate their barometer through a
# different mechanism (direct BAR_CAL register write, subtract semantics)
# and are excluded by CAP_BAROMETER_CAL, not by a type check here.


def _cal_error(detail: str) -> HTTPException:
    """Map an IPC error string to a status code.

    Follows the force-archive precedent (#219): a station that cannot do
    this is 501, a rejected argument is 400, anything else is a transient
    fault.  A command that did not run must never look like one that did.
    """
    if "does not support" in detail:
        return HTTPException(status_code=501, detail=detail)
    if "must be" in detail or "required" in detail:
        return HTTPException(status_code=400, detail=detail)
    return HTTPException(status_code=503, detail=detail)


@router.get("/station/barometer-calibration")
async def get_barometer_calibration(_admin=Depends(require_admin)):
    """Read the console's current barometer calibration (BARDATA)."""
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "barometer_cal"}, timeout=20.0)
        if result.get("ok"):
            return result["data"]
        raise _cal_error(result.get("error", "Failed"))
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Station did not respond in time (serial port busy?)",
        )
    except (ConnectionRefusedError, OSError):
        raise HTTPException(status_code=503, detail="Logger daemon not running")


@router.post("/station/barometer-calibration")
async def set_barometer_calibration(
    payload: dict,
    _admin=Depends(require_admin),
):
    """Set barometer calibration and elevation via BAR=.

    Body: ``{"bar_thousandths_inhg": int, "elevation_ft": int}``.

    ``bar_thousandths_inhg`` is the sea-level pressure the console should
    display right now — the console back-solves its own offset against
    the current raw reading, so the reference must be current rather than
    remembered.  Pass 0 to clear the offset while keeping elevation.

    Returns before/after BARDATA snapshots so the caller can log the pair
    the calibration procedure requires.
    """
    bar = payload.get("bar_thousandths_inhg")
    elevation = payload.get("elevation_ft")
    if bar is None or elevation is None:
        raise HTTPException(
            status_code=400,
            detail="bar_thousandths_inhg and elevation_ft are both required",
        )

    try:
        client = get_ipc_client()
        result = await client.send_command(
            {
                "cmd": "set_barometer",
                "bar_thousandths_inhg": int(bar),
                "elevation_ft": int(elevation),
            },
            timeout=30.0,
        )
        if result.get("ok"):
            return result["data"]
        raise _cal_error(result.get("error", "Failed"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="bar_thousandths_inhg and elevation_ft must be integers",
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Station did not respond in time (serial port busy?)",
        )
    except (ConnectionRefusedError, OSError):
        raise HTTPException(status_code=503, detail="Logger daemon not running")
