"""LOOP packet field definitions per station type.

Each station type has a different LOOP packet layout. Fields are defined
as (offset, size_bytes, signed, name) tuples where offset is relative to
the start of the data (after SOH byte).

Reference: techref.txt lines 510-591
"""

from dataclasses import dataclass
from typing import Optional

from .constants import StationModel, BASIC_STATIONS


@dataclass(frozen=True)
class LoopField:
    """Definition of a single field within a LOOP packet."""
    offset: int
    size: int  # bytes
    signed: bool
    name: str


# Monitor / Wizard / Perception LOOP layout (15 data bytes)
# Offsets are from start of data (byte after SOH)
BASIC_LOOP_FIELDS = [
    LoopField(0, 2, True, "inside_temp"),       # tenths F, signed int16
    LoopField(2, 2, True, "outside_temp"),       # tenths F, signed int16
    LoopField(4, 1, False, "wind_speed"),        # mph, unsigned byte
    LoopField(5, 2, False, "wind_direction"),    # degrees 0-359, unsigned int16
    LoopField(7, 2, False, "barometer"),         # thousandths inHg, unsigned int16
    LoopField(9, 1, False, "inside_humidity"),   # percent 0-100, unsigned byte
    LoopField(10, 1, False, "outside_humidity"), # percent 0-100, unsigned byte
    LoopField(11, 2, False, "rain_total"),       # clicks, unsigned int16
    # bytes 13-14 unused
]

# GroWeather LOOP layout (33 data bytes)
GROWEATHER_LOOP_FIELDS = [
    LoopField(0, 2, False, "archive_pointer"),   # next archive address
    LoopField(2, 1, False, "bar_power_status"),  # See Appendix A
    LoopField(3, 2, True, "soil_temp"),          # tenths F (replaces inside temp)
    LoopField(5, 2, True, "outside_temp"),       # tenths F
    LoopField(7, 1, False, "wind_speed"),        # mph
    LoopField(8, 2, False, "wind_direction"),    # degrees
    LoopField(10, 2, False, "barometer"),        # thousandths inHg
    LoopField(12, 1, False, "rain_rate"),        # half-seconds per click
    LoopField(13, 1, False, "outside_humidity"), # percent
    LoopField(14, 2, False, "rain_total"),       # clicks
    LoopField(16, 2, False, "solar_radiation"),  # W/m2
    LoopField(18, 3, False, "wind_run_total"),   # miles * 10
    LoopField(21, 2, False, "et_total"),         # hundredths inch
    LoopField(23, 3, False, "degree_days_total"),# tenths F-day
    LoopField(26, 3, False, "solar_energy_total"),# Langleys * 10
    LoopField(29, 3, False, "alarm_aom_status"), # alarm bits + AOM
    LoopField(32, 1, False, "leaf_wetness"),     # 0=dry, 15=wet
]

# Energy LOOP layout (27 data bytes)
ENERGY_LOOP_FIELDS = [
    LoopField(0, 2, False, "archive_pointer"),
    LoopField(2, 1, False, "bar_power_status"),
    LoopField(3, 2, True, "inside_temp"),        # tenths F
    LoopField(5, 2, True, "outside_temp"),       # tenths F
    LoopField(7, 1, False, "wind_speed"),        # mph
    LoopField(8, 2, False, "wind_direction"),    # degrees
    LoopField(10, 2, False, "barometer"),        # thousandths inHg
    LoopField(12, 1, False, "rain_rate"),
    LoopField(13, 1, False, "outside_humidity"), # percent
    LoopField(14, 2, False, "rain_total"),       # clicks
    LoopField(16, 2, False, "solar_radiation"),  # W/m2
    LoopField(18, 3, False, "alarm_aom_status"),
    # bytes 21-26 reserved
]

# Health LOOP layout (25 data bytes)
HEALTH_LOOP_FIELDS = [
    LoopField(0, 2, False, "archive_pointer"),
    LoopField(2, 1, False, "bar_power_status"),
    LoopField(3, 2, True, "inside_temp"),        # tenths F
    LoopField(5, 2, True, "outside_temp"),       # tenths F
    LoopField(7, 1, False, "wind_speed"),        # mph
    LoopField(8, 2, False, "wind_direction"),    # degrees
    LoopField(10, 2, False, "barometer"),        # thousandths inHg
    LoopField(12, 1, False, "rain_rate"),
    LoopField(13, 2, False, "rain_total"),       # clicks
    LoopField(15, 2, False, "solar_radiation"),  # W/m2
    LoopField(17, 1, False, "inside_humidity"),  # percent
    LoopField(18, 1, False, "outside_humidity"), # percent
    LoopField(19, 1, False, "uv_index"),         # index * 10
    LoopField(20, 2, False, "uv_dose"),          # MED * 10
    LoopField(22, 3, False, "alarm_aom_status"),
]


def get_loop_fields(model: StationModel) -> list[LoopField]:
    """Return the LOOP field definitions for the given station model."""
    if model in BASIC_STATIONS:
        return BASIC_LOOP_FIELDS
    elif model == StationModel.GROWEATHER:
        return GROWEATHER_LOOP_FIELDS
    elif model == StationModel.ENERGY:
        return ENERGY_LOOP_FIELDS
    elif model == StationModel.HEALTH:
        return HEALTH_LOOP_FIELDS
    else:
        raise ValueError(f"Unknown station model: {model}")


@dataclass
class SensorReading:
    """Parsed sensor data from a LOOP packet. All values in native units.

    Temperatures: tenths of degrees F (or None if invalid)
    Humidity: percent 0-100 (or None if invalid)
    Barometer: thousandths of inches Hg
    Wind speed: mph
    Wind direction: degrees 0-359
    Rain: raw clicks
    Solar radiation: W/m2 (or None if not available)
    UV index: tenths (or None if not available)
    """
    inside_temp: Optional[int] = None
    outside_temp: Optional[int] = None
    inside_humidity: Optional[int] = None
    outside_humidity: Optional[int] = None
    wind_speed: Optional[int] = None
    wind_direction: Optional[int] = None
    barometer: Optional[int] = None
    rain_total: Optional[int] = None
    rain_rate: Optional[int] = None
    rain_yearly: Optional[int] = None
    solar_radiation: Optional[int] = None
    uv_index: Optional[int] = None
    uv_dose: Optional[int] = None
    soil_temp: Optional[int] = None
    leaf_wetness: Optional[int] = None
    wind_run_total: Optional[int] = None
    et_total: Optional[int] = None
    degree_days_total: Optional[int] = None
    solar_energy_total: Optional[int] = None
