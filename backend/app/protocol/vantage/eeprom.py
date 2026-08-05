"""EEPROM address map for Davis Vantage stations.

Addresses reference the Vantage Pro, Pro2, and Vue Serial Communication
Reference Manual v2.6.1.  Read via EEBRD, write via EEBWR.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EEAddr:
    """EEPROM address and expected byte count."""
    address: int
    n_bytes: int


# --------------- System configuration ---------------

ARCHIVE_INTERVAL = EEAddr(0x2D, 1)    # minutes (1–120)
# NOTE: station type is NOT in EEPROM.  It lives in processor memory at
# 0x4D and is read with the WRD command — see STATION_TYPE_WRD_ADDR in
# constants.py.  A `STATION_TYPE = EEAddr(0x12, 1)` entry used to sit here;
# 0x12 was the WRD command byte mistaken for an address, and EEBRD 0x12
# reads an unrelated location that holds 0x00 on a Vue.
SETUP_BITS = EEAddr(0x2B, 1)          # bits 4-5: rain collector type
UNIT_BITS = EEAddr(0x29, 1)           # unit configuration byte
RAIN_YEAR_START = EEAddr(0x2C, 1)     # month (1–12)
TIME_ZONE = EEAddr(0x11, 1)           # signed byte, hours GMT offset
RETRANSMIT_ID = EEAddr(0x18, 1)       # 0 = off, 1–8 = ID

# --------------- Location ---------------

LATITUDE = EEAddr(0x0B, 2)            # i16, tenths of a degree
LONGITUDE = EEAddr(0x0D, 2)           # i16, tenths of a degree
ELEVATION = EEAddr(0x0F, 2)           # i16, feet

# --------------- Calibration offsets ---------------
#
# Source: Davis Vantage Serial Communication Reference Rev 2.6.1, section
# XIII (`reference/vantage_serial_ref_v261.txt`).  Quoting the map header:
#
#   "Calibration values are 1 byte signed numbers that are offsets applied
#    to the corresponding raw sensor value in the native sensor units
#    (either 0.1 °F or 1 %)"
#
# So every entry here is 1 byte per field, signed.  Multi-byte entries
# below are arrays of 1-byte fields, not wide integers.
#
# IMPORTANT: writing these with EEBWR alone does NOT change what the
# console reports.  Section XIV.1: the new value "will not take effect
# until the next time the Vantage receives a data packet containing that
# temperature or humidity value".  Use VantageDriver.write_calibration(),
# which performs the documented CALED/CALFIX sequence.

CAL_INSIDE_TEMP = EEAddr(0x32, 1)     # signed i8, tenths °F
# Documented companion byte: the 1's complement of CAL_INSIDE_TEMP.  We
# write it to keep the documented pair consistent, NOT because the console
# checks it — fw 3.0 applied an offset carrying a deliberately wrong
# complement (#273).  What applies a calibration is CALFIX.
CAL_INSIDE_TEMP_COMP = EEAddr(0x33, 1)

# VERIFIED on hardware (Vantage Vue fw 2.12): writing 10/25/50/-10 moved
# the reported outside temperature by +1.0/+2.5/+5.0/-1.0 °F.
CAL_OUTSIDE_TEMP = EEAddr(0x34, 1)    # signed i8, tenths °F

# 15 one-byte offsets: 7 "extra" temps, then 4 soil, then 4 leaf.
CAL_TEMP_EXTRA = EEAddr(0x35, 15)

CAL_INSIDE_HUM = EEAddr(0x44, 1)      # signed i8, percent

# HUM_CAL is 8 one-byte offsets.  Per the manual, "the first entry is the
# currently selected outside humidity sensor" — so outside humidity is
# 0x45 and the extra humidities are 0x46..0x4C.
#
# 0x46 is where this file previously (wrongly) put outside humidity; it is
# extra-humidity 1, which is inert on a station with no extra sensors.
# That is why writes to it appeared to succeed and do nothing (#209).
CAL_OUTSIDE_HUM = EEAddr(0x45, 1)     # signed i8, percent
CAL_HUM_ALL = EEAddr(0x45, 8)         # outside + 7 extra

CAL_WIND_DIR = EEAddr(0x4D, 2)        # i16, degrees

# The calibration block ends at 0x4E.  0x4F onward is graph defaults and
# then ALARM_START at 0x52 — see CAL_BLOCK_* in constants.py for why the
# manual's own "EEBWR 32 2B" example must not be followed literally.


# --------------- Helpers ---------------

def extract_rain_collector_type(setup_bits: int) -> int:
    """Extract rain collector code from the setup bits byte (bits 4-5).

    Returns: 0 = 0.01″, 1 = 0.2 mm, 2 = 0.1 mm
    """
    return (setup_bits >> 4) & 0x03
