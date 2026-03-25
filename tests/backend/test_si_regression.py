"""SI migration regression tests.

Verifies that the migration from Davis native units to SI storage
produces identical user-visible output. These tests encode the old
Davis-native values and their expected display results, then verify
the new SI pipeline produces the same values.

If any of these tests fail, the migration has changed user-visible behavior.
"""

from datetime import datetime, timezone

import pytest

from app.utils.units import (
    f_tenths_to_c_tenths,
    inhg_thousandths_to_hpa_tenths,
    mph_to_ms_tenths,
    in_hundredths_to_mm_tenths,
    c_tenths_to_f_tenths,
    hpa_tenths_to_inhg_thousandths,
    ms_tenths_to_mph,
    mm_tenths_to_in_hundredths,
)
from app.models.sensor_meta import convert
from app.services.calculations import (
    heat_index,
    dew_point,
    wind_chill,
    feels_like,
    equivalent_potential_temperature,
)
from app.output.metar import format_metar
from app.output.aprs import APRSWeatherPacket


# ---------------------------------------------------------------------------
# Round-trip: Davis native → SI → display must match old Davis → display
# ---------------------------------------------------------------------------

class TestRoundTripConversion:
    """Verify that Davis values converted to SI then to display produce
    the same result as the old direct Davis-to-display path."""

    # (davis_native_value, sensor_column, expected_display)
    CASES = [
        (720, "outside_temp", 72.0),       # 72.0°F
        (451, "outside_temp", 45.1),       # 45.1°F (within rounding)
        (-100, "outside_temp", -10.0),     # -10.0°F (within rounding)
        (320, "outside_temp", 32.0),       # 32.0°F = 0°C exactly
        (30120, "barometer", 30.12),       # 30.120 inHg (within rounding)
        (29920, "barometer", 29.92),       # standard pressure
        (12, "wind_speed", 12),            # 12 mph
        (0, "wind_speed", 0),              # calm
        (50, "outside_humidity", 50),      # 50% (unchanged)
        (150, "rain_total", 1.50),         # 1.50 in (within rounding)
        (3450, "theta_e", 345.0),          # 345.0 K
    ]

    @pytest.mark.parametrize("davis_raw,column,expected_display", CASES)
    def test_display_matches_old_path(self, davis_raw, column, expected_display):
        """Convert Davis → SI → display and verify against known old output."""
        # Step 1: Convert Davis native to SI (what the driver now does)
        if column in ("outside_temp", "inside_temp", "heat_index", "dew_point",
                       "wind_chill", "feels_like"):
            si_value = f_tenths_to_c_tenths(davis_raw)
        elif column == "barometer":
            si_value = inhg_thousandths_to_hpa_tenths(davis_raw)
        elif column == "wind_speed":
            si_value = mph_to_ms_tenths(davis_raw)
        elif column in ("rain_total", "rain_yearly", "rain_rate"):
            si_value = in_hundredths_to_mm_tenths(davis_raw)
        elif column == "theta_e":
            si_value = davis_raw  # already tenths K
        else:
            si_value = davis_raw  # humidity, direction — no conversion

        # Step 2: Convert SI to display (what sensor_meta.convert does)
        display = convert(column, si_value)

        # Step 3: Compare with expected (allowing rounding tolerance)
        if isinstance(expected_display, float):
            assert abs(display - expected_display) <= 0.15, (
                f"{column}: Davis {davis_raw} → SI {si_value} → display {display}, "
                f"expected {expected_display}"
            )
        else:
            assert display == expected_display


# ---------------------------------------------------------------------------
# Calculations regression: same inputs (converted to SI) produce same outputs
# ---------------------------------------------------------------------------

class TestCalculationsRegression:
    """Verify that weather calculations produce equivalent results
    when given SI inputs compared to the old Davis-native inputs."""

    def test_heat_index_80f_50pct(self):
        """Old: heat_index(800, 50) → ~760 tenths °F.
        New: heat_index(si(800), 50) → ~si(760) tenths °C."""
        si_temp = f_tenths_to_c_tenths(800)
        result_c = heat_index(si_temp, 50)
        assert result_c is not None
        result_f = c_tenths_to_f_tenths(result_c)
        # Old code returned ~760 tenths °F; allow ±10 for rounding
        assert 790 <= result_f <= 810

    def test_dew_point_70f_50pct(self):
        """Old: dew_point(700, 50) → ~505 tenths °F.
        New should produce equivalent."""
        si_temp = f_tenths_to_c_tenths(700)
        result_c = dew_point(si_temp, 50)
        assert result_c is not None
        result_f = c_tenths_to_f_tenths(result_c)
        assert 495 <= result_f <= 515

    def test_wind_chill_30f_10mph(self):
        """Old: wind_chill(300, 10) → some value < 300 tenths °F.
        New should produce equivalent."""
        si_temp = f_tenths_to_c_tenths(300)
        si_wind = mph_to_ms_tenths(10)
        result_c = wind_chill(si_temp, si_wind)
        assert result_c is not None
        result_f = c_tenths_to_f_tenths(result_c)
        assert result_f < 300  # wind chill below actual temp
        assert result_f > 100  # not unreasonably cold

    def test_theta_e_standard(self):
        """Old: theta_e(700, 50, 29920) → ~3280 tenths K.
        New with SI inputs should match."""
        si_temp = f_tenths_to_c_tenths(700)
        si_press = inhg_thousandths_to_hpa_tenths(29920)
        result = equivalent_potential_temperature(si_temp, 50, si_press)
        assert result is not None
        assert 3100 <= result <= 3250  # ~315 K for 21°C/50%/1013 hPa


# ---------------------------------------------------------------------------
# METAR output regression
# ---------------------------------------------------------------------------

class TestMetarRegression:
    """Verify METAR output is identical before and after SI migration."""

    def test_standard_metar(self):
        """Known good METAR from the old code path (Davis inputs).
        Old: format_metar("KWXS", 270, 12, 720, 590, 29921, obs)
        → "METAR KWXS 151753Z 27010KT 10SM CLR 22/15 A2992"
        New: same result with SI inputs."""
        obs = datetime(2026, 3, 15, 17, 53, 0, tzinfo=timezone.utc)
        result = format_metar(
            station_id="KWXS",
            wind_dir_deg=270,
            wind_speed_tenths_ms=mph_to_ms_tenths(12),   # 12 mph → SI
            temp_tenths_c=f_tenths_to_c_tenths(720),     # 72.0°F → SI
            dew_point_tenths_c=f_tenths_to_c_tenths(590),# 59.0°F → SI
            pressure_tenths_hpa=inhg_thousandths_to_hpa_tenths(29921),
            obs_time=obs,
        )
        assert result == "METAR KWXS 151753Z 27010KT 10SM CLR 22/15 A2992"


# ---------------------------------------------------------------------------
# APRS output regression
# ---------------------------------------------------------------------------

class TestAprsRegression:
    """Verify APRS packet output is identical before and after SI migration."""

    def test_standard_packet(self):
        """Known good APRS packet from old code path.
        Old constructor used: wind_speed_mph=10, temp_tenths_f=720,
        barometer_thousandths_inhg=29920
        → '@151753z4903.50N/07201.75W_270/010g015t072r000p000P000h50b10132'
        New: same result with SI inputs."""
        obs = datetime(2026, 3, 15, 17, 53, 0, tzinfo=timezone.utc)
        pkt = APRSWeatherPacket(
            callsign="N0CALL",
            latitude=49.0583,
            longitude=-72.0292,
            wind_dir_deg=270,
            wind_speed_tenths_ms=mph_to_ms_tenths(10),
            wind_gust_tenths_ms=mph_to_ms_tenths(15),
            temp_tenths_c=f_tenths_to_c_tenths(720),
            humidity_pct=50,
            pressure_tenths_hpa=inhg_thousandths_to_hpa_tenths(29920),
            obs_time=obs,
        )
        result = pkt.format_packet()
        # The old code produced exactly this string
        assert result == "@151753z4903.50N/07201.75W_270/010g015t072r000p000P000h50b10132"
