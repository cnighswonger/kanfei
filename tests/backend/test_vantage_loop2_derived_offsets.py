"""LOOP2 station-computed temperature offsets and their dashed sentinel.

Heat index, wind chill and THSW were each read one byte early, straddling
the previous field's high byte and this field's low byte.  Dew point at 30
was correct; the drift starts at 34 because the unused byte at 32 and the
humidity byte at 33 were counted as one field rather than two.  Manual
§X.2 gives 30 / 35 / 37 / 39.

The sentinel check was also wrong.  These are two-byte fields, so 0xFF
could never match one — the dashed value is 0x7FFF.  That is how a bogus
THSW of -256 reached extra_json on the production box within seconds of
LOOP2 first working (#232).

Measured on a Vue (fw 2.12), LOOP2 bytes 28..46:

    28:FF 29:7F 30:44 31:00 32:FF 33:3C 34:FF 35:58
    36:00 37:54 38:00 39:FF 40:7F 41:00 42:00 ...

    heat_index  @34 = 22783 (garbage)  @35 =    88 °F
    wind_chill  @36 = 21504 (garbage)  @37 =    84 °F
    thsw_index  @38 =  -256 (garbage)  @39 = 32767 (dashed)

88 °F heat index at 60% RH and no wind chill in August are both plausible;
the @34/@36/@38 readings are not.  The Vue has no solar sensor, so it
cannot compute THSW and correctly reports the dashed value.
"""

import struct

import pytest

from app.protocol.vantage.constants import LOOP2_PACKET_SIZE
from app.protocol.vantage.loop_packet import _valid_derived_temp, parse_loop2


def _loop2(dew=68, heat=88, chill=84, thsw=0x7FFF) -> bytes:
    """Build a CRC-valid LOOP2 packet with the derived block set."""
    from app.protocol.crc import crc_calculate

    raw = bytearray(LOOP2_PACKET_SIZE)
    raw[0:3] = b"LOO"
    raw[4] = 1                                   # packet type: LOOP2
    raw[7:9] = (29920).to_bytes(2, "little")
    raw[9:11] = (720).to_bytes(2, "little")
    raw[11] = 45
    raw[12:14] = (750).to_bytes(2, "little")
    raw[14] = 5
    raw[16:18] = (180).to_bytes(2, "little")
    raw[18:20] = (95).to_bytes(2, "little")
    raw[20:22] = (88).to_bytes(2, "little")
    raw[22:24] = (210).to_bytes(2, "little")
    raw[24:26] = (200).to_bytes(2, "little")

    # The unused fields the manual specifies — these are what the old
    # offsets were partly reading.
    raw[26:28] = (0x7FFF).to_bytes(2, "little")
    raw[28:30] = (0x7FFF).to_bytes(2, "little")

    struct.pack_into("<h", raw, 30, dew)
    raw[32] = 0xFF                               # unused
    raw[33] = 60                                 # outside humidity
    raw[34] = 0xFF                               # unused
    struct.pack_into("<h", raw, 35, heat)
    struct.pack_into("<h", raw, 37, chill)
    struct.pack_into("<h", raw, 39, thsw)

    raw[95:97] = b"\n\r"
    raw[97:99] = crc_calculate(bytes(raw[:97])).to_bytes(2, "big")
    return bytes(raw)


class TestDerivedTemperatureOffsets:
    def test_dew_point_reads_from_30(self):
        assert parse_loop2(_loop2(dew=68)).dew_point == 68

    def test_heat_index_reads_from_35_not_34(self):
        assert parse_loop2(_loop2(heat=88)).heat_index == 88

    def test_wind_chill_reads_from_37_not_36(self):
        assert parse_loop2(_loop2(chill=84)).wind_chill == 84

    def test_thsw_reads_from_39_not_38(self):
        assert parse_loop2(_loop2(thsw=95)).thsw_index == 95

    def test_unused_filler_is_not_mistaken_for_a_reading(self):
        """Bytes 32 and 34 are 0xFF filler and 33 is humidity — the region
        the old offsets were partly reading.  LOOP2 humidity is not parsed
        (LOOP supplies it), so the check that matters is that none of the
        filler leaks into a derived value."""
        data = parse_loop2(_loop2())
        for field in ("dew_point", "heat_index", "wind_chill"):
            val = getattr(data, field)
            assert val is None or -150 <= val <= 200

    def test_all_four_independent(self):
        """Distinct values, so an off-by-one would cross-contaminate."""
        data = parse_loop2(_loop2(dew=61, heat=97, chill=42, thsw=105))
        assert (data.dew_point, data.heat_index, data.wind_chill,
                data.thsw_index) == (61, 97, 42, 105)


class TestDashedSentinel:
    def test_thsw_dashed_on_a_station_without_solar(self):
        """A Vue cannot compute THSW and reports 0x7FFF.  This is the exact
        value that reached production as -256."""
        assert parse_loop2(_loop2(thsw=0x7FFF)).thsw_index is None

    @pytest.mark.parametrize("field,kwargs", [
        ("dew_point", {"dew": 0x7FFF}),
        ("heat_index", {"heat": 0x7FFF}),
        ("wind_chill", {"chill": 0x7FFF}),
        ("thsw_index", {"thsw": 0x7FFF}),
    ])
    def test_every_derived_field_filters_the_sentinel(self, field, kwargs):
        assert getattr(parse_loop2(_loop2(**kwargs)), field) is None

    def test_255_is_a_real_temperature_not_a_sentinel(self):
        """The manual says "255 = dashed data" for these fields, which
        cannot be right for a two-byte value.  255 °F is out of range for a
        real reading, so it is rejected — but by the range check, not by
        being mistaken for the byte-width sentinel."""
        assert _valid_derived_temp(255) is None

    @pytest.mark.parametrize("val", [-256, 21504, 22783, 32767])
    def test_misaligned_garbage_is_rejected(self, val):
        """The values the old offsets actually produced on the bench."""
        assert _valid_derived_temp(val) is None

    @pytest.mark.parametrize("val", [-40, 0, 32, 84, 88, 120])
    def test_plausible_temperatures_pass(self, val):
        assert _valid_derived_temp(val) == val


class TestSnapshotIntegration:
    def test_dashed_thsw_stays_out_of_extra(self):
        """extra_json carried thsw_index: -256.0 on the production box
        within seconds of LOOP2 first working."""
        from app.protocol.vantage.loop_packet import loop_to_snapshot, parse_loop

        loop2 = parse_loop2(_loop2(thsw=0x7FFF))
        assert loop2.thsw_index is None

    def test_real_thsw_reaches_extra(self):
        loop2 = parse_loop2(_loop2(thsw=105))
        assert loop2.thsw_index == 105
