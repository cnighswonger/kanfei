"""Tests for weather calculation services (SI units).

All inputs: tenths °C, tenths m/s, tenths hPa.
All temperature outputs: tenths °C.
"""

from app.services.calculations import (
    heat_index,
    dew_point,
    wind_chill,
    feels_like,
    equivalent_potential_temperature,
    rain_rate_inches_per_hour,
)
from app.utils.units import f_tenths_to_c_tenths, c_tenths_to_f_tenths, mph_to_ms_tenths


class TestHeatIndex:

    def test_at_27c_50pct(self):
        # 80°F / 50% → heat index ~80°F ≈ 26.7°C
        temp_c = f_tenths_to_c_tenths(800)  # 80°F → 267 tenths °C
        result = heat_index(temp_c, 50)
        assert result is not None
        # Heat index at 80°F/50% ≈ 80°F → ~267 tenths °C
        assert 260 <= result <= 275

    def test_at_32c_80pct(self):
        # 90°F / 80% → high heat index
        temp_c = f_tenths_to_c_tenths(900)
        result = heat_index(temp_c, 80)
        assert result is not None
        result_f = c_tenths_to_f_tenths(result)
        assert result_f > 1000  # > 100°F

    def test_below_20c_returns_none(self):
        # Below 68°F (20°C) → out of table range
        assert heat_index(f_tenths_to_c_tenths(600), 50) is None

    def test_above_50c_returns_none(self):
        # Above 122°F (50°C) → out of table range
        assert heat_index(f_tenths_to_c_tenths(1300), 50) is None

    def test_at_table_boundary(self):
        # Exactly 68°F = 20°C → should return a value
        temp_c = f_tenths_to_c_tenths(680)
        result = heat_index(temp_c, 50)
        assert result is not None

    def test_interpolation_between_rows(self):
        # 82.5°F, 55% → between table rows/cols
        temp_c = f_tenths_to_c_tenths(825)
        result = heat_index(temp_c, 55)
        assert result is not None


class TestDewPoint:

    def test_at_21c_50pct(self):
        # 70°F / 50% → dew point ~50.5°F ≈ 10.3°C
        temp_c = f_tenths_to_c_tenths(700)
        result = dew_point(temp_c, 50)
        assert result is not None
        assert 95 <= result <= 110  # ~10°C in tenths

    def test_at_100pct_humidity(self):
        # At 100% RH, dew point = temperature
        temp_c = 222  # 22.2°C
        result = dew_point(temp_c, 100)
        assert result is not None
        assert abs(result - temp_c) <= 2

    def test_zero_humidity_returns_none(self):
        assert dew_point(222, 0) is None

    def test_always_less_than_or_equal_temp(self):
        for temp_c in [0, 100, 200, 300]:
            for rh in [20, 50, 80, 100]:
                dp = dew_point(temp_c, rh)
                if dp is not None:
                    assert dp <= temp_c + 1  # allow ±1 rounding


class TestWindChill:

    def test_cold_and_windy(self):
        # 30°F ≈ -1.1°C, 10 mph ≈ 4.5 m/s
        temp_c = f_tenths_to_c_tenths(300)
        wind_ms = mph_to_ms_tenths(10)
        result = wind_chill(temp_c, wind_ms)
        assert result is not None
        assert result < temp_c

    def test_above_33c_returns_none(self):
        # Above 91.4°F (33°C) → not applicable
        assert wind_chill(340, mph_to_ms_tenths(10)) is None

    def test_zero_wind_returns_temp(self):
        temp_c = f_tenths_to_c_tenths(300)
        assert wind_chill(temp_c, 0) == temp_c

    def test_capped_at_50mph(self):
        temp_c = f_tenths_to_c_tenths(300)
        result_50 = wind_chill(temp_c, mph_to_ms_tenths(50))
        result_100 = wind_chill(temp_c, mph_to_ms_tenths(100))
        assert result_50 is not None and result_100 is not None
        assert abs(result_50 - result_100) <= 1

    def test_chill_increases_with_wind(self):
        temp_c = f_tenths_to_c_tenths(300)
        wc5 = wind_chill(temp_c, mph_to_ms_tenths(5))
        wc20 = wind_chill(temp_c, mph_to_ms_tenths(20))
        assert wc5 is not None and wc20 is not None
        assert wc20 < wc5

    def test_doesnt_exceed_actual_temp(self):
        temp_c = f_tenths_to_c_tenths(300)
        result = wind_chill(temp_c, mph_to_ms_tenths(5))
        assert result is not None
        assert result <= temp_c


class TestFeelsLike:

    def test_hot_and_humid_uses_heat_index(self):
        temp_c = f_tenths_to_c_tenths(850)  # 85°F
        result = feels_like(temp_c, 70, mph_to_ms_tenths(5))
        assert result > temp_c

    def test_cold_and_windy_uses_wind_chill(self):
        temp_c = f_tenths_to_c_tenths(300)  # 30°F
        result = feels_like(temp_c, 30, mph_to_ms_tenths(15))
        assert result < temp_c

    def test_moderate_conditions_uses_actual(self):
        temp_c = f_tenths_to_c_tenths(650)  # 65°F ≈ 18.3°C
        result = feels_like(temp_c, 50, mph_to_ms_tenths(2))
        assert result == temp_c


class TestEquivalentPotentialTemperature:

    def test_standard_conditions(self):
        # 20°C, 50% RH, 1013.2 hPa
        result = equivalent_potential_temperature(200, 50, 10132)
        assert result is not None
        assert result > 2930  # > 293K

    def test_hot_humid_higher_theta_e(self):
        cool = equivalent_potential_temperature(200, 50, 10132)
        hot = equivalent_potential_temperature(350, 90, 10132)
        assert cool is not None and hot is not None
        assert hot > cool

    def test_zero_humidity_returns_none(self):
        assert equivalent_potential_temperature(200, 0, 10132) is None

    def test_zero_pressure_returns_none(self):
        assert equivalent_potential_temperature(200, 50, 0) is None


class TestRainRate:

    def test_basic_rate(self):
        result = rain_rate_inches_per_hour(110, 100, 100, 600)
        assert result is not None
        assert result > 0

    def test_no_rain(self):
        result = rain_rate_inches_per_hour(100, 100, 100, 600)
        assert result == 0.0

    def test_zero_cal_returns_none(self):
        assert rain_rate_inches_per_hour(110, 100, 0, 600) is None

    def test_negative_delta_returns_none(self):
        assert rain_rate_inches_per_hour(100, 110, 100, 600) is None
