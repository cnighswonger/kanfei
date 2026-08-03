"""LOOP2 barometer block offsets (§X.2 bytes 60-70).

The whole block was read two bytes early, so every value straddled the
boundary between neighbouring fields.  Measured on a Vue (fw 2.12):

    absolute   read @62 -> 54.272 inHg    correct @67 -> 29.630 inHg
    altimeter  read @64 -> 36.095 inHg    correct @69 -> 29.915 inHg

Same class of error as #235's derived-temperature offsets, found the same
way: by dumping the raw bytes and checking the manual's own stated
relationships against them.

Two independent confirmations that the manual's map is right:

1. ``raw + user_offset == absolute``.  On the bench Vue: 29580 + 50 =
   29630, exactly the relationship §X.2 describes for those three fields.
2. The calibration number at byte 63 reads **-44** as a signed int16 —
   precisely what BARDATA independently reports as ``OFFSET -44`` over a
   completely different command path.

Neither wrong value was consumed by anything, so no stored data was
affected.  The fields are wired up now because barometer calibration
needs them: the gap between the raw sensor reading and the altimeter
setting is what a calibration tool has to show the user.
"""

import struct

import pytest

from app.protocol.crc import crc_calculate
from app.protocol.vantage.constants import LOOP2_PACKET_SIZE
from app.protocol.vantage.loop_packet import parse_loop2

# The exact bytes 58..71 read off the bench Vue, 2026-08-03.
_MEASURED_TAIL = bytes([
    0x08, 0x00,        # 58-59
    0x01,              # 60  reduction method = 1 (altimeter setting)
    0x32, 0x00,        # 61-62  user offset   = 50      (0.050 inHg)
    0xD4, 0xFF,        # 63-64  calibration   = -44 signed
    0x8C, 0x73,        # 65-66  raw sensor    = 29580   (29.580 inHg)
    0xBE, 0x73,        # 67-68  absolute      = 29630   (29.630 inHg)
    0xDB, 0x74,        # 69-70  altimeter     = 29915   (29.915 inHg)
    0xFF,              # 71  unused
])


def _loop2(tail: bytes = _MEASURED_TAIL) -> bytes:
    """CRC-valid LOOP2 packet carrying the measured barometer block."""
    raw = bytearray(LOOP2_PACKET_SIZE)
    raw[0:3] = b"LOO"
    raw[4] = 1                                   # packet type: LOOP2
    raw[7:9] = (29915).to_bytes(2, "little")     # LOOP sea-level barometer
    raw[9:11] = (720).to_bytes(2, "little")
    raw[11] = 45
    raw[12:14] = (750).to_bytes(2, "little")
    raw[14] = 5
    raw[16:18] = (180).to_bytes(2, "little")
    raw[33] = 60
    raw[58:58 + len(tail)] = tail
    raw[95:97] = b"\n\r"
    raw[97:99] = crc_calculate(bytes(raw[:97])).to_bytes(2, "big")
    return bytes(raw)


@pytest.fixture
def data():
    return parse_loop2(_loop2())


class TestOffsets:
    """Each field at the manual's offset, against the measured packet."""

    def test_reduction_method(self, data):
        """1 = Altimeter Setting.  The manual claims "For VP2, this will
        always be 2" — a Vue reports 1, so that claim does not hold for
        every Vantage.  Worth knowing before trusting the sea-level
        reduction path."""
        assert data.bar_reduction_method == 1

    def test_user_offset(self, data):
        assert data.bar_user_offset == 50

    def test_calibration_is_signed(self, data):
        """Read unsigned this is 65492.  BARDATA reports OFFSET -44 for
        the same console, so signed is the correct interpretation."""
        assert data.bar_calibration == -44

    def test_raw_sensor(self, data):
        assert data.bar_raw_sensor == 29580

    def test_absolute(self, data):
        assert data.abs_barometer == 29630

    def test_altimeter(self, data):
        assert data.altimeter_barometer == 29915

    def test_no_field_reads_the_old_garbage(self, data):
        """The pre-fix offsets produced 54272 and 36095 — both far outside
        any real barometric range.  If either reappears anywhere in the
        block, the offsets have regressed."""
        block = (data.bar_user_offset, data.bar_raw_sensor,
                 data.abs_barometer, data.altimeter_barometer)
        assert 54272 not in block
        assert 36095 not in block


class TestManualStatedRelationships:
    """§X.2 states how these fields relate.  These are the checks that
    caught the wrong offsets in the first place."""

    def test_raw_plus_user_offset_equals_absolute(self, data):
        """The manual defines absolute as "the raw sensor reading plus
        user entered offset".  Under the old offsets this identity failed
        by tens of inches."""
        assert data.bar_raw_sensor + data.bar_user_offset == data.abs_barometer

    def test_every_pressure_is_physically_plausible(self, data):
        """20-32.5 inHg is the range BAR= itself accepts.  A misaligned
        read lands outside it immediately — which is what made the bug
        visible."""
        for value in (data.bar_raw_sensor, data.abs_barometer,
                      data.altimeter_barometer):
            assert 20_000 <= value <= 32_500

    def test_altimeter_matches_the_loop_barometer(self, data):
        """With reduction method 1 the console's displayed barometer IS
        its altimeter setting.  That equality is what makes calibration
        against a METAR altimeter a like-for-like comparison with no
        temperature term."""
        assert data.altimeter_barometer == 29915


class TestSentinels:
    def test_dashed_pressures_are_none(self):
        """0 means no reading for barometer fields."""
        tail = bytearray(_MEASURED_TAIL)
        tail[7:9] = (0).to_bytes(2, "little")     # raw sensor  @65
        tail[9:11] = (0).to_bytes(2, "little")    # absolute    @67
        tail[11:13] = (0).to_bytes(2, "little")   # altimeter   @69
        data = parse_loop2(_loop2(bytes(tail)))
        assert data.bar_raw_sensor is None
        assert data.abs_barometer is None
        assert data.altimeter_barometer is None

    def test_zero_user_offset_is_a_value_not_a_sentinel(self):
        """`BAR=0 <elev>` explicitly CLEARS the offset, so 0 is the normal
        state for an uncalibrated console — it must not become None or the
        tool cannot distinguish "cleared" from "unreadable"."""
        tail = bytearray(_MEASURED_TAIL)
        tail[3:5] = (0).to_bytes(2, "little")     # user offset @61
        data = parse_loop2(_loop2(bytes(tail)))
        assert data.bar_user_offset == 0

    def test_negative_calibration_survives_round_trip(self):
        for value in (-500, -44, 0, 44, 500):
            tail = bytearray(_MEASURED_TAIL)
            struct.pack_into("<h", tail, 5, value)   # calibration @63
            assert parse_loop2(_loop2(bytes(tail))).bar_calibration == value
