"""GET /api/astronomy - Sun and moon data."""

import json
import logging
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..models.database import SessionLocal, get_db
from ..models.sensor_reading import SensorReadingModel
from ..services.astronomy import compute_astronomy
from .config import get_effective_config

logger = logging.getLogger(__name__)
router = APIRouter()


def _fmt_time(dt: Optional[datetime]) -> str:
    """Format a datetime as a locale-friendly time string."""
    if dt is None:
        return "--"
    if hasattr(dt, "astimezone"):
        local = dt.astimezone()
        hour = local.hour % 12 or 12
        return f"{hour}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"
    return str(dt)


def _fmt_date(d: Optional[date]) -> str:
    """Format a date for display."""
    if d is None:
        return "--"
    return d.strftime("%b %d, %Y")


def _fmt_duration(seconds: Optional[float]) -> str:
    """Format seconds into Xh Ym string."""
    if seconds is None:
        return "--"
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    return f"{h}h {m}m"


def _fmt_change(seconds: Optional[float]) -> str:
    """Format day length change in seconds to +/-Xm Ys."""
    if seconds is None:
        return "--"
    sign = "+" if seconds >= 0 else "-"
    total = abs(int(seconds))
    m = total // 60
    s = total % 60
    return f"{sign}{m}m {s}s"


def _fmt_hhmm_console(hm: Optional[int]) -> Optional[str]:
    """Format a Davis LOOP2 `hour*100 + minute` integer as `H:MM AM/PM`.

    LOOP2 encodes sunrise/sunset in the console's local time as a single
    integer: 615 → 06:15 AM, 1930 → 07:30 PM.  Returns None on out-of-range
    values (bounds guard) or a value of exactly 0, which the wire audit
    saw when LOOP2 offsets were wrong (`reference/vantage_fw433_wire_audit.md`
    §M2) and would be misleading to display as "12:00 AM".
    """
    if hm is None or hm == 0:
        return None
    h = hm // 100
    m = hm % 100
    if h < 0 or h > 23 or m < 0 or m > 59:
        return None
    hour12 = h % 12 or 12
    ampm = "AM" if h < 12 else "PM"
    return f"{hour12}:{m:02d} {ampm}"


def _read_console_sun_times() -> tuple[Optional[str], Optional[str]]:
    """Return `(sunrise_str, sunset_str)` from the latest sensor reading's
    ``extra_json``, both formatted to match ``_fmt_time`` above.

    Davis Vantage LOOP2 supplies the console's own sunrise/sunset — the
    values it computes from its own configured latitude/longitude and
    displays on the LCD.  When present, prefer those over astral's own
    computation (issue #237) so the API and the console's face don't
    disagree by a minute or two around whichever timezone-and-refraction
    conventions each computes with.  Either value ``None`` on:

      - No readings in the DB yet.
      - Latest row has no ``extra_json``.
      - Extras don't include the sunrise/sunset keys (non-Davis driver,
        Davis before the first LOOP2 with those bytes parsed).
      - Individual value is out-of-range or the wire-audit `0` sentinel.
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
        return None, None
    try:
        extras = json.loads(row[0])
    except (ValueError, TypeError):
        return None, None
    if not isinstance(extras, dict):
        return None, None
    return _fmt_hhmm_console(extras.get("sunrise")), _fmt_hhmm_console(extras.get("sunset"))


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
                "sunrise": "--", "sunrise_source": "astral",
                "sunset": "--", "sunset_source": "astral",
                "solar_noon": "--",
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

    # Console's own sunrise/sunset override astral's when reported (#237).
    # Only sunrise and sunset — the console doesn't report solar noon or
    # twilight ranges, so those stay astral-derived.
    console_sunrise, console_sunset = _read_console_sun_times()
    sunrise_source = "console" if console_sunrise else "astral"
    sunset_source = "console" if console_sunset else "astral"

    return {
        "sun": {
            "sunrise": console_sunrise or _fmt_time(data.sunrise),
            "sunrise_source": sunrise_source,
            "sunset": console_sunset or _fmt_time(data.sunset),
            "sunset_source": sunset_source,
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
