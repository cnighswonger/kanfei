"""Tests for HILOWS parsing on Vantage stations (Ref #221).

CAP_HILOWS was advertised by VantageDriver with no command behind it —
the same advertise-what-you-cannot-do bug as the rain-clear buttons
(#220).  This module tests the parser directly against synthesised
blocks so a wire-level regression is caught before it reaches the Vue.

The load-bearing test here is sentinel filtering: an unpopulated
sensor slot MUST come back as None, not as a real number derived from
0xFF / 0x7FFF / 0x8000.  A Vue with base sensors + OAT/OHUM has 6 of 7
extra-temp slots empty, so a leak would show up on every real station.
"""

import struct

import pytest

from app.protocol.crc import crc_calculate
from app.protocol.vantage.commands import cmd_hilows
from app.protocol.vantage.hilows import (
    HILOWS_BLOCK_SIZE,
    HILOWS_TOTAL_SIZE,
    VantageHighsLows,
    parse_hilows,
)


# --------------- helpers ---------------

def _u16(v: int) -> bytes:
    return struct.pack("<H", v & 0xFFFF)


def _s16(v: int) -> bytes:
    return struct.pack("<h", v)


def _pack(overrides: dict[int, bytes]) -> bytes:
    """Build a 436-byte payload prefilled with per-field 'dashed' sentinels.

    The trick with a HILOWS block is that the dashed sentinel is
    field-width-dependent, not uniform: signed 2-byte temps use 0x7FFF,
    unsigned 1-byte fields use 0xFF, unsigned 2-byte fields use 0xFFFF.
    Filling with 0xFF blindly would give signed shorts of -1, which is a
    perfectly valid reading and would slip past the parser's filter —
    that's the bug we're preventing, not the test setup we want.

    So this builds sentinels per section from the §X.3 layout.
    """
    payload = bytearray(b"\xFF" * HILOWS_BLOCK_SIZE)

    # Every 2-byte signed-temp field → 0x7FFF (INVALID_TEMP).  Also
    # covers time fields, which are u16 and dashed with 0xFFFF.  The
    # time positions get overwritten below with 0xFFFF because "dashed"
    # for time is 0xFFFF not 0x7FFF — either sentinel round-trips to
    # None but keeping the wire-accurate value is worth the extra care.
    signed_short_offsets = [
        # inside temp (21..35)
        21, 23, 29, 31, 33, 35,
        # outside temp (47..61)
        47, 49, 55, 57, 59, 61,
        # dew point (63..77)
        63, 65, 71, 73, 75, 77,
        # wind chill (79, 83, 85)
        79, 83, 85,
        # heat index (87, 91, 93)
        87, 91, 93,
        # thsw (95, 99, 101)
        95, 99, 101,
    ]
    for off in signed_short_offsets:
        payload[off:off + 2] = struct.pack("<h", 0x7FFF)

    # Barometer u16 fields at 0..10 — 0 means "no reading" per §X.
    for off in (0, 2, 4, 6, 8, 10):
        payload[off:off + 2] = struct.pack("<H", 0)

    # Solar u16 fields at 103, 107, 109 — must exceed INVALID_SOLAR.
    for off in (103, 107, 109):
        payload[off:off + 2] = struct.pack("<H", 0x7FFF)

    for off, blob in overrides.items():
        payload[off:off + len(blob)] = blob
    crc = crc_calculate(bytes(payload))
    return bytes(payload) + struct.pack(">H", crc)


# --------------- command builder ---------------

def test_cmd_hilows_shape():
    """§IX.2 spells the command 'HILOWS' — LF terminated, no arguments."""
    assert cmd_hilows() == b"HILOWS\n"


# --------------- length + CRC ---------------

class TestBlockValidation:
    def test_short_block_returns_none(self):
        assert parse_hilows(b"\x00" * 100) is None

    def test_bad_crc_returns_none(self):
        payload = b"\xFF" * HILOWS_BLOCK_SIZE
        # Deliberately wrong CRC — should be crc_calculate(payload)
        bad = payload + b"\x00\x00"
        assert parse_hilows(bad) is None

    def test_all_sentinels_produces_all_none(self):
        """A block full of dashed values MUST parse to a struct where every
        scalar field is None.  This is the whole point of the parser: an
        unpopulated console must not produce numeric-looking noise."""
        block = _pack({})   # every byte 0xFF, valid CRC
        hl = parse_hilows(block)
        assert hl is not None

        # Barometer + inside/outside/dew temperatures — every extremum None
        for period in (hl.barometer, hl.inside_temp, hl.outside_temp, hl.dew_point):
            for span in (period.day, period.month, period.year):
                assert span.low is None, f"leaked low: {span.low!r}"
                assert span.high is None, f"leaked high: {span.high!r}"

        # Every extra/soil/leaf slot None
        for arr in (hl.extra_temps, hl.soil_temps, hl.leaf_temps):
            for slot in arr:
                for span in (slot.day, slot.month, slot.year):
                    assert span.low is None and span.high is None

        # Humidities, moistures, wetnesses
        for arr in (hl.humidities, hl.soil_moistures, hl.leaf_wetnesses):
            for slot in arr:
                for span in (slot.day, slot.month, slot.year):
                    assert span.low is None and span.high is None

        # Hi-only + Lo-only structures
        for period in (hl.wind_speed, hl.heat_index, hl.thsw_index,
                       hl.solar_radiation, hl.uv_index, hl.rain_rate):
            for span in (period.day, period.month, period.year):
                assert span.value is None
        for span in (hl.wind_chill.day, hl.wind_chill.month, hl.wind_chill.year):
            assert span.value is None

        assert hl.rain_rate_hour_hi is None


# --------------- unit conversions ---------------

class TestScalarConversions:
    def test_barometer_low_high_pair_converts_to_hpa(self):
        # Day low bar = 29.500 inHg (= 998.98 hPa), high = 30.100 (= 1019.30)
        block = _pack({
            0: _u16(29500),   # day low
            2: _u16(30100),   # day high
        })
        hl = parse_hilows(block)
        assert hl.barometer.day.low == pytest.approx(999.0, abs=0.2)
        assert hl.barometer.day.high == pytest.approx(1019.3, abs=0.2)
        # Untouched positions still None
        assert hl.barometer.month.low is None

    def test_outside_temp_low_high_preserves_order_from_the_manual(self):
        # Manual documents outside temp as LOW then HIGH — reversed from
        # inside temp — and getting this wrong silently swaps the reading.
        # Day low = 40.0 °F (= 4.4 °C), high = 90.0 °F (= 32.2 °C)
        block = _pack({
            47: _s16(400),    # low, tenths F
            49: _s16(900),    # high, tenths F
        })
        hl = parse_hilows(block)
        assert hl.outside_temp.day.low == pytest.approx(4.4, abs=0.2)
        assert hl.outside_temp.day.high == pytest.approx(32.2, abs=0.2)
        assert hl.outside_temp.day.high > hl.outside_temp.day.low

    def test_inside_humidity_day_high_and_low(self):
        block = _pack({
            37: bytes([65]),   # day hi = 65 %
            38: bytes([30]),   # day lo = 30 %
        })
        hl = parse_hilows(block)
        assert hl.inside_humidity.day.high == 65
        assert hl.inside_humidity.day.low == 30

    def test_wind_speed_high_only(self):
        # 25 mph = 11.2 m/s
        block = _pack({16: bytes([25])})
        hl = parse_hilows(block)
        assert hl.wind_speed.day.value == pytest.approx(11.2, abs=0.1)

    def test_wind_chill_low_only(self):
        # -10 °F = -23.3 °C
        block = _pack({79: _s16(-10)})
        hl = parse_hilows(block)
        assert hl.wind_chill.day.value == pytest.approx(-23.3, abs=0.2)

    def test_heat_index_high_only(self):
        # 110 °F = 43.3 °C
        block = _pack({87: _s16(110)})
        hl = parse_hilows(block)
        assert hl.heat_index.day.value == pytest.approx(43.3, abs=0.2)

    def test_uv_high_uses_tenths(self):
        block = _pack({111: bytes([85])})   # 8.5 UV index
        hl = parse_hilows(block)
        assert hl.uv_index.day.value == pytest.approx(8.5, abs=0.05)

    def test_solar_radiation(self):
        block = _pack({103: _u16(432)})     # 432 W/m²
        hl = parse_hilows(block)
        assert hl.solar_radiation.day.value == 432

    def test_rain_rate_day_hi_uses_click_size(self):
        # 100 clicks/hr × 0.01 in × 25.4 = 25.40 mm/hr
        block = _pack({116: _u16(100)})
        hl = parse_hilows(block, rain_click_inches=0.01)
        assert hl.rain_rate.day.value == pytest.approx(25.4, abs=0.05)

    def test_rain_rate_hour_hi_lives_between_day_time_and_month(self):
        # Byte 120-121 is the hourly rain-total high, not a rate — parsing
        # it as if it were the day rate would swap it with month.
        block = _pack({120: _u16(50)})
        hl = parse_hilows(block, rain_click_inches=0.01)
        assert hl.rain_rate_hour_hi == pytest.approx(12.7, abs=0.05)
        assert hl.rain_rate.day.value is None
        assert hl.rain_rate.month.value is None


# --------------- time decoding ---------------

class TestTimeDecoding:
    def test_valid_time_of_day_high_bar(self):
        # 14:37 packed as hour*100 + minute = 1437
        block = _pack({14: _u16(1437)})
        hl = parse_hilows(block)
        assert hl.barometer.day.time_high is not None
        assert hl.barometer.day.time_high.hour == 14
        assert hl.barometer.day.time_high.minute == 37

    def test_invalid_time_becomes_none(self):
        # 25:99 is not a real clock reading; must not surface it
        block = _pack({14: _u16(2599)})
        hl = parse_hilows(block)
        assert hl.barometer.day.time_high is None

    def test_dashed_time_becomes_none(self):
        # 0xFFFF at every time position — no false 65:35s
        block = _pack({})
        hl = parse_hilows(block)
        for period in (hl.barometer, hl.inside_temp, hl.outside_temp,
                       hl.inside_humidity):
            assert period.day.time_low is None
            assert period.day.time_high is None


# --------------- extra sensor sentinel filtering ---------------

class TestExtraSensorSentinelFiltering:
    """Load-bearing: a Vue with only OAT/OHUM installed has six of seven
    extra-temp slots dashed.  If the parser doesn't filter, every empty
    slot shows up as -90 °F on the client, which is the exact class of
    bug that recurs on Davis stations."""

    def test_all_15_temp_slots_none_when_dashed(self):
        block = _pack({})   # every byte 0xFF
        hl = parse_hilows(block)
        for slot in hl.extra_temps + hl.soil_temps + hl.leaf_temps:
            for span in (slot.day, slot.month, slot.year):
                assert span.high is None
                assert span.low is None

    def test_a_populated_extra_temp_reads_back_correctly(self):
        # Byte 141 is day-hi of extra slot 0 (== "Extra Temperature 2").
        # Offset encoding: raw = F + 90, so raw=170 means 80 °F = 26.7 °C.
        block = _pack({141: bytes([170])})
        hl = parse_hilows(block)
        assert hl.extra_temps[0].day.high == pytest.approx(26.7, abs=0.2)
        # No spillover into the other 14 slots
        others = (hl.extra_temps[1:] + hl.soil_temps + hl.leaf_temps)
        for slot in others:
            assert slot.day.high is None

    def test_all_8_humidity_slots_none_when_dashed(self):
        block = _pack({})
        hl = parse_hilows(block)
        for slot in hl.humidities:
            for span in (slot.day, slot.month, slot.year):
                assert span.high is None
                assert span.low is None

    def test_populated_outside_humidity_reads_back_correctly(self):
        # Index 0 == outside humidity.  Byte 284 is day-hi.
        block = _pack({284: bytes([73])})
        hl = parse_hilows(block)
        assert hl.humidities[0].day.high == 73
        for slot in hl.humidities[1:]:
            assert slot.day.high is None

    def test_leaf_wetness_range_check(self):
        # Valid range is 0-15; 0xFF must not come through as "15".
        block = _pack({396: bytes([200])})    # out of range
        hl = parse_hilows(block)
        assert hl.leaf_wetnesses[0].day.high is None

    def test_leaf_wetness_valid_low(self):
        block = _pack({396: bytes([12])})
        hl = parse_hilows(block)
        assert hl.leaf_wetnesses[0].day.high == 12


# --------------- return type sanity ---------------

def test_parse_returns_the_documented_dataclass():
    block = _pack({})
    hl = parse_hilows(block)
    assert isinstance(hl, VantageHighsLows)
    assert len(hl.extra_temps) == 7
    assert len(hl.soil_temps) == 4
    assert len(hl.leaf_temps) == 4
    assert len(hl.humidities) == 8
    assert len(hl.soil_moistures) == 4
    assert len(hl.leaf_wetnesses) == 4
