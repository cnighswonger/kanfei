"""Tests for weather calculation services."""

from app.services.calculations import (
    heat_index,
    dew_point,
    wind_chill,
    feels_like,
    equivalent_potential_temperature,
    rain_rate_inches_per_hour,
)


class TestHeatIndex:
    def test_at_80f_50pct(self):
        """At 80F/50%, heat index should be around 80-82F."""
        result = heat_index(800, 50)
        assert result is not None
        assert 790 <= result <= 830

    def test_at_90f_80pct(self):
        """At 90F/80%, heat index should be quite high."""
        result = heat_index(900, 80)
        assert result is not None
        assert result > 1000  # > 100F

    def test_below_68f_returns_none(self):
        assert heat_index(670, 50) is None

    def test_above_122f_returns_none(self):
        assert heat_index(1230, 50) is None

    def test_at_table_boundary(self):
        """At 68F/0%, should return ~61F (per table)."""
        result = heat_index(680, 0)
        assert result is not None
        assert 600 <= result <= 620

    def test_interpolation_between_rows(self):
        """Value at 80.5F should be between 80F and 81F values."""
        result_80 = heat_index(800, 50)
        result_81 = heat_index(810, 50)
        result_mid = heat_index(805, 50)
        assert result_80 is not None and result_81 is not None and result_mid is not None
        assert result_80 <= result_mid <= result_81


class TestDewPoint:
    def test_at_70f_50pct(self):
        """At 70F/50%, dew point should be around 50F."""
        result = dew_point(700, 50)
        assert result is not None
        assert 490 <= result <= 520  # ~50F in tenths

    def test_at_100pct_humidity(self):
        """At 100% humidity, dew point should equal temperature."""
        result = dew_point(700, 100)
        assert result is not None
        assert abs(result - 700) < 10  # Within 1F

    def test_zero_humidity_returns_none(self):
        assert dew_point(700, 0) is None

    def test_always_less_than_or_equal_temp(self):
        """Dew point should never exceed actual temperature."""
        for temp in range(300, 1000, 100):
            for rh in range(10, 101, 10):
                result = dew_point(temp, rh)
                if result is not None:
                    assert result <= temp + 5  # Small tolerance for rounding


class TestWindChill:
    def test_at_30f_10mph(self):
        """At 30F/10mph, wind chill should be below 30F."""
        result = wind_chill(300, 10)
        assert result is not None
        assert result < 300

    def test_above_914f_returns_none(self):
        """Wind chill not applicable above 91.4F."""
        assert wind_chill(920, 10) is None

    def test_zero_wind_returns_temp(self):
        """No wind means no chill effect."""
        assert wind_chill(300, 0) == 300

    def test_capped_at_50mph(self):
        """Wind speed capped at 50 mph."""
        result_50 = wind_chill(300, 50)
        result_60 = wind_chill(300, 60)
        # Should be identical since capped at 50
        assert result_50 == result_60

    def test_chill_increases_with_wind(self):
        """More wind = more chill (lower value)."""
        result_5 = wind_chill(300, 5)
        result_20 = wind_chill(300, 20)
        assert result_5 is not None and result_20 is not None
        assert result_20 < result_5

    def test_doesnt_exceed_actual_temp(self):
        """Wind chill should not exceed actual temperature."""
        result = wind_chill(300, 5)
        assert result is not None
        assert result <= 300


class TestFeelsLike:
    def test_hot_and_humid_uses_heat_index(self):
        """Above 80F with humidity > 40% should use heat index."""
        result = feels_like(900, 80, 5)
        hi = heat_index(900, 80)
        assert hi is not None
        assert result == hi

    def test_cold_and_windy_uses_wind_chill(self):
        """Below 50F with wind > 3 mph should use wind chill."""
        result = feels_like(300, 50, 15)
        wc = wind_chill(300, 15)
        assert wc is not None
        assert result == wc

    def test_moderate_conditions_uses_actual(self):
        """Between 50-80F should return actual temperature."""
        result = feels_like(650, 50, 5)
        assert result == 650


class TestEquivalentPotentialTemperature:
    def test_standard_conditions(self):
        """At ~70F, 50% RH, ~30 inHg, theta_e should be reasonable."""
        result = equivalent_potential_temperature(700, 50, 30000)
        assert result is not None
        # Theta_e typically 300-360K for surface conditions
        assert 3000 <= result <= 3700  # tenths of K

    def test_hot_humid_higher_theta_e(self):
        """Hotter and more humid should give higher theta_e."""
        result_cool = equivalent_potential_temperature(600, 40, 30000)
        result_hot = equivalent_potential_temperature(900, 90, 30000)
        assert result_cool is not None and result_hot is not None
        assert result_hot > result_cool

    def test_zero_humidity_returns_none(self):
        assert equivalent_potential_temperature(700, 0, 30000) is None

    def test_zero_pressure_returns_none(self):
        assert equivalent_potential_temperature(700, 50, 0) is None


class TestRainRate:
    def test_basic_rate(self):
        """100 clicks per inch, 10 click delta in 10 seconds = 36 in/hr."""
        result = rain_rate_inches_per_hour(110, 100, 100, 10.0)
        assert result is not None
        assert abs(result - 36.0) < 0.1

    def test_no_rain(self):
        result = rain_rate_inches_per_hour(100, 100, 100, 10.0)
        assert result == 0.0

    def test_zero_cal_returns_none(self):
        assert rain_rate_inches_per_hour(110, 100, 0, 10.0) is None

    def test_negative_delta_returns_none(self):
        """Counter rollover should return None."""
        assert rain_rate_inches_per_hour(50, 100, 100, 10.0) is None
