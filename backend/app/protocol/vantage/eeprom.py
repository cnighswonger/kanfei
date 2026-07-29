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
# Only CAL_OUTSIDE_TEMP is verified against hardware (Vantage Vue fw 2.12).
# The others are unverified and MUST be confirmed on a real station before
# anything is wired up to them — see the note below and issue #209.

# VERIFIED: 1 signed byte, tenths °F.  Writing 10/25/50/-10 moved the
# reported outside temperature by +1.0/+2.5/+5.0/-1.0 °F respectively.
# Note this is ONE byte, not the i16 previously declared here; 0x35 was
# probed and is inert, so it is not a high byte.
CAL_OUTSIDE_TEMP = EEAddr(0x34, 1)    # signed i8, tenths °F

# UNVERIFIED — addresses below are believed-wrong or untested.
#
# The outside-humidity offset is NOT at 0x46 (the value this file used to
# carry) and NOT at 0x45.  Both accept a write and read the value back, yet
# leave the reported humidity unchanged.  Every byte in 0x40–0x50 was swept
# with a +20 offset against a console reading a rock-steady 55% RH; none
# moved it by more than ambient drift (±1%).  The correct address is not
# yet known, so no constant is defined for it — a wrong one is worse than
# a missing one, because it fails silently.
#
# CAL_INSIDE_TEMP and CAL_INSIDE_HUM are simply untested. They may be
# correct; nobody has checked. They plausibly came from the same source as
# the two known-bad entries, so treat them as suspect until proven.
CAL_INSIDE_TEMP = EEAddr(0x32, 1)     # UNVERIFIED: signed i8, tenths °F?
CAL_INSIDE_HUM = EEAddr(0x44, 1)      # UNVERIFIED: signed i8, percent?


# --------------- Helpers ---------------

def extract_rain_collector_type(setup_bits: int) -> int:
    """Extract rain collector code from the setup bits byte (bits 4-5).

    Returns: 0 = 0.01″, 1 = 0.2 mm, 2 = 0.1 mm
    """
    return (setup_bits >> 4) & 0x03
