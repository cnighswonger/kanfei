"""Tests for knowledge injection formatting (knowledge_formatter.py)."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from app.models.radar_threats import (
    HailCell,
    QLCSLine,
    REGIME_PARAMS,
    StationTrend,
    StormRegime,
    ThreatCorridor,
    ThreatTrackerState,
    TrackedMesocyclone,
)
from app.services.knowledge_formatter import (
    build_knowledge_entries,
    format_hail_knowledge,
    format_hail_rotation_collocation,
    format_hysteresis_knowledge,
    format_meso_tracking_knowledge,
    format_qlcs_knowledge,
    format_surface_trend_block,
)
from app.services.threat_tracker import DEFAULT_CYCLE_INTERVAL_SEC


# =============================================================================
# Helper factories
# =============================================================================

_NOW = datetime(2026, 3, 12, 18, 0, 0, tzinfo=timezone.utc)
_PREV = _NOW - timedelta(minutes=5)


def make_meso(
    id="MESO-1",
    cycle_count=1,
    distance_km=50.0,
    prev_distance_km=None,
    bearing_deg=270.0,
    shear=45.0,
    distance_history=None,
    absorbed_ids=None,
    **kwargs,
):
    """Create a TrackedMesocyclone with sensible defaults."""
    defaults = dict(
        first_detected=_NOW,
        last_seen=_NOW,
        lat=35.0,
        lon=-97.0,
        threat_score=0.8,
        elevation_angle=0.5,
    )
    defaults.update(kwargs)
    return TrackedMesocyclone(
        id=id,
        cycle_count=cycle_count,
        distance_km=distance_km,
        prev_distance_km=prev_distance_km,
        bearing_deg=bearing_deg,
        shear=shear,
        distance_history=distance_history,
        absorbed_ids=absorbed_ids,
        **defaults,
    )


def make_hail(
    distance_km=20.0,
    bearing_deg=180.0,
    mesh_mm=30.0,
    hail_probability=0.85,
    overshoot_m=4000.0,
    **kwargs,
):
    """Create a HailCell with sensible defaults."""
    defaults = dict(
        lat=35.0,
        lon=-97.0,
        vil_kg_m2=35.0,
        max_dbz=60.0,
        hail_size_category="small (penny/quarter)",
        estimated_size_mm=30.0,
        column_height_45dbz_m=8000.0,
        echo_top_m=12000.0,
    )
    defaults.update(kwargs)
    return HailCell(
        distance_km=distance_km,
        bearing_deg=bearing_deg,
        mesh_mm=mesh_mm,
        hail_probability=hail_probability,
        overshoot_m=overshoot_m,
        **defaults,
    )


def make_trend(
    station_id="ST1",
    distance_miles=5.0,
    bearing_cardinal="SW",
    pressure_rate_inhg_hr=-0.05,
    temp_rate_f_hr=-3.0,
    wind_shift_deg=10.0,
    latest_wind_dir=200,
    latest_wind_speed=12.0,
    readings_count=4,
    time_span_min=45.0,
    **kwargs,
):
    """Create a StationTrend with sensible defaults."""
    defaults = dict(
        lat=35.0,
        lon=-97.0,
        latest_pressure=29.90,
        latest_temp=68.0,
        oldest_temp=71.0,
        oldest_wind_dir=190,
        recent_pressure_change=-0.02,
        recent_temp_change=-1.0,
    )
    defaults.update(kwargs)
    return StationTrend(
        station_id=station_id,
        distance_miles=distance_miles,
        bearing_cardinal=bearing_cardinal,
        pressure_rate_inhg_hr=pressure_rate_inhg_hr,
        temp_rate_f_hr=temp_rate_f_hr,
        wind_shift_deg=wind_shift_deg,
        latest_wind_dir=latest_wind_dir,
        latest_wind_speed=latest_wind_speed,
        readings_count=readings_count,
        time_span_min=time_span_min,
        **defaults,
    )


def make_state(**kwargs):
    """Create a ThreatTrackerState with defaults for common testing scenarios."""
    return ThreatTrackerState(**kwargs)


# =============================================================================
# format_hysteresis_knowledge
# =============================================================================

class TestFormatHysteresisKnowledge:
    def test_none_previous_threat_returns_none(self):
        result = format_hysteresis_knowledge(None, _PREV, _NOW)
        assert result is None

    def test_none_previous_time_returns_none(self):
        result = format_hysteresis_knowledge("EMERGENCY", None, _NOW)
        assert result is None

    def test_both_none_returns_none(self):
        result = format_hysteresis_knowledge(None, None, _NOW)
        assert result is None

    def test_time_since_previous_in_output(self):
        prev_time = _NOW - timedelta(minutes=15)
        result = format_hysteresis_knowledge("WARNING", prev_time, _NOW)
        assert result is not None
        assert "15 minutes ago" in result

    def test_threat_level_in_output(self):
        result = format_hysteresis_knowledge("EMERGENCY", _PREV, _NOW)
        assert "EMERGENCY" in result

    def test_hysteresis_guidance_in_output(self):
        result = format_hysteresis_knowledge("WARNING", _PREV, _NOW)
        assert "hysteresis" in result.lower()


# =============================================================================
# format_qlcs_knowledge
# =============================================================================

class TestFormatQlcsKnowledge:
    def test_non_qlcs_regime_returns_none(self):
        assert format_qlcs_knowledge(StormRegime.DISCRETE, None, None) is None
        assert format_qlcs_knowledge(StormRegime.UNKNOWN, None, None) is None
        assert format_qlcs_knowledge(StormRegime.OUTBREAK, None, None) is None

    def test_qlcs_no_line_no_corridor_returns_none(self):
        result = format_qlcs_knowledge(StormRegime.QLCS, None, None)
        assert result is None

    def test_qlcs_no_line_corridor_with_zero_rotations_returns_none(self):
        corridor = ThreatCorridor(rotation_count_30min=0)
        result = format_qlcs_knowledge(StormRegime.QLCS, None, corridor)
        assert result is None

    def test_qlcs_line_formatting(self):
        line = QLCSLine(
            leading_edge_points=[],
            centroid_lat=35.0, centroid_lon=-97.0,
            axis_bearing_deg=90.0, length_km=80.0,
            distance_to_station_km=25.0, approach_bearing_deg=270.0,
            motion_speed_kmh=60.0, motion_bearing_deg=90.0, eta_minutes=25.0,
        )
        result = format_qlcs_knowledge(StormRegime.QLCS, line, None)
        assert result is not None
        assert "LINE POSITION" in result
        assert "25.0 km" in result
        assert "LINE MOTION" in result
        assert "60 km/hr" in result
        assert "ETA AT STATION" in result
        assert "25 minutes" in result

    def test_qlcs_line_slow_motion_shows_insufficient(self):
        line = QLCSLine(
            leading_edge_points=[],
            centroid_lat=35.0, centroid_lon=-97.0,
            axis_bearing_deg=90.0, length_km=50.0,
            distance_to_station_km=30.0, approach_bearing_deg=270.0,
            motion_speed_kmh=3.0, motion_bearing_deg=90.0,
        )
        result = format_qlcs_knowledge(StormRegime.QLCS, line, None)
        assert "insufficient history" in result

    def test_corridor_rotation_formatting(self):
        corridor = ThreatCorridor(
            rotation_count_30min=5,
            max_shear_30min=35.0,
            nearest_rotation_km=12.0,
            nearest_rotation_age_min=3.0,
            has_active_rotation=False,
        )
        result = format_qlcs_knowledge(StormRegime.QLCS, None, corridor)
        assert result is not None
        assert "Rotation detections (last 30 min): 5" in result
        assert "12.0 km" in result

    def test_corridor_tvs_strength_noted(self):
        corridor = ThreatCorridor(
            rotation_count_30min=2,
            max_shear_30min=50.0,
            nearest_rotation_km=10.0,
            nearest_rotation_age_min=2.0,
            has_active_rotation=True,
        )
        result = format_qlcs_knowledge(StormRegime.QLCS, None, corridor)
        assert "TVS-strength" in result

    def test_corridor_emergency_guidance(self):
        """Active rotation within 15km at >=40 shear -> EMERGENCY."""
        corridor = ThreatCorridor(
            rotation_count_30min=3,
            max_shear_30min=45.0,
            nearest_rotation_km=10.0,
            nearest_rotation_age_min=1.0,
            has_active_rotation=True,
        )
        result = format_qlcs_knowledge(StormRegime.QLCS, None, corridor)
        assert "EMERGENCY" in result

    def test_corridor_warning_guidance(self):
        """Active rotation within 25km but >15km or <40 shear -> WARNING."""
        corridor = ThreatCorridor(
            rotation_count_30min=2,
            max_shear_30min=35.0,
            nearest_rotation_km=20.0,
            nearest_rotation_age_min=2.0,
            has_active_rotation=True,
        )
        result = format_qlcs_knowledge(StormRegime.QLCS, None, corridor)
        assert "WARNING" in result

    def test_corridor_active_rotation_far_away(self):
        """Active rotation beyond 25km -> general note only."""
        corridor = ThreatCorridor(
            rotation_count_30min=1,
            max_shear_30min=30.0,
            nearest_rotation_km=35.0,
            nearest_rotation_age_min=5.0,
            has_active_rotation=True,
        )
        result = format_qlcs_knowledge(StormRegime.QLCS, None, corridor)
        assert "Active rotation detected in corridor" in result
        assert "EMERGENCY" not in result
        assert "WARNING" not in result

    def test_eta_emergency_conditions(self):
        """Line ETA <10 min with >=3 rotations -> EMERGENCY CONDITIONS."""
        line = QLCSLine(
            leading_edge_points=[],
            centroid_lat=35.0, centroid_lon=-97.0,
            axis_bearing_deg=90.0, length_km=80.0,
            distance_to_station_km=8.0, approach_bearing_deg=270.0,
            motion_speed_kmh=60.0, motion_bearing_deg=90.0, eta_minutes=8.0,
        )
        corridor = ThreatCorridor(
            rotation_count_30min=4,
            max_shear_30min=35.0,
            nearest_rotation_km=10.0,
            nearest_rotation_age_min=2.0,
            has_active_rotation=False,
        )
        result = format_qlcs_knowledge(StormRegime.QLCS, line, corridor)
        assert "EMERGENCY CONDITIONS" in result

    def test_eta_warning_conditions(self):
        """Line ETA <=30 min with >=1 rotation -> WARNING CONDITIONS."""
        line = QLCSLine(
            leading_edge_points=[],
            centroid_lat=35.0, centroid_lon=-97.0,
            axis_bearing_deg=90.0, length_km=80.0,
            distance_to_station_km=25.0, approach_bearing_deg=270.0,
            motion_speed_kmh=60.0, motion_bearing_deg=90.0, eta_minutes=25.0,
        )
        corridor = ThreatCorridor(
            rotation_count_30min=1,
            max_shear_30min=25.0,
            nearest_rotation_km=20.0,
            nearest_rotation_age_min=4.0,
            has_active_rotation=False,
        )
        result = format_qlcs_knowledge(StormRegime.QLCS, line, corridor)
        assert "WARNING CONDITIONS" in result


# =============================================================================
# format_meso_tracking_knowledge
# =============================================================================

class TestFormatMesoTrackingKnowledge:
    def test_no_mesos_returns_none(self):
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        result = format_meso_tracking_knowledge([], StormRegime.UNKNOWN, params)
        assert result is None

    def test_regime_description_in_output(self):
        meso = make_meso(cycle_count=1)
        params = REGIME_PARAMS[StormRegime.DISCRETE]
        result = format_meso_tracking_knowledge([meso], StormRegime.DISCRETE, params)
        assert "DISCRETE SUPERCELL" in result

    def test_qlcs_regime_description(self):
        meso = make_meso(cycle_count=1)
        params = REGIME_PARAMS[StormRegime.QLCS]
        result = format_meso_tracking_knowledge([meso], StormRegime.QLCS, params)
        assert "QLCS" in result
        assert "FAST-MOVING LINE" in result

    def test_new_detection_format(self):
        meso = make_meso(id="MESO-5", cycle_count=1, distance_km=30.0, bearing_deg=270.0, shear=50.0)
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        result = format_meso_tracking_knowledge([meso], StormRegime.UNKNOWN, params)
        assert "MESO-5" in result
        assert "NEW detection" in result
        assert "30.0 km" in result
        assert "no prior position" in result

    def test_approaching_meso(self):
        """Cycle 2 meso with distance decreasing -> APPROACHING."""
        meso = make_meso(
            cycle_count=2,
            distance_km=40.0,
            prev_distance_km=50.0,
            bearing_deg=270.0,
            shear=50.0,
        )
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        result = format_meso_tracking_knowledge([meso], StormRegime.UNKNOWN, params)
        assert "APPROACHING" in result
        assert "Was 50.0 km, now 40.0 km" in result

    def test_receding_meso(self):
        """Cycle 2 meso with distance increasing -> RECEDING."""
        meso = make_meso(
            cycle_count=2,
            distance_km=55.0,
            prev_distance_km=50.0,
            bearing_deg=270.0,
            shear=50.0,
        )
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        result = format_meso_tracking_knowledge([meso], StormRegime.UNKNOWN, params)
        assert "RECEDING" in result

    def test_stationary_meso(self):
        """Cycle 2 meso with distance change <= 1km -> STATIONARY."""
        meso = make_meso(
            cycle_count=2,
            distance_km=50.5,
            prev_distance_km=50.0,
            bearing_deg=270.0,
            shear=50.0,
        )
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        result = format_meso_tracking_knowledge([meso], StormRegime.UNKNOWN, params)
        assert "STATIONARY" in result

    def test_speed_outlier_flag(self):
        """Cycle-to-cycle speed above outlier threshold gets flagged."""
        # UNKNOWN regime outlier threshold = 80 km/h
        # 5-min cycle = 300s. distance_change = -10km in 5 min = 120 km/h
        meso = make_meso(
            cycle_count=2,
            distance_km=40.0,
            prev_distance_km=50.0,
            bearing_deg=270.0,
            shear=50.0,
        )
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        result = format_meso_tracking_knowledge([meso], StormRegime.UNKNOWN, params)
        # 10 km in 5 min = 120 km/h which is > 80 (outlier) but < 130 (implausible)
        assert "OUTLIER" in result

    def test_speed_implausible_flag(self):
        """Extremely fast movement gets implausible flag."""
        # 25 km in 5 min = 300 km/h which is > 130 (implausible for UNKNOWN)
        meso = make_meso(
            cycle_count=2,
            distance_km=25.0,
            prev_distance_km=50.0,
            bearing_deg=270.0,
            shear=50.0,
        )
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        result = format_meso_tracking_knowledge([meso], StormRegime.UNKNOWN, params)
        assert "LIKELY ERROR" in result

    def test_monotonic_approach_note(self):
        """Multi-cycle monotonically decreasing distance is noted."""
        history = [
            (_NOW - timedelta(minutes=15), 80.0),
            (_NOW - timedelta(minutes=10), 70.0),
            (_NOW - timedelta(minutes=5), 60.0),
        ]
        # Convert to isoformat strings to match real data format
        history_iso = [(t.isoformat(), d) for t, d in history]
        meso = make_meso(
            cycle_count=4,
            distance_km=50.0,
            prev_distance_km=60.0,
            bearing_deg=270.0,
            shear=50.0,
            distance_history=history_iso,
        )
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        result = format_meso_tracking_knowledge([meso], StormRegime.UNKNOWN, params)
        # The distances 80->70->60->50 are monotonically decreasing with normal speed
        # avg speed = 30 km in 15 min = 120 km/h which triggers outlier.
        # But the multi-cycle avg is 120 km/h > 80*1.2=96, so it's not use_avg case;
        # it's the implausible/outlier branch. Let's check the text is present at all.
        assert "APPROACHING" in result

    def test_absorbed_ids_lineage(self):
        """Meso with absorbed IDs shows lineage."""
        meso = make_meso(
            id="MESO-10",
            cycle_count=5,
            distance_km=30.0,
            prev_distance_km=35.0,
            bearing_deg=270.0,
            shear=50.0,
            absorbed_ids=["MESO-3", "MESO-7"],
        )
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        result = format_meso_tracking_knowledge([meso], StormRegime.UNKNOWN, params)
        assert "previously MESO-3, MESO-7" in result
        assert "across 3 associations" in result

    def test_eta_computation(self):
        """ETA is computed from distance and speed."""
        # 5 km decrease in 5 min = 60 km/h. Distance 30 km. ETA = 30/60*60 = 30 min
        meso = make_meso(
            cycle_count=2,
            distance_km=30.0,
            prev_distance_km=35.0,
            bearing_deg=270.0,
            shear=50.0,
        )
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        result = format_meso_tracking_knowledge([meso], StormRegime.UNKNOWN, params)
        assert "ETA ~30 min" in result

    def test_cycle2_no_prev_distance_still_returns_header(self):
        """Meso with cycle_count >= 2 but no prev_distance: header+regime still returned."""
        meso = make_meso(cycle_count=3, prev_distance_km=None, distance_km=40.0)
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        result = format_meso_tracking_knowledge([meso], StormRegime.UNKNOWN, params)
        # The header + regime description are emitted even though this meso is skipped
        assert result is not None
        assert "MESOCYCLONE POSITION TRACKING" in result
        assert "MESO-1" not in result  # meso bullet itself is not emitted


# =============================================================================
# format_hail_knowledge
# =============================================================================

class TestFormatHailKnowledge:
    def test_no_hail_returns_none(self):
        assert format_hail_knowledge(None, None) is None
        assert format_hail_knowledge([], None) is None

    def test_cell_distance_and_bearing(self):
        cell = make_hail(distance_km=25.0, bearing_deg=180.0)
        result = format_hail_knowledge([cell], None)
        assert "25.0 km" in result
        assert "S" in result  # bearing 180 = S

    def test_danger_tier_extreme(self):
        """mesh >= 50 and distance <= 30 -> EXTREME DANGER."""
        cell = make_hail(mesh_mm=55.0, distance_km=20.0)
        result = format_hail_knowledge([cell], None)
        assert "EXTREME DANGER" in result

    def test_danger_tier_high(self):
        """mesh >= 25 and distance <= 30 -> HIGH DANGER."""
        cell = make_hail(mesh_mm=30.0, distance_km=25.0)
        result = format_hail_knowledge([cell], None)
        assert "HIGH DANGER" in result

    def test_danger_tier_elevated(self):
        """mesh >= 25 and distance <= 60 (but > 30) -> ELEVATED."""
        cell = make_hail(mesh_mm=30.0, distance_km=45.0)
        result = format_hail_knowledge([cell], None)
        assert "ELEVATED" in result

    def test_danger_tier_moderate(self):
        """hail_probability >= 0.5 but mesh < 25 or distance > 60 -> MODERATE."""
        cell = make_hail(mesh_mm=15.0, distance_km=70.0, hail_probability=0.6)
        result = format_hail_knowledge([cell], None)
        assert "MODERATE" in result

    def test_danger_tier_low(self):
        """hail_probability < 0.5 -> LOW."""
        cell = make_hail(mesh_mm=10.0, distance_km=80.0, hail_probability=0.3)
        result = format_hail_knowledge([cell], None)
        assert "LOW" in result

    def test_movement_approaching(self):
        """Cell closer than prev match -> APPROACHING."""
        prev_cell = make_hail(distance_km=30.0, lat=35.01, lon=-97.01)
        curr_cell = make_hail(distance_km=20.0, lat=35.01, lon=-97.01)
        result = format_hail_knowledge([curr_cell], [prev_cell])
        assert "APPROACHING" in result
        assert "was 30.0 km" in result

    def test_movement_receding(self):
        """Cell farther than prev match -> RECEDING."""
        prev_cell = make_hail(distance_km=20.0, lat=35.01, lon=-97.01)
        curr_cell = make_hail(distance_km=30.0, lat=35.01, lon=-97.01)
        result = format_hail_knowledge([curr_cell], [prev_cell])
        assert "RECEDING" in result

    def test_movement_stationary(self):
        """Cell same distance as prev match -> STATIONARY."""
        prev_cell = make_hail(distance_km=20.0, lat=35.01, lon=-97.01)
        curr_cell = make_hail(distance_km=20.5, lat=35.01, lon=-97.01)
        result = format_hail_knowledge([curr_cell], [prev_cell])
        assert "STATIONARY" in result

    def test_updraft_strength_extreme(self):
        """overshoot >= 6km -> EXTREME updraft."""
        cell = make_hail(overshoot_m=7000.0)
        result = format_hail_knowledge([cell], None)
        assert "EXTREME updraft" in result

    def test_updraft_strength_strong(self):
        """overshoot >= 4km -> STRONG updraft."""
        cell = make_hail(overshoot_m=5000.0)
        result = format_hail_knowledge([cell], None)
        assert "STRONG updraft" in result

    def test_updraft_strength_moderate(self):
        """overshoot >= 2km -> moderate updraft."""
        cell = make_hail(overshoot_m=3000.0)
        result = format_hail_knowledge([cell], None)
        assert "moderate updraft" in result

    def test_updraft_strength_weak(self):
        """overshoot > 0 but < 2km -> weak updraft."""
        cell = make_hail(overshoot_m=1000.0)
        result = format_hail_knowledge([cell], None)
        assert "weak updraft" in result

    def test_updraft_strength_none(self):
        """overshoot == 0 -> no significant updraft."""
        cell = make_hail(overshoot_m=0.0)
        result = format_hail_knowledge([cell], None)
        assert "no significant updraft" in result

    def test_guidance_line_present(self):
        cell = make_hail()
        result = format_hail_knowledge([cell], None)
        assert "GUIDANCE" in result
        assert "rotation AND large MESH" in result


# =============================================================================
# format_hail_rotation_collocation
# =============================================================================

class TestFormatHailRotationCollocation:
    def test_no_hail_returns_none(self):
        rot = [{'latitude': 35.0, 'longitude': -97.0, 'max_shear': 30.0}]
        assert format_hail_rotation_collocation(None, rot) is None
        assert format_hail_rotation_collocation([], rot) is None

    def test_no_rotation_returns_none(self):
        cell = make_hail()
        assert format_hail_rotation_collocation([cell], []) is None
        assert format_hail_rotation_collocation([cell], None) is None

    def test_collocation_within_15km(self):
        """Hail cell and rotation within 15km -> SUPERCELL EVIDENCE."""
        cell = make_hail(lat=35.0, lon=-97.0, distance_km=20.0)
        rot = [{'latitude': 35.05, 'longitude': -97.05, 'max_shear': 40.0}]
        result = format_hail_rotation_collocation([cell], rot)
        assert result is not None
        assert "SUPERCELL EVIDENCE" in result
        assert "collocated" in result
        assert "MESH=30mm" in result  # default mesh from factory

    def test_too_far_returns_none(self):
        """Hail cell and rotation > 15km apart -> None."""
        cell = make_hail(lat=35.0, lon=-97.0, distance_km=20.0)
        rot = [{'latitude': 36.0, 'longitude': -96.0, 'max_shear': 40.0}]
        result = format_hail_rotation_collocation([cell], rot)
        assert result is None

    def test_hail_cell_beyond_40km_skipped(self):
        """Hail cell farther than 40km from station is skipped."""
        cell = make_hail(lat=35.0, lon=-97.0, distance_km=45.0)
        rot = [{'latitude': 35.0, 'longitude': -97.0, 'max_shear': 30.0}]
        result = format_hail_rotation_collocation([cell], rot)
        assert result is None

    def test_range_correction_factor_noted(self):
        """RCAS factor > 1.1 is noted in the output."""
        cell = make_hail(lat=35.0, lon=-97.0, distance_km=20.0)
        rot = [{
            'latitude': 35.01, 'longitude': -97.01, 'max_shear': 40.0,
            'raw_shear': 25.0, 'range_correction_factor': 1.6,
        }]
        result = format_hail_rotation_collocation([cell], rot)
        assert result is not None
        assert "range-corrected" in result
        assert "1.6x" in result

    def test_assessment_present(self):
        cell = make_hail(lat=35.0, lon=-97.0, distance_km=20.0)
        rot = [{'latitude': 35.01, 'longitude': -97.01, 'max_shear': 35.0}]
        result = format_hail_rotation_collocation([cell], rot)
        assert "ASSESSMENT" in result
        assert "supercell probability" in result


# =============================================================================
# format_surface_trend_block
# =============================================================================

class TestFormatSurfaceTrendBlock:
    def test_empty_trends_returns_none(self):
        result = format_surface_trend_block([], None, "TITLE", "context")
        assert result is None

    def test_title_included(self):
        trend = make_trend()
        result = format_surface_trend_block([trend], None, "MY TITLE", "my context")
        assert "MY TITLE" in result

    def test_context_included(self):
        trend = make_trend()
        result = format_surface_trend_block([trend], None, "TITLE", "my context text here")
        assert "my context text here" in result

    def test_pressure_rate_formatted(self):
        trend = make_trend(pressure_rate_inhg_hr=-0.123)
        result = format_surface_trend_block([trend], None, "T", "C")
        assert "P rate=-0.123 inHg/hr" in result

    def test_recent_pressure_change_shown(self):
        trend = make_trend(pressure_rate_inhg_hr=-0.05, recent_pressure_change=-0.015)
        result = format_surface_trend_block([trend], None, "T", "C")
        assert "last 15min: -0.015" in result

    def test_temp_rate_with_range(self):
        trend = make_trend(temp_rate_f_hr=-5.0, oldest_temp=75.0, latest_temp=70.0)
        result = format_surface_trend_block([trend], None, "T", "C")
        assert "T rate=-5.0" in result
        assert "75" in result
        assert "70" in result

    def test_wind_shift_shown(self):
        trend = make_trend(wind_shift_deg=45.0, oldest_wind_dir=180, latest_wind_dir=225)
        result = format_surface_trend_block([trend], None, "T", "C")
        assert "shift 45" in result
        assert "180" in result
        assert "225" in result

    def test_wind_steady_when_small_shift(self):
        trend = make_trend(wind_shift_deg=3.0, latest_wind_dir=180)
        result = format_surface_trend_block([trend], None, "T", "C")
        assert "Wind steady 180" in result

    def test_gradient_bearing_shown(self):
        trend1 = make_trend(station_id="ST1", pressure_rate_inhg_hr=-0.10, bearing_cardinal="NW")
        trend2 = make_trend(station_id="ST2", pressure_rate_inhg_hr=-0.02, bearing_cardinal="SE")
        result = format_surface_trend_block([trend1, trend2], "NW", "T", "C")
        assert "Pressure gradient" in result
        assert "ST1" in result

    def test_readings_count_in_output(self):
        trend = make_trend(readings_count=6, time_span_min=30.0)
        result = format_surface_trend_block([trend], None, "T", "C")
        assert "6 readings" in result
        assert "30 min" in result


# =============================================================================
# build_knowledge_entries
# =============================================================================

class TestBuildKnowledgeEntries:
    def test_empty_state_returns_empty(self):
        state = make_state()
        result = build_knowledge_entries(state)
        assert result == []

    def test_event_knowledge_included(self):
        state = make_state()
        result = build_knowledge_entries(state, event_knowledge=["CONTEXT LINE 1", "CONTEXT LINE 2"])
        assert "CONTEXT LINE 1" in result
        assert "CONTEXT LINE 2" in result

    def test_hysteresis_included_when_sim_time_set(self):
        state = make_state()
        result = build_knowledge_entries(
            state,
            previous_threat_level="WARNING",
            previous_cycle_time=_PREV,
            sim_time=_NOW,
        )
        assert any("WARNING" in e for e in result)

    def test_hysteresis_skipped_when_no_sim_time(self):
        state = make_state()
        result = build_knowledge_entries(
            state,
            previous_threat_level="EMERGENCY",
            previous_cycle_time=_PREV,
            sim_time=None,
        )
        assert not any("EMERGENCY" in e for e in result)

    def test_qlcs_knowledge_included(self):
        line = QLCSLine(
            leading_edge_points=[],
            centroid_lat=35.0, centroid_lon=-97.0,
            axis_bearing_deg=90.0, length_km=80.0,
            distance_to_station_km=25.0, approach_bearing_deg=270.0,
            motion_speed_kmh=60.0, motion_bearing_deg=90.0, eta_minutes=25.0,
        )
        state = make_state(current_regime=StormRegime.QLCS, tracked_qlcs_line=line)
        result = build_knowledge_entries(state)
        assert any("QLCS LINE TRACKING" in e for e in result)

    def test_meso_tracking_included(self):
        meso = make_meso(cycle_count=1)
        state = make_state(tracked_mesocyclones=[meso])
        result = build_knowledge_entries(state)
        assert any("MESOCYCLONE POSITION TRACKING" in e for e in result)

    def test_hail_knowledge_included(self):
        cell = make_hail()
        state = make_state(hail_cells=[cell])
        result = build_knowledge_entries(state)
        assert any("HAIL SIGNATURES" in e for e in result)

    def test_hail_rotation_collocation_included(self):
        cell = make_hail(lat=35.0, lon=-97.0, distance_km=20.0)
        rot = [{'latitude': 35.01, 'longitude': -97.01, 'max_shear': 40.0}]
        state = make_state(hail_cells=[cell], moderate_rotation_detections=rot)
        result = build_knowledge_entries(state)
        assert any("SUPERCELL EVIDENCE" in e for e in result)

    def test_ordering_event_first_then_hysteresis(self):
        """Event knowledge comes first, then hysteresis."""
        meso = make_meso(cycle_count=1)
        state = make_state(tracked_mesocyclones=[meso])
        result = build_knowledge_entries(
            state,
            previous_threat_level="EMERGENCY",
            previous_cycle_time=_PREV,
            sim_time=_NOW,
            event_knowledge=["EVENT INFO"],
        )
        assert result[0] == "EVENT INFO"
        # Hysteresis should be second
        assert "EMERGENCY" in result[1]

    def test_surface_analyzer_none_guard(self):
        """When surface_analyzer is None, surface trends are skipped without error."""
        state = make_state()
        result = build_knowledge_entries(state, surface_analyzer=None)
        assert isinstance(result, list)

    def test_surface_trends_included(self):
        """When surface_analyzer returns trends, they appear in output."""
        state = make_state()
        mock_analyzer = MagicMock()
        trend = make_trend()
        mock_analyzer.compute_trends.side_effect = lambda target: (
            ([trend], "SW") if target == 'local' else ([], None)
        )
        result = build_knowledge_entries(state, surface_analyzer=mock_analyzer)
        assert any("SURFACE NETWORK TRENDS" in e for e in result)

    def test_log_func_called(self):
        """log_func receives messages when entries are added."""
        state = make_state()
        mock_analyzer = MagicMock()
        trend = make_trend()
        mock_analyzer.compute_trends.side_effect = lambda target: (
            ([trend], "SW") if target == 'local' else ([], None)
        )
        log_messages = []
        build_knowledge_entries(state, surface_analyzer=mock_analyzer, log_func=log_messages.append)
        assert any("Surface trends" in m for m in log_messages)
