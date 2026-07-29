"""Resolve a persisted station_type code to a human-readable model name.

`sensor_readings.station_type` is a bare integer whose meaning depends on
which driver produced the reading: legacy serial stations use
`protocol.constants.StationModel` (0-15), Vantage stations use
`protocol.vantage.constants.VantageModel` (16-17).  The two ranges do not
currently overlap, but nothing enforces that, so resolution is done against
the driver family recorded in station_config rather than by guessing.

Before #215 this lookup was done inline against StationModel alone.  A
Vantage reading (which was also being persisted as 0 — see
logger_main._driver_model_code) resolved to StationModel(0) = "Weather
Wizard III": a confidently wrong answer rather than an unknown one.
"""

from typing import Optional

from sqlalchemy.orm import Session

from ..models.station_config import StationConfigModel
from ..protocol.constants import STATION_NAMES, StationModel
from ..protocol.vantage.constants import VANTAGE_NAMES, VantageModel

UNKNOWN = "Unknown"


def _lookup(code: int, enum_cls, names: dict) -> Optional[str]:
    try:
        return names.get(enum_cls(code))
    except ValueError:
        return None


def resolve_station_name(
    station_type: Optional[int],
    db: Optional[Session] = None,
    driver_type: Optional[str] = None,
) -> str:
    """Return a display name for a persisted station_type code.

    `driver_type` selects the enum.  If not given it is read from
    station_config; if that is unavailable both enums are tried, legacy
    first, and an unmatched code yields "Unknown".
    """
    if station_type is None:
        return UNKNOWN

    # -1 is the "no model code" sentinel written for drivers that have none
    # (see logger_main.STATION_TYPE_UNKNOWN).  It collides numerically with
    # VantageModel.UNKNOWN, so resolve it here rather than let the fallback
    # below label a non-Vantage station "Vantage (unknown model)".
    if station_type == -1 and driver_type != "vantage":
        return UNKNOWN

    if driver_type is None and db is not None:
        row = (
            db.query(StationConfigModel)
            .filter_by(key="station_driver_type")
            .first()
        )
        driver_type = row.value if row else None

    if driver_type == "vantage":
        return _lookup(station_type, VantageModel, VANTAGE_NAMES) or UNKNOWN
    if driver_type == "legacy":
        return _lookup(station_type, StationModel, STATION_NAMES) or UNKNOWN

    # Unknown or non-serial driver (weatherlink_ip, ecowitt, tempest, ...).
    # Those have no numeric model code, so a code here is either legacy data
    # predating the driver_type column or a genuine unknown.
    return (
        _lookup(station_type, StationModel, STATION_NAMES)
        or _lookup(station_type, VantageModel, VANTAGE_NAMES)
        or UNKNOWN
    )
