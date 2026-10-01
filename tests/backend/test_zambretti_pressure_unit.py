"""Regression tests for the Zambretti + pressure-trend unit bug.

``sensor_readings.barometer`` is stored in **tenths of hPa** (schema
canonical — see ``utils.units.si_pressure_to_display_inhg`` and
``archive_sync.py``).  Two consumers were reading the raw column as
if it were already thousandths of inHg and feeding it directly to
their algorithms:

- ``api/forecast.py`` → ``zambretti_forecast`` — a real high-pressure
  reading (e.g. 10220 tenths-hPa = 1022.0 hPa = 30.18 inHg) got
  clamped to ``PRESSURE_LOW`` and the z-number pinned to the worst
  entry in whatever table trend chose.  On "steady" that was
  "Stormy, much rain" — the user-visible symptom reported 2026-10-01.
- ``poller._get_pressure_trend`` → ``analyze_pressure_trend`` — the
  threshold constants are in thousandths of inHg (0.020 inHg over
  3h = 20 thousandths).  Feeding tenths-hPa deltas scales the
  threshold by ~3.4×, under-reporting real trends.

Both callers now convert via ``hpa_tenths_to_inhg_thousandths``.
These tests pin the invariant so a future edit that drops the
conversion fails loudly instead of silently reverting to always
reporting "Stormy, much rain" / "steady".
"""

import time

from app.services.forecast_local import (
    FALLING_THRESHOLD,
    RISING_THRESHOLD,
    STEADY_FORECASTS,
    zambretti_forecast,
)
from app.services.pressure_trend import analyze_pressure_trend
from app.utils.units import hpa_tenths_to_inhg_thousandths


class TestZambrettiPressureUnit:
    """``zambretti_forecast`` after the ``api/forecast.py`` conversion."""

    def test_high_pressure_lands_in_fine_bucket(self):
        """1022.0 hPa (DB value 10220) is well above the 1013.25 hPa
        standard — Zambretti should land in the lower (better-weather)
        half of the steady table, not pinned to "Stormy, much rain"
        the way the pre-fix code did."""
        baro_db_tenths_hpa = 10220
        result = zambretti_forecast(
            pressure_thousandths=hpa_tenths_to_inhg_thousandths(
                baro_db_tenths_hpa,
            ),
            pressure_change_3h=0,
            wind_dir_deg=None,
            month=10,
        )
        assert result.trend == "steady"
        assert "Stormy" not in result.forecast_text
        assert "much rain" not in result.forecast_text
        # Lower half of STEADY_FORECASTS is "fine" territory.
        assert result.z_number <= len(STEADY_FORECASTS) // 2 - 1, (
            f"z={result.z_number} '{result.forecast_text}' — "
            "30.18 inHg should map to the fine half of the table"
        )

    def test_low_pressure_lands_in_stormy_bucket(self):
        """980.0 hPa (DB value 9800) is nor'easter territory —
        Zambretti should land in the upper (worse-weather) half of
        the steady table."""
        baro_db_tenths_hpa = 9800
        result = zambretti_forecast(
            pressure_thousandths=hpa_tenths_to_inhg_thousandths(
                baro_db_tenths_hpa,
            ),
            pressure_change_3h=0,
            wind_dir_deg=None,
            month=10,
        )
        assert result.trend == "steady"
        assert result.z_number >= len(STEADY_FORECASTS) // 2, (
            f"z={result.z_number} '{result.forecast_text}' — "
            "28.94 inHg should map to the stormy half of the table"
        )

    def test_raw_db_value_without_conversion_misclassifies(self):
        """Negative control.  Pins the shape of the pre-fix bug so if
        a future edit removes the conversion the regression above
        would otherwise still pass by coincidence — this one won't."""
        baro_db_tenths_hpa = 10220  # Real 1022.0 hPa — fine weather.
        result = zambretti_forecast(
            pressure_thousandths=baro_db_tenths_hpa,  # NO conversion.
            pressure_change_3h=0,
            wind_dir_deg=None,
            month=10,
        )
        # Pre-fix behaviour: 10220 clamps to PRESSURE_LOW=28050,
        # normalized to 0.0, z_raw = (len-1), text = worst entry.
        assert result.z_number == len(STEADY_FORECASTS) - 1
        assert result.forecast_text == STEADY_FORECASTS[-1]


class TestPressureTrendUnit:
    """``analyze_pressure_trend`` after the ``poller._get_pressure_trend``
    conversion."""

    def test_real_rise_classifies_as_rising_after_conversion(self):
        """1020.0 → 1022.0 hPa over 3h is a clearly-rising pressure
        change.  Raw DB diff: 20 tenths-hPa.  Converted to thousandths
        of inHg the diff is ~59 — well over RISING_THRESHOLD (20).
        Pre-fix the raw 20 would have been exactly ON the threshold
        and the classifier's strict ``>`` would read as 'steady'."""
        now = time.time()
        readings_db_raw = [(now - 10800, 10200), (now, 10220)]
        readings_converted = [
            (t, hpa_tenths_to_inhg_thousandths(b))
            for t, b in readings_db_raw
        ]
        result = analyze_pressure_trend(readings_converted)
        assert result is not None
        assert result.trend == "rising", (
            f"got '{result.trend}' with change={result.change} "
            f"(threshold={RISING_THRESHOLD})"
        )

    def test_real_fall_classifies_as_falling_after_conversion(self):
        """1020.0 → 1018.0 hPa over 3h is a clearly-falling pressure
        change.  Symmetric to the rising case."""
        now = time.time()
        readings_db_raw = [(now - 10800, 10200), (now, 10180)]
        readings_converted = [
            (t, hpa_tenths_to_inhg_thousandths(b))
            for t, b in readings_db_raw
        ]
        result = analyze_pressure_trend(readings_converted)
        assert result is not None
        assert result.trend == "falling", (
            f"got '{result.trend}' with change={result.change} "
            f"(threshold={FALLING_THRESHOLD})"
        )

    def test_tiny_wiggle_still_classifies_as_steady(self):
        """1020.00 → 1020.03 hPa over 3h — real sensor jitter, not a
        trend.  Must stay 'steady' or the arrow becomes noise."""
        now = time.time()
        readings_db_raw = [(now - 10800, 10200), (now, 10200)]
        readings_converted = [
            (t, hpa_tenths_to_inhg_thousandths(b))
            for t, b in readings_db_raw
        ]
        result = analyze_pressure_trend(readings_converted)
        assert result is not None
        assert result.trend == "steady"
