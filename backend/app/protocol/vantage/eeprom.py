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
STATION_TYPE = EEAddr(0x12, 1)        # 16 = VP1/VP2, 17 = Vue
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

CAL_INSIDE_TEMP = EEAddr(0x32, 2)     # signed i16, tenths °F
CAL_OUTSIDE_TEMP = EEAddr(0x34, 2)    # signed i16, tenths °F
CAL_INSIDE_HUM = EEAddr(0x44, 1)      # signed i8, percent
CAL_OUTSIDE_HUM = EEAddr(0x46, 1)     # signed i8, percent


# --------------- Helpers ---------------

def extract_rain_collector_type(setup_bits: int) -> int:
    """Extract rain collector code from the setup bits byte (bits 4-5).

    Returns: 0 = 0.01″, 1 = 0.2 mm, 2 = 0.1 mm
    """
    return (setup_bits >> 4) & 0x03
