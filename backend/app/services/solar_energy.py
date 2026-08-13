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

from datetime import date, datetime, timedelta, timezone
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


def compute_daily_solar_energy_series(
    db: Session, days: int,
) -> list[dict]:
    """Return one integrated solar-energy value per local calendar day
    for the last ``days`` days, oldest first.

    Shape:

        [
          {"date": "2026-08-11", "j_per_m2": 21_400_000.0},
          {"date": "2026-08-12", "j_per_m2": 18_950_000.0},
          {"date": "2026-08-13", "j_per_m2": 9_100_000.0},  # today, partial
          ...
        ]

    Days with fewer than two samples (no solar sensor, station offline
    all day) still appear in the list with ``j_per_m2: None`` so the
    caller can render a gap without a separate absence-lookup query.

    The last entry is always today up to the current instant — it's a
    partial-day value that grows as the day progresses.

    ``days`` is clamped to ``[1, 366]`` to prevent an unbounded query.
    """
    days = max(1, min(int(days), 366))
    try:
        tz = _get_station_timezone(db)
    except Exception:
        return []

    # Time-window: from N-1 days back at local midnight, through "now".
    today_local_midnight = datetime.now(tz).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    window_start_local = today_local_midnight - timedelta(days=days - 1)
    window_start_utc_naive = (
        window_start_local.astimezone(timezone.utc).replace(tzinfo=None)
    )

    # One query pulls everything in-window; bucket in Python by local date.
    rows = (
        db.query(
            SensorReadingModel.timestamp,
            SensorReadingModel.solar_radiation,
        )
        .filter(SensorReadingModel.timestamp >= window_start_utc_naive)
        .filter(SensorReadingModel.solar_radiation.isnot(None))
        .order_by(asc(SensorReadingModel.timestamp))
        .all()
    )

    # Group rows by their local calendar date.  Timestamps in the DB are
    # naive UTC — attach UTC tz, then convert to the station's local tz
    # so the bucket boundary aligns with local midnight (same rule the
    # single-day helper above uses).
    per_day_rows: dict[date, list[tuple[datetime, int]]] = {}
    for ts_naive, flux in rows:
        ts_utc = ts_naive.replace(tzinfo=timezone.utc)
        local_date = ts_utc.astimezone(tz).date()
        per_day_rows.setdefault(local_date, []).append((ts_utc, flux))

    # Walk the window day by day so absent days appear as None (not
    # missing from the output list).
    result: list[dict] = []
    for i in range(days):
        d = (window_start_local + timedelta(days=i)).date()
        day_rows = per_day_rows.get(d, [])
        if len(day_rows) < 2:
            result.append({"date": d.isoformat(), "j_per_m2": None})
            continue
        joules_per_m2 = 0.0
        for (t0, f0), (t1, f1) in zip(day_rows, day_rows[1:]):
            dt_seconds = (t1 - t0).total_seconds()
            if dt_seconds <= 0:
                continue
            avg_flux = (f0 + f1) / 2.0
            joules_per_m2 += avg_flux * dt_seconds
        result.append({"date": d.isoformat(), "j_per_m2": joules_per_m2})
    return result


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
