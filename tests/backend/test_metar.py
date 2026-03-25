"""Tests for METAR string formatting (SI inputs)."""

from datetime import datetime, timezone

from app.output.metar import (
    _format_wind,
    _si_temp_to_whole_c,
    _format_temp_c,
    _ms_tenths_to_knots,
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


class TestSiTempToWholeC:

    def test_freezing(self):
        assert _si_temp_to_whole_c(0) == 0

    def test_room_temp(self):
        assert _si_temp_to_whole_c(222) == 22

    def test_negative(self):
        assert _si_temp_to_whole_c(-200) == -20

    def test_boiling(self):
        assert _si_temp_to_whole_c(1000) == 100


class TestFormatTempC:

    def test_positive(self):
        assert _format_temp_c(22) == "22"

    def test_negative(self):
        assert _format_temp_c(-5) == "M05"

    def test_zero(self):
        assert _format_temp_c(0) == "00"

    def test_large_negative(self):
        assert _format_temp_c(-20) == "M20"


class TestMsTenthsToKnots:

    def test_moderate_wind(self):
        # 4.5 m/s = 8.7 knots → 9
        assert _ms_tenths_to_knots(45) == 9

    def test_zero(self):
        assert _ms_tenths_to_knots(0) == 0

    def test_strong_wind(self):
        # 44.7 m/s = 86.9 knots → 87
        assert _ms_tenths_to_knots(447) == 87


class TestFormatAltimeter:

    def test_standard_pressure(self):
        # 1013.2 hPa = 29.92 inHg → A2992
        assert _format_altimeter(10132) == "A2992"

    def test_low_pressure(self):
        # 965.0 hPa ≈ 28.50 inHg → A2850
        assert _format_altimeter(9650) == "A2850"

    def test_high_pressure(self):
        # 1033.0 hPa ≈ 30.50 inHg → A3050
        result = _format_altimeter(10330)
        assert result == "A3050"


class TestFormatMetar:

    def test_complete_metar(self):
        obs = datetime(2026, 3, 15, 17, 53, 0, tzinfo=timezone.utc)
        result = format_metar(
            station_id="KWXS",
            wind_dir_deg=270,
            wind_speed_tenths_ms=54,    # 5.4 m/s ≈ 12 mph ≈ 10 knots
            temp_tenths_c=222,          # 22.2°C
            dew_point_tenths_c=150,     # 15.0°C
            pressure_tenths_hpa=10132,  # 1013.2 hPa = 29.92 inHg
            obs_time=obs,
        )
        assert result == "METAR KWXS 151753Z 27010KT 10SM CLR 22/15 A2992"

    def test_station_id_padded(self):
        obs = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = format_metar("AB", 0, 0, 211, 100, 10132, obs)
        # 21.1°C = 21, 10.0°C = 10, calm wind
        assert result == "METAR ABXX 010000Z 00000KT 10SM CLR 21/10 A2992"

    def test_station_id_truncated(self):
        obs = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = format_metar("TOOLONG", 0, 0, 211, 100, 10132, obs)
        assert result == "METAR TOOL 010000Z 00000KT 10SM CLR 21/10 A2992"
