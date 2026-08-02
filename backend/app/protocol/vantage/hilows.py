"""HILOWS block parser for the Davis Vantage protocol.

The HILOWS command returns a 436-byte block of daily, monthly, and yearly
highs and lows for every sensor the console tracks, plus a trailing
big-endian CRC-16.  Section X.3 of the Davis Vantage Serial Communication
Reference (Rev 2.6.1) documents the layout.

The dataclass exposes SI-unit values (°C, hPa, m/s, mm) so it matches the
convention already used by VantageArchiveRecord.  Dashed / no-sensor
sentinels are filtered here rather than surfaced to callers — an
unpopulated extra-temp slot must not appear as -90 °F, which is what
would happen if the offset-encoded byte 255 leaked through unfiltered.
"""

import logging
import struct
from dataclasses import dataclass, field
from datetime import time
from typing import Optional

from ..crc import crc_validate
from .loop_packet import (
    _f10_to_c,
    _inhg1000_to_hpa,
    _mph_to_ms,
    _valid_barometer,
    _valid_humidity,
    _valid_solar,
    _valid_temp,
    _decode_extra_temp,
)

logger = logging.getLogger(__name__)


HILOWS_BLOCK_SIZE = 436          # payload
HILOWS_TOTAL_SIZE = 438          # payload + 2-byte CRC

# --- section-level sentinels ---
#
# The manual specifies dash values field-by-field but they cluster around
# a handful of values.  We treat every one of these as "no reading" for the
# field width they belong to.
_DASH_U16 = {0x7FFF, 0xFFFF, 0x8000}     # signed & unsigned "dashed" for 2-byte fields
_DASH_U8 = 0xFF                          # 1-byte "dashed"

# "Whole degrees F" fields (dew / heat / chill / thsw) use signed shorts.
# The LOOP2 doc calls out 255 as the dash value, but a signed short of 255
# is a real -something reading; the actual sentinel observed on the wire
# for these u16 fields is 0x7FFF / 0x8000 (32767 / -32768).
_DASH_TEMP_WHOLE = {0x7FFF, 0x8000, -32768, 32767}


@dataclass
class HiLo:
    """Symmetric hi/lo pair with optional timestamps.

    `time_low` / `time_high` are the wall-clock times the extreme occurred
    (Vantage stores them per day; monthly/yearly extrema have no time
    field, so those pairs use `HiOnly` / `LoOnly`).
    """
    low: Optional[float] = None
    high: Optional[float] = None
    time_low: Optional[time] = None
    time_high: Optional[time] = None


@dataclass
class HiOnly:
    """High-only extremum (heat index, THSW, solar, UV, rain rate)."""
    value: Optional[float] = None
    time: Optional[time] = None


@dataclass
class LoOnly:
    """Low-only extremum (wind chill has no meaningful high)."""
    value: Optional[float] = None
    time: Optional[time] = None


@dataclass
class Period:
    """Day / month / year triple of hi/lo pairs.

    Times are populated only on the daily entry because the console does
    not retain per-monthly / per-yearly timestamps — a decision baked into
    the HILOWS block format itself.
    """
    day: HiLo = field(default_factory=HiLo)
    month: HiLo = field(default_factory=HiLo)
    year: HiLo = field(default_factory=HiLo)


@dataclass
class HiOnlyPeriod:
    day: HiOnly = field(default_factory=HiOnly)
    month: HiOnly = field(default_factory=HiOnly)
    year: HiOnly = field(default_factory=HiOnly)


@dataclass
class LoOnlyPeriod:
    day: LoOnly = field(default_factory=LoOnly)
    month: LoOnly = field(default_factory=LoOnly)
    year: LoOnly = field(default_factory=LoOnly)


@dataclass
class VantageHighsLows:
    """Parsed HILOWS block in SI units.

    Every scalar is Optional[float] and None-safe: an unpopulated sensor
    or a dashed reading comes back as None rather than 0 or a sentinel.
    Extra/soil/leaf arrays have fixed length so index positions line up
    with the console's own numbering, but individual slots are None when
    the sensor is not installed.
    """
    barometer: Period = field(default_factory=Period)               # hPa
    wind_speed: HiOnlyPeriod = field(default_factory=HiOnlyPeriod)  # m/s
    inside_temp: Period = field(default_factory=Period)             # °C
    inside_humidity: Period = field(default_factory=Period)         # %
    outside_temp: Period = field(default_factory=Period)            # °C
    dew_point: Period = field(default_factory=Period)               # °C
    wind_chill: LoOnlyPeriod = field(default_factory=LoOnlyPeriod)  # °C
    heat_index: HiOnlyPeriod = field(default_factory=HiOnlyPeriod)  # °C
    thsw_index: HiOnlyPeriod = field(default_factory=HiOnlyPeriod)  # °C
    solar_radiation: HiOnlyPeriod = field(default_factory=HiOnlyPeriod)  # W/m²
    uv_index: HiOnlyPeriod = field(default_factory=HiOnlyPeriod)    # index
    rain_rate: HiOnlyPeriod = field(default_factory=HiOnlyPeriod)   # mm/hr
    rain_rate_hour_hi: Optional[float] = None                       # mm/hr, day

    # Slot layout matches §X.3: indexes 0-6 map to Extra Temperatures 2-8,
    # 7-10 to Soil Temperatures 1-4, 11-14 to Leaf Temperatures 1-4.  We
    # split into three arrays here for readability; each entry is a Period.
    extra_temps: list[Period] = field(default_factory=list)         # 7 slots
    soil_temps: list[Period] = field(default_factory=list)          # 4 slots
    leaf_temps: list[Period] = field(default_factory=list)          # 4 slots
    # Outside humidity is index 0; extras 1-7 are 2-8 by console numbering.
    humidities: list[Period] = field(default_factory=list)          # 8 slots
    soil_moistures: list[Period] = field(default_factory=list)      # 4 slots
    leaf_wetnesses: list[Period] = field(default_factory=list)      # 4 slots


# --------------- Helpers ---------------

def _time_from_raw(raw: int) -> Optional[time]:
    """Vantage stores times as hour*100 + minute.

    0xFFFF and 0x7FFF are treated as "no time recorded".  Anything else
    outside 00:00-23:59 is rejected the same way — better to report None
    than surface a 25:37 time to callers.
    """
    if raw in _DASH_U16:
        return None
    hour, minute = divmod(raw, 100)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour=hour, minute=minute)


def _temp_c(raw: int) -> Optional[float]:
    """Tenths-°F signed short → °C, sentinels → None."""
    valid = _valid_temp(raw)
    return _f10_to_c(valid) if valid is not None else None


def _temp_whole_c(raw: int) -> Optional[float]:
    """Whole-degree-F signed short (dew / heat / chill / thsw) → °C."""
    if raw in _DASH_TEMP_WHOLE:
        return None
    return round((raw - 32) * 5 / 9, 1)


def _bar_hpa(raw: int) -> Optional[float]:
    """Thousandths inHg u16 → hPa."""
    valid = _valid_barometer(raw)
    return _inhg1000_to_hpa(valid) if valid is not None else None


def _wind_ms(raw: int) -> Optional[float]:
    """mph u8 → m/s.  255 is "dashed"."""
    if raw == _DASH_U8:
        return None
    return _mph_to_ms(raw)


def _extra_c(raw: int) -> Optional[float]:
    """Offset-encoded extra temp (F+90) u8 → °C."""
    decoded = _decode_extra_temp(raw)
    if decoded is None:
        return None
    return _f10_to_c(decoded)


def _hum(raw: int) -> Optional[int]:
    """u8 humidity 0-100.  255 or >100 → None."""
    return _valid_humidity(raw)


def _uv(raw: int) -> Optional[float]:
    """u8 UV in tenths.  255 → None."""
    if raw == _DASH_U8:
        return None
    return round(raw / 10.0, 1)


def _solar(raw: int) -> Optional[int]:
    return _valid_solar(raw)


def _rain_rate_mm_hr(raw: int, click_inches: float) -> Optional[float]:
    """Rain rate in clicks/hr → mm/hr.  0xFFFF sentinel handled."""
    if raw == 0xFFFF:
        return None
    return round(raw * click_inches * 25.4, 2)


def _soil_moisture(raw: int) -> Optional[int]:
    """Soil moisture centibar u8.  255 → None."""
    if raw == _DASH_U8:
        return None
    return raw


def _leaf_wetness(raw: int) -> Optional[int]:
    """Leaf wetness scale 0-15.  Anything else → None."""
    if raw == _DASH_U8 or raw > 15:
        return None
    return raw


# --------------- Parser ---------------

def parse_hilows(block: bytes, rain_click_inches: float = 0.01) -> Optional[VantageHighsLows]:
    """Parse a 438-byte HILOWS response (436-byte block + 2-byte CRC).

    Returns None on length mismatch or CRC failure — the driver already
    raises on those cases before calling us, so hitting a None here means
    the caller bypassed the driver and passed in raw bytes directly.
    """
    if len(block) < HILOWS_TOTAL_SIZE:
        logger.warning("HILOWS block too short: %d/%d", len(block), HILOWS_TOTAL_SIZE)
        return None
    if not crc_validate(block[:HILOWS_TOTAL_SIZE]):
        logger.warning("HILOWS block CRC failed")
        return None

    b = block  # brevity — offsets are dense and match the manual verbatim
    hl = VantageHighsLows()

    # --- Barometer (offsets 0-15, all u16 thousandths inHg) ---
    hl.barometer.day.low = _bar_hpa(struct.unpack_from("<H", b, 0)[0])
    hl.barometer.day.high = _bar_hpa(struct.unpack_from("<H", b, 2)[0])
    hl.barometer.month.low = _bar_hpa(struct.unpack_from("<H", b, 4)[0])
    hl.barometer.month.high = _bar_hpa(struct.unpack_from("<H", b, 6)[0])
    hl.barometer.year.low = _bar_hpa(struct.unpack_from("<H", b, 8)[0])
    hl.barometer.year.high = _bar_hpa(struct.unpack_from("<H", b, 10)[0])
    hl.barometer.day.time_low = _time_from_raw(struct.unpack_from("<H", b, 12)[0])
    hl.barometer.day.time_high = _time_from_raw(struct.unpack_from("<H", b, 14)[0])

    # --- Wind Speed (offsets 16-20; hi only, day speed is u8 mph) ---
    hl.wind_speed.day.value = _wind_ms(b[16])
    hl.wind_speed.day.time = _time_from_raw(struct.unpack_from("<H", b, 17)[0])
    hl.wind_speed.month.value = _wind_ms(b[19])
    hl.wind_speed.year.value = _wind_ms(b[20])

    # --- Inside Temp (21-36, s16 tenths °F) ---
    hl.inside_temp.day.high = _temp_c(struct.unpack_from("<h", b, 21)[0])
    hl.inside_temp.day.low = _temp_c(struct.unpack_from("<h", b, 23)[0])
    hl.inside_temp.day.time_high = _time_from_raw(struct.unpack_from("<H", b, 25)[0])
    hl.inside_temp.day.time_low = _time_from_raw(struct.unpack_from("<H", b, 27)[0])
    hl.inside_temp.month.low = _temp_c(struct.unpack_from("<h", b, 29)[0])
    hl.inside_temp.month.high = _temp_c(struct.unpack_from("<h", b, 31)[0])
    hl.inside_temp.year.low = _temp_c(struct.unpack_from("<h", b, 33)[0])
    hl.inside_temp.year.high = _temp_c(struct.unpack_from("<h", b, 35)[0])

    # --- Inside Humidity (37-46) ---
    hl.inside_humidity.day.high = _hum(b[37])
    hl.inside_humidity.day.low = _hum(b[38])
    hl.inside_humidity.day.time_high = _time_from_raw(struct.unpack_from("<H", b, 39)[0])
    hl.inside_humidity.day.time_low = _time_from_raw(struct.unpack_from("<H", b, 41)[0])
    hl.inside_humidity.month.high = _hum(b[43])
    hl.inside_humidity.month.low = _hum(b[44])
    hl.inside_humidity.year.high = _hum(b[45])
    hl.inside_humidity.year.low = _hum(b[46])

    # --- Outside Temp (47-62, s16 tenths °F).  Layout is low-first, then
    # high, mirroring inside temp with the pair reversed — following the
    # manual literally rather than assuming symmetry avoids a class of
    # off-by-two bugs that would silently swap high and low. ---
    hl.outside_temp.day.low = _temp_c(struct.unpack_from("<h", b, 47)[0])
    hl.outside_temp.day.high = _temp_c(struct.unpack_from("<h", b, 49)[0])
    hl.outside_temp.day.time_low = _time_from_raw(struct.unpack_from("<H", b, 51)[0])
    hl.outside_temp.day.time_high = _time_from_raw(struct.unpack_from("<H", b, 53)[0])
    hl.outside_temp.month.high = _temp_c(struct.unpack_from("<h", b, 55)[0])
    hl.outside_temp.month.low = _temp_c(struct.unpack_from("<h", b, 57)[0])
    hl.outside_temp.year.high = _temp_c(struct.unpack_from("<h", b, 59)[0])
    hl.outside_temp.year.low = _temp_c(struct.unpack_from("<h", b, 61)[0])

    # --- Dew Point (63-78, s16 whole °F) ---
    hl.dew_point.day.low = _temp_whole_c(struct.unpack_from("<h", b, 63)[0])
    hl.dew_point.day.high = _temp_whole_c(struct.unpack_from("<h", b, 65)[0])
    hl.dew_point.day.time_low = _time_from_raw(struct.unpack_from("<H", b, 67)[0])
    hl.dew_point.day.time_high = _time_from_raw(struct.unpack_from("<H", b, 69)[0])
    hl.dew_point.month.high = _temp_whole_c(struct.unpack_from("<h", b, 71)[0])
    hl.dew_point.month.low = _temp_whole_c(struct.unpack_from("<h", b, 73)[0])
    hl.dew_point.year.high = _temp_whole_c(struct.unpack_from("<h", b, 75)[0])
    hl.dew_point.year.low = _temp_whole_c(struct.unpack_from("<h", b, 77)[0])

    # --- Wind Chill (79-86, s16 whole °F, LOW ONLY) ---
    hl.wind_chill.day.value = _temp_whole_c(struct.unpack_from("<h", b, 79)[0])
    hl.wind_chill.day.time = _time_from_raw(struct.unpack_from("<H", b, 81)[0])
    hl.wind_chill.month.value = _temp_whole_c(struct.unpack_from("<h", b, 83)[0])
    hl.wind_chill.year.value = _temp_whole_c(struct.unpack_from("<h", b, 85)[0])

    # --- Heat Index (87-94, HIGH ONLY) ---
    hl.heat_index.day.value = _temp_whole_c(struct.unpack_from("<h", b, 87)[0])
    hl.heat_index.day.time = _time_from_raw(struct.unpack_from("<H", b, 89)[0])
    hl.heat_index.month.value = _temp_whole_c(struct.unpack_from("<h", b, 91)[0])
    hl.heat_index.year.value = _temp_whole_c(struct.unpack_from("<h", b, 93)[0])

    # --- THSW Index (95-102, HIGH ONLY) ---
    hl.thsw_index.day.value = _temp_whole_c(struct.unpack_from("<h", b, 95)[0])
    hl.thsw_index.day.time = _time_from_raw(struct.unpack_from("<H", b, 97)[0])
    hl.thsw_index.month.value = _temp_whole_c(struct.unpack_from("<h", b, 99)[0])
    hl.thsw_index.year.value = _temp_whole_c(struct.unpack_from("<h", b, 101)[0])

    # --- Solar Radiation (103-110, u16 W/m², HIGH ONLY) ---
    hl.solar_radiation.day.value = _solar(struct.unpack_from("<H", b, 103)[0])
    hl.solar_radiation.day.time = _time_from_raw(struct.unpack_from("<H", b, 105)[0])
    hl.solar_radiation.month.value = _solar(struct.unpack_from("<H", b, 107)[0])
    hl.solar_radiation.year.value = _solar(struct.unpack_from("<H", b, 109)[0])

    # --- UV (111-115, u8 tenths, HIGH ONLY) ---
    hl.uv_index.day.value = _uv(b[111])
    hl.uv_index.day.time = _time_from_raw(struct.unpack_from("<H", b, 112)[0])
    hl.uv_index.month.value = _uv(b[114])
    hl.uv_index.year.value = _uv(b[115])

    # --- Rain Rate (116-125, u16 clicks/hr, HIGH ONLY).  120-121 is the
    # highest hourly *total* rain, not a rain rate, but the manual files
    # it in this section so we expose it as `rain_rate_hour_hi`. ---
    hl.rain_rate.day.value = _rain_rate_mm_hr(
        struct.unpack_from("<H", b, 116)[0], rain_click_inches)
    hl.rain_rate.day.time = _time_from_raw(struct.unpack_from("<H", b, 118)[0])
    hl.rain_rate_hour_hi = _rain_rate_mm_hr(
        struct.unpack_from("<H", b, 120)[0], rain_click_inches)
    hl.rain_rate.month.value = _rain_rate_mm_hr(
        struct.unpack_from("<H", b, 122)[0], rain_click_inches)
    hl.rain_rate.year.value = _rain_rate_mm_hr(
        struct.unpack_from("<H", b, 124)[0], rain_click_inches)

    # --- Extra / Soil / Leaf Temps (126-275) — 15 slots per sub-array.
    # Indexes 0-6 = Extra 2-8, 7-10 = Soil 1-4, 11-14 = Leaf 1-4.
    #
    # Sub-blocks (offsets are into b, not into the sub-block):
    #   126..140  Day Low     (15 * 1 byte, offset-encoded)
    #   141..155  Day Hi
    #   156..185  Time Day Low (15 * 2)
    #   186..215  Time Day Hi  (15 * 2)
    #   216..230  Month Hi    (15 * 1)
    #   231..245  Month Low   (15 * 1)
    #   246..260  Year Hi     (15 * 1)
    #   261..275  Year Low    (15 * 1)
    hl.extra_temps = [Period() for _ in range(7)]
    hl.soil_temps = [Period() for _ in range(4)]
    hl.leaf_temps = [Period() for _ in range(4)]
    all_temp_slots: list[Period] = hl.extra_temps + hl.soil_temps + hl.leaf_temps
    for i, slot in enumerate(all_temp_slots):
        slot.day.low = _extra_c(b[126 + i])
        slot.day.high = _extra_c(b[141 + i])
        slot.day.time_low = _time_from_raw(struct.unpack_from("<H", b, 156 + i * 2)[0])
        slot.day.time_high = _time_from_raw(struct.unpack_from("<H", b, 186 + i * 2)[0])
        slot.month.high = _extra_c(b[216 + i])
        slot.month.low = _extra_c(b[231 + i])
        slot.year.high = _extra_c(b[246 + i])
        slot.year.low = _extra_c(b[261 + i])

    # --- Outside / Extra Humidities (276-355) — 8 slots.
    #   276..283  Day Low         (8 * 1)
    #   284..291  Day Hi
    #   292..307  Time Day Low    (8 * 2)
    #   308..323  Time Day Hi
    #   324..331  Month Hi        (8 * 1)
    #   332..339  Month Low
    #   340..347  Year Hi
    #   348..355  Year Low
    hl.humidities = [Period() for _ in range(8)]
    for i, slot in enumerate(hl.humidities):
        slot.day.low = _hum(b[276 + i])
        slot.day.high = _hum(b[284 + i])
        slot.day.time_low = _time_from_raw(struct.unpack_from("<H", b, 292 + i * 2)[0])
        slot.day.time_high = _time_from_raw(struct.unpack_from("<H", b, 308 + i * 2)[0])
        slot.month.high = _hum(b[324 + i])
        slot.month.low = _hum(b[332 + i])
        slot.year.high = _hum(b[340 + i])
        slot.year.low = _hum(b[348 + i])

    # --- Soil Moisture (356-395) — 4 slots.
    #   356..359  Day Hi          (4 * 1)
    #   360..367  Time Day Hi     (4 * 2)
    #   368..371  Day Low
    #   372..379  Time Day Low    (4 * 2)
    #   380..383  Month Low
    #   384..387  Month Hi
    #   388..391  Year Low
    #   392..395  Year Hi
    hl.soil_moistures = [Period() for _ in range(4)]
    for i, slot in enumerate(hl.soil_moistures):
        slot.day.high = _soil_moisture(b[356 + i])
        slot.day.time_high = _time_from_raw(struct.unpack_from("<H", b, 360 + i * 2)[0])
        slot.day.low = _soil_moisture(b[368 + i])
        slot.day.time_low = _time_from_raw(struct.unpack_from("<H", b, 372 + i * 2)[0])
        slot.month.low = _soil_moisture(b[380 + i])
        slot.month.high = _soil_moisture(b[384 + i])
        slot.year.low = _soil_moisture(b[388 + i])
        slot.year.high = _soil_moisture(b[392 + i])

    # --- Leaf Wetness (396-435) — same layout as soil moisture. ---
    hl.leaf_wetnesses = [Period() for _ in range(4)]
    for i, slot in enumerate(hl.leaf_wetnesses):
        slot.day.high = _leaf_wetness(b[396 + i])
        slot.day.time_high = _time_from_raw(struct.unpack_from("<H", b, 400 + i * 2)[0])
        slot.day.low = _leaf_wetness(b[408 + i])
        slot.day.time_low = _time_from_raw(struct.unpack_from("<H", b, 412 + i * 2)[0])
        slot.month.low = _leaf_wetness(b[420 + i])
        slot.month.high = _leaf_wetness(b[424 + i])
        slot.year.low = _leaf_wetness(b[428 + i])
        slot.year.high = _leaf_wetness(b[432 + i])

    return hl
