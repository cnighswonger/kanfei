"""Download and backfill archive records from the WeatherLink SRAM.

On startup (before the LOOP poller begins), this module reads all archive
records from the station's 32KB circular buffer and inserts any that are
missing from our database.  This ensures no weather history is lost during
application downtime.
"""

import asyncio
import logging
import struct
from datetime import datetime, timezone
from typing import Optional

from ..protocol.link_driver import LinkDriver, bcd_decode
from ..protocol.constants import StationModel, BASIC_STATIONS
from ..models.database import SessionLocal
from ..models.archive_record import ArchiveRecordModel

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
