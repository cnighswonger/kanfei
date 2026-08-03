"""LOOP and LOOP2 packet parsers for the Davis Vantage protocol.

Parses the 99-byte LOOP (type 0) and LOOP2 (type 1) packets into
intermediate dataclasses, then merges them into a SensorSnapshot with
standard float units.

Reference: Davis Vantage Serial Communication Reference v2.6.1,
           weewx vantage.py driver.
"""

import logging
import struct
from dataclasses import dataclass, field
from typing import Optional

from ..base import SensorSnapshot
from ..crc import crc_validate
from .constants import (
    LOOP_HEADER,
    LOOP_PACKET_SIZE,
    INVALID_TEMP,
    INVALID_HUMIDITY,
    INVALID_UV,
    INVALID_SOLAR,
    INVALID_BAROMETER,
    INVALID_RAIN_RATE,
    INVALID_EXTRA_TEMP,
    BAR_TREND_UNKNOWN,
)

logger = logging.getLogger(__name__)


# --------------- Intermediate data structures ---------------

@dataclass
class LoopData:
    """Raw parsed LOOP (type 0) fields in native units."""
    bar_trend: Optional[int] = None          # signed: -60..+60
    barometer: Optional[int] = None          # thousandths inHg
    inside_temp: Optional[int] = None        # tenths °F
    inside_humidity: Optional[int] = None    # percent
    outside_temp: Optional[int] = None       # tenths °F
    outside_humidity: Optional[int] = None   # percent
    wind_speed: Optional[int] = None         # mph
    wind_speed_10min: Optional[int] = None   # mph
    wind_direction: Optional[int] = None     # degrees 0-360
    rain_rate: Optional[int] = None          # clicks/hr
    uv_index: Optional[int] = None           # tenths UV
    solar_radiation: Optional[int] = None    # W/m²
    storm_rain: Optional[int] = None         # clicks
    day_rain: Optional[int] = None           # clicks
    month_rain: Optional[int] = None         # clicks
    year_rain: Optional[int] = None          # clicks
    day_et: Optional[int] = None             # thousandths inch
    sunrise: Optional[int] = None            # hour*100 + min
    sunset: Optional[int] = None             # hour*100 + min
    forecast_icons: Optional[int] = None
    forecast_rule: Optional[int] = None
    # Battery status — LOOP bytes 86 and 87.  Present in every packet all
    # along; we simply never read them.  transmitter_battery_status is a
    # bitmask, one bit per transmitter ID (bit 0 = transmitter 1, the ISS
    # on a Vue).  The manual names byte 86 but documents no bit layout, so
    # that reading is inferred rather than specified.
    transmitter_battery_status: Optional[int] = None   # bitmask
    console_battery_voltage: Optional[float] = None    # volts
    extra_temps: list[Optional[int]] = field(default_factory=list)
    soil_temps: list[Optional[int]] = field(default_factory=list)
    leaf_temps: list[Optional[int]] = field(default_factory=list)
    extra_humidities: list[Optional[int]] = field(default_factory=list)
    soil_moistures: list[Optional[int]] = field(default_factory=list)
    leaf_wetnesses: list[Optional[int]] = field(default_factory=list)


@dataclass
class Loop2Data:
    """Raw parsed LOOP2 (type 1) fields in native units."""
    bar_trend: Optional[int] = None
    barometer: Optional[int] = None          # thousandths inHg
    wind_speed_10min: Optional[int] = None   # tenths mph
    wind_speed_2min: Optional[int] = None    # tenths mph
    wind_gust_10min: Optional[int] = None    # tenths mph
    wind_gust_dir: Optional[int] = None      # degrees
    dew_point: Optional[int] = None          # °F integer
    heat_index: Optional[int] = None         # °F integer
    wind_chill: Optional[int] = None         # °F integer
    thsw_index: Optional[int] = None         # °F integer
    rain_rate: Optional[int] = None          # clicks/hr
    uv_index: Optional[int] = None           # tenths UV
    solar_radiation: Optional[int] = None    # W/m²
    day_rain: Optional[int] = None           # clicks
    rain_last_15min: Optional[int] = None    # clicks
    rain_last_hour: Optional[int] = None     # clicks
    # Barometer block (§X.2 bytes 60-70).  These are what a calibration
    # tool needs: the raw sensor reading, what the user has already
    # offset it by, and the corrected values the console displays.
    bar_reduction_method: Optional[int] = None  # 0=user offset, 1=altimeter, 2=NOAA
    bar_user_offset: Optional[int] = None    # thousandths inHg, set by BAR=
    bar_calibration: Optional[int] = None    # thousandths inHg, SIGNED
    bar_raw_sensor: Optional[int] = None     # thousandths inHg, uncorrected
    abs_barometer: Optional[int] = None      # thousandths inHg = raw + user offset
    altimeter_barometer: Optional[int] = None  # thousandths inHg


# --------------- Validation helpers ---------------

def _valid_temp(val: int) -> Optional[int]:
    """Return temp in tenths F if valid, else None."""
    if val == INVALID_TEMP or val == -32768:
        return None
    if val > 2500 or val < -900:   # > 250°F or < -90°F
        return None
    return val


def _valid_humidity(val: int) -> Optional[int]:
    """Return humidity % if valid (0-100), else None."""
    if val == INVALID_HUMIDITY or val > 100:
        return None
    return val


def _valid_barometer(val: int) -> Optional[int]:
    """Return barometer in thousandths inHg if valid, else None."""
    if val == INVALID_BAROMETER or val == 0xFFFF:
        return None
    return val


def _valid_uv(val: int) -> Optional[int]:
    """Return UV index in tenths if valid, else None."""
    if val == INVALID_UV:
        return None
    return val


def _valid_solar(val: int) -> Optional[int]:
    """Return solar radiation W/m² if valid, else None."""
    if val >= INVALID_SOLAR:
        return None
    return val


def _valid_rain_rate(val: int) -> Optional[int]:
    """Return rain rate in clicks/hr if valid, else None."""
    if val == INVALID_RAIN_RATE:
        return None
    return val


def _valid_wind_dir(val: int) -> Optional[int]:
    """Return wind direction in degrees if valid, else None."""
    if val == 0x7FFF or val > 360:
        return None
    return val


def _valid_wind_speed(val: int) -> Optional[int]:
    """Return wind speed in mph if valid, else None.

    255 is the dashed sentinel for the single-byte wind fields.  It was
    previously passed straight through, so a transmitter dropout logged
    255 mph (114 m/s) as a real reading — and did so on every poll for the
    duration of the outage, because a stuck sentinel does not look like
    noise, it looks like a sustained gale.

    Everything around it was already guarded: wind DIRECTION has
    _valid_wind_dir(), temperature and humidity have their own filters,
    and the LOOP2 wind fields check 0x7FFF.  Only the two LOOP wind speed
    bytes were unfiltered, which is why a dropout produced a snapshot with
    every other outdoor field None and a plausible-looking number here.

    The manual notes wind speed "is forced to be 0" when the console loses
    sync, so 255 specifically means no data rather than a real extreme.
    """
    if val == 0xFF:
        return None
    return val


def _valid_derived_temp(val: int) -> Optional[int]:
    """Return a LOOP2 station-computed temperature, or None when dashed.

    Dew point, heat index, wind chill and THSW are two-byte signed values
    in whole °F.  The dashed sentinel is 0x7FFF — the manual's table says
    "255 = dashed data" for all four, but 255 cannot be the sentinel for a
    two-byte field, and the wire agrees: a Vue with no solar sensor puts
    32767 in THSW, not 255.

    The range check is deliberately wide.  These are whole-degree °F
    values, and -150..200 °F comfortably covers any real reading while
    still catching a sentinel or a misaligned read.
    """
    if val == 0x7FFF or val == -1 or not (-150 <= val <= 200):
        return None
    return val


def _valid_clock(val: int) -> Optional[int]:
    """Return an hour*100+min time if it decodes to a real clock value.

    Guards the sunrise/sunset fields.  A wrong offset here previously went
    unnoticed for months precisely because nothing rejected implausible
    values — sunrise read 0 and sunset read 10497, and both flowed
    straight through to the UI.
    """
    # 0 is rejected deliberately.  It decodes to a superficially valid
    # 00:00, and that is exactly how the old wrong offset survived: it
    # pointed into a zeroed alarm block, so sunrise came out as "midnight"
    # rather than as anything obviously broken.  Neither sunrise nor sunset
    # is ever truly 00:00, so treating 0 as "no reading" costs nothing and
    # makes a mis-set offset fail loudly instead of silently.
    if val == 0 or val in (0xFFFF, 0x7FFF):
        return None
    hour, minute = divmod(val, 100)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return val


def _decode_extra_temp(raw: int) -> Optional[int]:
    """Decode offset-encoded extra temperature.

    Raw value is temp_F + 90.  255 = invalid.
    Returns tenths °F for consistency with main temp fields.
    """
    if raw == INVALID_EXTRA_TEMP:
        return None
    return (raw - 90) * 10


# --------------- LOOP parser ---------------

def parse_loop(raw: bytes) -> Optional[LoopData]:
    """Parse a 99-byte LOOP (type 0) packet.

    Packet layout:
      [0:3]   "LOO" header
      [3]     bar trend (signed byte)
      [4]     packet type (0 = LOOP)
      [5:7]   next archive record (u16 LE, ignored)
      [7:9]   barometer (u16 LE, thousandths inHg)
      [9:11]  inside temp (i16 LE, tenths °F)
      [11]    inside humidity (u8, %)
      [12:14] outside temp (i16 LE, tenths °F)
      [14]    wind speed (u8, mph)
      [15]    10-min avg wind speed (u8, mph)
      [16:18] wind direction (u16 LE, degrees 0-360)
      [18:25] extra temps ×7 (u8, temp+90)
      [25:29] soil temps ×4 (u8, temp+90)
      [29:33] leaf temps ×4 (u8, temp+90)
      [33]    outside humidity (u8, %)
      [34:41] extra humidities ×7 (u8, %)
      [41:43] rain rate (u16 LE, clicks/hr)
      [43]    UV index (u8, tenths)
      [44:46] solar radiation (u16 LE, W/m²)
      [46:48] storm rain (u16 LE, clicks)
      [48:50] storm start date (u16 LE, bit-packed)
      [50:52] day rain (u16 LE, clicks)
      [52:54] month rain (u16 LE, clicks)
      [54:56] year rain (u16 LE, clicks)
      [56:58] day ET (u16 LE, thousandths inch)
      [58:60] month ET (u16 LE, hundredths inch)
      [60:62] year ET (u16 LE, hundredths inch)
      [62:66] soil moistures ×4 (u8, centibars)
      [66:70] leaf wetnesses ×4 (u8, 0-15)
      [70]    inside alarms (u8)
      [71]    rain alarms (u8)
      [72:74] outside alarms (u16)
      [74:82] extra temp/hum alarms (8 bytes)
      [82:86] soil & leaf alarms (4 bytes)
      [86]    transmitter battery status (u8 bitmask, bit N = transmitter N+1)
      [87:89] console battery voltage (u16 LE, ((raw*300)/512)/100.0 volts)
      [89]    forecast icons (u8)
      [90]    forecast rule (u8)
      [91:93] sunrise (u16 LE, hour*100+min)
      [93:95] sunset (u16 LE, hour*100+min)
      [95]    \\n (0x0A)
      [96]    \\r (0x0D)
      [97:99] CRC (u16 BE) — over bytes 0-96
      Total = 99 bytes

    The tail offsets above were previously wrong: forecast/sunrise/sunset
    were read at 82/83/84/86, which lands in the alarm block.  On a
    Vantage Vue (fw 2.12) with no alarms active that region is all zeroes,
    so sunrise decoded as 0 ("00:00") and sunset as 10497 — not a clock
    value at all.  Measured against the wire, the manual's offsets give
    sunrise=515 (05:15) and sunset=1921 (19:21), which match the almanac
    for 35.38N 78.60W once the console's standard-time setting is
    accounted for.  Two further fields corroborate the layout: byte 87
    yields 4.74 V for the console cell, and byte 86 reads 0x01 on a
    console actively displaying an ISS low-battery warning.
    """
    if len(raw) < LOOP_PACKET_SIZE:
        logger.warning("LOOP packet too short: %d/%d bytes", len(raw), LOOP_PACKET_SIZE)
        return None

    # Validate header
    if raw[0:3] != LOOP_HEADER:
        logger.warning("LOOP missing header: %s", raw[0:3])
        return None

    # Validate packet type
    pkt_type = raw[4]
    if pkt_type != 0 and pkt_type != ord("P"):
        # Type 0 = Rev B LOOP; "P" (0x50) at offset 4 = Rev A LOOP
        # For Rev A, byte 3 has no bar trend (it's part of "LOOP")
        pass  # accept both

    # CRC: covers bytes 0 through 96, CRC at 97-98
    if not crc_validate(raw[:LOOP_PACKET_SIZE]):
        logger.warning("LOOP CRC validation failed")
        return None

    data = LoopData()

    # Bar trend (signed byte at offset 3)
    bar_trend_raw = struct.unpack_from("<b", raw, 3)[0]
    if bar_trend_raw != BAR_TREND_UNKNOWN:
        data.bar_trend = bar_trend_raw

    # Barometer
    data.barometer = _valid_barometer(struct.unpack_from("<H", raw, 7)[0])

    # Temperatures
    data.inside_temp = _valid_temp(struct.unpack_from("<h", raw, 9)[0])
    data.outside_temp = _valid_temp(struct.unpack_from("<h", raw, 12)[0])

    # Humidity
    data.inside_humidity = _valid_humidity(raw[11])
    data.outside_humidity = _valid_humidity(raw[33])

    # Wind
    data.wind_speed = _valid_wind_speed(raw[14])
    data.wind_speed_10min = _valid_wind_speed(raw[15])
    data.wind_direction = _valid_wind_dir(struct.unpack_from("<H", raw, 16)[0])

    # Rain
    data.rain_rate = _valid_rain_rate(struct.unpack_from("<H", raw, 41)[0])
    data.storm_rain = struct.unpack_from("<H", raw, 46)[0]
    data.day_rain = struct.unpack_from("<H", raw, 50)[0]
    data.month_rain = struct.unpack_from("<H", raw, 52)[0]
    data.year_rain = struct.unpack_from("<H", raw, 54)[0]

    # UV / Solar
    data.uv_index = _valid_uv(raw[43])
    data.solar_radiation = _valid_solar(struct.unpack_from("<H", raw, 44)[0])

    # ET
    data.day_et = struct.unpack_from("<H", raw, 56)[0]

    # Extra temps (7 values at offsets 18-24, each u8, encoded as temp+90)
    data.extra_temps = [_decode_extra_temp(raw[i]) for i in range(18, 25)]

    # Soil temps (4 values at offsets 25-28)
    data.soil_temps = [_decode_extra_temp(raw[i]) for i in range(25, 29)]

    # Leaf temps (4 values at offsets 29-32)
    data.leaf_temps = [_decode_extra_temp(raw[i]) for i in range(29, 33)]

    # Extra humidities (7 values at offsets 34-40)
    data.extra_humidities = [_valid_humidity(raw[i]) for i in range(34, 41)]

    # Soil moistures (4 values at offsets 62-65)
    data.soil_moistures = [raw[i] if raw[i] != 0xFF else None for i in range(62, 66)]

    # Leaf wetnesses (4 values at offsets 66-69)
    data.leaf_wetnesses = [raw[i] if raw[i] != 0xFF else None for i in range(66, 70)]

    # Battery status.  Both bytes have always been present; they were
    # simply never read.  The manual names byte 86 but documents no bit
    # layout, so the per-transmitter reading is inference — corroborated
    # on a Vue whose console showed an ISS low-battery warning while this
    # byte read 0x01.
    data.transmitter_battery_status = raw[86]
    console_raw = struct.unpack_from("<H", raw, 87)[0]
    data.console_battery_voltage = (
        round(((console_raw * 300) / 512) / 100.0, 2)
        if console_raw else None
    )

    # Forecast
    data.forecast_icons = raw[89]
    data.forecast_rule = raw[90]

    # Sunrise/sunset
    data.sunrise = _valid_clock(struct.unpack_from("<H", raw, 91)[0])
    data.sunset = _valid_clock(struct.unpack_from("<H", raw, 93)[0])

    return data


# --------------- LOOP2 parser ---------------

def parse_loop2(raw: bytes) -> Optional[Loop2Data]:
    """Parse a 99-byte LOOP2 (type 1) packet.

    LOOP2-specific fields (offsets differ from LOOP):
      [0:3]   "LOO" header
      [3]     bar trend (signed byte)
      [4]     packet type (must be 1)
      [5:7]   unused
      [7:9]   barometer (u16 LE, thousandths inHg)
      [12:14] outside temp (i16 LE, tenths °F)  — same as LOOP
      [14]    wind speed (u8, mph)
      [16:18] wind direction (u16 LE, degrees)
      [18:20] wind speed 10-min avg (u16 LE, tenths mph)
      [20:22] wind speed 2-min avg (u16 LE, tenths mph)
      [22:24] wind gust 10-min (u16 LE, tenths mph)
      [24:26] wind gust direction (u16 LE, degrees)
      [30:32] dew point (i16 LE, °F)
      [33]    outside humidity (u8, %)
      [34:36] heat index (i16 LE, °F)
      [36:38] wind chill (i16 LE, °F)
      [38:40] THSW index (i16 LE, °F)
      [41:43] rain rate (u16 LE, clicks/hr)
      [43]    UV index (u8, tenths)
      [44:46] solar radiation (u16 LE, W/m²)
      [46:48] storm rain (u16 LE, clicks)
      [50:52] day rain (u16 LE, clicks)
      [52:54] rain last 15 min (u16 LE, clicks)
      [54:56] rain last hour (u16 LE, clicks)
      [56:58] day ET (u16 LE, thousandths inch)
      [58:60] rain last 24 hours (u16 LE, clicks)
      [62:64] absolute barometric pressure (u16 LE, thousandths inHg)
      [64:66] altimeter barometric pressure (u16 LE, thousandths inHg)
      [97:99] CRC (u16 BE)
    """
    if len(raw) < LOOP_PACKET_SIZE:
        logger.warning("LOOP2 packet too short: %d/%d bytes", len(raw), LOOP_PACKET_SIZE)
        return None

    if raw[0:3] != LOOP_HEADER:
        logger.warning("LOOP2 missing header: %s", raw[0:3])
        return None

    if raw[4] != 1:
        logger.warning("LOOP2 wrong packet type: %d (expected 1)", raw[4])
        return None

    if not crc_validate(raw[:LOOP_PACKET_SIZE]):
        logger.warning("LOOP2 CRC validation failed")
        return None

    data = Loop2Data()

    # Bar trend
    bar_trend_raw = struct.unpack_from("<b", raw, 3)[0]
    if bar_trend_raw != BAR_TREND_UNKNOWN:
        data.bar_trend = bar_trend_raw

    # Barometer
    data.barometer = _valid_barometer(struct.unpack_from("<H", raw, 7)[0])

    # Higher-precision wind fields (tenths mph)
    val = struct.unpack_from("<H", raw, 18)[0]
    data.wind_speed_10min = val if val != 0x7FFF else None
    val = struct.unpack_from("<H", raw, 20)[0]
    data.wind_speed_2min = val if val != 0x7FFF else None
    val = struct.unpack_from("<H", raw, 22)[0]
    data.wind_gust_10min = val if val != 0x7FFF else None
    val = struct.unpack_from("<H", raw, 24)[0]
    data.wind_gust_dir = val if val != 0x7FFF else None

    # Derived values computed by the station.
    #
    # Heat index, wind chill and THSW were each read one byte early,
    # straddling the previous field's high byte and this field's low byte.
    # Dew point at 30 was correct; the drift starts at 34 because the
    # single unused byte at 32 and the humidity byte at 33 were counted as
    # one field, not two.  Manual §X.2 gives 30 / 35 / 37 / 39.
    #
    # The dashed sentinel is 0x7FFF, not 0xFF: these are two-byte fields,
    # so the byte-width sentinel could never match one.  That is how a
    # bogus -256 THSW reached extra_json rather than being filtered.  The
    # manual's own table says "255 = dashed data" for all four, which is
    # wrong for the same reason -- the Vue puts 0x7FFF in THSW when it has
    # no solar sensor to compute one from, and that is what the wire
    # shows.
    #
    # Measured on a Vue (fw 2.12), bytes 28..46, to settle it:
    #   heat_index  @34 = 22783 (garbage)  @35 =    88 °F
    #   wind_chill  @36 = 21504 (garbage)  @37 =    84 °F
    #   thsw_index  @38 =  -256 (garbage)  @39 = 32767 (dashed)
    val = struct.unpack_from("<h", raw, 30)[0]
    data.dew_point = _valid_derived_temp(val)
    val = struct.unpack_from("<h", raw, 35)[0]
    data.heat_index = _valid_derived_temp(val)
    val = struct.unpack_from("<h", raw, 37)[0]
    data.wind_chill = _valid_derived_temp(val)
    val = struct.unpack_from("<h", raw, 39)[0]
    data.thsw_index = _valid_derived_temp(val)

    # Rain
    data.rain_rate = _valid_rain_rate(struct.unpack_from("<H", raw, 41)[0])
    data.day_rain = struct.unpack_from("<H", raw, 50)[0]
    data.rain_last_15min = struct.unpack_from("<H", raw, 52)[0]
    data.rain_last_hour = struct.unpack_from("<H", raw, 54)[0]

    # UV / Solar
    data.uv_index = _valid_uv(raw[43])
    data.solar_radiation = _valid_solar(struct.unpack_from("<H", raw, 44)[0])

    # Barometer block, §X.2 bytes 60-70.  The whole block was read two
    # bytes early, so both values straddled the boundary between the
    # neighbouring fields and were garbage:
    #
    #   absolute   read @62 -> 54.272 inHg   correct @67 -> 29.630 inHg
    #   altimeter  read @64 -> 36.095 inHg   correct @69 -> 29.915 inHg
    #
    # Two independent confirmations that the manual's map is the right
    # one, measured on a Vue (fw 2.12):
    #
    #   raw 29580 + user_offset 50 == absolute 29630, the relationship
    #   the manual states between those three fields; and
    #
    #   the calibration number at 63 reads -44 as a SIGNED int16, which
    #   is exactly what BARDATA independently reports as OFFSET.
    #
    # Nothing consumed either field, so no stored data is affected.  They
    # are wired up now because barometer calibration needs them: the
    # difference between the raw sensor reading and the altimeter setting
    # is what a calibration tool has to show.
    data.bar_reduction_method = raw[60]
    data.bar_user_offset = struct.unpack_from("<H", raw, 61)[0]
    # Signed: a negative calibration number is normal, and reading it
    # unsigned turns -44 into 65492.
    data.bar_calibration = struct.unpack_from("<h", raw, 63)[0]
    data.bar_raw_sensor = _valid_barometer(struct.unpack_from("<H", raw, 65)[0])
    data.abs_barometer = _valid_barometer(struct.unpack_from("<H", raw, 67)[0])
    data.altimeter_barometer = _valid_barometer(struct.unpack_from("<H", raw, 69)[0])

    return data


# --------------- Merge to SensorSnapshot ---------------

def _f10_to_c(tenths_f: int) -> float:
    """Tenths °F → °C float."""
    return round((tenths_f / 10.0 - 32) * 5 / 9, 1)


def _inhg1000_to_hpa(thousandths_inhg: int) -> float:
    """Thousandths inHg → hPa float."""
    return round(thousandths_inhg / 1000.0 * 33.8639, 1)


def _mph_to_ms(mph: int) -> float:
    """mph integer → m/s float."""
    return round(mph * 0.44704, 1)


def _clicks_to_mm(clicks: float, click_inches: float) -> float:
    """Rain clicks → mm."""
    return round(clicks * click_inches * 25.4, 2)


def loop_to_snapshot(
    loop: LoopData,
    loop2: Optional[Loop2Data],
    rain_click_inches: float,
) -> SensorSnapshot:
    """Merge LOOP + optional LOOP2 data into a SensorSnapshot (SI).

    Davis native units converted to SI: °C, hPa, m/s, mm.
    LOOP2 fields override LOOP where both are available.
    """
    # Temperature: tenths F → °C
    inside_temp = _f10_to_c(loop.inside_temp) if loop.inside_temp is not None else None
    outside_temp = _f10_to_c(loop.outside_temp) if loop.outside_temp is not None else None

    # Barometer: thousandths inHg → hPa
    barometer = _inhg1000_to_hpa(loop.barometer) if loop.barometer is not None else None

    # Wind: mph → m/s; prefer LOOP2 gust if available
    wind_speed = _mph_to_ms(loop.wind_speed) if loop.wind_speed is not None else None
    wind_direction = loop.wind_direction
    wind_gust = None
    thsw_index = None

    if loop2 is not None:
        if loop2.wind_gust_10min is not None:
            wind_gust = _mph_to_ms(round(loop2.wind_gust_10min / 10.0))

    # Rain: clicks → mm
    rain_rate = None
    if loop.rain_rate is not None:
        rain_rate = _clicks_to_mm(loop.rain_rate, rain_click_inches)
    if loop2 is not None and loop2.rain_rate is not None:
        rain_rate = _clicks_to_mm(loop2.rain_rate, rain_click_inches)

    rain_daily = _clicks_to_mm(loop.day_rain, rain_click_inches) if loop.day_rain is not None else None
    rain_yearly = _clicks_to_mm(loop.year_rain, rain_click_inches) if loop.year_rain is not None else None

    if loop2 is not None and loop2.day_rain is not None:
        rain_daily = _clicks_to_mm(loop2.day_rain, rain_click_inches)

    # UV: tenths → float
    uv = loop.uv_index
    if loop2 is not None and loop2.uv_index is not None:
        uv = loop2.uv_index
    uv_index = uv / 10.0 if uv is not None else None

    # Solar: direct W/m²
    solar = loop.solar_radiation
    if loop2 is not None and loop2.solar_radiation is not None:
        solar = loop2.solar_radiation

    # Soil: tenths F → °C
    soil_temp = None
    if loop.soil_temps and loop.soil_temps[0] is not None:
        soil_temp = _f10_to_c(loop.soil_temps[0])

    soil_moisture = None
    if loop.soil_moistures and loop.soil_moistures[0] is not None:
        soil_moisture = loop.soil_moistures[0]

    leaf_wetness = None
    if loop.leaf_wetnesses and loop.leaf_wetnesses[0] is not None:
        leaf_wetness = loop.leaf_wetnesses[0]

    # ET: thousandths inch → mm
    et_daily = None
    if loop.day_et is not None:
        et_daily = round(loop.day_et / 1000.0 * 25.4, 2)

    # Build extra dict with LOOP2-only and multi-sensor data
    extra: dict = {}
    if loop.bar_trend is not None:
        extra["bar_trend"] = loop.bar_trend
    if loop.forecast_rule is not None:
        extra["forecast_rule"] = loop.forecast_rule
    if loop.sunrise is not None:
        extra["sunrise"] = loop.sunrise
    if loop.sunset is not None:
        extra["sunset"] = loop.sunset
    # Battery status.  Surface the raw bitmask alongside a decoded list of
    # transmitter IDs so a consumer can show "ISS battery low" without
    # re-deriving the bit positions.
    if loop.transmitter_battery_status is not None:
        extra["transmitter_battery_status"] = loop.transmitter_battery_status
        low = [n + 1 for n in range(8)
               if loop.transmitter_battery_status & (1 << n)]
        extra["transmitters_low_battery"] = low
    if loop.console_battery_voltage is not None:
        extra["console_battery_voltage"] = loop.console_battery_voltage
    if loop.storm_rain is not None and loop.storm_rain > 0:
        extra["storm_rain_mm"] = _clicks_to_mm(loop.storm_rain, rain_click_inches)
    if loop.month_rain is not None:
        extra["month_rain_mm"] = _clicks_to_mm(loop.month_rain, rain_click_inches)

    if loop2 is not None:
        # THSW is the one derived value we cannot compute: it needs solar
        # radiation.  A station without a solar sensor sends the dashed
        # sentinel, which _valid_derived_temp() has already turned into
        # None, so this is gated on the value arriving rather than on the
        # station model — fit a solar sensor and it starts working with no
        # code change.
        #
        # Converted to °C here.  It used to go into extra as raw °F while
        # every other snapshot field was SI, which would have put a 90 °F
        # THSW on a °C dashboard.
        if loop2.thsw_index is not None:
            thsw_c = (loop2.thsw_index - 32) * 5.0 / 9.0
            thsw_index = round(thsw_c, 1)
            extra["thsw_index_c"] = thsw_index
        if loop2.wind_speed_2min is not None:
            extra["wind_2min_avg_ms"] = _mph_to_ms(round(loop2.wind_speed_2min / 10.0))
        if loop2.wind_speed_10min is not None:
            extra["wind_10min_avg_ms"] = _mph_to_ms(round(loop2.wind_speed_10min / 10.0))
        if loop2.wind_gust_10min is not None:
            extra["wind_gust_10min_ms"] = _mph_to_ms(round(loop2.wind_gust_10min / 10.0))
        if loop2.wind_gust_dir is not None:
            extra["wind_gust_dir"] = loop2.wind_gust_dir
        if loop2.rain_last_15min is not None:
            extra["rain_15min_mm"] = _clicks_to_mm(loop2.rain_last_15min, rain_click_inches)
        if loop2.rain_last_hour is not None:
            extra["rain_hour_mm"] = _clicks_to_mm(loop2.rain_last_hour, rain_click_inches)

    return SensorSnapshot(
        inside_temp=inside_temp,
        outside_temp=outside_temp,
        inside_humidity=loop.inside_humidity,
        outside_humidity=loop.outside_humidity,
        wind_speed=wind_speed,
        wind_direction=wind_direction,
        wind_gust=wind_gust,
        barometer=barometer,
        rain_rate=rain_rate,
        rain_daily=rain_daily,
        rain_yearly=rain_yearly,
        solar_radiation=solar,
        uv_index=uv_index,
        soil_temp=soil_temp,
        soil_moisture=soil_moisture,
        leaf_wetness=leaf_wetness,
        et_daily=et_daily,
        thsw_index=thsw_index,
        extra=extra,
    )
