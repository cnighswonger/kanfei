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

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from ..ipc.dependencies import get_ipc_client

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
async def get_weatherlink_config():
    """Read current hardware settings from the WeatherLink."""
    try:
        client = get_ipc_client()
        # Longer timeout — serial reads compete with poller for lock
        result = await client.send_command({"cmd": "read_config"}, timeout=20.0)
        if result.get("ok"):
            data = result["data"]
            return WeatherLinkConfigResponse(
                archive_period=data.get("archive_period"),
                sample_period=data.get("sample_period"),
                calibration=CalibrationConfig(**data["calibration"]),
            )
        return {"error": result.get("error", "Not connected")}
    except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
        return {"error": "Logger daemon not running"}


@router.post("/weatherlink/config")
async def update_weatherlink_config(config: WeatherLinkConfigUpdate):
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
            return {"error": result.get("error", "Failed")}

        # Re-read current state to return
        read_result = await client.send_command(
            {"cmd": "read_config"}, timeout=20.0,
        )
        if read_result.get("ok"):
            data = read_result["data"]
            return {
                "results": result["data"]["results"],
                "config": WeatherLinkConfigResponse(
                    archive_period=data.get("archive_period"),
                    sample_period=data.get("sample_period"),
                    calibration=CalibrationConfig(**data["calibration"]),
                ),
            }
        return {"results": result["data"]["results"]}
    except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
        return {"error": "Logger daemon not running"}


@router.post("/weatherlink/clear-rain-daily")
async def clear_rain_daily():
    """Clear the daily rain accumulator."""
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "clear_rain_daily"})
        if result.get("ok"):
            return result["data"]
        return {"error": result.get("error", "Failed")}
    except (ConnectionRefusedError, OSError):
        return {"error": "Logger daemon not running"}


@router.post("/weatherlink/clear-rain-yearly")
async def clear_rain_yearly():
    """Clear the yearly rain accumulator."""
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "clear_rain_yearly"})
        if result.get("ok"):
            return result["data"]
        return {"error": result.get("error", "Failed")}
    except (ConnectionRefusedError, OSError):
        return {"error": "Logger daemon not running"}


@router.post("/weatherlink/force-archive")
async def force_archive():
    """Force the WeatherLink to write an archive record now."""
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "force_archive"})
        if result.get("ok"):
            return result["data"]
        return {"error": result.get("error", "Failed")}
    except (ConnectionRefusedError, OSError):
        return {"error": "Logger daemon not running"}
