"""Tests for radar threat detection data models and utility functions."""

import math
import pytest

from app.models.radar_threats import (
    haversine_km,
    calculate_bearing,
    bearing_to_cardinal,
    QLCSLine,
    ThreatCorridor,
    HailCell,
    StormRegime,
    RegimeParameters,
    REGIME_PARAMS,
    TrackedMesocyclone,
    CWOPReading,
    StationTrend,
    ThreatTrackerState,
    SurfaceAnalyzerState,
    RadarProcessingResult,
)
from datetime import datetime, timezone


# =============================================================================
# haversine_km
# =============================================================================

class TestHaversineKm:
    def test_same_point_returns_zero(self):
        assert haversine_km(35.0, -97.0, 35.0, -97.0) == 0.0

    def test_known_distance_okc_to_moore(self):
        """OKC (35.47, -97.52) to Moore (35.34, -97.49) is ~15 km."""
        dist = haversine_km(35.47, -97.52, 35.34, -97.49)
        assert 14.0 < dist < 16.0

    def test_known_distance_long(self):
        """NYC (40.71, -74.01) to LA (34.05, -118.24) is ~3940 km."""
        dist = haversine_km(40.71, -74.01, 34.05, -118.24)
        assert 3900 < dist < 4000

    def test_equator_one_degree_longitude(self):
        """1 degree of longitude at equator is ~111 km."""
        dist = haversine_km(0.0, 0.0, 0.0, 1.0)
        assert 110 < dist < 112

    def test_symmetry(self):
        d1 = haversine_km(35.0, -97.0, 40.0, -80.0)
        d2 = haversine_km(40.0, -80.0, 35.0, -97.0)
        assert abs(d1 - d2) < 0.001

    def test_antipodal(self):
        """Half circumference is ~20015 km."""
        dist = haversine_km(0.0, 0.0, 0.0, 180.0)
        assert 20000 < dist < 20100


# =============================================================================
# calculate_bearing
# =============================================================================

class TestCalculateBearing:
    def test_due_north(self):
        b = calculate_bearing(35.0, -97.0, 36.0, -97.0)
        assert abs(b - 0.0) < 1.0 or abs(b - 360.0) < 1.0

    def test_due_east(self):
        b = calculate_bearing(35.0, -97.0, 35.0, -96.0)
        assert 89.0 < b < 91.0

    def test_due_south(self):
        b = calculate_bearing(35.0, -97.0, 34.0, -97.0)
        assert 179.0 < b < 181.0

    def test_due_west(self):
        b = calculate_bearing(35.0, -97.0, 35.0, -98.0)
        assert 269.0 < b < 271.0

    def test_always_positive(self):
        b = calculate_bearing(35.0, -97.0, 34.0, -98.0)
        assert 0.0 <= b < 360.0


# =============================================================================
# bearing_to_cardinal
# =============================================================================

class TestBearingToCardinal:
    def test_north(self):
        assert bearing_to_cardinal(0.0) == "N"

    def test_east(self):
        assert bearing_to_cardinal(90.0) == "E"

    def test_south(self):
        assert bearing_to_cardinal(180.0) == "S"

    def test_west(self):
        assert bearing_to_cardinal(270.0) == "W"

    def test_northeast(self):
        assert bearing_to_cardinal(45.0) == "NE"

    def test_360_wraps_to_north(self):
        assert bearing_to_cardinal(360.0) == "N"

    @pytest.mark.parametrize("bearing,expected", [
        (0, "N"), (22.5, "NNE"), (45, "NE"), (67.5, "ENE"),
        (90, "E"), (112.5, "ESE"), (135, "SE"), (157.5, "SSE"),
        (180, "S"), (202.5, "SSW"), (225, "SW"), (247.5, "WSW"),
        (270, "W"), (292.5, "WNW"), (315, "NW"), (337.5, "NNW"),
    ])
    def test_all_16_directions(self, bearing, expected):
        assert bearing_to_cardinal(bearing) == expected


# =============================================================================
# StormRegime and REGIME_PARAMS
# =============================================================================

class TestStormRegime:
    def test_enum_values(self):
        assert StormRegime.UNKNOWN.value == "unknown"
        assert StormRegime.DISCRETE.value == "discrete"
        assert StormRegime.QLCS.value == "qlcs"
        assert StormRegime.OUTBREAK.value == "outbreak"

    def test_all_regimes_have_params(self):
        for regime in StormRegime:
            assert regime in REGIME_PARAMS

    def test_qlcs_wider_thresholds_than_discrete(self):
        qlcs = REGIME_PARAMS[StormRegime.QLCS]
        disc = REGIME_PARAMS[StormRegime.DISCRETE]
        assert qlcs.persistence_threshold_km > disc.persistence_threshold_km
        assert qlcs.speed_outlier_kmh > disc.speed_outlier_kmh
        assert qlcs.association_threshold_km > disc.association_threshold_km


# =============================================================================
# Dataclass instantiation and mutable defaults
# =============================================================================

class TestDataclasses:
    def test_threat_tracker_state_independent_lists(self):
        """Two ThreatTrackerState instances should not share mutable fields."""
        s1 = ThreatTrackerState()
        s2 = ThreatTrackerState()
        s1.tracked_mesocyclones.append("test")
        assert len(s2.tracked_mesocyclones) == 0

    def test_surface_analyzer_state_independent_dicts(self):
        s1 = SurfaceAnalyzerState()
        s2 = SurfaceAnalyzerState()
        s1.cwop_station_history["foo"] = []
        assert "foo" not in s2.cwop_station_history

    def test_qlcs_line_defaults(self):
        line = QLCSLine(
            leading_edge_points=[], centroid_lat=35.0, centroid_lon=-97.0,
            axis_bearing_deg=90.0, length_km=50.0,
            distance_to_station_km=10.0, approach_bearing_deg=270.0,
        )
        assert line.motion_speed_kmh is None
        assert line.eta_minutes is None

    def test_threat_corridor_defaults(self):
        tc = ThreatCorridor()
        assert tc.corridor_half_width_km == 15.0
        assert tc.rotation_count_30min == 0
        assert tc.has_active_rotation is False

    def test_hail_cell_creation(self):
        hc = HailCell(
            lat=35.0, lon=-97.0, distance_km=20.0, bearing_deg=180.0,
            vil_kg_m2=35.0, max_dbz=60.0, mesh_mm=25.0,
            hail_probability=0.85, hail_size_category="small (penny/quarter)",
            estimated_size_mm=25.0, column_height_45dbz_m=8000.0,
            echo_top_m=12000.0, overshoot_m=4000.0,
        )
        assert hc.mesh_mm == 25.0

    def test_cwop_reading_defaults(self):
        r = CWOPReading(timestamp=datetime.now(timezone.utc))
        assert r.pressure_inhg is None
        assert r.temp_f is None
        assert r.distance_miles == 0.0

    def test_tracked_mesocyclone_defaults(self):
        now = datetime.now(timezone.utc)
        m = TrackedMesocyclone(
            id="MESO-1", first_detected=now, last_seen=now, cycle_count=1,
            lat=35.0, lon=-97.0, distance_km=20.0, bearing_deg=270.0,
            shear=50.0, threat_score=0.8, elevation_angle=0.5,
        )
        assert m.prev_distance_km is None
        assert m.distance_history is None
        assert m.absorbed_ids is None
        assert m.status == "tracking"

    def test_station_trend_required_fields(self):
        t = StationTrend(
            station_id="CW1234",
            distance_miles=5.2,
            bearing_cardinal="NW",
            lat=35.0,
            lon=-97.0,
        )
        assert t.station_id == "CW1234"
        assert t.distance_miles == 5.2

    def test_station_trend_optional_defaults(self):
        t = StationTrend(
            station_id="X", distance_miles=1.0,
            bearing_cardinal="N", lat=35.0, lon=-97.0,
        )
        assert t.pressure_rate_inhg_hr is None
        assert t.temp_rate_f_hr is None
        assert t.wind_shift_deg is None
        assert t.latest_pressure is None
        assert t.latest_temp is None
        assert t.latest_wind_dir is None
        assert t.latest_wind_speed is None
        assert t.oldest_temp is None
        assert t.oldest_wind_dir is None
        assert t.readings_count == 0
        assert t.time_span_min == 0.0
        assert t.recent_pressure_change is None
        assert t.recent_temp_change is None

    def test_station_trend_with_rates(self):
        t = StationTrend(
            station_id="CW5678",
            distance_miles=10.0,
            bearing_cardinal="SW",
            lat=35.0, lon=-97.0,
            pressure_rate_inhg_hr=-0.08,
            temp_rate_f_hr=-12.0,
            wind_shift_deg=45.0,
            readings_count=4,
            time_span_min=60.0,
        )
        assert t.pressure_rate_inhg_hr == -0.08
        assert t.temp_rate_f_hr == -12.0
        assert t.wind_shift_deg == 45.0
        assert t.readings_count == 4

    def test_qlcs_line_defaults(self):
        line = QLCSLine(
            leading_edge_points=[], centroid_lat=35.0, centroid_lon=-97.0,
            axis_bearing_deg=90.0, length_km=50.0,
            distance_to_station_km=10.0, approach_bearing_deg=270.0,
        )
        assert line.motion_speed_kmh is None
        assert line.motion_bearing_deg is None
        assert line.eta_minutes is None
        assert line.centroid_history is None

    def test_threat_corridor_defaults(self):
        tc = ThreatCorridor()
        assert tc.corridor_half_width_km == 15.0
        assert tc.rotation_count_30min == 0
        assert tc.has_active_rotation is False
        assert tc.rotation_detections is None
        assert tc.nearest_rotation_km is None
        assert tc.nearest_rotation_age_min is None

    def test_mutable_default_independence_tracked_meso(self):
        """Two TrackedMesocyclone instances should not share mutable fields."""
        now = datetime.now(timezone.utc)
        m1 = TrackedMesocyclone(
            id="M1", first_detected=now, last_seen=now, cycle_count=1,
            lat=35.0, lon=-97.0, distance_km=20.0, bearing_deg=270.0,
            shear=50.0, threat_score=0.8, elevation_angle=0.5,
            position_history=[], distance_history=[], absorbed_ids=[],
        )
        m2 = TrackedMesocyclone(
            id="M2", first_detected=now, last_seen=now, cycle_count=1,
            lat=35.0, lon=-97.0, distance_km=20.0, bearing_deg=270.0,
            shear=50.0, threat_score=0.8, elevation_angle=0.5,
            position_history=[], distance_history=[], absorbed_ids=[],
        )
        m1.position_history.append((35.0, -97.0))
        m1.distance_history.append(20.0)
        m1.absorbed_ids.append("OLD-1")
        assert len(m2.position_history) == 0
        assert len(m2.distance_history) == 0
        assert len(m2.absorbed_ids) == 0

    def test_mutable_default_independence_rotation_history(self):
        """Two ThreatTrackerState instances should not share rotation_history."""
        s1 = ThreatTrackerState()
        s2 = ThreatTrackerState()
        s1.rotation_history.append(("test",))
        assert len(s2.rotation_history) == 0

    def test_radar_processing_result(self):
        r = RadarProcessingResult(
            all_detections=[], strong_detections=[], moderate_detections=[],
            hail_cells=None, qlcs_line=None, primary_detection=None,
            radar_timestamp=None, radar_site="KTLX",
        )
        assert r.radar_station_dist_km == 0.0
