"""DMPAFT archive record parser for the Davis Vantage protocol.

Parses 52-byte archive records (Rev A and Rev B) and 267-byte archive
pages.  Used by VantageDriver.dmpaft() for historical data retrieval.

Reference: Davis Vantage Serial Communication Reference v2.6.1,
           weewx vantage.py driver.
"""

import logging
import struct
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..crc import crc_validate
from .constants import (
    ARCHIVE_PAGE_SIZE,
    ARCHIVE_RECORD_SIZE,
    ARCHIVE_RECORDS_PER_PAGE,
    INVALID_TEMP,
    INVALID_EXTRA_TEMP,
)

logger = logging.getLogger(__name__)

# Wind direction codes (0-15) → degrees
WIND_DIR_DEGREES = [
    0, 22.5, 45, 67.5, 90, 112.5, 135, 157.5,
    180, 202.5, 225, 247.5, 270, 292.5, 315, 337.5,
]


@dataclass
class VantageArchiveRecord:
    """Parsed 52-byte Vantage archive record."""
    timestamp: datetime
    outside_temp_avg: Optional[float] = None    # °F
    outside_temp_hi: Optional[float] = None     # °F
    outside_temp_lo: Optional[float] = None     # °F
    inside_temp: Optional[float] = None         # °F
    inside_humidity: Optional[int] = None       # %
    outside_humidity: Optional[int] = None      # %
    barometer: Optional[float] = None           # inHg
    wind_speed_avg: Optional[int] = None        # mph
    wind_speed_hi: Optional[int] = None         # mph
    wind_dir_hi: Optional[int] = None           # degrees
    wind_dir_prevailing: Optional[int] = None   # degrees
    rainfall: Optional[float] = None            # inches
    rain_rate_hi: Optional[float] = None        # in/hr
    solar_radiation: Optional[int] = None       # W/m²
    solar_radiation_hi: Optional[int] = None    # W/m²
    uv_index: Optional[float] = None            # index
    uv_index_hi: Optional[float] = None         # index
    et: Optional[float] = None                  # inches
    forecast_rule: Optional[int] = None
    record_type: int = 0xFF                     # 0xFF = Rev A, 0x00 = Rev B
    soil_temps: list[Optional[float]] = field(default_factory=list)
    soil_moistures: list[Optional[int]] = field(default_factory=list)
    leaf_temps: list[Optional[float]] = field(default_factory=list)
    leaf_wetnesses: list[Optional[int]] = field(default_factory=list)
    extra_temps: list[Optional[float]] = field(default_factory=list)
    extra_humidities: list[Optional[int]] = field(default_factory=list)


# --------------- Date/time helpers ---------------

def decode_datestamp(raw: int) -> tuple[int, int, int]:
    """Decode bit-packed date: day[0:4], month[5:8], year+2000[9:15].

    Returns (year, month, day).
    """
    day = raw & 0x1F
    month = (raw >> 5) & 0x0F
    year = ((raw >> 9) & 0x7F) + 2000
    return year, month, day


def decode_timestamp(raw: int) -> tuple[int, int]:
    """Decode time value = hour*100 + minute.

    Returns (hour, minute).
    """
    return raw // 100, raw % 100


def _decode_wind_dir(code: int) -> Optional[int]:
    """Convert 0-15 wind direction code to degrees."""
    if code > 15:
        return None
    return round(WIND_DIR_DEGREES[code])


# --------------- Record parser ---------------

def parse_archive_record(
    data: bytes,
    rain_click_inches: float,
) -> Optional[VantageArchiveRecord]:
    """Parse a single 52-byte archive record.

    Record layout:
      [0:2]   date stamp (u16 LE, bit-packed)
      [2:4]   time stamp (u16 LE, hour*100+min)
      [4:6]   outside temp avg (i16 LE, tenths °F)
      [6:8]   outside temp hi (i16 LE, tenths °F)
      [8:10]  outside temp lo (i16 LE, tenths °F)
      [10:12] rainfall (u16 LE, clicks)
      [12:14] high rain rate (u16 LE, clicks/hr)
      [14:16] barometer (u16 LE, thousandths inHg)
      [16:18] solar radiation (u16 LE, W/m²)
      [18:20] wind samples (u16 LE)
      [20:22] inside temp (i16 LE, tenths °F)
      [22]    inside humidity (u8, %)
      [23]    outside humidity (u8, %)
      [24]    avg wind speed (u8, mph for Rev A, 0.1 mph for Rev B)
      [25]    high wind speed (u8, mph)
      [26]    dir of high wind (u8, coded 0-15)
      [27]    prevailing wind dir (u8, coded 0-15)
      [28]    avg UV index (u8, tenths)
      [29]    ET (u8, thousandths inch)
      [30:32] high solar (u16 LE, W/m²)  [Rev B]
      [32]    high UV (u8, tenths)        [Rev B]
      [33]    forecast rule (u8)          [Rev B]
      [34:36] leaf temps ×2 (u8, temp+90) [Rev B]
      [36:38] leaf wetnesses ×2 (u8)      [Rev B]
      [38:42] soil temps ×4 (u8, temp+90) [Rev B]
      [42]    record type (0xFF = Rev A, 0x00 = Rev B)
      [43:45] extra humidities ×2 (u8)    [Rev B]
      [45:48] extra temps ×3 (u8, temp+90) [Rev B]
      [48:50] soil moistures ×2 (u8, cb)  [Rev B]
    """
    if len(data) < ARCHIVE_RECORD_SIZE:
        return None

    # Decode timestamp
    date_raw = struct.unpack_from("<H", data, 0)[0]
    time_raw = struct.unpack_from("<H", data, 2)[0]

    # Skip empty records (all 0xFF or date = 0xFFFF)
    if date_raw == 0xFFFF or date_raw == 0:
        return None

    try:
        year, month, day = decode_datestamp(date_raw)
        hour, minute = decode_timestamp(time_raw)
        ts = datetime(year, month, day, hour, minute)
    except (ValueError, OverflowError):
        logger.debug("Invalid archive timestamp: date=%04X time=%04X", date_raw, time_raw)
        return None

    # Determine record type
    record_type = data[42]
    is_rev_b = (record_type == 0x00)

    # Temperatures (tenths °F → float °F)
    def _temp(offset: int) -> Optional[float]:
        val = struct.unpack_from("<h", data, offset)[0]
        if val == INVALID_TEMP or val == -32768:
            return None
        return val / 10.0

    def _extra_temp(raw: int) -> Optional[float]:
        if raw == INVALID_EXTRA_TEMP:
            return None
        return float(raw - 90)

    rec = VantageArchiveRecord(timestamp=ts)
    rec.record_type = record_type
    rec.outside_temp_avg = _temp(4)
    rec.outside_temp_hi = _temp(6)
    rec.outside_temp_lo = _temp(8)
    rec.inside_temp = _temp(20)

    # Rain
    rain_clicks = struct.unpack_from("<H", data, 10)[0]
    rec.rainfall = rain_clicks * rain_click_inches if rain_clicks != 0xFFFF else None
    rate_clicks = struct.unpack_from("<H", data, 12)[0]
    rec.rain_rate_hi = rate_clicks * rain_click_inches if rate_clicks != 0xFFFF else None

    # Barometer
    baro = struct.unpack_from("<H", data, 14)[0]
    rec.barometer = baro / 1000.0 if baro not in (0, 0xFFFF) else None

    # Solar
    solar = struct.unpack_from("<H", data, 16)[0]
    rec.solar_radiation = solar if solar != 0x7FFF else None

    # Inside humidity
    rec.inside_humidity = data[22] if data[22] != 0xFF and data[22] <= 100 else None
    rec.outside_humidity = data[23] if data[23] != 0xFF and data[23] <= 100 else None

    # Wind
    rec.wind_speed_avg = data[24] if data[24] != 0xFF else None
    rec.wind_speed_hi = data[25] if data[25] != 0xFF else None
    rec.wind_dir_hi = _decode_wind_dir(data[26])
    rec.wind_dir_prevailing = _decode_wind_dir(data[27])

    # UV
    uv_raw = data[28]
    rec.uv_index = uv_raw / 10.0 if uv_raw != 0xFF else None

    # ET
    et_raw = data[29]
    rec.et = et_raw / 1000.0 if et_raw != 0xFF else None

    # Rev B extras
    if is_rev_b:
        solar_hi = struct.unpack_from("<H", data, 30)[0]
        rec.solar_radiation_hi = solar_hi if solar_hi != 0x7FFF else None

        uv_hi = data[32]
        rec.uv_index_hi = uv_hi / 10.0 if uv_hi != 0xFF else None

        rec.forecast_rule = data[33] if data[33] != 0xFF else None

        # Leaf temps (2)
        rec.leaf_temps = [_extra_temp(data[i]) for i in range(34, 36)]
        # Leaf wetnesses (2)
        rec.leaf_wetnesses = [
            data[i] if data[i] != 0xFF else None for i in range(36, 38)
        ]
        # Soil temps (4)
        rec.soil_temps = [_extra_temp(data[i]) for i in range(38, 42)]
        # Extra humidities (2)
        rec.extra_humidities = [
            data[i] if data[i] != 0xFF and data[i] <= 100 else None
            for i in range(43, 45)
        ]
        # Extra temps (3)
        rec.extra_temps = [_extra_temp(data[i]) for i in range(45, 48)]
        # Soil moistures (2)
        rec.soil_moistures = [
            data[i] if data[i] != 0xFF else None for i in range(48, 50)
        ]

    return rec


# --------------- Page parser ---------------

def parse_archive_page(page: bytes) -> list[tuple[int, bytes]]:
    """Parse a 267-byte archive page into (index, record_bytes) tuples.

    Page layout: 5 × 52-byte records + 4 unused bytes + 2-byte CRC.
    Returns up to 5 records with their 0-based index within the page.
    """
    if len(page) < ARCHIVE_PAGE_SIZE:
        logger.warning("Archive page too short: %d/%d bytes", len(page), ARCHIVE_PAGE_SIZE)
        return []

    if not crc_validate(page[:ARCHIVE_PAGE_SIZE]):
        logger.warning("Archive page CRC failed")
        return []

    records = []
    for i in range(ARCHIVE_RECORDS_PER_PAGE):
        start = i * ARCHIVE_RECORD_SIZE
        end = start + ARCHIVE_RECORD_SIZE
        record_bytes = page[start:end]
        records.append((i, record_bytes))

    return records
