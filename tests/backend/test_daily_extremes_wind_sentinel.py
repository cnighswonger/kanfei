"""Daily extremes must respect SENSOR_BOUNDS.

An extreme is stickier than a reading. A sentinel that slips past the
parser becomes a daily MAXIMUM, and then outlives the outage that produced
it — republished on every poll until midnight rollover.

That happened on 2026-08-01: a 27-minute transmitter dropout on the bench
Vue wrote 107 rows of 255 mph. No bad packets went out *during* the outage
(cwop.py short-circuits when outside temp is None), but once the link
recovered, every subsequent APRS packet carried the poisoned daily high as
its gust. The instantaneous wind was correct the whole time; findu showed
a false gust for hours.

The underlying gap was broader than wind. SENSOR_BOUNDS already existed
and was applied by history.py and export.py, so charts and CSV exports had
always discarded out-of-range values. daily_extremes.py consulted it for
nothing — which made the PUBLISHED path the least guarded one, since
cwop.py and wunderground.py both source their gust from wind_speed_hi.
"""

import pytest

from app.models.sensor_meta import SENSOR_BOUNDS
from app.services.daily_extremes import _bounded, _in_bounds


class TestWindSentinel:
    """The value that actually caused the incident."""

    def test_the_observed_sentinel_is_out_of_bounds(self):
        """1140 tenths m/s = 114 m/s = 255 mph, the Davis single-byte
        sentinel as it lands in the database."""
        assert _in_bounds("wind_speed", 1140) is False

    def test_sentinel_yields_no_extreme(self):
        assert _bounded("wind_speed", 1140, lambda: None) is None

    def test_bound_sits_below_the_sentinel(self):
        """The declared ceiling must actually exclude 1140, or the guard
        does not guard. An earlier version used a hand-picked 300 mph
        threshold that let 255 mph straight through."""
        assert SENSOR_BOUNDS["wind_speed"][1] < 1140


class TestRealWindPreserved:
    @pytest.mark.parametrize("tenths_ms", [0, 10, 100, 400, 894])
    def test_in_range_speeds_survive(self, tenths_ms):
        assert _in_bounds("wind_speed", tenths_ms) is True
        assert _bounded("wind_speed", tenths_ms, lambda: None) is not None

    def test_calm_is_a_reading_not_an_absence(self):
        """0 is data. The Davis manual gives 0 as the dash value for High
        Wind Speed, which is exactly why that particular sentinel can
        never be filtered — it is indistinguishable from a calm interval."""
        out = _bounded("wind_speed", 0, lambda: None)
        assert out is not None
        assert out["value"] == 0

    def test_upper_bound_is_inclusive(self):
        """894 tenths m/s ≈ 200 mph — the declared ceiling is a valid
        reading, not the first rejected one."""
        assert _in_bounds("wind_speed", 894) is True
        assert _in_bounds("wind_speed", 895) is False


class TestUnitIndependence:
    """Bounds are in storage units, so the check must happen before
    convert(). Otherwise the threshold would differ for a user displaying
    km/h versus mph, and the same sentinel would pass on one and fail on
    the other."""

    def test_bounds_are_raw_not_display(self):
        # 1140 raw = 255 mph = 410 km/h = 114 m/s. Only the raw value has
        # a stable relationship to the bound.
        assert _in_bounds("wind_speed", 1140) is False
        # 255, if it were mistaken for a display-unit mph value, would sit
        # comfortably inside the raw bound and be wrongly accepted.
        assert _in_bounds("wind_speed", 255) is True


class TestAllBoundedSensors:
    """daily_extremes now applies SENSOR_BOUNDS to every extreme it
    returns, matching what history.py and export.py already did."""

    @pytest.mark.parametrize("column", [
        "outside_temp", "inside_temp", "wind_speed", "barometer",
        "outside_humidity", "inside_humidity", "rain_rate",
    ])
    def test_every_extreme_column_has_bounds(self, column):
        assert column in SENSOR_BOUNDS, (
            f"{column} feeds a daily extreme but declares no bounds"
        )

    @pytest.mark.parametrize("column,below,above", [
        ("outside_temp", -401, 657),
        ("inside_temp", -401, 657),
        ("barometer", 8465, 11864),
        ("outside_humidity", 0, 105),
        ("inside_humidity", 0, 105),
        ("rain_rate", -1, 25401),
    ])
    def test_out_of_range_rejected_for_each(self, column, below, above):
        assert _bounded(column, below, lambda: None) is None
        assert _bounded(column, above, lambda: None) is None

    @pytest.mark.parametrize("column,ok", [
        ("outside_temp", 222),        # 22.2 C
        ("inside_temp", 210),
        ("barometer", 10132),         # 1013.2 hPa
        ("outside_humidity", 55),
        ("inside_humidity", 50),
        ("rain_rate", 0),
    ])
    def test_normal_readings_survive_for_each(self, column, ok):
        assert _bounded(column, ok, lambda: None) is not None


class TestPassthrough:
    def test_none_raw_is_not_an_out_of_range_error(self):
        """Missing is missing — it must not be conflated with invalid."""
        assert _in_bounds("wind_speed", None) is True
        assert _bounded("wind_speed", None, lambda: None) is None

    def test_unknown_column_is_permitted(self):
        """A sensor with no declared bounds must not be silently dropped."""
        assert _in_bounds("some_new_sensor", 99999) is True

    def test_timestamp_lookup_skipped_when_out_of_bounds(self):
        """The `at` lookup is a database query. No point running it for a
        value that is about to be discarded."""
        called = []

        def at_fn():
            called.append(True)
            return None

        _bounded("wind_speed", 1140, at_fn)
        assert called == [], "should not query for a rejected extreme"

    def test_timestamp_lookup_runs_when_in_bounds(self):
        called = []

        def at_fn():
            called.append(True)
            return None

        _bounded("wind_speed", 100, at_fn)
        assert called == [True]
