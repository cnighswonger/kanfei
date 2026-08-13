"""Daily cumulative solar radiation integration.

Solar radiation is reported as an instantaneous flux in W/m² on every poll.
The daily *energy* — the quantity a solar-panel or agricultural user cares
about — is the time integral of that flux from local midnight to now.

Davis stations do not report a native daily-solar-energy accumulator (the
`SOLAR_ALARM` register is an instantaneous threshold, not a running sum),
so Kanfei computes the integral itself from stored ``sensor_readings``.

The integration is a trapezoid over irregularly-spaced samples:

    E = Σ ((f_i + f_{i+1}) / 2) * (t_{i+1} - t_i)

Units in this module are SI: joules per square metre (J/m²). Callers
(the API layer) convert to the user's preferred display unit:

    1 MJ/m²  = 1_000_000 J/m²      (agricultural / meteorological)
    1 Wh/m²  = 3600 J/m²
    1 kWh/m² = 3_600_000 J/m²      (solar-panel convention)
"""

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import asc
from sqlalchemy.orm import Session

from ..models.sensor_reading import SensorReadingModel
from ..models.station_config import StationConfigModel


def _local_midnight_utc_naive(tz: ZoneInfo) -> datetime:
    """Return today's local-midnight moment as a naive UTC datetime — the
    shape `sensor_readings.timestamp` uses for filtering (see the same
    conversion in ``logger_main._last_reading_before_local_midnight_mm``).
    """
    now_local = datetime.now(tz)
    today_local_midnight = now_local.replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    return today_local_midnight.astimezone(timezone.utc).replace(tzinfo=None)


def _get_station_timezone(db: Session) -> ZoneInfo:
    row = db.query(StationConfigModel).filter_by(key="station_timezone").first()
    if row and row.value:
        try:
            return ZoneInfo(row.value)
        except Exception:
            pass
    # Fall back to system local tz.
    return ZoneInfo(str(datetime.now().astimezone().tzinfo))


def compute_daily_solar_energy_j_per_m2(db: Session) -> Optional[float]:
    """Trapezoid-integrate today's solar radiation samples since local
    midnight and return the accumulated energy in J/m².

    Returns ``None`` when:
      - The station has no solar sensor (no non-null solar_radiation rows).
      - Only a single sample has landed today (nothing to integrate over).
      - The timezone lookup or DB read fails.
    """
    try:
        tz = _get_station_timezone(db)
    except Exception:
        return None

    cutoff = _local_midnight_utc_naive(tz)

    rows = (
        db.query(
            SensorReadingModel.timestamp,
            SensorReadingModel.solar_radiation,
        )
        .filter(SensorReadingModel.timestamp >= cutoff)
        .filter(SensorReadingModel.solar_radiation.isnot(None))
        .order_by(asc(SensorReadingModel.timestamp))
        .all()
    )

    if len(rows) < 2:
        return None

    joules_per_m2 = 0.0
    for prev, curr in zip(rows, rows[1:]):
        dt_seconds = (curr[0] - prev[0]).total_seconds()
        if dt_seconds <= 0:
            continue
        # Trapezoid area between two samples: W/m² * seconds → J/m²
        avg_flux = (prev[1] + curr[1]) / 2.0
        joules_per_m2 += avg_flux * dt_seconds

    return joules_per_m2


def joules_to_display_unit(
    joules_per_m2: Optional[float], unit: str,
) -> Optional[float]:
    """Convert J/m² to the caller's chosen display unit.

    Accepts ``"MJ/m²"``, ``"kWh/m²"``, ``"Wh/m²"``. Returns ``None`` when
    the input is ``None`` or the unit isn't recognised — the API layer
    is expected to have validated the unit already, but we don't crash
    on a bad one.
    """
    if joules_per_m2 is None:
        return None
    if unit == "MJ/m²":
        return round(joules_per_m2 / 1_000_000.0, 2)
    if unit == "kWh/m²":
        return round(joules_per_m2 / 3_600_000.0, 3)
    if unit == "Wh/m²":
        return round(joules_per_m2 / 3600.0, 1)
    return None
