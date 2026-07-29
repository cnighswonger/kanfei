"""Command builders for the Davis Vantage serial protocol.

All Vantage commands are ASCII text terminated with LF (0x0A).
Binary payloads (DMPAFT timestamp, SETTIME data) include a trailing
big-endian CRC-16 per the Davis specification.
"""

import struct

from ..crc import crc_calculate


# --------------- Simple commands ---------------

def cmd_wakeup() -> bytes:
    """Wakeup: send LF, expect LF CR response."""
    return b"\n"


def cmd_loop(count: int = 1) -> bytes:
    """LOOP command — request *count* LOOP packets (VP1 compatible)."""
    return f"LOOP {count}\n".encode()


def cmd_lps(bitmask: int, count: int) -> bytes:
    """LPS command — interleaved LOOP/LOOP2 packets.

    bitmask: 1=LOOP only, 2=LOOP2 only, 3=both alternating
    count:   number of iterations
    Requires VP2/Vue with firmware >= 1.90.
    """
    return f"LPS {bitmask} {count}\n".encode()


def cmd_ver() -> bytes:
    """VER — get firmware date string."""
    return b"VER\n"


def cmd_nver() -> bytes:
    """NVER — get firmware version number (VP2/Vue only, VP1 will NAK)."""
    return b"NVER\n"


def cmd_rxcheck() -> bytes:
    """RXCHECK — receiver diagnostics."""
    return b"RXCHECK\n"


def cmd_dmpaft() -> bytes:
    """DMPAFT — begin archive dump after timestamp."""
    return b"DMPAFT\n"


def cmd_gettime() -> bytes:
    """GETTIME — read station clock."""
    return b"GETTIME\n"


def cmd_settime() -> bytes:
    """SETTIME — begin clock set sequence (followed by 8-byte payload)."""
    return b"SETTIME\n"


def cmd_eebrd(address: int, n_bytes: int) -> bytes:
    """EEBRD — read *n_bytes* from EEPROM at *address*."""
    return f"EEBRD {address:02X} {n_bytes:02X}\n".encode()


def cmd_eebwr(address: int, n_bytes: int) -> bytes:
    """EEBWR — begin write of *n_bytes* to EEPROM at *address*."""
    return f"EEBWR {address:02X} {n_bytes:02X}\n".encode()


def cmd_bar(current_bar: int, elevation: int) -> bytes:
    """BAR= — set barometer calibration.

    current_bar: thousandths inHg
    elevation:   feet
    """
    return f"BAR={current_bar} {elevation}\n".encode()


def cmd_clrlog() -> bytes:
    """CLRLOG — clear archive memory."""
    return b"CLRLOG\n"


def cmd_clrhighs(period: int = 0) -> bytes:
    """CLRHIGHS — clear high records (0=daily, 1=monthly, -1=yearly)."""
    return f"CLRHIGHS {period}\n".encode()


def cmd_clrlows(period: int = 0) -> bytes:
    """CLRLOWS — clear low records (0=daily, 1=monthly, -1=yearly)."""
    return f"CLRLOWS {period}\n".encode()


# --------------- Binary payload builders ---------------

def build_dmpaft_timestamp(
    year: int, month: int, day: int, hour: int, minute: int,
) -> bytes:
    """Build the 6-byte DMPAFT timestamp payload.

    Returns: date_stamp(u16 LE) + time_stamp(u16 LE) + CRC(u16 BE)
    date_stamp = day + month*32 + (year-2000)*512
    time_stamp = hour*100 + minute
    """
    date_stamp = day + month * 32 + (year - 2000) * 512
    time_stamp = hour * 100 + minute
    data = struct.pack("<HH", date_stamp, time_stamp)
    crc = crc_calculate(data)
    return data + struct.pack(">H", crc)


def build_settime_payload(
    year: int, month: int, day: int,
    hour: int, minute: int, second: int,
) -> bytes:
    """Build the 8-byte SETTIME data payload.

    Returns: sec, min, hr, day, month, year-1900 (6 bytes) + CRC(u16 BE)
    """
    data = bytes([second, minute, hour, day, month, year - 1900])
    crc = crc_calculate(data)
    return data + struct.pack(">H", crc)


def cmd_caled() -> bytes:
    """CALED — request the current CALIBRATED temp/humidity block."""
    return b"CALED\n"


def cmd_calfix() -> bytes:
    """CALFIX — send UN-CALIBRATED values so the display adopts new cal."""
    return b"CALFIX\n"


def cmd_clrcal() -> bytes:
    """CLRCAL — clear all temperature and humidity calibration offsets."""
    return b"CLRCAL\n"


def cmd_setper(minutes: int) -> bytes:
    """SETPER — set the archive interval in minutes.

    Manual section IX.7 claims this "automatically clears the archive
    memory ... so that all archived records in the archive memory use the
    same archive interval".  **It does not**, at least on a Vantage Vue
    running fw 2.12: the interval changed and every existing record stayed
    put, leaving precisely the mixed-interval archive the manual says this
    prevents.  Send CLRLOG explicitly if a clean archive is wanted.
    """
    return f"SETPER {minutes}\n".encode()
