"""DMPAFT catchup — backfill sensor_readings from the Vantage console
after a poll gap.

Umbrella #472 / sub-issue #477.  The Vue console holds a rolling
ring buffer of archive records (~2560 records; ~1.7 days at
1-min interval).  When the daemon reconnects after a stall, the
LINE data ``/api/history`` charts comes from ``sensor_readings``,
which stops advancing when the poller stops.  This module drops the
gap onto the console's archive rows so the chart is continuous
across the outage.

Scope:

- Vantage-only.  Legacy stations already have their own bespoke
  backfill via ``archive_sync.py``, which walks the SRAM directly.
- Writes only to ``sensor_readings``.  ``archive_records`` is
  address-keyed (unique constraint ``archive_address``,
  ``record_time``); DMPAFT rows have no meaningful address, and
  the archive-records lens isn't what ``/api/history`` looks at.
- Idempotent by timestamp — running twice does not duplicate rows.
- Duty-cycle safe: hardware I/O is bounded by ``max_records`` and
  the caller runs this as a background task so the poll cadence
  isn't blocked.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol

from sqlalchemy import func

from ..models.database import SessionLocal
from ..models.sensor_reading import SensorReadingModel
from ..protocol.vantage.archive import VantageArchiveRecord
from .calculations import (
    dew_point,
    equivalent_potential_temperature,
    feels_like,
    heat_index,
    wind_chill,
)

logger = logging.getLogger(__name__)

# Hard cap on records to accept from a single DMPAFT call.  The
# console's ring holds ~2560 records; 3000 is a comfortable ceiling
# that catches the whole buffer without leaving unbounded work for a
# runaway driver bug.  Matches the guard #477 specified.
MAX_BACKFILL_RECORDS = 3000

# Fallback "after" horizon when we have no live-sample floor to key
# off (fresh install, or the DB was cleared).  3 days is well beyond
# the ring at 1-min interval; on a 30-min-interval station it grabs
# ~144 records, still well below MAX_BACKFILL_RECORDS.
FRESH_INSTALL_HORIZON = timedelta(days=3)


class _VantageBackfillDriver(Protocol):
    """Structural type for the tiny driver surface this module uses.

    Kept protocol-shaped rather than importing VantageDriver so the
    tests can pass a plain stub without dragging in the whole driver
    stack.
    """

    async def async_dmpaft(
        self, after: datetime,
    ) -> list[VantageArchiveRecord]: ...


def _local_tzinfo() -> Any:
    """Return the system's current local timezone.

    The Vantage console's clock is set to system local time (see
    ``LoggerDaemon._connect`` clock-sync block), so DMPAFT records
    come back as naive datetimes in the same local zone.  Live
    ``sensor_readings`` rows are written as UTC by ``Poller``, so
    backfilled rows need the same convention or ``/api/history``
    will chart them at the wrong hour.
    """
    return datetime.now().astimezone().tzinfo


def _to_utc_naive(local_naive: datetime) -> datetime:
    """Convert a naive local-time datetime to a naive-UTC datetime.

    Naive-in / naive-out so the storage convention matches the
    live-write path exactly — ``Poller`` writes
    ``datetime.now(timezone.utc)`` and SQLAlchemy's ``DateTime`` column
    silently drops the tz info, so what's stored is naive-UTC.
    """
    aware_local = local_naive.replace(tzinfo=_local_tzinfo())
    aware_utc = aware_local.astimezone(timezone.utc)
    return aware_utc.replace(tzinfo=None)


def _floor_timestamp() -> datetime:
    """Timestamp to ask the console for records AFTER.

    Uses the newest ``sensor_readings`` row when one exists (the tight
    reconnect case), else falls back to a fixed horizon so a fresh
    install doesn't pull the entire ring.  Returned in the console's
    local zone as a naive datetime, since that is what DMPAFT
    compares against.
    """
    db = SessionLocal()
    try:
        newest_utc = db.query(
            func.max(SensorReadingModel.timestamp),
        ).scalar()
    finally:
        db.close()

    if newest_utc is None:
        local_naive = (
            datetime.now(timezone.utc) - FRESH_INSTALL_HORIZON
        ).astimezone().replace(tzinfo=None)
        return local_naive

    # sensor_readings.timestamp is stored as naive UTC (see
    # ``_to_utc_naive`` note).  Attach UTC, convert to local, strip tz.
    return (
        newest_utc.replace(tzinfo=timezone.utc)
        .astimezone(_local_tzinfo())
        .replace(tzinfo=None)
    )


async def async_backfill_from_vantage(
    driver: _VantageBackfillDriver,
    station_type_code: int,
    max_records: int = MAX_BACKFILL_RECORDS,
) -> int:
    """Pull archive records after the last-known live sample and
    insert them into ``sensor_readings``.  Returns count inserted.

    Safe to call redundantly — dedupes on ``timestamp`` before
    insert, so overlap with existing live samples or a prior
    backfill drops silently to a no-op for those rows.
    """
    after_local = _floor_timestamp()
    logger.info(
        "DMPAFT catchup: requesting archive records after %s (local)",
        after_local.isoformat(),
    )
    try:
        records = await driver.async_dmpaft(after=after_local)
    except Exception as exc:
        logger.warning("DMPAFT catchup failed: %s", exc)
        return 0

    if not records:
        logger.info("DMPAFT catchup: no records returned")
        return 0

    if len(records) > max_records:
        logger.warning(
            "DMPAFT catchup: driver returned %d records; capping to %d",
            len(records), max_records,
        )
        records = records[:max_records]

    inserted = 0
    skipped = 0
    db = SessionLocal()
    try:
        for rec in records:
            ts_utc = _to_utc_naive(rec.timestamp)
            existing = db.query(SensorReadingModel.id).filter(
                SensorReadingModel.timestamp == ts_utc,
            ).first()
            if existing is not None:
                skipped += 1
                continue
            db.add(_project_to_sensor_reading(rec, ts_utc, station_type_code))
            inserted += 1
            if inserted % 200 == 0:
                db.commit()
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("DMPAFT catchup insert failed: %s", exc, exc_info=True)
        return inserted
    finally:
        db.close()

    logger.info(
        "DMPAFT catchup: %d inserted, %d skipped (already present)",
        inserted, skipped,
    )
    return inserted


def _tenths(value: Optional[float]) -> Optional[int]:
    """Scale to storage tenths, matching the live-poller convention."""
    if value is None:
        return None
    return round(value * 10)


def _project_to_sensor_reading(
    rec: VantageArchiveRecord,
    ts_utc: datetime,
    station_type_code: int,
) -> SensorReadingModel:
    """Project a VantageArchiveRecord onto SensorReadingModel columns.

    Field choices follow the live poller (``Poller._process_reading``)
    so a backfilled row displays identically to a live one on the
    chart.  The averaged fields on VantageArchiveRecord map to the
    ``sensor_readings`` snapshot columns; the hi/lo companions
    aren't stored in the live path so they're dropped here too.

    Rain fields are intentionally NULL for the same reason
    ``archive_sync._project_to_sensor_reading`` leaves them NULL:
    ``rain_total`` is a daily-cumulative counter with no meaningful
    baseline reconstructible from period deltas across a gap.
    """
    outside_temp_c = rec.outside_temp_avg
    inside_temp_c = rec.inside_temp
    outside_hum = rec.outside_humidity
    inside_hum = rec.inside_humidity
    wind_speed_ms = rec.wind_speed_avg
    wind_gust_ms = rec.wind_speed_hi
    wind_dir = rec.wind_dir_prevailing
    barometer_hpa = rec.barometer

    hi = dp = wc = fl = theta = None
    if outside_temp_c is not None and outside_hum is not None:
        hi = _tenths(heat_index(outside_temp_c, outside_hum))
        dp = _tenths(dew_point(outside_temp_c, outside_hum))
        if barometer_hpa is not None:
            theta = _tenths(equivalent_potential_temperature(
                outside_temp_c, outside_hum, barometer_hpa,
            ))
    if outside_temp_c is not None and wind_speed_ms is not None:
        wc = _tenths(wind_chill(outside_temp_c, wind_speed_ms))
    if (outside_temp_c is not None
            and outside_hum is not None
            and wind_speed_ms is not None):
        fl = _tenths(feels_like(outside_temp_c, outside_hum, wind_speed_ms))

    # Backfilled rows are flagged in extra_json so a debugger tracing
    # a chart anomaly can tell "this cell came from DMPAFT catchup"
    # from "this cell came from the live poller."  The rest of the
    # app treats them identically.
    extra = json.dumps({"backfill_source": "vantage_dmpaft"})

    return SensorReadingModel(
        timestamp=ts_utc,
        station_type=station_type_code,
        inside_temp=_tenths(inside_temp_c),
        outside_temp=_tenths(outside_temp_c),
        inside_humidity=inside_hum,
        outside_humidity=outside_hum,
        wind_speed=_tenths(wind_speed_ms),
        wind_gust=_tenths(wind_gust_ms),
        wind_direction=wind_dir,
        barometer=_tenths(barometer_hpa),
        solar_radiation=rec.solar_radiation,
        uv_index=_tenths(rec.uv_index),
        heat_index=hi,
        dew_point=dp,
        wind_chill=wc,
        feels_like=fl,
        theta_e=theta,
        extra_json=extra,
    )
