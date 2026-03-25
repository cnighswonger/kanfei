"""Tests for SI unit conversion utilities."""

from app.utils.units import (
    f_tenths_to_c_tenths,
    c_tenths_to_f_tenths,
    inhg_thousandths_to_hpa_tenths,
    hpa_tenths_to_inhg_thousandths,
    mph_to_ms_tenths,
    ms_tenths_to_mph,
    in_hundredths_to_mm_tenths,
    mm_tenths_to_in_hundredths,
    si_temp_to_display_f,
    si_temp_to_display_c,
    si_pressure_to_display_inhg,
    si_pressure_to_display_hpa,
    si_wind_to_display_mph,
    si_rain_to_display_in,
    si_rain_to_display_mm,
)


class TestTemperatureConversion:

    def test_freezing_f_to_c(self):
        assert f_tenths_to_c_tenths(320) == 0  # 32.0°F = 0°C

    def test_boiling_f_to_c(self):
        assert f_tenths_to_c_tenths(2120) == 1000  # 212.0°F = 100.0°C

    def test_room_temp_f_to_c(self):
        assert f_tenths_to_c_tenths(720) == 222  # 72.0°F = 22.2°C

    def test_negative_f_to_c(self):
        assert f_tenths_to_c_tenths(-400) == -400  # -40°F = -40°C

    def test_freezing_c_to_f(self):
        assert c_tenths_to_f_tenths(0) == 320

    def test_boiling_c_to_f(self):
        assert c_tenths_to_f_tenths(1000) == 2120

    def test_round_trip_temp(self):
        for raw_f in [0, 320, 500, 720, 1000, -100, -400]:
            c = f_tenths_to_c_tenths(raw_f)
            back = c_tenths_to_f_tenths(c)
            assert abs(back - raw_f) <= 1  # allow ±1 rounding


class TestPressureConversion:

    def test_standard_pressure_to_hpa(self):
        result = inhg_thousandths_to_hpa_tenths(29920)
        assert 10130 <= result <= 10135  # 1013.2 hPa

    def test_low_pressure_to_hpa(self):
        result = inhg_thousandths_to_hpa_tenths(28500)
        assert 9640 <= result <= 9660

    def test_standard_hpa_to_inhg(self):
        result = hpa_tenths_to_inhg_thousandths(10132)
        assert 29910 <= result <= 29930

    def test_round_trip_pressure(self):
        for raw_inhg in [28000, 29000, 29920, 30500]:
            hpa = inhg_thousandths_to_hpa_tenths(raw_inhg)
            back = hpa_tenths_to_inhg_thousandths(hpa)
            assert abs(back - raw_inhg) <= 5  # small rounding tolerance


class TestWindConversion:

    def test_ten_mph_to_ms(self):
        result = mph_to_ms_tenths(10)
        assert result == 45  # 4.47 m/s → 45 tenths

    def test_zero_mph(self):
        assert mph_to_ms_tenths(0) == 0

    def test_ms_to_mph(self):
        assert ms_tenths_to_mph(45) == 10

    def test_round_trip_wind(self):
        for mph in [0, 5, 10, 25, 50, 100]:
            ms = mph_to_ms_tenths(mph)
            back = ms_tenths_to_mph(ms)
            assert abs(back - mph) <= 1


class TestRainConversion:

    def test_one_inch_to_mm(self):
        assert in_hundredths_to_mm_tenths(100) == 254  # 1 in = 25.4 mm

    def test_zero_rain(self):
        assert in_hundredths_to_mm_tenths(0) == 0

    def test_small_rain(self):
        result = in_hundredths_to_mm_tenths(1)  # 0.01 in
        assert result == 3  # 0.254 mm → 3 tenths

    def test_mm_to_in(self):
        assert mm_tenths_to_in_hundredths(254) == 100

    def test_round_trip_rain(self):
        for raw_in in [0, 1, 10, 50, 100, 500]:
            mm = in_hundredths_to_mm_tenths(raw_in)
            back = mm_tenths_to_in_hundredths(mm)
            assert abs(back - raw_in) <= 1


class TestDisplayConversions:

    def test_temp_to_f(self):
        assert si_temp_to_display_f(222) == 72.0  # 22.2°C → 72.0°F

    def test_temp_to_c(self):
        assert si_temp_to_display_c(222) == 22.2

    def test_freezing_to_f(self):
        assert si_temp_to_display_f(0) == 32.0

    def test_negative_temp_to_f(self):
        result = si_temp_to_display_f(-400)  # -40°C
        assert result == -40.0

    def test_pressure_to_inhg(self):
        result = si_pressure_to_display_inhg(10132)
        assert 29.91 <= result <= 29.93

    def test_pressure_to_hpa(self):
        assert si_pressure_to_display_hpa(10132) == 1013.2

    def test_wind_to_mph(self):
        assert si_wind_to_display_mph(45) == 10  # 4.5 m/s → 10 mph

    def test_rain_to_in(self):
        assert si_rain_to_display_in(254) == 1.0

    def test_rain_to_mm(self):
        assert si_rain_to_display_mm(254) == 25.4
