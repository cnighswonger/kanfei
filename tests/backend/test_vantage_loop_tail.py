"""Tests for the tail of the LOOP packet — battery, forecast, sun times.

These offsets were wrong for a long time and nothing caught it. The parser
read forecast/sunrise/sunset at 82/83/84/86, which lands inside the alarm
block; the manual (§X.1) puts them at 89/90/91/93 and calls byte 86 the
transmitter battery status.

It went unnoticed because on a station with no alarms active that region
is all zeroes, so sunrise decoded to a plausible-looking 0 and flowed
straight to the UI as "00:00". The lesson driving these tests: a field
that silently accepts an implausible value will hide a wrong offset
indefinitely. So the sun-time tests here assert on *decoded clock
plausibility*, not just on "some number came back".

Ground truth is a real LOOP packet captured from a Vantage Vue (fw 2.12)
on 2026-08-01, cross-checked three ways: sunrise/sunset match the almanac
for 35.38N 78.60W, byte 87 yields 4.74 V for the console cell, and byte 86
reads 0x01 while that console displayed an ISS low-battery warning.
"""

import struct

import pytest

from app.protocol.crc import crc_calculate
from app.protocol.vantage.loop_packet import parse_loop, loop_to_snapshot


def _build_loop(**overrides) -> bytes:
    """Build a minimal but valid 99-byte LOOP packet.

    Defaults put realistic values in the tail fields under test and leave
    the alarm block (74..85) zeroed — which is exactly the condition that
    let the old wrong offsets look plausible.
    """
    p = bytearray(99)
    p[0:3] = b"LOO"
    p[3] = 0            # bar trend steady
    p[4] = 0            # packet type LOOP
    struct.pack_into("<H", p, 7, 29920)     # barometer
    struct.pack_into("<h", p, 9, 750)       # inside temp
    p[11] = 50                              # inside humidity
    struct.pack_into("<h", p, 12, 983)      # outside temp 98.3 F
    p[14] = 3                               # wind speed
    p[15] = 2                               # 10-min avg
    struct.pack_into("<H", p, 16, 217)      # wind direction
    p[33] = 56                              # outside humidity

    # unpopulated sensor slots
    for i in range(18, 33):
        p[i] = 0xFF
    for i in range(34, 41):
        p[i] = 0xFF

    struct.pack_into("<H", p, 41, 0)        # rain rate
    p[43] = 0xFF                            # UV dashed
    struct.pack_into("<H", p, 44, 0x7FFF)   # solar dashed

    # --- the tail under test ---
    p[86] = overrides.get("tx_battery", 0x01)
    struct.pack_into("<H", p, 87, overrides.get("console_raw", 809))
    p[89] = overrides.get("forecast_icons", 3)
    p[90] = overrides.get("forecast_rule", 188)
    struct.pack_into("<H", p, 91, overrides.get("sunrise", 515))    # 05:15
    struct.pack_into("<H", p, 93, overrides.get("sunset", 1921))    # 19:21

    p[95] = 0x0A
    p[96] = 0x0D
    struct.pack_into(">H", p, 97, crc_calculate(bytes(p[:97])))
    return bytes(p)


class TestSunTimes:
    """The regression that started this: wrong offsets produced 0 and
    10497, and nothing rejected either."""

    def test_sunrise_and_sunset_decode_from_the_documented_offsets(self):
        loop = parse_loop(_build_loop())
        assert loop.sunrise == 515
        assert loop.sunset == 1921

    def test_sun_times_are_plausible_clock_values(self):
        """Decoded as hour*100+min they must be real times of day. This is
        the assertion the old code could not have passed."""
        loop = parse_loop(_build_loop())
        for val in (loop.sunrise, loop.sunset):
            hour, minute = divmod(val, 100)
            assert 0 <= hour <= 23, f"{val} -> hour {hour}"
            assert 0 <= minute <= 59, f"{val} -> minute {minute}"

    def test_sunrise_precedes_sunset(self):
        loop = parse_loop(_build_loop())
        assert loop.sunrise < loop.sunset

    def test_zero_is_rejected_rather_than_passed_through_as_midnight(self):
        """A zeroed alarm block read as sunrise gives 0. Treating that as
        a valid 00:00 is precisely how the bug hid."""
        loop = parse_loop(_build_loop(sunrise=0))
        assert loop.sunrise is None

    def test_implausible_value_rejected(self):
        """10497 was the old sunset reading. Not a clock value."""
        loop = parse_loop(_build_loop(sunset=10497))
        assert loop.sunset is None

    @pytest.mark.parametrize("sentinel", [0xFFFF, 0x7FFF])
    def test_dashed_sentinels_rejected(self, sentinel):
        loop = parse_loop(_build_loop(sunrise=sentinel))
        assert loop.sunrise is None


class TestBatteryStatus:
    def test_transmitter_battery_bitmask_read_from_byte_86(self):
        loop = parse_loop(_build_loop(tx_battery=0x01))
        assert loop.transmitter_battery_status == 0x01

    def test_all_transmitters_ok(self):
        loop = parse_loop(_build_loop(tx_battery=0x00))
        assert loop.transmitter_battery_status == 0x00

    def test_console_voltage_conversion(self):
        """((raw * 300) / 512) / 100.0 — 809 is the value observed on a
        healthy Vue console."""
        loop = parse_loop(_build_loop(console_raw=809))
        assert loop.console_battery_voltage == pytest.approx(4.74, abs=0.01)

    def test_console_voltage_zero_is_none_not_zero_volts(self):
        loop = parse_loop(_build_loop(console_raw=0))
        assert loop.console_battery_voltage is None

    def test_snapshot_decodes_low_transmitters_to_ids(self):
        """A consumer should not have to re-derive bit positions."""
        loop = parse_loop(_build_loop(tx_battery=0x01))
        snap = loop_to_snapshot(loop, None, 0.01)
        assert snap.extra["transmitters_low_battery"] == [1]
        assert snap.extra["transmitter_battery_status"] == 0x01

    def test_snapshot_reports_multiple_low_transmitters(self):
        # bits 0 and 2 -> transmitters 1 and 3
        loop = parse_loop(_build_loop(tx_battery=0b00000101))
        snap = loop_to_snapshot(loop, None, 0.01)
        assert snap.extra["transmitters_low_battery"] == [1, 3]

    def test_snapshot_empty_list_when_all_ok(self):
        loop = parse_loop(_build_loop(tx_battery=0x00))
        snap = loop_to_snapshot(loop, None, 0.01)
        assert snap.extra["transmitters_low_battery"] == []

    def test_snapshot_carries_console_voltage(self):
        loop = parse_loop(_build_loop(console_raw=809))
        snap = loop_to_snapshot(loop, None, 0.01)
        assert snap.extra["console_battery_voltage"] == pytest.approx(4.74, abs=0.01)


class TestForecastFields:
    def test_forecast_icons_and_rule_from_documented_offsets(self):
        loop = parse_loop(_build_loop(forecast_icons=3, forecast_rule=188))
        assert loop.forecast_icons == 3
        assert loop.forecast_rule == 188

    def test_forecast_not_read_from_the_alarm_block(self):
        """Bytes 82-85 are soil/leaf alarms. Writing there must not move
        the forecast fields — the old parser read 82/83 for exactly this."""
        pkt = bytearray(_build_loop(forecast_icons=3, forecast_rule=188))
        pkt[82] = 0xAA
        pkt[83] = 0xBB
        struct.pack_into(">H", pkt, 97, crc_calculate(bytes(pkt[:97])))
        loop = parse_loop(bytes(pkt))
        assert loop.forecast_icons == 3
        assert loop.forecast_rule == 188


class TestAlarmBlockIsolation:
    """The whole failure mode in one test: a zeroed alarm block must not
    be able to masquerade as valid tail data."""

    def test_zeroed_alarm_block_does_not_produce_fake_sun_times(self):
        pkt = bytearray(_build_loop())
        for i in range(74, 86):
            pkt[i] = 0x00
        struct.pack_into(">H", pkt, 97, crc_calculate(bytes(pkt[:97])))
        loop = parse_loop(bytes(pkt))
        # Real values still come from 91/93, untouched by the alarm zeros.
        assert loop.sunrise == 515
        assert loop.sunset == 1921
