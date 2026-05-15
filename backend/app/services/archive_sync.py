"""Download and backfill archive records from the WeatherLink SRAM.

On startup (before the LOOP poller begins), this module reads all archive
records from the station's 32KB circular buffer and inserts any that are
missing from our database.  This ensures no weather history is lost during
application downtime.
"""

import asyncio
import logging
import struct
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..protocol.link_driver import LinkDriver, bcd_decode
from ..protocol.constants import StationModel, BASIC_STATIONS
from ..models.database import SessionLocal
from ..models.archive_record import ArchiveRecordModel
from ..models.sensor_reading import SensorReadingModel
from ..utils.units import (
    f_tenths_to_c_tenths,
    inhg_thousandths_to_hpa_tenths,
    mph_to_ms_tenths,
)
from .calculations import (
    dew_point,
    equivalent_potential_temperature,
    feels_like,
    heat_index,
    wind_chill,
)

logger = logging.getLogger(__name__)

# Archive record sizes per station type (bytes).
ARCHIVE_RECORD_SIZE = {
    StationModel.WIZARD_III: 21,
    StationModel.WIZARD_II: 21,
    StationModel.MONITOR: 21,
    StationModel.PERCEPTION: 21,
    StationModel.OLD_LINK: 21,
    StationModel.GROWEATHER: 32,
    StationModel.ENERGY: 32,
    StationModel.HEALTH: 30,
}

# Maximum valid SRAM address (0x7F00-0x7FFF reserved for MDMP).
SRAM_MAX_ADDR = 0x7F00

# Compass-rose direction codes (0–15) → degrees, per Davis appendix.txt:F.
_WIND_DIR_DEGREES = [
    0, 22, 45, 68, 90, 112, 135, 158,
    180, 202, 225, 248, 270, 292, 315, 338,
]


# --- Archive-field invalid-sentinel filters ---
#
# The Davis SRAM archive image uses sentinel values to mark fields where the
# sensor was unplugged or the reading was rejected (database.txt:148-153).
# The existing per-station parsers already strip a few (humidity 0xFF, wind
# direction 0xFF) but pass the rest through unchanged, so values like
# -32768 °F/10 land in archive_records.  The live LOOP parser handles the
# full set in loop_packet._valid_temp_*/_valid_humidity/etc.  The bridge
# mirrors those rules here, before any unit conversion, so backfilled
# sensor_readings rows never carry sentinel-derived garbage to the chart,
# extremes, or upstream uploaders.

def _valid_archive_temp(value):
    """Davis archive temp (i16, 1/10 °F).  -32768 / 32767 = invalid."""
    if value is None or value == -32768 or value == 32767:
        return None
    if value > 2500 or value < -900:  # > 250 °F or < -90 °F: out-of-range
        return None
    return value


def _valid_archive_baro(value):
    """Davis archive barometer (u16, 1/1000 inHg).  0 / 0xFFFF = invalid."""
    if value is None or value == 0 or value == 0xFFFF:
        return None
    return value


def _valid_archive_u8(value):
    """Davis archive u8 field (wind speed, gust, UV).  0xFF = invalid."""
    if value is None or value == 0xFF:
        return None
    return value


def _valid_archive_humidity(value):
    """Davis archive humidity (u8).  0xFF or 0x80 (128) = invalid
    per database.txt:150-152."""
    if value is None or value == 0xFF or value == 0x80:
        return None
    return value


def _valid_archive_solar(value):
    """Davis archive solar radiation (u16, W/m²).  >= 0xFFF / 0xFFFF = invalid."""
    if value is None or value >= 0xFFF:
        return None
    return value


# --- Timestamp decoding ---

def _decode_archive_timestamp(raw: bytes, offset: int) -> Optional[datetime]:
    """Decode a 4-byte BCD archive timestamp.

    Format: hours(BCD), minutes(BCD), day(BCD), month(binary low nibble).
    Year is inferred from the current date.
    """
    if len(raw) < offset + 4:
        return None

    hours = bcd_decode(raw[offset])
    minutes = bcd_decode(raw[offset + 1])
    day = bcd_decode(raw[offset + 2])
    month = raw[offset + 3] & 0x0F

    if hours > 23 or minutes > 59 or day < 1 or day > 31 or month < 1 or month > 12:
        return None

    now = datetime.now()
    year = now.year
    try:
        dt = datetime(year, month, day, hours, minutes)
    except ValueError:
        return None

    # If the decoded date is in the future, assume it's from last year.
    if dt > now:
        year -= 1
        try:
            dt = datetime(year, month, day, hours, minutes)
        except ValueError:
            return None

    return dt


# --- Per-type archive record parsers ---

def _parse_basic_archive(data: bytes, address: int, station_type: int) -> Optional[dict]:
    """Parse a 21-byte Monitor/Wizard/Perception archive record."""
    if len(data) < 21:
        return None

    ts = _decode_archive_timestamp(data, 15)
    if ts is None:
        return None

    return {
        "archive_address": address,
        "record_time": ts,
        "station_type": station_type,
        "barometer": struct.unpack_from("<H", data, 0)[0],
        "inside_humidity": data[2] if data[2] != 0xFF else None,
        "outside_humidity": data[3] if data[3] != 0xFF else None,
        "rain_in_period": struct.unpack_from("<H", data, 4)[0],
        "inside_temp_avg": struct.unpack_from("<h", data, 6)[0],
        "outside_temp_avg": struct.unpack_from("<h", data, 8)[0],
        "wind_speed_avg": data[10],
        "wind_direction": data[11] if data[11] != 0xFF else None,
        "outside_temp_hi": struct.unpack_from("<h", data, 12)[0],
        "wind_gust": data[14],
        "outside_temp_lo": struct.unpack_from("<h", data, 19)[0],
    }


def _parse_groweather_archive(data: bytes, address: int, station_type: int) -> Optional[dict]:
    """Parse a 32-byte GroWeather archive record."""
    if len(data) < 32:
        return None

    ts = _decode_archive_timestamp(data, 12)
    if ts is None:
        return None

    return {
        "archive_address": address,
        "record_time": ts,
        "station_type": station_type,
        "barometer": struct.unpack_from("<H", data, 0)[0],
        "outside_humidity": data[2] if data[2] != 0xFF else None,
        "wind_speed_avg": data[3],
        "wind_gust": data[4],
        "wind_direction": data[5] if data[5] != 0xFF else None,
        "rain_in_period": struct.unpack_from("<H", data, 6)[0],
        "inside_temp_avg": struct.unpack_from("<h", data, 8)[0],
        "outside_temp_avg": struct.unpack_from("<h", data, 10)[0],
        "outside_temp_hi": struct.unpack_from("<h", data, 16)[0],
        "outside_temp_lo": struct.unpack_from("<h", data, 18)[0],
        "degree_days": struct.unpack_from("<H", data, 20)[0],
        "et": data[22],
        "wind_run": struct.unpack_from("<H", data, 24)[0],
        "solar_rad_avg": struct.unpack_from("<H", data, 26)[0],
        "solar_energy": struct.unpack_from("<H", data, 28)[0],
        "rain_rate_hi": data[30],
    }


def _parse_energy_archive(data: bytes, address: int, station_type: int) -> Optional[dict]:
    """Parse a 32-byte Energy archive record."""
    if len(data) < 32:
        return None

    ts = _decode_archive_timestamp(data, 12)
    if ts is None:
        return None

    return {
        "archive_address": address,
        "record_time": ts,
        "station_type": station_type,
        "barometer": struct.unpack_from("<H", data, 0)[0],
        "outside_humidity": data[2] if data[2] != 0xFF else None,
        "wind_speed_avg": data[3],
        "wind_gust": data[4],
        "wind_direction": data[5] if data[5] != 0xFF else None,
        "rain_in_period": struct.unpack_from("<H", data, 6)[0],
        "inside_temp_avg": struct.unpack_from("<h", data, 8)[0],
        "outside_temp_avg": struct.unpack_from("<h", data, 10)[0],
        "outside_temp_hi": struct.unpack_from("<h", data, 16)[0],
        "outside_temp_lo": struct.unpack_from("<h", data, 18)[0],
        "degree_days": data[20],
        "wind_run": struct.unpack_from("<H", data, 24)[0],
        "solar_rad_avg": struct.unpack_from("<H", data, 26)[0],
        "solar_energy": struct.unpack_from("<H", data, 28)[0],
        "rain_rate_hi": data[30],
    }


def _parse_health_archive(data: bytes, address: int, station_type: int) -> Optional[dict]:
    """Parse a 30-byte Health archive record."""
    if len(data) < 30:
        return None

    ts = _decode_archive_timestamp(data, 12)
    if ts is None:
        return None

    return {
        "archive_address": address,
        "record_time": ts,
        "station_type": station_type,
        "barometer": struct.unpack_from("<H", data, 0)[0],
        "wind_speed_avg": data[2],
        "wind_gust": data[3],
        "wind_direction": data[4] if data[4] != 0xFF else None,
        "rain_rate_hi": data[5],
        "rain_in_period": struct.unpack_from("<H", data, 6)[0],
        "inside_temp_avg": struct.unpack_from("<h", data, 8)[0],
        "outside_temp_avg": struct.unpack_from("<h", data, 10)[0],
        "outside_temp_hi": struct.unpack_from("<h", data, 16)[0],
        "outside_temp_lo": struct.unpack_from("<h", data, 18)[0],
        "inside_humidity": data[20] if data[20] != 0xFF else None,
        "outside_humidity": data[21] if data[21] != 0xFF else None,
        "uv_avg": data[22],
        "uv_dose": struct.unpack_from("<H", data, 24)[0],
        "solar_rad_avg": struct.unpack_from("<H", data, 26)[0],
    }


def parse_archive_record(
    data: bytes, address: int, model: StationModel
) -> Optional[dict]:
    """Parse an archive record based on station type."""
    station_type = model.value
    if model in BASIC_STATIONS:
        return _parse_basic_archive(data, address, station_type)
    elif model == StationModel.GROWEATHER:
        return _parse_groweather_archive(data, address, station_type)
    elif model == StationModel.ENERGY:
        return _parse_energy_archive(data, address, station_type)
    elif model == StationModel.HEALTH:
        return _parse_health_archive(data, address, station_type)
    return None


# --- Circular buffer iteration ---

def _iter_archive_addresses(
    old_ptr: int, new_ptr: int, record_size: int
) -> list[int]:
    """Generate list of archive record start addresses from the circular buffer.

    Returns empty list if buffer is empty (old_ptr == new_ptr).
    Handles wrap-around when new_ptr < old_ptr.
    """
    if old_ptr == new_ptr:
        return []

    addresses: list[int] = []
    if new_ptr > old_ptr:
        addr = old_ptr
        while addr < new_ptr:
            addresses.append(addr)
            addr += record_size
    else:
        # Wrap-around: old_ptr -> end, then 0 -> new_ptr
        addr = old_ptr
        while addr < SRAM_MAX_ADDR:
            addresses.append(addr)
            addr += record_size
        addr = 0
        while addr < new_ptr:
            addresses.append(addr)
            addr += record_size

    return addresses


# --- archive_records → sensor_readings projection ---

def _project_to_sensor_reading(record: dict) -> SensorReadingModel:
    """Build a SensorReadingModel from a parsed archive record dict.

    Davis on-device archive records store period aggregates (TinAvg/TOutAvg/
    WspAvg + THiOut/TLowOut/Gust) in native units (1/10 °F, 1/1000 inHg, mph,
    compass code 0–15).  This projects the avg/snapshot fields into SI tenths
    matching sensor_readings, recomputing derived values (heat index, dew
    point, wind chill, feels-like, theta-e) the same way the live poller does.

    The hi/lo period extremes from archive_records have no home in
    sensor_readings and are preserved only in archive_records.
    """
    # Strip Davis invalid sentinels before unit conversion (see helper
    # comments above) — otherwise -32768 °F/10 becomes -18382 °C/10 in
    # sensor_readings and surfaces as a -1838 °C spike on the chart.
    inside_temp_raw = _valid_archive_temp(record.get("inside_temp_avg"))
    outside_temp_raw = _valid_archive_temp(record.get("outside_temp_avg"))
    barometer_raw = _valid_archive_baro(record.get("barometer"))
    wind_speed_raw = _valid_archive_u8(record.get("wind_speed_avg"))
    wind_gust_raw = _valid_archive_u8(record.get("wind_gust"))
    inside_hum = _valid_archive_humidity(record.get("inside_humidity"))
    outside_hum = _valid_archive_humidity(record.get("outside_humidity"))
    solar_rad = _valid_archive_solar(record.get("solar_rad_avg"))
    uv_tenths = _valid_archive_u8(record.get("uv_avg"))

    inside_temp_c = (
        f_tenths_to_c_tenths(inside_temp_raw)
        if inside_temp_raw is not None else None
    )
    outside_temp_c = (
        f_tenths_to_c_tenths(outside_temp_raw)
        if outside_temp_raw is not None else None
    )
    barometer_hpa = (
        inhg_thousandths_to_hpa_tenths(barometer_raw)
        if barometer_raw is not None else None
    )
    wind_speed_ms = (
        mph_to_ms_tenths(wind_speed_raw)
        if wind_speed_raw is not None else None
    )
    wind_gust_ms = (
        mph_to_ms_tenths(wind_gust_raw)
        if wind_gust_raw is not None else None
    )
    wind_dir_deg = (
        _WIND_DIR_DEGREES[record["wind_direction"]]
        if record.get("wind_direction") is not None
        and 0 <= record["wind_direction"] <= 15
        else None
    )

    hi = dp = wc = fl = theta = None
    if outside_temp_c is not None and outside_hum is not None:
        hi = heat_index(outside_temp_c, outside_hum)
        dp = dew_point(outside_temp_c, outside_hum)
        if barometer_hpa is not None:
            theta = equivalent_potential_temperature(
                outside_temp_c, outside_hum, barometer_hpa
            )
    if outside_temp_c is not None and wind_speed_ms is not None:
        wc = wind_chill(outside_temp_c, wind_speed_ms)
    if (outside_temp_c is not None
            and outside_hum is not None
            and wind_speed_ms is not None):
        fl = feels_like(outside_temp_c, outside_hum, wind_speed_ms)

    return SensorReadingModel(
        timestamp=record["record_time"],
        station_type=record["station_type"],
        inside_temp=inside_temp_c,
        outside_temp=outside_temp_c,
        inside_humidity=inside_hum,
        outside_humidity=outside_hum,
        wind_speed=wind_speed_ms,
        wind_gust=wind_gust_ms,
        wind_direction=wind_dir_deg,
        barometer=barometer_hpa,
        solar_radiation=solar_rad,
        uv_index=uv_tenths,
        heat_index=hi,
        dew_point=dp,
        wind_chill=wc,
        feels_like=fl,
        theta_e=theta,
        # Rain fields are intentionally left NULL on backfilled rows:
        # rain_total is daily-cumulative (needs a known midnight baseline
        # we can't reconstruct from period deltas across a sleep gap), and
        # rain_rate would need the rain-collector resolution nibble decoded
        # against per-station config to be meaningful.
    )


# --- Orchestrator ---

async def async_sync_archive(driver: LinkDriver) -> int:
    """Download all archive records and insert missing ones into the database.

    Called on startup before the LOOP poller begins, and on reconnect.
    Returns the number of new records inserted.
    """
    if driver.station_model is None:
        logger.error("Cannot sync archive: station type not detected")
        return 0

    model = driver.station_model
    record_size = ARCHIVE_RECORD_SIZE.get(model)
    if record_size is None:
        logger.error("Unknown station model for archive: %s", model)
        return 0

    logger.info("Starting archive sync for %s (record size: %d bytes)", model.name, record_size)

    loop = asyncio.get_event_loop()

    # 1. Read archive pointers
    pointers = await loop.run_in_executor(None, driver.read_archive_pointers)
    if pointers is None:
        logger.error("Failed to read archive pointers")
        return 0

    new_ptr, old_ptr = pointers
    logger.info("Archive pointers: OldPtr=0x%04X NewPtr=0x%04X", old_ptr, new_ptr)

    if old_ptr == new_ptr:
        logger.info("Archive buffer is empty, nothing to sync")
        return 0

    # 2. Read archive period
    period = await loop.run_in_executor(None, driver.read_archive_period)
    logger.info("Archive period: %s minutes", period)

    # 3. Enumerate all record addresses
    addresses = _iter_archive_addresses(old_ptr, new_ptr, record_size)
    total = len(addresses)
    logger.info("Archive contains %d records to check", total)

    # 4. Download, parse, and insert
    inserted = 0
    skipped = 0
    errors = 0

    db = SessionLocal()
    try:
        for i, addr in enumerate(addresses):
            if i % 50 == 0 and i > 0:
                logger.info(
                    "Archive sync progress: %d/%d (inserted=%d, skipped=%d, errors=%d)",
                    i, total, inserted, skipped, errors,
                )

            raw = await loop.run_in_executor(
                None, driver.read_archive, addr, record_size
            )

            if raw is None:
                errors += 1
                continue

            record = parse_archive_record(raw, addr, model)
            if record is None:
                errors += 1
                continue

            record["archive_interval"] = period

            # Check for existing record
            existing = db.query(ArchiveRecordModel).filter_by(
                archive_address=record["archive_address"],
                record_time=record["record_time"],
            ).first()

            if existing is not None:
                skipped += 1
                continue

            db.add(ArchiveRecordModel(**record))
            inserted += 1

            # Bridge to sensor_readings so the history chart shows the
            # backfilled interval.  Each archive row at HH:MM:00 represents
            # the [HH:MM-N:00, HH:MM:00) period (N = archive_interval).
            # Skip the bridge insert when any live sample already falls in
            # that period — the live sample is a true instantaneous reading
            # and is preferred over a derived-from-aggregate row.
            #
            # The interval-aligned check avoids the bug where a symmetric
            # ±30 s window around the archive timestamp suppressed the
            # NEXT minute's archive row whenever a live row landed at
            # HH:MM:59 (Codex review on PR #145).
            rt = record["record_time"]
            interval = timedelta(minutes=period or 1)
            has_live_in_period = db.query(SensorReadingModel.id).filter(
                SensorReadingModel.timestamp >= rt - interval,
                SensorReadingModel.timestamp < rt,
            ).first() is not None
            if not has_live_in_period:
                db.add(_project_to_sensor_reading(record))

            if inserted % 100 == 0:
                db.commit()

        db.commit()
    except Exception as e:
        logger.error("Archive sync failed: %s", e, exc_info=True)
        db.rollback()
    finally:
        db.close()

    logger.info(
        "Archive sync complete: %d inserted, %d skipped, %d errors, %d total",
        inserted, skipped, errors, total,
    )
    return inserted
