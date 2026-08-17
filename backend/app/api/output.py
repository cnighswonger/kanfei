"""GET /api/metar, GET /api/aprs - Output format endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import settings
from ..models.database import get_db
from ..models.sensor_reading import SensorReadingModel
from ..output.metar import format_metar
from .config import get_effective_config

router = APIRouter()

# Legacy hook — kept for backward compat but no longer required:
# ``get_metar`` now formats from the latest reading directly, so the
# endpoint works out of the box.  ``_aprs_gen`` still uses the setter
# because APRS packet generation has state (call sign, path) that
# lives in the injected generator.
_metar_gen = None
_aprs_gen = None


def set_output_generators(metar, aprs):
    global _metar_gen, _aprs_gen
    _metar_gen = metar
    _aprs_gen = aprs


@router.get("/metar")
def get_metar(db: Session = Depends(get_db)):
    """Return METAR-formatted string from the latest sensor reading.

    Formats via ``output.metar.format_metar()`` — no wiring required.
    The optional legacy ``_metar_gen`` hook overrides if set, so a
    caller that injects a custom generator (bots, tests) still wins.
    """
    reading = (
        db.query(SensorReadingModel)
        .order_by(SensorReadingModel.timestamp.desc())
        .first()
    )
    if reading is None:
        return {"error": "No data available"}

    if _metar_gen is not None:
        return {"metar": _metar_gen.generate(reading)}

    # SI-unit fields required by format_metar.  None on any missing
    # column → return an error rather than a partial METAR that would
    # mislead a downstream reader.
    required = (
        reading.wind_speed, reading.outside_temp,
        reading.dew_point, reading.barometer,
    )
    if any(v is None for v in required):
        return {"error": "Insufficient sensor data for METAR"}

    cfg = get_effective_config(db)
    station_id = str(cfg.get("metar_station") or settings.metar_station_id or "XXXX")

    metar_str = format_metar(
        station_id=station_id,
        wind_dir_deg=reading.wind_direction,
        wind_speed_tenths_ms=int(reading.wind_speed),
        temp_tenths_c=int(reading.outside_temp),
        dew_point_tenths_c=int(reading.dew_point),
        pressure_tenths_hpa=int(reading.barometer),
        obs_time=reading.timestamp,
    )
    return {"metar": metar_str}


@router.get("/aprs")
def get_aprs(db: Session = Depends(get_db)):
    """Return APRS-formatted weather packet string."""
    if _aprs_gen is None:
        return {"error": "APRS not configured"}

    reading = (
        db.query(SensorReadingModel)
        .order_by(SensorReadingModel.timestamp.desc())
        .first()
    )
    if reading is None:
        return {"error": "No data available"}

    return {"aprs": _aprs_gen.format_packet(reading)}
