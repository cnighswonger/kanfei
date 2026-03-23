"""Tests for METAR string formatting."""

from datetime import datetime, timezone

from app.output.metar import (
    _format_wind,
    _f_to_c,
    _format_temp_c,
    _mph_to_knots,
    _format_altimeter,
    format_metar,
)


class TestFormatWind:

    def test_calm_wind(self):
        assert _format_wind(270, 0) == "00000KT"

    def test_normal_wind(self):
        assert _format_wind(270, 10) == "27010KT"

    def test_variable_wind_no_direction(self):
        assert _format_wind(None, 5) == "VRB05KT"

    def test_north_wind(self):
        assert _format_wind(0, 15) == "00015KT"

    def test_light_wind(self):
        assert _format_wind(180, 3) == "18003KT"


class TestFtoC:

    def test_freezing(self):
        assert _f_to_c(320) == 0  # 32.0°F = 0°C

    def test_boiling(self):
        assert _f_to_c(2120) == 100  # 212.0°F = 100°C

    def test_negative(self):
        # -4.0°F = (-4 - 32) * 5/9 = -20°C
        assert _f_to_c(-40) == -20

    def test_room_temp(self):
        # 72.0°F = (72-32)*5/9 = 22.2°C → rounds to 22
        assert _f_to_c(720) == 22


class TestFormatTempC:

    def test_positive(self):
        assert _format_temp_c(22) == "22"

    def test_negative(self):
        assert _format_temp_c(-5) == "M05"

    def test_zero(self):
        assert _format_temp_c(0) == "00"

    def test_large_negative(self):
        assert _format_temp_c(-20) == "M20"


class TestMphToKnots:

    def test_ten_mph(self):
        assert _mph_to_knots(10) == 9  # 10 * 0.868976 ≈ 8.69 → 9

    def test_zero(self):
        assert _mph_to_knots(0) == 0

    def test_hundred_mph(self):
        assert _mph_to_knots(100) == 87  # 100 * 0.868976 ≈ 86.9 → 87


class TestFormatAltimeter:

    def test_standard_pressure(self):
        assert _format_altimeter(29920) == "A2992"

    def test_low_pressure(self):
        assert _format_altimeter(28500) == "A2850"

    def test_high_pressure(self):
        assert _format_altimeter(30500) == "A3050"


class TestFormatMetar:

    def test_complete_metar(self):
        obs = datetime(2026, 3, 15, 17, 53, 0, tzinfo=timezone.utc)
        result = format_metar(
            station_id="KWXS",
            wind_dir_deg=270,
            wind_speed_mph=12,
            temp_tenths_f=720,
            dew_point_tenths_f=590,
            barometer_thousandths=29921,
            obs_time=obs,
        )
        assert result.startswith("METAR KWXS 151753Z")
        assert "10SM" in result
        assert "CLR" in result
        assert "A2992" in result

    def test_station_id_padded(self):
        obs = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = format_metar("AB", 0, 0, 700, 500, 29920, obs)
        assert "METAR ABXX" in result

    def test_station_id_truncated(self):
        obs = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = format_metar("TOOLONG", 0, 0, 700, 500, 29920, obs)
        assert "METAR TOOL" in result
