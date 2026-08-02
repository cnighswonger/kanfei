"""Tests for wind-speed sentinel handling in LOOP packets.

A transmitter dropout on the bench Vue logged 255 mph (114 m/s) as a real
wind reading, on every poll, for 27 minutes. 107 identical rows.

255 is the dashed sentinel for the single-byte wind fields, and it was the
only outdoor field not being filtered. Wind DIRECTION had
_valid_wind_dir(); temperature and humidity had their own guards; the
LOOP2 wind fields checked 0x7FFF. Just the two LOOP wind-speed bytes went
through raw — which is why a dropout produced a snapshot with every other
outdoor field None and one plausible-looking number.

That shape is the thing worth testing against: a stuck sentinel does not
look like noise, it looks like a sustained gale, and it is *self
consistent* across polls. So the tests below assert not just that 255
becomes None, but that a dropout packet yields no outdoor readings at all
— because "everything None except wind" is the signature that let this
sit unnoticed.
"""

import struct

import pytest

from app.protocol.crc import crc_calculate
from app.protocol.vantage.loop_packet import parse_loop, loop_to_snapshot


def _build_loop(wind=5, wind_10min=4, outside_temp=983, outside_hum=56,
                wind_dir=217) -> bytes:
    """A valid 99-byte LOOP packet with controllable outdoor fields."""
    p = bytearray(99)
    p[0:3] = b"LOO"
    p[3] = 0
    p[4] = 0
    struct.pack_into("<H", p, 7, 29920)
    struct.pack_into("<h", p, 9, 750)
    p[11] = 50
    struct.pack_into("<h", p, 12, outside_temp)
    p[14] = wind
    p[15] = wind_10min
    struct.pack_into("<H", p, 16, wind_dir)
    p[33] = outside_hum
    for i in range(18, 33):
        p[i] = 0xFF
    for i in range(34, 41):
        p[i] = 0xFF
    struct.pack_into("<H", p, 41, 0)
    p[43] = 0xFF
    struct.pack_into("<H", p, 44, 0x7FFF)
    p[86] = 0x00
    struct.pack_into("<H", p, 87, 809)
    struct.pack_into("<H", p, 91, 515)
    struct.pack_into("<H", p, 93, 1921)
    p[95] = 0x0A
    p[96] = 0x0D
    struct.pack_into(">H", p, 97, crc_calculate(bytes(p[:97])))
    return bytes(p)


class TestWindSentinel:
    def test_255_is_not_a_wind_speed(self):
        """The actual bug: 255 logged as 114 m/s = 255 mph."""
        loop = parse_loop(_build_loop(wind=0xFF))
        assert loop.wind_speed is None

    def test_255_rejected_for_10min_average_too(self):
        loop = parse_loop(_build_loop(wind_10min=0xFF))
        assert loop.wind_speed_10min is None

    def test_real_speeds_pass_through(self):
        loop = parse_loop(_build_loop(wind=12, wind_10min=8))
        assert loop.wind_speed == 12
        assert loop.wind_speed_10min == 8

    def test_zero_is_a_real_reading_not_missing(self):
        """Calm is data. The manual notes speed is forced to 0 on loss of
        sync, so 0 must stay distinguishable from the 255 sentinel."""
        loop = parse_loop(_build_loop(wind=0))
        assert loop.wind_speed == 0
        assert loop.wind_speed is not None

    @pytest.mark.parametrize("speed", [1, 50, 100, 200, 254])
    def test_high_but_valid_speeds_survive(self, speed):
        """Only 255 is the sentinel. 254 mph is absurd meteorologically but
        it is not the dashed value, so the parser must not invent a
        plausibility limit the protocol does not define."""
        loop = parse_loop(_build_loop(wind=speed))
        assert loop.wind_speed == speed


class TestDropoutSignature:
    """The shape that let this hide: every other outdoor field None, and
    one number that looks like weather."""

    def test_dropout_packet_yields_no_outdoor_readings(self):
        loop = parse_loop(_build_loop(
            wind=0xFF, wind_10min=0xFF,
            outside_temp=0x7FFF, outside_hum=0xFF, wind_dir=0x7FFF,
        ))
        assert loop.wind_speed is None
        assert loop.wind_speed_10min is None
        assert loop.outside_temp is None
        assert loop.outside_humidity is None
        assert loop.wind_direction is None

    def test_snapshot_from_a_dropout_has_no_wind(self):
        loop = parse_loop(_build_loop(
            wind=0xFF, wind_10min=0xFF,
            outside_temp=0x7FFF, outside_hum=0xFF, wind_dir=0x7FFF,
        ))
        snap = loop_to_snapshot(loop, None, 0.01)
        assert snap.wind_speed is None, (
            "a transmitter dropout must not surface as a wind reading"
        )

    def test_indoor_readings_survive_a_dropout(self):
        """The console's own sensors keep working when the link drops —
        that asymmetry is what makes the bug subtle rather than obvious."""
        loop = parse_loop(_build_loop(
            wind=0xFF, outside_temp=0x7FFF, outside_hum=0xFF,
        ))
        assert loop.inside_temp is not None
        assert loop.inside_humidity is not None
        assert loop.barometer is not None


class TestConsistencyWithNeighbouringFields:
    """Every other outdoor field already filtered its sentinel. This pins
    wind speed to the same standard so the set stays uniform."""

    def test_all_outdoor_fields_filter_their_sentinels(self):
        loop = parse_loop(_build_loop(
            wind=0xFF, wind_10min=0xFF,
            outside_temp=0x7FFF, outside_hum=0xFF, wind_dir=0x7FFF,
        ))
        for field in ("wind_speed", "wind_speed_10min", "outside_temp",
                      "outside_humidity", "wind_direction"):
            assert getattr(loop, field) is None, f"{field} leaked a sentinel"
