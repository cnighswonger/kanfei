"""GET /api/metar, GET /api/aprs - Output format endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.sensor_reading import SensorReadingModel

router = APIRouter()

# Will be set by main.py
_metar_gen = None
_aprs_gen = None


def set_output_generators(metar, aprs):
    global _metar_gen, _aprs_gen
    _metar_gen = metar
    _aprs_gen = aprs


@router.get("/metar")
def get_metar(db: Session = Depends(get_db)):
    """Return METAR-formatted string from current conditions."""
    if _metar_gen is None:
        return {"error": "METAR generation not enabled"}

    reading = (
        db.query(SensorReadingModel)
        .order_by(SensorReadingModel.timestamp.desc())
        .first()
    )
    if reading is None:
        return {"error": "No data available"}

    return {"metar": _metar_gen.generate(reading)}


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
