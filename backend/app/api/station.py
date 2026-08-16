"""GET /api/station - Station type, connection status, diagnostics.
   POST /api/station/sync-time - Sync station clock to computer time.

All hardware operations are proxied to the logger daemon via IPC.
"""

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..ipc.dependencies import get_ipc_client
from ..models.database import SessionLocal, get_db
from ..models.sensor_reading import SensorReadingModel
from ..services.barometer_aggregation import (
    MAX_STATION_DISTANCE_MILES,
    compute_aggregate_recommendation,
    fetch_station_medians,
    read_console_barometer_median,
)
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
    "firmware_version": None,
    "firmware_date": None,
    "product_sku": None,
    "poll_interval": 0,
    "station_time": None,
    "station_time_components": None,
    "server_epoch_ms_at_read": None,
    "battery": None,
}


def _read_battery_from_latest_reading() -> dict | None:
    """Extract battery-status fields from the latest ``sensor_readings.extra_json``.

    Battery data (Vantage transmitter bitmask, decoded low-battery TX
    list, console-battery voltage) is populated by every driver poll
    into the row's ``extra_json`` blob (see #236 / #329 pattern).
    Nothing was reading it — this surfaces the state that was already
    being written so the operator can see a low battery before it
    turns into a sentinel outage.

    Returns ``None`` on:
      - No readings yet in the DB (fresh install).
      - The latest row has no ``extra_json`` (driver doesn't populate).
      - Neither battery key is present in the parsed extras (station
        has no supported battery reporting).

    Returned shape when data is present:

        {
          "transmitters_low": [1, 3],       # empty list means all OK
          "console_voltage": 4.72,          # volts, or None
          "raw_transmitter_bitmask": 0x05,  # kept for diagnostics
        }
    """
    db = SessionLocal()
    try:
        row = (
            db.query(SensorReadingModel.extra_json)
            .order_by(SensorReadingModel.timestamp.desc())
            .first()
        )
    finally:
        db.close()
    if row is None or row[0] is None:
        return None
    try:
        extras = json.loads(row[0])
    except (ValueError, TypeError):
        return None
    if not isinstance(extras, dict):
        return None

    tx_low = extras.get("transmitters_low_battery")
    tx_mask = extras.get("transmitter_battery_status")
    console_v = extras.get("console_battery_voltage")

    if tx_low is None and tx_mask is None and console_v is None:
        return None

    return {
        "transmitters_low": tx_low if isinstance(tx_low, list) else [],
        "console_voltage": console_v if isinstance(console_v, (int, float)) else None,
        "raw_transmitter_bitmask": tx_mask if isinstance(tx_mask, int) else None,
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
    #
    # The clock read returns two paired values for the frontend's live-tick
    # display (`StationStatus.tsx`):
    #
    #   - `station_time_components`: the raw wall-clock fields the console
    #     reported (year may be null on stations that don't return one)
    #   - `server_epoch_ms_at_read`: the server's UTC epoch (ms) at the
    #     moment of the read
    #
    # The client uses (Date.now() - server_epoch_ms_at_read) to advance
    # the components forward — treating them as opaque wall values,
    # never converting between timezones. This avoids the browser tz
    # ≠ server tz display drift that an epoch-of-a-naive-datetime
    # representation would introduce.
    station_time = None
    station_time_components = None
    server_epoch_ms_at_read = None
    if data.get("connected"):
        try:
            # Longer timeout — serial lock may be held by archive sync
            time_result = await client.send_command(
                {"cmd": "read_station_time"}, timeout=20.0,
            )
            if time_result.get("ok") and time_result["data"] is not None:
                t = time_result["data"]
                station_time = _format_station_time(t)
                station_time_components = {
                    "year": t.get("year"),
                    "month": t["month"],
                    "day": t["day"],
                    "hour": t["hour"],
                    "minute": t["minute"],
                    "second": t["second"],
                }
                server_epoch_ms_at_read = int(datetime.now().timestamp() * 1000)

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
                        now = datetime.now()
                        # Build components from the fresh `now` but inherit
                        # `year` availability from the pre-sync read `t`.
                        # Then re-derive `station_time` from the same dict
                        # via `_format_station_time` so the display string
                        # and the components can never disagree on whether
                        # the year suffix is present.
                        station_time_components = {
                            "year": t.get("year"),
                            "month": now.month,
                            "day": now.day,
                            "hour": now.hour,
                            "minute": now.minute,
                            "second": now.second,
                        }
                        station_time = _format_station_time(station_time_components)
                        server_epoch_ms_at_read = int(now.timestamp() * 1000)
                        logger.info("Auto-sync complete")
            else:
                logger.warning(
                    "Station time IPC returned ok=%s data=%s",
                    time_result.get("ok"), time_result.get("data"),
                )
        except Exception as exc:
            logger.warning("Failed to read station time via IPC: %s", exc)

    # archive_records ships as a diagnostic row on the dashboard station-
    # status strip; total row count of the archive-record table.  Raw
    # SQL (not ORM) avoids the ORM ``select … FROM (SELECT …)`` subquery
    # shape that SQLite complained about when driven from the request
    # scope with only-recently-touched migrations.  Warns (rather than
    # silently returning null) so a real error surfaces in the log
    # instead of vanishing.
    try:
        row = db.execute(text("SELECT COUNT(*) FROM archive_records")).scalar()
        archive_records = int(row) if row is not None else None
    except Exception as exc:
        logger.warning("archive_records count failed: %s", exc)
        archive_records = None

    # Site name for the dashboard title row ("Sanford, NC") + elevation
    # from settings.  Both public so the anonymous dashboard render can
    # populate the title without an admin round-trip.
    cfg_effective = get_effective_config(db)
    station_name = str(cfg_effective.get("station_name", "") or "")
    try:
        elevation_ft = float(cfg_effective.get("elevation", 0.0) or 0.0)
    except (TypeError, ValueError):
        elevation_ft = None

    return {
        "type_code": data.get("type_code", -1),
        "type_name": data.get("type_name", "Unknown"),
        "connected": data.get("connected", False),
        "link_revision": data.get("link_revision", "unknown"),
        "firmware_version": data.get("firmware_version"),
        "firmware_date": data.get("firmware_date"),
        "product_sku": data.get("product_sku"),
        "poll_interval": data.get("poll_interval", 0),
        "last_poll": data.get("last_poll"),
        "uptime_seconds": data.get("uptime_seconds", 0),
        "crc_errors": data.get("crc_errors", 0),
        "timeouts": data.get("timeouts", 0),
        "station_time": station_time,
        "station_time_components": station_time_components,
        "server_epoch_ms_at_read": server_epoch_ms_at_read,
        "battery": _read_battery_from_latest_reading(),
        "archive_records": archive_records,
        "station_name": station_name,
        "elevation_ft": elevation_ft,
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
    {
        # Public-facing droplet mode.  Selecting this driver puts the
        # entire app into read-only public mode (issue #336) — the
        # write-block middleware and require_admin guest bypass both
        # key off this exact string.  See app/services/public_mode.py.
        "type": "public_relay",
        "name": "Public Relay (droplet demo)",
        "connection": "http_push",
        "description": "Read-only public droplet.  Data is pushed by a local station's private Kanfei instance; the entire Settings UI is accessible read-only.",
        "config_fields": [],
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


@router.get("/station/radio-state")
async def get_radio_state(_admin=Depends(require_admin)):
    """Vantage radio state and per-unit crystal cal via OPMODE.

    Undocumented Davis command, read-only, safe on Vue fw 2.12 and
    fw 4.33.  See `reference/vantage_fw433_wire_audit.md` §N3 for
    the wire behaviour and audit results.

    Admin-gated like the other station endpoints — read-only but
    holds the serial lock briefly, and on a single-master port that
    is enough to stall a poll.  Returns the parsed dict of
    ``KEY -> int``; on a station that does not implement OPMODE a
    501 is raised, on a transient fault a 503, on serial-lock
    timeout a 504.  Same 501/503/504 split as `/signal-quality`
    because the failure classes are the same.
    """
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "radio_state"}, timeout=20.0)
        if result.get("ok"):
            return result["data"]
        detail = result.get("error", "Failed")
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
                # round(), not int(): the console takes whole feet, and
                # truncating 265.7 to 265 discards most of a foot the
                # caller measured.  Callers may hold sub-foot precision
                # because station_config.elevation does.
                "elevation_ft": round(float(elevation)),
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
    """Multi-station aggregate for barometer calibration (#298).

    A Vantage reports reduction method 1 (Altimeter Setting), so a METAR's
    ``Axxxx`` group compares like-for-like with what the console displays.

    Previously returned a list of the ``limit`` nearest single METAR
    observations for the operator to pick from.  That let a single
    anomalous METAR silently pin the console's persistent barometer offset
    to a wrong value.  Now returns a full aggregation with two gates
    (min-stations, cross-station spread) and a signed
    ``recommendation.offset_thousandths_inhg`` derived from
    median-of-per-station-medians vs. the median of the console's own last
    ``CONSOLE_WINDOW_MINUTES`` of readings.  See
    ``backend/app/services/barometer_aggregation.py`` for the algorithm
    and the phone-sensor citation.

    Returns 200 with ``location_configured: false`` when the station has
    no coordinates, rather than an error: that is a normal first-run
    state, and the caller renders a "set your location" prompt pointing
    at the Location card on the same settings tab.  Treating it as a
    fault would make an unconfigured install look broken.

    ``references`` (the pre-#298 single-obs-per-station list) is also
    included, unchanged, so the diagnostic table on gate-fail can show
    "here are the individual stations we consulted" without a second
    request.
    """
    cfg = get_effective_config(db)
    lat = float(cfg.get("latitude", 0.0) or 0.0)
    lon = float(cfg.get("longitude", 0.0) or 0.0)
    now = datetime.now(timezone.utc).isoformat()

    if lat == 0.0 and lon == 0.0:
        return {
            "location_configured": False,
            "home_lat": lat,
            "home_lon": lon,
            "radius_miles": DEFAULT_RADIUS_MILES,
            "fetched_at": now,
            "references": [],
            "aggregate": None,
        }

    # Two independent reads; either can be empty without breaking the
    # other.  fetch_metar_references keeps the single-obs shape the UI
    # already renders; fetch_station_medians is the aggregation source.
    references = await fetch_metar_references(lat, lon)
    per_station = await fetch_station_medians(lat, lon)
    console = read_console_barometer_median(db)
    aggregate = compute_aggregate_recommendation(console, per_station)

    return {
        "location_configured": True,
        "home_lat": lat,
        "home_lon": lon,
        "radius_miles": DEFAULT_RADIUS_MILES,
        "fetched_at": now,
        "references": [asdict(r) for r in references],
        "aggregate": {
            "console": asdict(aggregate.console) if aggregate.console else None,
            "per_station_medians": [
                asdict(s) for s in aggregate.per_station_medians
            ],
            "n_stations_considered": aggregate.n_stations_considered,
            "n_stations_used": aggregate.n_stations_used,
            "cross_station_spread_hpa": aggregate.cross_station_spread_hpa,
            "recommendation": asdict(aggregate.recommendation),
            "thresholds": aggregate.thresholds,
            # Effective radius used by the aggregation is narrower than
            # the display radius that seeds `references` above — expose
            # it here so the UI does not have to know the constant.
            "reference_radius_miles": MAX_STATION_DISTANCE_MILES,
        },
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


# --------------- Console highs and lows ---------------


@router.get("/station/highs-lows")
async def get_station_highs_lows(_admin=Depends(require_admin)):
    """The console's own daily/monthly/yearly extremes (HILOWS).

    Read-only.  Worth having alongside Kanfei's computed extremes rather
    than instead of them: ours come from 10-second polls, the console
    samples continuously, and a disagreement bounds what our sampling
    misses.

    Admin-gated like the other station endpoints — it holds the serial
    lock briefly, which on a single-master port is enough to stall a poll.
    """
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "highs_lows"}, timeout=25.0)
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
# --------------- Vantage temperature/humidity calibration ---------------
#
# Distinct from the barometer panel above.  A Vantage adjusts temperature
# and humidity by per-sensor EEPROM offsets applied through CALED/CALFIX;
# the barometer is BAR= and lives elsewhere.  Putting a barometer row in
# this panel would be the terminology trap the barometer handler warns
# about, so the two are deliberately separate surfaces.


@router.get("/station/calibration")
async def get_station_calibration(_admin=Depends(require_admin)):
    """Current temperature/humidity offsets, in the console's own units."""
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "read_vantage_cal"}, timeout=25.0)
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


@router.post("/station/calibration")
async def set_station_calibration(payload: dict, _admin=Depends(require_admin)):
    """Set one calibration offset.

    Body: ``{"field": str, "offset": int}`` where field is one of
    inside_temp, outside_temp, inside_humidity, outside_humidity.

    ``offset`` is in the console's native units — TENTHS of a degree
    Fahrenheit for temperature, whole percent for humidity.  Getting that
    wrong is a tenfold error, so the units are returned by the GET rather
    than left for the caller to assume.
    """
    field = payload.get("field")
    offset = payload.get("offset")
    if field is None or offset is None:
        raise HTTPException(
            status_code=400, detail="field and offset are both required",
        )

    try:
        client = get_ipc_client()
        result = await client.send_command(
            {"cmd": "write_vantage_cal", "field": str(field), "offset": int(offset)},
            timeout=40.0,
        )
        if result.get("ok"):
            return result["data"]
        raise _cal_error(result.get("error", "Failed"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="offset must be an integer")
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Station did not respond in time (serial port busy?)",
        )
    except (ConnectionRefusedError, OSError):
        raise HTTPException(status_code=503, detail="Logger daemon not running")


@router.post("/station/calibration/clear")
async def clear_station_calibration(_admin=Depends(require_admin)):
    """CLRCAL — zero every temperature and humidity offset.

    Does not touch barometer calibration, which is a separate mechanism.
    """
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "clear_vantage_cal"}, timeout=40.0)
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


# --------------- Console location ---------------
#
# Vantage only.  The console keeps its own latitude/longitude in EEPROM
# and uses them for its sunrise/sunset calculation and pressure
# correction, so a disagreement with Kanfei's configured location
# produces quietly wrong derived data rather than an obvious failure.


@router.get("/station/location")
async def get_station_location(_admin=Depends(require_admin)):
    """Read the console's own latitude/longitude."""
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "read_location"}, timeout=20.0)
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


@router.post("/station/location")
async def set_station_location(payload: dict, _admin=Depends(require_admin)):
    """Push Kanfei's configured location to the console.

    Body: ``{"latitude": float, "longitude": float}``.

    One-directional by design.  The console stores signed tenths of a
    degree (~11 km per step), so copying its value back into Kanfei would
    discard precision Kanfei actually holds.  The response returns what
    the console now reads, which is the rounded value rather than what
    was sent.
    """
    lat = payload.get("latitude")
    lon = payload.get("longitude")
    if lat is None or lon is None:
        raise HTTPException(
            status_code=400,
            detail="latitude and longitude are both required",
        )

    try:
        client = get_ipc_client()
        result = await client.send_command(
            {"cmd": "set_location", "latitude": float(lat), "longitude": float(lon)},
            timeout=30.0,
        )
        if result.get("ok"):
            return result["data"]
        raise _cal_error(result.get("error", "Failed"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400, detail="latitude and longitude must be numbers",
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Station did not respond in time (serial port busy?)",
        )
    except (ConnectionRefusedError, OSError):
        raise HTTPException(status_code=503, detail="Logger daemon not running")


@router.get("/station/rain-season")
async def get_rain_season(_admin=Depends(require_admin)):
    """Read the console's yearly-rain-reset month (1-12).

    Vantage only.  The console uses this to decide when the yearly rain
    total drops back to zero — factory default is January, hydrological
    "water year" installs typically want July so a mid-winter storm
    season is not split across two yearly totals.
    """
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "read_rain_season"}, timeout=20.0)
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


@router.post("/station/rain-season")
async def set_rain_season(payload: dict, _admin=Depends(require_admin)):
    """Set the console's yearly-rain-reset month.

    Body: ``{"month": int}`` where month is 1-12.  The response returns
    the register's before/after values, not what was sent — a written
    value that does not read back is treated as failure per the barometer
    write precedent (#252).
    """
    month = payload.get("month")
    if month is None:
        raise HTTPException(
            status_code=400,
            detail="month is required",
        )
    try:
        month_int = int(month)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=f"month must be an integer 1-12 (got {month!r})",
        )
    if not 1 <= month_int <= 12:
        raise HTTPException(
            status_code=400,
            detail=f"month must be 1-12 (got {month_int})",
        )

    try:
        client = get_ipc_client()
        result = await client.send_command(
            {"cmd": "set_rain_season", "month": month_int},
            timeout=20.0,
        )
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
