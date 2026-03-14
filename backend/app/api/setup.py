"""Setup wizard API endpoints.

GET  /api/setup/status       - Check if initial setup is complete
GET  /api/setup/serial-ports - List available serial ports
POST /api/setup/probe        - Test a specific port+baud for a WeatherLink station
POST /api/setup/auto-detect  - Scan all ports for a WeatherLink station
POST /api/setup/complete     - Save config and trigger reconnect
POST /api/setup/reconnect    - Reconnect with current DB config

Hardware operations (probe, detect, connect) are proxied to the logger
daemon via IPC.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.station_config import StationConfigModel
from ..protocol.serial_port import list_serial_ports
from ..ipc.dependencies import get_ipc_client

logger = logging.getLogger(__name__)
router = APIRouter()


# --------------- Request/Response models ---------------

class ProbeRequest(BaseModel):
    port: str
    baud_rate: int


class ProbeResult(BaseModel):
    success: bool
    station_type: str | None = None
    station_code: int | None = None
    driver_type: str | None = None
    error: str | None = None


class AutoDetectResult(BaseModel):
    found: bool
    port: str | None = None
    baud_rate: int | None = None
    station_type: str | None = None
    station_code: int | None = None
    driver_type: str | None = None
    attempts: list[dict] = []


class SetupConfig(BaseModel):
    serial_port: str
    baud_rate: int
    station_driver_type: str = "legacy"
    latitude: float
    longitude: float
    elevation: float
    temp_unit: str = "F"
    pressure_unit: str = "inHg"
    wind_unit: str = "mph"
    rain_unit: str = "in"
    metar_enabled: bool = False
    metar_station: str = "XXXX"
    nws_enabled: bool = False


# --------------- Endpoints ---------------

@router.get("/setup/status")
def get_setup_status(db: Session = Depends(get_db)):
    """Check if initial setup has been completed."""
    row = db.query(StationConfigModel).filter_by(key="setup_complete").first()
    return {"setup_complete": row is not None and row.value == "true"}


@router.get("/setup/serial-ports")
def get_serial_ports():
    """List available serial ports on the host machine."""
    return {"ports": list_serial_ports()}


@router.post("/setup/probe")
async def probe_serial_port(req: ProbeRequest):
    """Test a specific port+baud for a WeatherLink station."""
    if req.baud_rate not in (1200, 2400, 19200):
        return ProbeResult(success=False, error="Baud rate must be 1200, 2400, or 19200")

    try:
        client = get_ipc_client()
        result = await client.send_command({
            "cmd": "probe",
            "port": req.port,
            "baud": req.baud_rate,
        })
        if result.get("ok"):
            data = result["data"]
            return ProbeResult(
                success=data["success"],
                station_type=data.get("station_type"),
                station_code=data.get("station_code"),
                driver_type=data.get("driver_type"),
            )
        return ProbeResult(success=False, error=result.get("error", "Unknown error"))
    except (ConnectionRefusedError, OSError) as exc:
        return ProbeResult(success=False, error="Logger daemon not running")


@router.post("/setup/auto-detect")
async def auto_detect_station():
    """Scan all available ports for a WeatherLink station."""
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "auto_detect"}, timeout=30.0)
        if result.get("ok"):
            data = result["data"]
            return AutoDetectResult(
                found=data.get("found", False),
                port=data.get("port"),
                baud_rate=data.get("baud_rate"),
                station_type=data.get("station_type"),
                station_code=data.get("station_code"),
                driver_type=data.get("driver_type"),
                attempts=data.get("attempts", []),
            )
        return AutoDetectResult(found=False, attempts=[])
    except (ConnectionRefusedError, OSError):
        return AutoDetectResult(
            found=False,
            attempts=[{"error": "Logger daemon not running"}],
        )


@router.post("/setup/complete")
async def complete_setup(config: SetupConfig, db: Session = Depends(get_db)):
    """Save all setup config and trigger reconnect."""
    # Save config to DB
    config_dict = config.model_dump()
    for key, value in config_dict.items():
        val = str(value).lower() if isinstance(value, bool) else str(value)
        existing = db.query(StationConfigModel).filter_by(key=key).first()
        if existing:
            existing.value = val
            existing.updated_at = datetime.now(timezone.utc)
        else:
            db.add(StationConfigModel(
                key=key, value=val,
                updated_at=datetime.now(timezone.utc),
            ))

    # Mark setup complete
    existing = db.query(StationConfigModel).filter_by(key="setup_complete").first()
    if existing:
        existing.value = "true"
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(StationConfigModel(
            key="setup_complete", value="true",
            updated_at=datetime.now(timezone.utc),
        ))

    db.commit()
    logger.info("Setup complete — config saved to database")

    # Tell the logger daemon to connect with the new settings
    try:
        client = get_ipc_client()
        result = await client.send_command({
            "cmd": "connect",
            "port": config.serial_port,
            "baud": config.baud_rate,
        })
        reconnect = result.get("data", {}) if result.get("ok") else {
            "success": False, "error": result.get("error", "Unknown error"),
        }
    except (ConnectionRefusedError, OSError):
        reconnect = {"success": False, "error": "Logger daemon not running"}

    return {"status": "ok", "reconnect": reconnect}


@router.post("/setup/reconnect")
async def reconnect_endpoint():
    """Reconnect using current DB config."""
    try:
        client = get_ipc_client()
        result = await client.send_command({"cmd": "reconnect"})
        if result.get("ok"):
            return result["data"]
        return {"success": False, "error": result.get("error", "Unknown error")}
    except (ConnectionRefusedError, OSError):
        return {"success": False, "error": "Logger daemon not running"}
