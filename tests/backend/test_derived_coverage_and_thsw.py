"""Derived-value coverage, and the station-computed THSW index.

Two separate problems, both about a value being absent when it should not
be.

**Coverage.** ``heat_index()`` returned None across a large part of the
hot, humid quadrant — 94 °F/80%, 96 °F/70%, 98 °F/60%, 100 °F/50% and
everything beyond — which is exactly the weather where heat index is the
number someone wants. The cause was a guard testing the interpolated
*result* against 125. Davis pads the unreachable upper-right corner of
its table with 150 "to facilitate interpolation only"
(reference/thitable.h), and real entries reach 144, so a result of 128
from a genuine table cell was thrown away along with the padding.

It also returned None below 68 °F, blanking the dashboard tile for most
of the year. Below the table there is no humidity-driven warming to add,
so apparent temperature is air temperature — that is a value, not
missing data.

**THSW.** The one derived quantity we cannot compute: it needs solar
radiation, so only a station with a solar sensor reports one. It was
parsed but landed in ``extra_json`` as raw °F while every other snapshot
field was SI. Now a first-class column in tenths °C, gated on the value
arriving rather than on the station model — fit a solar sensor and it
starts working with no code change.
"""

import pytest

from app.protocol.base import SensorSnapshot
from app.services.calculations import (
    THI_MAX_TEMP,
    THI_PAD_VALUE,
    THI_TABLE,
    heat_index,
)


def _c(temp_f: float) -> int:
    """°F → tenths °C, matching the storage unit."""
    return round((temp_f - 32) * 5 / 9 * 10)


def _f(tenths_c) -> float | None:
    """tenths °C → °F, for readable assertions."""
    if tenths_c is None:
        return None
    return tenths_c / 10.0 * 9 / 5 + 32


class TestHotHumidCoverage:
    """The quadrant that used to go blank."""

    @pytest.mark.parametrize("temp_f,humidity", [
        (90, 90),
        (92, 90),
        (94, 80),
        (96, 70),
        (98, 60),
        (100, 60),
        (102, 50),
        (104, 50),
        (106, 40),
        (110, 40),
    ])
    def test_hot_humid_conditions_return_a_value(self, temp_f, humidity):
        assert heat_index(_c(temp_f), humidity) is not None

    def test_the_exact_case_that_exposed_it(self):
        """96 °F / 70% RH lands on the cell holding 128 — a real Davis
        value — with the 150 beside it carrying zero interpolation weight.
        The old guard rejected it anyway."""
        result = heat_index(_c(96), 70)
        assert result is not None
        assert 125 < _f(result) < 132

    def test_heat_index_at_or_above_air_temperature_when_humid(self):
        """Sanity: humidity makes it feel hotter, never cooler."""
        for temp_f in (85, 90, 95, 100):
            hi = heat_index(_c(temp_f), 70)
            if hi is not None:
                assert _f(hi) >= temp_f - 1     # allow table rounding

    def test_rises_with_humidity(self):
        vals = [heat_index(_c(95), h) for h in (30, 50, 70)]
        vals = [v for v in vals if v is not None]
        assert vals == sorted(vals)


class TestPaddingStillRejected:
    """Recovering real values must not start returning the 150 filler."""

    def test_padding_constant_matches_the_table(self):
        real = [v for row in THI_TABLE for v in row if v < THI_PAD_VALUE]
        assert max(real) == 144, "real entries top out below the pad value"

    @pytest.mark.parametrize("temp_f,humidity", [
        (110, 90),
        (115, 80),
        (120, 100),
        (122, 90),
    ])
    def test_unreachable_corner_returns_none(self, temp_f, humidity):
        """Deep in the padded region there is no real data to interpolate."""
        assert heat_index(_c(temp_f), humidity) is None

    def test_never_returns_the_pad_value_itself(self):
        for temp_f in range(68, THI_MAX_TEMP + 1):
            for hum in range(0, 101, 5):
                val = heat_index(_c(temp_f), hum)
                if val is not None:
                    assert _f(val) < THI_PAD_VALUE


class TestBelowTableReturnsAirTemperature:
    @pytest.mark.parametrize("temp_f", [20, 40, 50, 60, 67])
    def test_cool_weather_returns_air_temperature(self, temp_f):
        """Not None — an empty tile reads as a fault, and the console keeps
        displaying a value."""
        temp_c = _c(temp_f)
        assert heat_index(temp_c, 50) == temp_c

    def test_boundary_still_uses_the_table(self):
        """68 °F is the first table row, so it interpolates rather than
        falling through to the passthrough."""
        assert heat_index(_c(68), 50) is not None

    def test_above_the_table_is_still_none(self):
        """Past 122 °F there is genuinely nothing to interpolate from."""
        assert heat_index(_c(130), 50) is None

    def test_invalid_humidity_still_rejected(self):
        assert heat_index(_c(80), 150) is None
        assert heat_index(_c(80), -1) is None


class TestThswIsCarriedOnTheSnapshot:
    def test_snapshot_has_the_field(self):
        assert SensorSnapshot().thsw_index is None

    def test_snapshot_accepts_a_value(self):
        assert SensorSnapshot(thsw_index=31.5).thsw_index == 31.5


class TestThswFromLoop2:
    """Parsed from LOOP2 and converted to °C, gated on the value arriving
    rather than on the station model."""

    def _snapshot(self, thsw_f):
        import struct

        from app.protocol.crc import crc_calculate
        from app.protocol.vantage.constants import (
            LOOP2_PACKET_SIZE,
            LOOP_PACKET_SIZE,
        )
        from app.protocol.vantage.loop_packet import (
            loop_to_snapshot,
            parse_loop,
            parse_loop2,
        )

        def _pkt(size, is_loop2):
            raw = bytearray(size)
            raw[0:3] = b"LOO"
            raw[4] = 1 if is_loop2 else 0
            raw[7:9] = (29920).to_bytes(2, "little")
            raw[9:11] = (720).to_bytes(2, "little")
            raw[11] = 45
            raw[12:14] = (750).to_bytes(2, "little")
            raw[14] = 5
            raw[16:18] = (180).to_bytes(2, "little")
            raw[33] = 55
            if is_loop2:
                struct.pack_into("<h", raw, 39, thsw_f)
            raw[95:97] = b"\n\r"
            raw[97:99] = crc_calculate(bytes(raw[:97])).to_bytes(2, "big")
            return bytes(raw)

        loop = parse_loop(_pkt(LOOP_PACKET_SIZE, False))
        loop2 = parse_loop2(_pkt(LOOP2_PACKET_SIZE, True))
        return loop_to_snapshot(loop, loop2, 0.01)

    def test_real_value_converted_to_celsius(self):
        """90 °F ≈ 32.2 °C.  It used to reach extra as raw °F, which would
        have put 90 on a °C dashboard."""
        snapshot = self._snapshot(90)
        assert snapshot.thsw_index == pytest.approx(32.2, abs=0.1)

    def test_dashed_station_reports_nothing(self):
        """A station with no solar sensor sends 0x7FFF.  The Vue on the
        bench does exactly this."""
        assert self._snapshot(0x7FFF).thsw_index is None

    def test_extra_key_is_unit_suffixed(self):
        """extra carries °C now, so the key says so — a bare thsw_index in
        °F is what the old code stored."""
        snapshot = self._snapshot(90)
        assert "thsw_index" not in snapshot.extra
        assert snapshot.extra["thsw_index_c"] == pytest.approx(32.2, abs=0.1)


class TestThswMetadata:
    def test_registered_as_a_temperature(self):
        from app.models.sensor_meta import SENSOR_UNITS, convert

        assert SENSOR_UNITS["thsw_index"] == "F"
        assert convert("thsw_index", 322) == pytest.approx(90.0, abs=0.5)

    def test_has_bounds(self):
        """It reaches the published payload, so it needs the same guard the
        other published values got in #234."""
        from app.models.sensor_meta import SENSOR_BOUNDS

        assert "thsw_index" in SENSOR_BOUNDS

    def test_is_queryable_as_a_column(self):
        from app.models.sensor_meta import SENSOR_COLUMNS

        assert "thsw_index" in SENSOR_COLUMNS
