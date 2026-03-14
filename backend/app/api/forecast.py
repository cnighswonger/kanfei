"""GET /api/forecast - Zambretti barometric + optional NWS forecast."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.sensor_reading import SensorReadingModel
from ..services.forecast_local import zambretti_forecast
from ..services.forecast_nws import fetch_nws_forecast
from .config import get_effective_config

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/forecast")
async def get_forecast(db: Session = Depends(get_db)):
    """Return Zambretti local forecast and optional NWS grid forecast."""
    now = datetime.now(timezone.utc)

    # --- Zambretti (local barometric) ---
    local_forecast = None

    latest = (
        db.query(SensorReadingModel)
        .filter(SensorReadingModel.barometer.isnot(None))
        .order_by(SensorReadingModel.timestamp.desc())
        .first()
    )

    if latest is not None and latest.barometer is not None:
        cutoff_3h = datetime.fromtimestamp(
            now.timestamp() - 3 * 3600, tz=timezone.utc
        )
        oldest = (
            db.query(SensorReadingModel)
            .filter(SensorReadingModel.barometer.isnot(None))
            .filter(SensorReadingModel.timestamp >= cutoff_3h)
            .order_by(SensorReadingModel.timestamp)
            .first()
        )

        pressure_change = (
            latest.barometer - oldest.barometer
            if oldest is not None and oldest.barometer is not None
            else 0
        )

        result = zambretti_forecast(
            pressure_thousandths=latest.barometer,
            pressure_change_3h=pressure_change,
            wind_dir_deg=latest.wind_direction,
            month=now.month,
        )

        local_forecast = {
            "source": "zambretti",
            "text": result.forecast_text,
            "confidence": round(result.confidence * 100),
            "trend": result.trend,
            "updated": now.isoformat(),
        }

    # --- NWS (grid forecast) ---
    nws_forecast = None

    cfg = get_effective_config(db)
    lat = float(cfg.get("latitude", 0.0))
    lon = float(cfg.get("longitude", 0.0))
    nws_enabled = bool(cfg.get("nws_enabled", False))

    has_location = not (lat == 0.0 and lon == 0.0)
    if nws_enabled and has_location:
        try:
            nws = await fetch_nws_forecast(lat, lon)
            if nws is not None and nws.periods:
                nws_forecast = {
                    "source": "nws",
                    "periods": [
                        {
                            "name": p.name,
                            "temperature": p.temperature,
                            "wind": p.wind,
                            "precipitation_pct": p.precipitation_pct or 0,
                            "text": p.text,
                            "icon_url": p.icon_url,
                            "short_forecast": p.short_forecast,
                            "is_daytime": p.is_daytime,
                        }
                        for p in nws.periods
                    ],
                    "updated": datetime.fromtimestamp(
                        nws.fetched_at, tz=timezone.utc
                    ).isoformat(),
                }
        except Exception as e:
            logger.warning("NWS forecast fetch failed: %s", e)

    return {"local": local_forecast, "nws": nws_forecast}
