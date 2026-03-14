"""Tests for surface observation trend analysis."""

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from app.models.radar_threats import (
    CWOPReading,
    StationTrend,
    SurfaceAnalyzerState,
)
from app.services.surface_analyzer import SurfaceAnalyzer


def _make_obs(station_id, pressure=29.92, temp=72.0, dew=60.0,
              wind_speed=5.0, wind_dir=180, distance=5.0,
              bearing="S", lat=35.0, lon=-97.0):
    """Create a fake station observation with the expected attributes."""
    return SimpleNamespace(
        station_id=station_id,
        pressure_inhg=pressure,
        temp_f=temp,
        dew_point_f=dew,
        wind_speed_mph=wind_speed,
        wind_dir_deg=wind_dir,
        distance_miles=distance,
        bearing_cardinal=bearing,
        latitude=lat,
        longitude=lon,
    )


def _make_result(*observations):
    """Wrap observations in an object with .stations attribute."""
    return SimpleNamespace(stations=list(observations))


# =============================================================================
# Initialization
# =============================================================================

class TestSurfaceAnalyzerInit:
    def test_default_state(self):
        sa = SurfaceAnalyzer()
        assert isinstance(sa.state, SurfaceAnalyzerState)
        assert sa.state.cwop_station_history == {}

    def test_custom_state(self):
        state = SurfaceAnalyzerState()
        state.cwop_station_history["X"] = []
        sa = SurfaceAnalyzer(state=state)
        assert "X" in sa.state.cwop_station_history

    def test_custom_max_readings(self):
        sa = SurfaceAnalyzer(max_readings_per_station=5)
        assert sa._max_readings == 5


# =============================================================================
# update_history
# =============================================================================

class TestUpdateHistory:
    def test_single_station_single_update(self):
        sa = SurfaceAnalyzer()
        t = datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc)
        sa.update_history(_make_result(_make_obs("ST1")), t)
        assert "ST1" in sa.state.cwop_station_history
        assert len(sa.state.cwop_station_history["ST1"]) == 1

    def test_multiple_stations(self):
        sa = SurfaceAnalyzer()
        t = datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc)
        sa.update_history(_make_result(
            _make_obs("ST1"), _make_obs("ST2"), _make_obs("ST3"),
        ), t)
        assert len(sa.state.cwop_station_history) == 3

    def test_multiple_cycles_accumulate(self):
        sa = SurfaceAnalyzer()
        for i in range(3):
            t = datetime(2026, 3, 12, 16, i * 5, tzinfo=timezone.utc)
            sa.update_history(_make_result(_make_obs("ST1")), t)
        assert len(sa.state.cwop_station_history["ST1"]) == 3

    def test_deduplication_within_60_seconds(self):
        sa = SurfaceAnalyzer()
        t1 = datetime(2026, 3, 12, 16, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 12, 16, 0, 30, tzinfo=timezone.utc)
        sa.update_history(_make_result(_make_obs("ST1")), t1)
        sa.update_history(_make_result(_make_obs("ST1")), t2)
        assert len(sa.state.cwop_station_history["ST1"]) == 1

    def test_no_dedup_beyond_60_seconds(self):
        sa = SurfaceAnalyzer()
        t1 = datetime(2026, 3, 12, 16, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 12, 16, 1, 1, tzinfo=timezone.utc)
        sa.update_history(_make_result(_make_obs("ST1")), t1)
        sa.update_history(_make_result(_make_obs("ST1")), t2)
        assert len(sa.state.cwop_station_history["ST1"]) == 2

    def test_cap_at_max_readings(self):
        sa = SurfaceAnalyzer(max_readings_per_station=3)
        for i in range(5):
            t = datetime(2026, 3, 12, 16, i * 5, tzinfo=timezone.utc)
            sa.update_history(_make_result(_make_obs("ST1")), t)
        assert len(sa.state.cwop_station_history["ST1"]) == 3

    def test_target_local_vs_meso(self):
        sa = SurfaceAnalyzer()
        t = datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc)
        sa.update_history(_make_result(_make_obs("ST1")), t, target='local')
        sa.update_history(_make_result(_make_obs("ST2")), t, target='meso')
        assert "ST1" in sa.state.cwop_station_history
        assert "ST2" in sa.state.meso_cwop_station_history
        assert "ST1" not in sa.state.meso_cwop_station_history

    def test_target_corridor(self):
        sa = SurfaceAnalyzer()
        t = datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc)
        sa.update_history(_make_result(_make_obs("ST1")), t, target='corridor')
        assert "ST1" in sa.state.corridor_cwop_station_history

    def test_none_fields_stored(self):
        sa = SurfaceAnalyzer()
        t = datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc)
        sa.update_history(_make_result(
            _make_obs("ST1", pressure=None, temp=None)
        ), t)
        reading = sa.state.cwop_station_history["ST1"][0]
        assert reading.pressure_inhg is None
        assert reading.temp_f is None


# =============================================================================
# compute_trends
# =============================================================================

class TestComputeTrends:
    def test_empty_history_returns_empty(self):
        sa = SurfaceAnalyzer()
        trends, gradient = sa.compute_trends()
        assert trends == []
        assert gradient is None

    def test_single_reading_skipped(self):
        sa = SurfaceAnalyzer()
        t = datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc)
        sa.update_history(_make_result(_make_obs("ST1")), t)
        trends, _ = sa.compute_trends()
        assert len(trends) == 0

    def test_pressure_rate_falling(self):
        sa = SurfaceAnalyzer()
        t1 = datetime(2026, 3, 12, 15, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc)
        sa.update_history(_make_result(_make_obs("ST1", pressure=30.00)), t1)
        sa.update_history(_make_result(_make_obs("ST1", pressure=29.90)), t2)
        trends, _ = sa.compute_trends()
        assert len(trends) == 1
        assert abs(trends[0].pressure_rate_inhg_hr - (-0.10)) < 0.001

    def test_pressure_rate_rising(self):
        sa = SurfaceAnalyzer()
        t1 = datetime(2026, 3, 12, 15, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc)
        sa.update_history(_make_result(_make_obs("ST1", pressure=29.90)), t1)
        sa.update_history(_make_result(_make_obs("ST1", pressure=30.00)), t2)
        trends, _ = sa.compute_trends()
        assert abs(trends[0].pressure_rate_inhg_hr - 0.10) < 0.001

    def test_temperature_rate(self):
        sa = SurfaceAnalyzer()
        t1 = datetime(2026, 3, 12, 15, 30, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc)
        sa.update_history(_make_result(_make_obs("ST1", temp=70.0)), t1)
        sa.update_history(_make_result(_make_obs("ST1", temp=65.0)), t2)
        trends, _ = sa.compute_trends()
        # -5F in 30 min = -10F/hr
        assert abs(trends[0].temp_rate_f_hr - (-10.0)) < 0.1

    def test_wind_shift_simple(self):
        sa = SurfaceAnalyzer()
        t1 = datetime(2026, 3, 12, 15, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc)
        sa.update_history(_make_result(_make_obs("ST1", wind_dir=90)), t1)
        sa.update_history(_make_result(_make_obs("ST1", wind_dir=180)), t2)
        trends, _ = sa.compute_trends()
        assert trends[0].wind_shift_deg == 90

    def test_wind_shift_wraparound(self):
        """350 -> 10 should be 20 degrees, not 340."""
        sa = SurfaceAnalyzer()
        t1 = datetime(2026, 3, 12, 15, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc)
        sa.update_history(_make_result(_make_obs("ST1", wind_dir=350)), t1)
        sa.update_history(_make_result(_make_obs("ST1", wind_dir=10)), t2)
        trends, _ = sa.compute_trends()
        assert trends[0].wind_shift_deg == 20

    def test_sorted_by_distance(self):
        sa = SurfaceAnalyzer()
        t1 = datetime(2026, 3, 12, 15, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc)
        sa.update_history(_make_result(
            _make_obs("FAR", distance=20.0),
            _make_obs("NEAR", distance=2.0),
            _make_obs("MID", distance=10.0),
        ), t1)
        sa.update_history(_make_result(
            _make_obs("FAR", distance=20.0),
            _make_obs("NEAR", distance=2.0),
            _make_obs("MID", distance=10.0),
        ), t2)
        trends, _ = sa.compute_trends()
        assert trends[0].station_id == "NEAR"
        assert trends[1].station_id == "MID"
        assert trends[2].station_id == "FAR"

    def test_pressure_gradient_bearing(self):
        """Fastest falling station's bearing returned as gradient."""
        sa = SurfaceAnalyzer()
        t1 = datetime(2026, 3, 12, 15, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc)
        sa.update_history(_make_result(
            _make_obs("ST1", pressure=30.00, bearing="N"),
            _make_obs("ST2", pressure=30.00, bearing="SW"),
        ), t1)
        sa.update_history(_make_result(
            _make_obs("ST1", pressure=29.95, bearing="N"),   # -0.05/hr
            _make_obs("ST2", pressure=29.80, bearing="SW"),  # -0.20/hr (fastest)
        ), t2)
        _, gradient = sa.compute_trends()
        assert gradient == "SW"

    def test_pressure_gradient_none_when_small(self):
        """No gradient when all rates > -0.01."""
        sa = SurfaceAnalyzer()
        t1 = datetime(2026, 3, 12, 15, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc)
        sa.update_history(_make_result(
            _make_obs("ST1", pressure=30.00, bearing="N"),
            _make_obs("ST2", pressure=30.00, bearing="S"),
        ), t1)
        sa.update_history(_make_result(
            _make_obs("ST1", pressure=30.00, bearing="N"),
            _make_obs("ST2", pressure=29.995, bearing="S"),  # -0.005/hr
        ), t2)
        _, gradient = sa.compute_trends()
        assert gradient is None

    def test_very_short_timespan_skipped(self):
        """< 36 seconds between readings should be skipped."""
        sa = SurfaceAnalyzer()
        t1 = datetime(2026, 3, 12, 16, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 12, 16, 0, 30, tzinfo=timezone.utc)  # 30 sec later
        # Force two readings by manually inserting (bypass dedup)
        sa.state.cwop_station_history["ST1"] = [
            CWOPReading(timestamp=t1, pressure_inhg=30.0, distance_miles=5.0),
            CWOPReading(timestamp=t2, pressure_inhg=29.9, distance_miles=5.0),
        ]
        trends, _ = sa.compute_trends()
        assert len(trends) == 0

    def test_none_pressure_skips_rate(self):
        sa = SurfaceAnalyzer()
        t1 = datetime(2026, 3, 12, 15, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc)
        sa.update_history(_make_result(
            _make_obs("ST1", pressure=None, temp=70.0)
        ), t1)
        sa.update_history(_make_result(
            _make_obs("ST1", pressure=None, temp=65.0)
        ), t2)
        trends, _ = sa.compute_trends()
        assert trends[0].pressure_rate_inhg_hr is None
        assert trends[0].temp_rate_f_hr is not None

    def test_recent_pressure_change_15min(self):
        """Verify 15-min recent window picks correct readings."""
        sa = SurfaceAnalyzer()
        times = [
            datetime(2026, 3, 12, 15, 0, tzinfo=timezone.utc),   # -60 min
            datetime(2026, 3, 12, 15, 50, tzinfo=timezone.utc),  # -10 min (in 15-min window)
            datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc),   # now
        ]
        pressures = [30.00, 29.95, 29.90]
        for t, p in zip(times, pressures):
            sa.update_history(_make_result(_make_obs("ST1", pressure=p)), t)
        trends, _ = sa.compute_trends()
        # Recent change should be from 29.95 to 29.90 = -0.05
        assert abs(trends[0].recent_pressure_change - (-0.05)) < 0.001

    def test_multiple_targets_independent(self):
        sa = SurfaceAnalyzer()
        t1 = datetime(2026, 3, 12, 15, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 12, 16, 0, tzinfo=timezone.utc)
        sa.update_history(_make_result(_make_obs("LOCAL1", pressure=30.0)), t1, target='local')
        sa.update_history(_make_result(_make_obs("LOCAL1", pressure=29.9)), t2, target='local')
        sa.update_history(_make_result(_make_obs("MESO1", pressure=29.8)), t1, target='meso')
        sa.update_history(_make_result(_make_obs("MESO1", pressure=29.7)), t2, target='meso')

        local_trends, _ = sa.compute_trends(target='local')
        meso_trends, _ = sa.compute_trends(target='meso')

        assert len(local_trends) == 1
        assert local_trends[0].station_id == "LOCAL1"
        assert len(meso_trends) == 1
        assert meso_trends[0].station_id == "MESO1"

    def test_readings_count_and_timespan(self):
        sa = SurfaceAnalyzer()
        for i in range(4):
            t = datetime(2026, 3, 12, 15, i * 15, tzinfo=timezone.utc)
            sa.update_history(_make_result(_make_obs("ST1")), t)
        trends, _ = sa.compute_trends()
        assert trends[0].readings_count == 4
        assert abs(trends[0].time_span_min - 45.0) < 0.1
