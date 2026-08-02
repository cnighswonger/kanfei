"""WeatherLink hardware configuration API endpoints.

GET  /api/weatherlink/config        - Read current hardware settings
POST /api/weatherlink/config        - Write settings to hardware
POST /api/weatherlink/clear-rain-daily   - Clear daily rain accumulator
POST /api/weatherlink/clear-rain-yearly  - Clear yearly rain accumulator
POST /api/weatherlink/force-archive      - Force immediate archive write

All operations are proxied to the logger daemon via IPC.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..ipc.dependencies import get_ipc_client
from .dependencies import require_admin

logger = logging.getLogger(__name__)
router = APIRouter()


# --------------- Request/Response models ---------------

class CalibrationConfig(BaseModel):
    inside_temp: int = 0
    outside_temp: int = 0
    barometer: int = 0
    outside_humidity: int = 0
    rain_cal: int = 100


class WeatherLinkConfigResponse(BaseModel):
    archive_period: Optional[int] = None
    sample_period: Optional[int] = None
    calibration: CalibrationConfig


class WeatherLinkConfigUpdate(BaseModel):
    archive_period: Optional[int] = None
    sample_period: Optional[int] = None
    calibration: Optional[CalibrationConfig] = None


# --------------- Endpoints ---------------

@router.get("/weatherlink/config")
async def get_weatherlink_config(_admin=Depends(require_admin)):
    """Read current hardware settings from the WeatherLink."""
    try:
        client = get_ipc_client()
        # Longer timeout — serial reads compete with poller for lock
        result = await client.send_command({"cmd": "read_config"}, timeout=20.0)
        if result.get("ok"):
            data = result["data"]
            cal = data.get("calibration")
            return {
                "archive_period": data.get("archive_period"),
                "sample_period": data.get("sample_period"),
                # None when the station has no legacy-shaped calibration
                # block (e.g. Vantage).  The `supported` map tells the UI
                # which controls to offer at all.
                "calibration": CalibrationConfig(**cal) if cal else None,
                "supported": data.get("supported", {}),
            }
        # A failure must not be reported as HTTP 200 — the UI cannot
        # distinguish "worked" from "did nothing" otherwise (#219).
        raise HTTPException(
            status_code=503,
            detail=result.get("error", "Station not connected"),
        )
    except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
        raise HTTPException(status_code=503, detail="Logger daemon not running")


@router.post("/weatherlink/config")
async def update_weatherlink_config(config: WeatherLinkConfigUpdate, _admin=Depends(require_admin)):
    """Write settings to the WeatherLink hardware."""
    try:
        client = get_ipc_client()
        cmd: dict = {"cmd": "write_config"}
        if config.archive_period is not None:
            cmd["archive_period"] = config.archive_period
        if config.sample_period is not None:
            cmd["sample_period"] = config.sample_period
        if config.calibration is not None:
            cmd["calibration"] = config.calibration.model_dump()

        # Longer timeout — write does serial I/O with poller stopped
        result = await client.send_command(cmd, timeout=30.0)
        if not result.get("ok"):
            raise HTTPException(
                status_code=503,
                detail=result.get("error", "Settings write failed"),
            )

        # Re-read current state to return
        read_result = await client.send_command(
            {"cmd": "read_config"}, timeout=20.0,
        )
        results = result["data"]["results"]
        # Every requested field rejected as unsupported is a client error,
        # not a server one: the station simply has no such setting.
        if results and all(v == "unsupported" for v in results.values()):
            raise HTTPException(
                status_code=501,
                detail=f"Not supported by this station: {', '.join(sorted(results))}",
            )
        if read_result.get("ok"):
            data = read_result["data"]
            cal = data.get("calibration")
            return {
                "results": results,
                "config": {
                    "archive_period": data.get("archive_period"),
                    "sample_period": data.get("sample_period"),
                    "calibration": CalibrationConfig(**cal) if cal else None,
                    "supported": data.get("supported", {}),
                },
            }
        return {"results": results}
    except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
        raise HTTPException(status_code=503, detail="Logger daemon not running")


@router.post("/weatherlink/clear-rain-daily")
async def clear_rain_daily(_admin=Depends(require_admin)):
    """Clear the daily rain accumulator."""
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "clear_rain_daily"}, timeout=20.0)
        if result.get("ok"):
            return result["data"]
        detail = result.get("error", "Failed")
        # "does not support" is a station limitation (501), anything else
        # is a transient/connection problem (503).  Neither is a 200 — a
        # command that did not run must not look like one that did (#219).
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


@router.post("/weatherlink/clear-rain-yearly")
async def clear_rain_yearly(_admin=Depends(require_admin)):
    """Clear the yearly rain accumulator."""
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "clear_rain_yearly"}, timeout=20.0)
        if result.get("ok"):
            return result["data"]
        detail = result.get("error", "Failed")
        # "does not support" is a station limitation (501), anything else
        # is a transient/connection problem (503).  Neither is a 200 — a
        # command that did not run must not look like one that did (#219).
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


@router.post("/weatherlink/force-archive")
async def force_archive(_admin=Depends(require_admin)):
    """Force the WeatherLink to write an archive record now."""
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "force_archive"}, timeout=20.0)
        if result.get("ok"):
            return result["data"]
        detail = result.get("error", "Failed")
        # "does not support" is a station limitation (501), anything else
        # is a transient/connection problem (503).  Neither is a 200 — a
        # command that did not run must not look like one that did (#219).
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
