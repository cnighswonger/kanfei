"""GET /api/astronomy - Sun and moon data."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..services.astronomy import compute_astronomy
from .config import get_effective_config

logger = logging.getLogger(__name__)
router = APIRouter()


def _fmt_time(dt) -> str:
    """Format a datetime as a locale-friendly time string."""
    if dt is None:
        return "--"
    if hasattr(dt, "astimezone"):
        local = dt.astimezone()
        hour = local.hour % 12 or 12
        return f"{hour}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"
    return str(dt)


def _fmt_date(d) -> str:
    """Format a date for display."""
    if d is None:
        return "--"
    return d.strftime("%b %d, %Y")


def _fmt_duration(seconds) -> str:
    """Format seconds into Xh Ym string."""
    if seconds is None:
        return "--"
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    return f"{h}h {m}m"


def _fmt_change(seconds) -> str:
    """Format day length change in seconds to +/-Xm Ys."""
    if seconds is None:
        return "--"
    sign = "+" if seconds >= 0 else "-"
    total = abs(int(seconds))
    m = total // 60
    s = total % 60
    return f"{sign}{m}m {s}s"


@router.get("/astronomy")
def get_astronomy(db: Session = Depends(get_db)):
    """Return sunrise/sunset, twilight, moon phase data."""
    cfg = get_effective_config(db)
    lat = float(cfg.get("latitude", 0.0))
    lon = float(cfg.get("longitude", 0.0))
    elevation = float(cfg.get("elevation", 0.0))

    if lat == 0.0 and lon == 0.0:
        return {
            "sun": {
                "sunrise": "--", "sunset": "--", "solar_noon": "--",
                "day_length": "--", "day_change": "--",
                "civil_twilight": {"dawn": "--", "dusk": "--"},
                "nautical_twilight": {"dawn": "--", "dusk": "--"},
                "astronomical_twilight": {"dawn": "--", "dusk": "--"},
            },
            "moon": {
                "phase": "Unknown", "illumination": 0,
                "next_full": "--", "next_new": "--",
            },
        }

    try:
        elevation_m = elevation * 0.3048
        data = compute_astronomy(lat, lon, elevation_m)
    except Exception as e:
        logger.error("Astronomy computation failed: %s", e)
        return {"error": str(e)}

    tw = data.twilight
    moon = data.moon_info

    return {
        "sun": {
            "sunrise": _fmt_time(data.sunrise),
            "sunset": _fmt_time(data.sunset),
            "solar_noon": _fmt_time(data.solar_noon),
            "day_length": _fmt_duration(data.day_length_seconds),
            "day_change": _fmt_change(data.day_change_seconds),
            "civil_twilight": {
                "dawn": _fmt_time(tw.civil_start),
                "dusk": _fmt_time(tw.civil_end),
            },
            "nautical_twilight": {
                "dawn": _fmt_time(tw.nautical_start),
                "dusk": _fmt_time(tw.nautical_end),
            },
            "astronomical_twilight": {
                "dawn": _fmt_time(tw.astronomical_start),
                "dusk": _fmt_time(tw.astronomical_end),
            },
        },
        "moon": {
            "phase": moon.phase_name if moon else "Unknown",
            "illumination": moon.illumination_pct if moon else 0,
            "next_full": _fmt_date(moon.next_full_moon) if moon else "--",
            "next_new": _fmt_date(moon.next_new_moon) if moon else "--",
        },
    }
