"""BARDATA response parser for the Davis Vantage protocol.

BARDATA reports the console's barometer calibration state as text: the
current reading, the elevation and offset in use, and the intermediate
terms of the correction formula.  Manual section IX.5.

Captured from a Vantage Vue (fw 2.12) — the response is a bare "OK"
followed by one KEY VALUE line per field, each terminated LF CR:

    b'\\n\\rOK\\n\\rBAR 29916\\n\\rELEVATION 265\\n\\rDEW POINT 80\\n\\r'
    b'VIRTUAL TEMP 74\\n\\rC 69\\n\\rR 1007\\n\\rBARCAL 50\\n\\rGAIN 0\\n\\r'
    b'OFFSET -44\\n\\r'

Two details in that sample drive the parsing below, and neither is
obvious from the manual's example:

  * Keys contain spaces ("DEW POINT", "VIRTUAL TEMP"), so a line has to
    be split on its LAST space, not its first.
  * OFFSET came back negative.  The manual only ever shows positive
    values, so an unsigned parse would look correct until a console like
    this one produced -44.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# Scaling per field.  The console reports everything as an integer; the
# divisor differs per field and is documented in section IX.5's table.
#   BAR     thousandths inHg
#   R       thousandths (a ratio, ~1.0)
#   BARCAL  thousandths inHg
# The rest are plain integers in their natural unit.
_THOUSANDTHS = frozenset({"BAR", "R", "BARCAL"})

_EXPECTED_KEYS = (
    "BAR", "ELEVATION", "DEW POINT", "VIRTUAL TEMP",
    "C", "R", "BARCAL", "GAIN", "OFFSET",
)

# Key is everything up to the last space; value is the final token.
_LINE_RE = re.compile(r"^(?P<key>.+?)\s+(?P<value>-?\d+)$")


@dataclass
class BarometerCalibration:
    """Parsed BARDATA response.

    Raw integers are preserved alongside the scaled values: GAIN and
    OFFSET are factory sensor-calibration constants with no documented
    unit, so there is nothing meaningful to scale them by, and callers
    comparing against another console need the values as reported.
    """
    barometer_inhg: Optional[float] = None       # BAR, thousandths -> inHg
    elevation_ft: Optional[int] = None           # ELEVATION, feet
    dew_point_f: Optional[int] = None            # DEW POINT, whole F
    virtual_temp_f: Optional[int] = None         # VIRTUAL TEMP, whole F
    humidity_correction: Optional[int] = None    # C
    correction_ratio: Optional[float] = None     # R, thousandths -> ratio
    barcal_inhg: Optional[float] = None          # BARCAL, thousandths -> inHg
    gain: Optional[int] = None                   # factory constant
    offset: Optional[int] = None                 # factory constant, may be < 0
    raw: dict[str, int] = None                   # every key as reported

    def __post_init__(self):
        if self.raw is None:
            self.raw = {}


def parse_bardata(response: str) -> Optional[BarometerCalibration]:
    """Parse a BARDATA text response.

    Returns None only if nothing parseable was found at all.  A response
    missing some fields still yields a record with the rest populated —
    a console that omits a field should not cost us the ones it did send.
    """
    if not response:
        logger.warning("BARDATA: empty response")
        return None

    values: dict[str, int] = {}
    # The console terminates lines LF CR; normalise both so the split does
    # not depend on which the firmware happens to emit first.
    for line in response.replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line or line == "OK":
            continue
        match = _LINE_RE.match(line)
        if not match:
            logger.debug("BARDATA: unparsed line %r", line)
            continue
        key = match.group("key").strip()
        try:
            values[key] = int(match.group("value"))
        except ValueError:
            logger.debug("BARDATA: non-integer value in %r", line)

    if not values:
        logger.warning("BARDATA: no parseable fields in %r", response)
        return None

    missing = [k for k in _EXPECTED_KEYS if k not in values]
    if missing:
        logger.info("BARDATA: response omitted %s", ", ".join(missing))

    def scaled(key: str) -> Optional[float]:
        v = values.get(key)
        if v is None:
            return None
        return round(v / 1000.0, 3) if key in _THOUSANDTHS else v

    return BarometerCalibration(
        barometer_inhg=scaled("BAR"),
        elevation_ft=values.get("ELEVATION"),
        dew_point_f=values.get("DEW POINT"),
        virtual_temp_f=values.get("VIRTUAL TEMP"),
        humidity_correction=values.get("C"),
        correction_ratio=scaled("R"),
        barcal_inhg=scaled("BARCAL"),
        gain=values.get("GAIN"),
        offset=values.get("OFFSET"),
        raw=values,
    )
