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


def cmd_opmode() -> bytes:
    """OPMODE — read radio state and per-unit crystal calibration.

    Undocumented in Davis Serial Communication Reference v2.6.1, but
    verified working identically on Vantage Vue Console fw 2.12 and
    fw 4.33 during the wire audit (see
    `reference/vantage_fw433_wire_audit.md`).  Returns a multi-line
    ASCII block, one ``KEY: value`` per line, terminated by an empty
    ``\\n\\r`` line.  Fields observed on Vue:

        TST:      test-mode flag (0 = normal ops, 1 = test)
        TX:       transmit configuration
        RX:       receive configuration
        HOP:      hop mode
        BAND:     radio band
        CHAN:     radio channel
        DOM:      radio domain (1 = US 902-928 MHz per convention)
        XTLCAL:   per-unit factory crystal calibration (immutable)
        TEMP:     raw crystal / oven temperature reading
        TEMP CAL: temperature calibration offset

    Behaviour on VP1 / older VP2 firmware is not verified — callers
    must tolerate an empty or malformed response.
    """
    return b"OPMODE\n"


def cmd_ident() -> bytes:
    """IDENT — get product SKU.

    Undocumented in Davis Serial Communication Reference v2.6.1, but
    verified working identically on Vantage Vue Console fw 2.12 and
    fw 4.33 during the wire audit (see
    `reference/vantage_fw433_wire_audit.md`).  Returns the four-digit
    product number as ASCII (`6351` for Vantage Vue Wireless with
    WeatherLink IP, etc.).  Behaviour on older Vantage Pro / Pro2
    firmware is not verified — callers must tolerate an empty or
    malformed response.
    """
    return b"IDENT\n"


def cmd_rxcheck() -> bytes:
    """RXCHECK — receiver diagnostics."""
    return b"RXCHECK\n"


def cmd_bardata() -> bytes:
    """BARDATA — read barometer calibration parameters as text (§IX.5)."""
    return b"BARDATA\n"


def cmd_receivers() -> bytes:
    """RECEIVERS — bitmask of transmitter IDs the console is hearing.

    Manual section IX.1.  Replies "OK" then a single RAW byte, not text:
    bit 0 = Tx ID 1.  Note this reports what is being *received*, not what
    the console is configured to listen for (EEPROM USETX at 0x18).
    """
    return b"RECEIVERS\n"


def cmd_getee() -> bytes:
    """GETEE — dump the entire 4096-byte EEPROM plus a 2-byte CRC (§IX.4)."""
    return b"GETEE\n"


def cmd_rxtest() -> bytes:
    """RXTEST — leave the "Receiving From…" screen (§IX.1).

    Moves the console from the "Receiving From…" setup screen to the main
    current-conditions screen.  The manual presents this as the way to
    "programmatically recover from a powerloss when the console boots into
    the receiving from screen" — and NEWSETUP appears to leave it in that
    same state, which stops normal sensor reception even though the
    console still answers serial commands.

    Also clears the CRC error count reported by RXCHECK.
    """
    return b"RXTEST\n"


def cmd_newsetup() -> bytes:
    """NEWSETUP — re-initialise the console after a config change (§IX.7).

    The manual is emphatic that this must follow a latitude or longitude
    write, and any change to the setup bits at 0x2B.  It says only
    "re-initializes" and does not enumerate what that resets, so callers
    should verify anything they care about afterwards rather than assume.
    """
    return b"NEWSETUP\n"


def cmd_putrain(clicks: int) -> bytes:
    """PUTRAIN — set the yearly rain total, in RAIN CLICKS (§IX.2).

    The unit is clicks, not inches and not millimetres, and a click is not
    a fixed size: 0.01", 0.2 mm or 0.1 mm depending on the collector
    fitted (EEPROM setup bits, 0x2B).  Passing a value in any other unit
    silently sets the wrong yearly total, so callers should go through
    VantageDriver.set_yearly_rain(), which converts from mm using the
    collector this station actually reports.

    The manual's example sets 24.83 inches on a 0.01" collector as
    "PUTRAIN 2483".
    """
    return f"PUTRAIN {clicks}\n".encode()


def cmd_putet(hundredths_inch: int) -> bytes:
    """PUTET — set the yearly ET total, in HUNDREDTHS OF AN INCH (§IX.2).

    Note this differs from PUTRAIN: ET is a fixed hundredths-of-an-inch
    unit with no collector dependency.  The two commands sit next to each
    other in the manual and read alike, which makes it easy to assume they
    share a unit.  They do not.
    """
    return f"PUTET {hundredths_inch}\n".encode()


def cmd_dmp() -> bytes:
    """DMP — download the entire archive memory (§IX.3).

    Uses the same paged transfer as DMPAFT (§X.6): 267-byte pages, each
    ACKed or NAKed, ESC to abort.
    """
    return b"DMP\n"


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


# --------------- CLRHIGHS / CLRLOWS periods ---------------
# Manual sections IX.6 / IX.13: the argument is 0, 1, or 2.  An earlier
# docstring here claimed -1 meant yearly; that is wrong and would have put
# an undefined value on the wire.  Nothing called it, so nothing broke.
#
# These clear *every* extremum for the period.  Per section II.4, "You can
# not reset individual high or low values" — there is no way to clear just
# one sensor's high, so callers must accept the collateral.
CLR_PERIOD_DAILY = 0
CLR_PERIOD_MONTHLY = 1
CLR_PERIOD_YEARLY = 2

CLR_PERIODS: frozenset[int] = frozenset({
    CLR_PERIOD_DAILY, CLR_PERIOD_MONTHLY, CLR_PERIOD_YEARLY,
})

CLR_PERIOD_NAMES: dict[int, str] = {
    CLR_PERIOD_DAILY: "daily",
    CLR_PERIOD_MONTHLY: "monthly",
    CLR_PERIOD_YEARLY: "yearly",
}


def cmd_clrhighs(period: int = CLR_PERIOD_DAILY) -> bytes:
    """CLRHIGHS — clear ALL high records for a period (0/1/2)."""
    return f"CLRHIGHS {period}\n".encode()


def cmd_hilows() -> bytes:
    """HILOWS — read the current 436-byte hi/low block + 2-byte CRC.

    Manual section IX.2: the station responds with <ACK> then a 436-byte
    payload holding daily, monthly, and yearly highs/lows for every
    supported sensor, plus a trailing big-endian CRC-16.  Layout is
    documented in section X.3.
    """
    return b"HILOWS\n"


def cmd_clrlows(period: int = CLR_PERIOD_DAILY) -> bytes:
    """CLRLOWS — clear ALL low records for a period (0/1/2)."""
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


# --------------- CLRVAR data-variable numbers ---------------
# Manual section IX.6.  "Results are undefined if you use a number not on
# this list", so callers must be restricted to exactly these values.
# Note 15 is deliberately absent — the documented set is not contiguous.
CLRVAR_RAIN_DAILY = 13
CLRVAR_RAIN_STORM = 14
CLRVAR_RAIN_MONTH = 16
CLRVAR_RAIN_YEAR = 17
CLRVAR_ET_MONTH = 25
CLRVAR_ET_DAY = 26
CLRVAR_ET_YEAR = 27

CLRVAR_VARIABLES: frozenset[int] = frozenset({
    CLRVAR_RAIN_DAILY, CLRVAR_RAIN_STORM, CLRVAR_RAIN_MONTH, CLRVAR_RAIN_YEAR,
    CLRVAR_ET_MONTH, CLRVAR_ET_DAY, CLRVAR_ET_YEAR,
})

CLRVAR_NAMES: dict[int, str] = {
    CLRVAR_RAIN_DAILY: "daily rain",
    CLRVAR_RAIN_STORM: "storm rain",
    CLRVAR_RAIN_MONTH: "month rain",
    CLRVAR_RAIN_YEAR: "year rain",
    CLRVAR_ET_MONTH: "month ET",
    CLRVAR_ET_DAY: "day ET",
    CLRVAR_ET_YEAR: "year ET",
}


def cmd_clrvar(variable: int) -> bytes:
    """CLRVAR — clear a single rain or ET accumulator.

    `variable` must be one of CLRVAR_VARIABLES; the manual warns that any
    other number produces undefined behaviour, so this is not a value to
    pass through from user input unchecked.
    """
    return f"CLRVAR {variable}\n".encode()
