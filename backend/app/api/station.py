"""GET /api/station - Station type, connection status, diagnostics.
   POST /api/station/sync-time - Sync station clock to computer time.

All hardware operations are proxied to the logger daemon via IPC.
"""

import asyncio
import logging
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..ipc.dependencies import get_ipc_client
from ..models.database import get_db
from ..services.metar_reference import DEFAULT_RADIUS_MILES, fetch_metar_references
from .config import get_effective_config
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


# Phrases that mark a message as the caller's fault rather than the
# station's.  This list exists because matching on "must be" alone was
# wrong three separate times: "out of range" (#267), "unknown calibration
# field" (#267 again), and "cannot be negative" (#264) all described bad
# arguments and all routed to 503 — telling the user their hardware had a
# transient fault when they had simply sent something invalid.
#
# Adding a phrase here is cheaper than rewording every raise site, and
# unlike a reworded message it cannot be undone by someone rephrasing an
# error later.
# Scoped deliberately.  A bare "unknown" was too greedy and matched a
# STATION fault: "Station did not accept the rain total; console now
# reads: unknown mm" routed to 400, sending a UI down a fix-your-input
# path for hardware that had refused a write.  My own new message, in the
# same PR that widened this list — Codex caught it on #269 R1.
#
# The rule these follow: match the phrasing of an ARGUMENT complaint, not
# a word that could appear anywhere in a sentence about the station.
_CLIENT_ERROR_PHRASES = (
    "must be",
    "must not be",
    "cannot be negative",
    "is required",
    "are both required",
    "out of range",
    "unknown calibration field",
    "expected one of",
    "outside the calibration block",
)


def _cal_error(detail: str) -> HTTPException:
    """Map an IPC error string to a status code.

    Follows the force-archive precedent (#219): a station that cannot do
    this is 501, a rejected argument is 400, anything else is a transient
    fault.  A command that did not run must never look like one that did.
    """
    if "does not support" in detail:
        return HTTPException(status_code=501, detail=detail)
    lowered = detail.lower()
    if any(phrase in lowered for phrase in _CLIENT_ERROR_PHRASES):
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


@router.get("/station/barometer-reference")
async def get_barometer_reference(
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Nearby METAR observations to calibrate the barometer against.

    A Vantage reports reduction method 1 (Altimeter Setting), so a METAR's
    ``Axxxx`` group compares like-for-like with what the console displays.

    Returns 200 with ``location_configured: false`` and no references when
    the station has no coordinates, rather than an error: that is a normal
    first-run state, and the caller renders a "set your location" prompt
    pointing at the Location card on the same settings tab.  Treating it as
    a fault would make an unconfigured install look broken.
    """
    cfg = get_effective_config(db)
    lat = float(cfg.get("latitude", 0.0) or 0.0)
    lon = float(cfg.get("longitude", 0.0) or 0.0)

    if lat == 0.0 and lon == 0.0:
        return {
            "references": [],
            "location_configured": False,
            "home_lat": lat,
            "home_lon": lon,
            "radius_miles": DEFAULT_RADIUS_MILES,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    references = await fetch_metar_references(lat, lon)
    return {
        "references": [asdict(r) for r in references],
        "location_configured": True,
        "home_lat": lat,
        "home_lon": lon,
        "radius_miles": DEFAULT_RADIUS_MILES,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# --------------- Destructive console operations ---------------
#
# PUTRAIN and CLRLOG both destroy data on the console.  Each is paired
# with a preflight endpoint that reports what the operation would cost,
# so the UI can show the price before the user pays it rather than
# offering to undo afterwards.


@router.get("/station/rain-preflight")
async def get_rain_preflight(_admin=Depends(require_admin)):
    """Console yearly rain vs the last total Kanfei recorded.

    The difference is rain that fell since the last poll — exactly what
    restoring the stored value would discard.
    """
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "rain_preflight"}, timeout=25.0)
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


@router.post("/station/yearly-rain")
async def set_yearly_rain(payload: dict, _admin=Depends(require_admin)):
    """PUTRAIN — overwrite the console's yearly rain total.  IRREVERSIBLE.

    Body: ``{"millimetres": float}``.

    Millimetres, never clicks: a click is 0.01in, 0.2 mm or 0.1 mm
    depending on the collector fitted, so the same integer means three
    different totals on three different stations.  The driver converts
    using the collector this station reported, and refuses rather than
    guessing if that is unknown.
    """
    # Typed confirmation, matching the precedent for destructive DB
    # operations (db_admin.py requires confirm == "PURGE"/"COMPACT").
    #
    # The React panel confirms too, but a dialog protects only the users
    # who go through that panel.  An authenticated script, a browser
    # console call, a stale client or a future code path would otherwise
    # reach an irreversible hardware write with no acknowledgement that
    # the loss was understood.  Codex, #269 R1: the safety mechanism has
    # to be structural, not cosmetic.
    if payload.get("confirm") != "OVERWRITE":
        raise HTTPException(
            status_code=400,
            detail="Confirmation required: set confirm to 'OVERWRITE'. This "
                   "permanently replaces the console's yearly rain total.",
        )

    millimetres = payload.get("millimetres")
    if millimetres is None:
        raise HTTPException(status_code=400, detail="millimetres is required")

    try:
        client = get_ipc_client()
        result = await client.send_command(
            {"cmd": "set_yearly_rain", "millimetres": float(millimetres)},
            timeout=40.0,
        )
        if result.get("ok"):
            return result["data"]
        raise _cal_error(result.get("error", "Failed"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="millimetres must be a number")
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Station did not respond in time (serial port busy?)",
        )
    except (ConnectionRefusedError, OSError):
        raise HTTPException(status_code=503, detail="Logger daemon not running")


@router.get("/station/archive-preflight")
async def get_archive_preflight(_admin=Depends(require_admin)):
    """What clearing the console's archive memory would cost."""
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "archive_preflight"}, timeout=25.0)
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


@router.post("/station/clear-archive")
async def clear_archive(payload: dict | None = None, _admin=Depends(require_admin)):
    """CLRLOG — wipe the console's archive memory.  IRREVERSIBLE.

    Records Kanfei has already downloaded are unaffected; anything the
    console holds that has not been synced is destroyed.

    Requires ``{"confirm": "CLEAR"}`` for the same reason as the rain
    total: a UI dialog protects only the users who go through the UI.
    """
    if (payload or {}).get("confirm") != "CLEAR":
        raise HTTPException(
            status_code=400,
            detail="Confirmation required: set confirm to 'CLEAR'. This "
                   "permanently erases archive records the console has not "
                   "yet handed over.",
        )

    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "clear_archive"}, timeout=40.0)
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
