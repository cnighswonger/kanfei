"""Tests for persistent multi-cycle threat tracking system."""

import math
from datetime import datetime, timedelta, timezone

import pytest

from app.models.radar_threats import (
    HailCell,
    QLCSLine,
    RadarProcessingResult,
    REGIME_PARAMS,
    RegimeParameters,
    StormRegime,
    ThreatCorridor,
    ThreatTrackerState,
    TrackedMesocyclone,
    haversine_km,
)
from app.services.threat_tracker import DEFAULT_CYCLE_INTERVAL_SEC, ThreatTracker


# =============================================================================
# HELPER FACTORIES
# =============================================================================

T0 = datetime(2026, 3, 12, 18, 0, 0, tzinfo=timezone.utc)


def _make_detection(
    lat=35.0,
    lon=-97.0,
    shear=50.0,
    dist_km=30.0,
    threat_score=0.8,
    elevation_angle=0.5,
    range_km=40.0,
    azimuth_deg=270.0,
):
    """Create a detection dict matching the format expected by ThreatTracker."""
    return {
        "latitude": lat,
        "longitude": lon,
        "max_shear": shear,
        "distance_to_station_km": dist_km,
        "threat_score": threat_score,
        "elevation_angle": elevation_angle,
        "range_km": range_km,
        "azimuth_deg": azimuth_deg,
    }


def _make_radar_result(
    strong=None,
    moderate=None,
    all_dets=None,
    hail_cells=None,
    qlcs_line=None,
):
    """Create a RadarProcessingResult with sensible defaults."""
    strong = strong or []
    moderate = moderate or []
    if all_dets is None:
        all_dets = strong + moderate
    return RadarProcessingResult(
        all_detections=all_dets,
        strong_detections=strong,
        moderate_detections=moderate,
        hail_cells=hail_cells,
        qlcs_line=qlcs_line,
        primary_detection=strong[0] if strong else None,
        radar_timestamp=T0,
        radar_site="KTLX",
    )


def _make_tracker(
    station_lat=35.2,
    station_lon=-97.4,
    state=None,
    log_func=None,
):
    """Create a ThreatTracker with optional pre-seeded state."""
    return ThreatTracker(
        station_lat=station_lat,
        station_lon=station_lon,
        state=state,
        log_func=log_func,
    )


def _make_tracked_meso(
    id="MESO-1",
    lat=35.0,
    lon=-97.0,
    distance_km=30.0,
    shear=50.0,
    threat_score=0.8,
    cycle_count=3,
    last_seen=None,
    first_detected=None,
    position_history=None,
    distance_history=None,
    motion_speed_kmh=None,
    motion_bearing_deg=None,
    status="tracking",
    absorbed_ids=None,
):
    """Create a TrackedMesocyclone for pre-seeding tracker state."""
    last_seen = last_seen or T0
    first_detected = first_detected or T0 - timedelta(minutes=15)
    return TrackedMesocyclone(
        id=id,
        first_detected=first_detected,
        last_seen=last_seen,
        cycle_count=cycle_count,
        lat=lat,
        lon=lon,
        distance_km=distance_km,
        bearing_deg=270.0,
        shear=shear,
        threat_score=threat_score,
        elevation_angle=0.5,
        status=status,
        position_history=position_history,
        distance_history=distance_history,
        motion_speed_kmh=motion_speed_kmh,
        motion_bearing_deg=motion_bearing_deg,
        absorbed_ids=absorbed_ids,
    )


def _seeded_state(**overrides):
    """Create a ThreatTrackerState with keyword overrides applied."""
    state = ThreatTrackerState()
    for k, v in overrides.items():
        setattr(state, k, v)
    return state


# =============================================================================
# ThreatTracker.__init__
# =============================================================================

class TestThreatTrackerInit:
    def test_default_state(self):
        tt = _make_tracker()
        assert isinstance(tt.state, ThreatTrackerState)
        assert tt.state.cycle_count == 0
        assert tt.state.tracked_mesocyclones == []
        assert tt.state.next_meso_id == 1
        assert tt.state.current_regime == StormRegime.UNKNOWN

    def test_custom_state_preserved(self):
        state = _seeded_state(cycle_count=5, next_meso_id=3)
        tt = _make_tracker(state=state)
        assert tt.state.cycle_count == 5
        assert tt.state.next_meso_id == 3

    def test_station_location_stored(self):
        tt = _make_tracker(station_lat=34.5, station_lon=-98.0)
        assert tt._station_lat == 34.5
        assert tt._station_lon == -98.0

    def test_log_func_default_noop(self):
        tt = _make_tracker()
        # Should not raise
        tt._log("test message")

    def test_log_func_custom(self):
        messages = []
        tt = _make_tracker(log_func=messages.append)
        tt._log("hello")
        assert messages == ["hello"]


# =============================================================================
# _classify_storm_regime
# =============================================================================

class TestClassifyStormRegime:
    def test_unknown_before_3_cycles(self):
        """Must return UNKNOWN when cycle_count < 3."""
        tt = _make_tracker(state=_seeded_state(cycle_count=0))
        assert tt.classify_storm_regime([]) == StormRegime.UNKNOWN
        tt.state.cycle_count = 1
        assert tt.classify_storm_regime([]) == StormRegime.UNKNOWN
        tt.state.cycle_count = 2
        assert tt.classify_storm_regime([]) == StormRegime.UNKNOWN

    def test_unknown_at_3_cycles_no_signals(self):
        """With no mesos and no displacement, stays UNKNOWN."""
        tt = _make_tracker(state=_seeded_state(cycle_count=3))
        result = tt.classify_storm_regime([])
        assert result == StormRegime.UNKNOWN

    def test_qlcs_high_displacement(self):
        """High average displacement (>15 km) should vote QLCS after hysteresis."""
        # Seed a meso with large position displacements to drive avg_displacement > 15
        t0 = T0
        t1 = T0 + timedelta(minutes=5)
        t2 = T0 + timedelta(minutes=10)
        meso = _make_tracked_meso(
            position_history=[
                (t0.isoformat(), 35.0, -97.0),
                (t1.isoformat(), 35.2, -97.0),    # ~22 km north
                (t2.isoformat(), 35.4, -97.0),    # ~22 km more north
            ],
            cycle_count=3,
        )
        state = _seeded_state(
            cycle_count=3,
            tracked_mesocyclones=[meso],
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        # First call: candidate = QLCS, count = 1 (hysteresis not met yet)
        result = tt.classify_storm_regime([])
        assert result == StormRegime.UNKNOWN  # need 2 cycles to enter

        # Second call: count reaches 2, should switch
        tt.state.cycle_count = 4
        result = tt.classify_storm_regime([])
        assert result == StormRegime.QLCS

    def test_discrete_slow_persistent(self):
        """High persistence + low displacement should classify DISCRETE."""
        # Seed dissipated mesos with high cycle counts (avg_persistence >= 4)
        # and mesos with small position displacements (avg_displacement < 10)
        t0 = T0
        t1 = T0 + timedelta(minutes=5)
        dissipated = [
            _make_tracked_meso(id=f"MESO-{i}", cycle_count=5)
            for i in range(1, 4)
        ]
        active_meso = _make_tracked_meso(
            id="MESO-4",
            position_history=[
                (t0.isoformat(), 35.0, -97.0),
                (t1.isoformat(), 35.01, -97.0),  # ~1.1 km
            ],
            cycle_count=5,
        )
        state = _seeded_state(
            cycle_count=3,
            tracked_mesocyclones=[active_meso],
            dissipated_mesocyclones=dissipated,
            next_meso_id=5,
        )
        tt = _make_tracker(state=state)

        # First call: hysteresis 1
        tt.classify_storm_regime([])
        assert tt.state.current_regime == StormRegime.UNKNOWN

        # Second call: enters DISCRETE (2 to enter from UNKNOWN)
        tt.state.cycle_count = 4
        result = tt.classify_storm_regime([])
        assert result == StormRegime.DISCRETE

    def test_hysteresis_2_to_enter(self):
        """From UNKNOWN, need 2 consecutive matching candidate cycles to transition."""
        t0 = T0
        t1 = T0 + timedelta(minutes=5)
        meso = _make_tracked_meso(
            position_history=[
                (t0.isoformat(), 35.0, -97.0),
                (t1.isoformat(), 35.3, -97.0),  # ~33 km
            ],
        )
        state = _seeded_state(
            cycle_count=3,
            tracked_mesocyclones=[meso],
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        # Cycle 1: QLCS candidate, but count=1, stays UNKNOWN
        tt.classify_storm_regime([])
        assert tt.state.current_regime == StormRegime.UNKNOWN
        assert tt.state.regime_candidate == StormRegime.QLCS
        assert tt.state.regime_candidate_count == 1

        # Cycle 2: same candidate, count=2 -> transition
        tt.state.cycle_count = 4
        tt.classify_storm_regime([])
        assert tt.state.current_regime == StormRegime.QLCS

    def test_hysteresis_5_to_leave_qlcs(self):
        """Once in QLCS, need 5 consecutive non-QLCS candidate cycles to leave."""
        # Start already in QLCS
        state = _seeded_state(
            cycle_count=10,
            current_regime=StormRegime.QLCS,
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        # No displacement data -> candidate will be UNKNOWN, but need 5 to leave
        for i in range(4):
            tt.state.cycle_count = 10 + i
            tt.classify_storm_regime([])
            assert tt.state.current_regime == StormRegime.QLCS, f"Left QLCS too early at iteration {i}"

        # 5th cycle should finally transition out
        tt.state.cycle_count = 14
        result = tt.classify_storm_regime([])
        assert result != StormRegime.QLCS

    def test_hysteresis_5_to_leave_outbreak(self):
        """Outbreak also requires 5 to leave."""
        state = _seeded_state(
            cycle_count=10,
            current_regime=StormRegime.OUTBREAK,
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        for i in range(4):
            tt.state.cycle_count = 10 + i
            tt.classify_storm_regime([])
            assert tt.state.current_regime == StormRegime.OUTBREAK

        tt.state.cycle_count = 14
        tt.classify_storm_regime([])
        assert tt.state.current_regime != StormRegime.OUTBREAK

    def test_displacement_memory_decay(self):
        """When no mesos have 2+ position entries, decay last_valid_displacement by 0.8."""
        state = _seeded_state(
            cycle_count=5,
            last_valid_displacement=20.0,
        )
        tt = _make_tracker(state=state)

        # No mesos -> triggers decay
        tt._compute_average_displacement()
        assert abs(tt.state.last_valid_displacement - 16.0) < 0.01  # 20 * 0.8

        # Subsequent decay
        tt._compute_average_displacement()
        assert abs(tt.state.last_valid_displacement - 12.8) < 0.01  # 16 * 0.8

    def test_nws_qlcs_keywords_accelerate(self):
        """QLCS NWS keywords + moderate displacement should push toward QLCS."""
        t0 = T0
        t1 = T0 + timedelta(minutes=5)
        meso = _make_tracked_meso(
            position_history=[
                (t0.isoformat(), 35.0, -97.0),
                (t1.isoformat(), 35.1, -97.0),  # ~11 km
            ],
        )
        state = _seeded_state(
            cycle_count=3,
            tracked_mesocyclones=[meso],
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        alerts = [
            {"description": "squall line with embedded rotation and bow echo expected"},
        ]
        # With qlcs_keyword_score >= 2 and avg_displacement > 8 -> QLCS candidate
        tt.classify_storm_regime(alerts)
        assert tt.state.regime_candidate == StormRegime.QLCS

    def test_nws_discrete_keywords(self):
        """Discrete keywords + low displacement should classify DISCRETE."""
        t0 = T0
        t1 = T0 + timedelta(minutes=5)
        meso = _make_tracked_meso(
            position_history=[
                (t0.isoformat(), 35.0, -97.0),
                (t1.isoformat(), 35.01, -97.0),  # ~1.1 km
            ],
            cycle_count=3,
        )
        state = _seeded_state(
            cycle_count=3,
            tracked_mesocyclones=[meso],
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        alerts = [{"description": "An isolated supercell is expected"}]
        tt.classify_storm_regime(alerts)
        assert tt.state.regime_candidate == StormRegime.DISCRETE

    def test_qlcs_fingerprint_low_persist_high_frag(self):
        """Low persistence + high fragmentation rate -> QLCS candidate."""
        dissipated = [
            _make_tracked_meso(id=f"MESO-{i}", cycle_count=1)
            for i in range(1, 6)
        ]
        state = _seeded_state(
            cycle_count=3,
            dissipated_mesocyclones=dissipated,
            next_meso_id=6,  # 6 IDs / 3 cycles = frag_rate 2.0
        )
        tt = _make_tracker(state=state)

        tt.classify_storm_regime([])
        # avg_persistence = 1.0, frag_rate = 2.0 -> QLCS fingerprint
        assert tt.state.regime_candidate == StormRegime.QLCS

    def test_candidate_reset_when_matching_current(self):
        """When candidate matches current regime, reset candidate tracking."""
        state = _seeded_state(
            cycle_count=5,
            current_regime=StormRegime.UNKNOWN,
            regime_candidate=StormRegime.QLCS,
            regime_candidate_count=1,
        )
        tt = _make_tracker(state=state)

        # Classify with no signals => candidate UNKNOWN = current regime
        tt.classify_storm_regime([])
        assert tt.state.regime_candidate is None
        assert tt.state.regime_candidate_count == 0


# =============================================================================
# _track_mesocyclones
# =============================================================================

class TestTrackMesocyclones:
    def test_new_detection_creates_meso_1(self):
        """First detection should create MESO-1."""
        state = _seeded_state(cycle_count=1)
        tt = _make_tracker(state=state)

        det = _make_detection(lat=35.0, lon=-97.0, shear=55.0, dist_km=25.0)
        tracked = tt.track_mesocyclones([det], T0)

        assert len(tracked) == 1
        assert tracked[0].id == "MESO-1"
        assert tracked[0].status == "new"
        assert tracked[0].shear == 55.0
        assert tracked[0].cycle_count == 1
        assert tt.state.next_meso_id == 2

    def test_multiple_new_detections(self):
        """Multiple detections in one cycle create sequential IDs."""
        state = _seeded_state(cycle_count=1)
        tt = _make_tracker(state=state)

        dets = [
            _make_detection(lat=35.0, lon=-97.0, shear=55.0, dist_km=25.0),
            _make_detection(lat=35.3, lon=-97.5, shear=45.0, dist_km=50.0),
        ]
        tracked = tt.track_mesocyclones(dets, T0)

        assert len(tracked) == 2
        ids = {m.id for m in tracked}
        assert ids == {"MESO-1", "MESO-2"}
        assert tt.state.next_meso_id == 3

    def test_position_matching_same_location(self):
        """Detection near existing meso should match, not create new."""
        t1 = T0 + timedelta(minutes=5)
        existing = _make_tracked_meso(
            id="MESO-1",
            lat=35.0,
            lon=-97.0,
            shear=50.0,
            distance_km=30.0,
            last_seen=T0,
            position_history=[(T0.isoformat(), 35.0, -97.0)],
            distance_history=[(T0.isoformat(), 30.0)],
            cycle_count=1,
        )
        state = _seeded_state(
            cycle_count=2,
            tracked_mesocyclones=[existing],
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        # Detection very close to existing meso
        det = _make_detection(lat=35.01, lon=-97.01, shear=52.0, dist_km=29.0)
        tracked = tt.track_mesocyclones([det], t1)

        assert len(tracked) == 1
        assert tracked[0].id == "MESO-1"
        assert tracked[0].cycle_count == 2
        assert tracked[0].shear == 52.0

    def test_detection_too_far_creates_new(self):
        """Detection far from existing meso should create a new one."""
        t1 = T0 + timedelta(minutes=5)
        existing = _make_tracked_meso(
            id="MESO-1",
            lat=35.0,
            lon=-97.0,
            last_seen=T0,
            position_history=[(T0.isoformat(), 35.0, -97.0)],
            distance_history=[(T0.isoformat(), 30.0)],
            cycle_count=1,
        )
        state = _seeded_state(
            cycle_count=2,
            tracked_mesocyclones=[existing],
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        # Detection 100 km away (well beyond any persistence threshold)
        det = _make_detection(lat=36.0, lon=-97.0, shear=60.0, dist_km=90.0)
        tracked = tt.track_mesocyclones([det], t1)

        ids = {m.id for m in tracked}
        assert "MESO-1" in ids
        assert "MESO-2" in ids
        assert len(tracked) == 2

    def test_dissipation_after_missed_cycles(self):
        """Meso not seen for dissipation_cycles should be removed."""
        existing = _make_tracked_meso(
            id="MESO-1",
            lat=35.0,
            lon=-97.0,
            last_seen=T0,
            position_history=[(T0.isoformat(), 35.0, -97.0)],
            distance_history=[(T0.isoformat(), 30.0)],
            cycle_count=3,
        )
        state = _seeded_state(
            cycle_count=5,
            tracked_mesocyclones=[existing],
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        # Detection far away, MESO-1 won't match.
        # Time is 3 cycle intervals later -> triggers dissipation (2 cycles for UNKNOWN)
        t_far = T0 + timedelta(seconds=DEFAULT_CYCLE_INTERVAL_SEC * 3)
        det = _make_detection(lat=36.0, lon=-97.0, shear=60.0, dist_km=90.0)
        tracked = tt.track_mesocyclones([det], t_far)

        active_ids = {m.id for m in tracked}
        assert "MESO-1" not in active_ids
        assert len(tt.state.dissipated_mesocyclones) == 1
        assert tt.state.dissipated_mesocyclones[0].id == "MESO-1"

    def test_missed_one_cycle_marks_dissipating(self):
        """Missing one cycle should mark status as 'dissipated' but keep active."""
        existing = _make_tracked_meso(
            id="MESO-1",
            lat=35.0,
            lon=-97.0,
            last_seen=T0,
            position_history=[(T0.isoformat(), 35.0, -97.0)],
            distance_history=[(T0.isoformat(), 30.0)],
            cycle_count=3,
        )
        state = _seeded_state(
            cycle_count=5,
            tracked_mesocyclones=[existing],
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        # 1 cycle later, no matching detection
        t1 = T0 + timedelta(seconds=DEFAULT_CYCLE_INTERVAL_SEC)
        det = _make_detection(lat=36.0, lon=-97.0, shear=60.0, dist_km=90.0)
        tracked = tt.track_mesocyclones([det], t1)

        meso1 = next((m for m in tracked if m.id == "MESO-1"), None)
        assert meso1 is not None
        assert meso1.status == "dissipated"

    def test_status_intensifying(self):
        """Shear increase > 5 should mark status as 'intensifying'."""
        existing = _make_tracked_meso(
            id="MESO-1",
            lat=35.0,
            lon=-97.0,
            shear=50.0,
            last_seen=T0,
            position_history=[(T0.isoformat(), 35.0, -97.0)],
            distance_history=[(T0.isoformat(), 30.0)],
            cycle_count=2,
        )
        state = _seeded_state(
            cycle_count=3,
            tracked_mesocyclones=[existing],
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        # Detection at same spot but shear jumped +10
        t1 = T0 + timedelta(minutes=5)
        det = _make_detection(lat=35.0, lon=-97.0, shear=60.0, dist_km=30.0)
        tracked = tt.track_mesocyclones([det], t1)

        assert tracked[0].status == "intensifying"

    def test_status_dissipating_shear_drop(self):
        """Shear decrease > 5 should mark status as 'dissipating'."""
        existing = _make_tracked_meso(
            id="MESO-1",
            lat=35.0,
            lon=-97.0,
            shear=50.0,
            last_seen=T0,
            position_history=[(T0.isoformat(), 35.0, -97.0)],
            distance_history=[(T0.isoformat(), 30.0)],
            cycle_count=2,
        )
        state = _seeded_state(
            cycle_count=3,
            tracked_mesocyclones=[existing],
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        t1 = T0 + timedelta(minutes=5)
        det = _make_detection(lat=35.0, lon=-97.0, shear=40.0, dist_km=30.0)
        tracked = tt.track_mesocyclones([det], t1)

        assert tracked[0].status == "dissipating"

    def test_status_tracking_small_shear_change(self):
        """Shear change <= 5 should keep status as 'tracking'."""
        existing = _make_tracked_meso(
            id="MESO-1",
            lat=35.0,
            lon=-97.0,
            shear=50.0,
            last_seen=T0,
            position_history=[(T0.isoformat(), 35.0, -97.0)],
            distance_history=[(T0.isoformat(), 30.0)],
            cycle_count=2,
        )
        state = _seeded_state(
            cycle_count=3,
            tracked_mesocyclones=[existing],
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        t1 = T0 + timedelta(minutes=5)
        det = _make_detection(lat=35.0, lon=-97.0, shear=53.0, dist_km=30.0)
        tracked = tt.track_mesocyclones([det], t1)

        assert tracked[0].status == "tracking"

    def test_distance_history_capped(self):
        """distance_history should not exceed history_cap."""
        # Under UNKNOWN regime, history_cap = 6
        t_start = T0
        state = _seeded_state(cycle_count=1, next_meso_id=1)
        tt = _make_tracker(state=state)

        # Run 10 cycles with matching detections
        for i in range(10):
            t = t_start + timedelta(minutes=5 * i)
            det = _make_detection(lat=35.0, lon=-97.0, shear=50.0, dist_km=30.0)
            tracked = tt.track_mesocyclones([det], t)

        assert len(tracked) == 1
        cap = REGIME_PARAMS[StormRegime.UNKNOWN].history_cap
        assert len(tracked[0].distance_history) <= cap
        assert len(tracked[0].position_history) <= cap

    def test_position_history_capped(self):
        """position_history should not exceed history_cap."""
        t_start = T0
        state = _seeded_state(cycle_count=1, next_meso_id=1)
        tt = _make_tracker(state=state)

        for i in range(10):
            t = t_start + timedelta(minutes=5 * i)
            det = _make_detection(lat=35.0 + i * 0.01, lon=-97.0, shear=50.0, dist_km=30.0)
            tracked = tt.track_mesocyclones([det], t)

        cap = REGIME_PARAMS[StormRegime.UNKNOWN].history_cap
        assert len(tracked[0].position_history) <= cap


# =============================================================================
# _check_association
# =============================================================================

class TestCheckAssociation:
    def test_no_dissipated_mesos(self):
        """With no dissipated mesos, association should not modify new meso."""
        state = _seeded_state(cycle_count=5, next_meso_id=2)
        tt = _make_tracker(state=state)

        new_meso = _make_tracked_meso(
            id="MESO-2", lat=35.0, lon=-97.0, shear=50.0, cycle_count=1,
        )
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        tt._check_association(new_meso, T0, params)

        assert new_meso.absorbed_ids is None
        assert new_meso.cycle_count == 1

    def test_association_within_threshold(self):
        """New meso near recently dissipated one should inherit history."""
        old_meso = _make_tracked_meso(
            id="MESO-1",
            lat=35.0,
            lon=-97.0,
            shear=48.0,
            cycle_count=5,
            last_seen=T0 - timedelta(minutes=3),
            first_detected=T0 - timedelta(minutes=30),
            position_history=[
                ((T0 - timedelta(minutes=10)).isoformat(), 34.95, -97.05),
                ((T0 - timedelta(minutes=5)).isoformat(), 35.0, -97.0),
            ],
            distance_history=[
                ((T0 - timedelta(minutes=10)).isoformat(), 32.0),
                ((T0 - timedelta(minutes=5)).isoformat(), 30.0),
            ],
        )
        state = _seeded_state(
            cycle_count=10,
            dissipated_mesocyclones=[old_meso],
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        new_meso = _make_tracked_meso(
            id="MESO-2",
            lat=35.02,
            lon=-97.02,
            shear=50.0,
            cycle_count=1,
            last_seen=T0,
            first_detected=T0,
            position_history=[(T0.isoformat(), 35.02, -97.02)],
            distance_history=[(T0.isoformat(), 29.0)],
        )
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        tt._check_association(new_meso, T0, params)

        assert new_meso.absorbed_ids is not None
        assert "MESO-1" in new_meso.absorbed_ids
        assert new_meso.cycle_count == 6  # 1 + 5 inherited
        assert len(new_meso.position_history) == 3  # 2 old + 1 new

    def test_association_too_far(self):
        """Dissipated meso too far away should not be associated."""
        old_meso = _make_tracked_meso(
            id="MESO-1",
            lat=36.0,
            lon=-97.0,  # ~111 km north
            shear=50.0,
            cycle_count=3,
            last_seen=T0 - timedelta(minutes=3),
        )
        state = _seeded_state(
            cycle_count=10,
            dissipated_mesocyclones=[old_meso],
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        new_meso = _make_tracked_meso(
            id="MESO-2",
            lat=35.0,
            lon=-97.0,
            shear=50.0,
            cycle_count=1,
            last_seen=T0,
        )
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        tt._check_association(new_meso, T0, params)

        assert new_meso.absorbed_ids is None
        assert new_meso.cycle_count == 1

    def test_association_too_old(self):
        """Dissipated meso from too many cycles ago should not be associated."""
        old_meso = _make_tracked_meso(
            id="MESO-1",
            lat=35.0,
            lon=-97.0,
            shear=50.0,
            cycle_count=3,
            # UNKNOWN association_window_cycles = 3, so 4 cycles ago is too old
            last_seen=T0 - timedelta(seconds=DEFAULT_CYCLE_INTERVAL_SEC * 4),
        )
        state = _seeded_state(
            cycle_count=10,
            dissipated_mesocyclones=[old_meso],
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        new_meso = _make_tracked_meso(
            id="MESO-2",
            lat=35.0,
            lon=-97.0,
            shear=50.0,
            cycle_count=1,
            last_seen=T0,
        )
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        tt._check_association(new_meso, T0, params)

        assert new_meso.absorbed_ids is None

    def test_association_inherits_first_detected(self):
        """Association should inherit the original first_detected timestamp."""
        old_first = T0 - timedelta(hours=1)
        old_meso = _make_tracked_meso(
            id="MESO-1",
            lat=35.0,
            lon=-97.0,
            shear=50.0,
            cycle_count=10,
            first_detected=old_first,
            last_seen=T0 - timedelta(minutes=3),
            position_history=[((T0 - timedelta(minutes=5)).isoformat(), 35.0, -97.0)],
            distance_history=[((T0 - timedelta(minutes=5)).isoformat(), 30.0)],
        )
        state = _seeded_state(
            cycle_count=20,
            dissipated_mesocyclones=[old_meso],
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        new_meso = _make_tracked_meso(
            id="MESO-2",
            lat=35.01,
            lon=-97.01,
            shear=50.0,
            cycle_count=1,
            first_detected=T0,
            last_seen=T0,
            position_history=[(T0.isoformat(), 35.01, -97.01)],
            distance_history=[(T0.isoformat(), 29.0)],
        )
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        tt._check_association(new_meso, T0, params)

        assert new_meso.first_detected == old_first

    def test_association_removes_from_dissipated_list(self):
        """After association, the old meso should be removed from dissipated list."""
        old_meso = _make_tracked_meso(
            id="MESO-1",
            lat=35.0,
            lon=-97.0,
            shear=50.0,
            cycle_count=3,
            last_seen=T0 - timedelta(minutes=3),
            position_history=[((T0 - timedelta(minutes=5)).isoformat(), 35.0, -97.0)],
            distance_history=[((T0 - timedelta(minutes=5)).isoformat(), 30.0)],
        )
        state = _seeded_state(
            cycle_count=10,
            dissipated_mesocyclones=[old_meso],
            next_meso_id=2,
        )
        tt = _make_tracker(state=state)

        new_meso = _make_tracked_meso(
            id="MESO-2",
            lat=35.01,
            lon=-97.01,
            shear=50.0,
            cycle_count=1,
            last_seen=T0,
            position_history=[(T0.isoformat(), 35.01, -97.01)],
            distance_history=[(T0.isoformat(), 29.0)],
        )
        params = REGIME_PARAMS[StormRegime.UNKNOWN]
        tt._check_association(new_meso, T0, params)

        assert len(tt.state.dissipated_mesocyclones) == 0


# =============================================================================
# _compute_motion_vector
# =============================================================================

class TestComputeMotionVector:
    def test_insufficient_history(self):
        """With <2 position_history entries, returns (None, None)."""
        tt = _make_tracker()
        meso = _make_tracked_meso(position_history=[(T0.isoformat(), 35.0, -97.0)])
        speed, bearing = tt._compute_motion_vector(meso)
        assert speed is None
        assert bearing is None

    def test_no_history(self):
        """With None position_history, returns (None, None)."""
        tt = _make_tracker()
        meso = _make_tracked_meso(position_history=None)
        speed, bearing = tt._compute_motion_vector(meso)
        assert speed is None
        assert bearing is None

    def test_stationary(self):
        """Same position at different times should give ~0 speed."""
        tt = _make_tracker()
        t0 = T0
        t1 = T0 + timedelta(minutes=5)
        meso = _make_tracked_meso(
            position_history=[
                (t0.isoformat(), 35.0, -97.0),
                (t1.isoformat(), 35.0, -97.0),
            ],
        )
        speed, bearing = tt._compute_motion_vector(meso)
        assert speed is not None
        assert speed < 1.0  # effectively stationary

    def test_northward_motion(self):
        """Moving north should give bearing near 0/360 degrees."""
        tt = _make_tracker()
        t0 = T0
        t1 = T0 + timedelta(hours=1)
        meso = _make_tracked_meso(
            position_history=[
                (t0.isoformat(), 35.0, -97.0),
                (t1.isoformat(), 35.5, -97.0),  # ~55.5 km north
            ],
        )
        speed, bearing = tt._compute_motion_vector(meso)
        assert speed is not None
        assert speed > 40.0  # ~55.5 km/hr
        assert bearing < 10.0 or bearing > 350.0  # near north

    def test_eastward_motion(self):
        """Moving east should give bearing near 90 degrees."""
        tt = _make_tracker()
        t0 = T0
        t1 = T0 + timedelta(hours=1)
        meso = _make_tracked_meso(
            position_history=[
                (t0.isoformat(), 35.0, -97.0),
                (t1.isoformat(), 35.0, -96.5),  # east
            ],
        )
        speed, bearing = tt._compute_motion_vector(meso)
        assert speed is not None
        assert 80.0 < bearing < 100.0

    def test_weighted_average_favors_recent(self):
        """More recent position pairs should be weighted more heavily."""
        tt = _make_tracker()
        t0 = T0
        t1 = T0 + timedelta(hours=1)
        t2 = T0 + timedelta(hours=2)

        # First segment goes east, second goes north (should be weighted more)
        meso = _make_tracked_meso(
            position_history=[
                (t0.isoformat(), 35.0, -97.0),
                (t1.isoformat(), 35.0, -96.0),   # east ~91 km
                (t2.isoformat(), 35.5, -96.0),   # north ~55.5 km
            ],
        )
        speed, bearing = tt._compute_motion_vector(meso)
        assert speed is not None
        # Weighted: east weight=1, north weight=2
        # vx ~= (91*1 + 0*2)/3 ~= 30.3
        # vy ~= (0*1 + 55.5*2)/3 ~= 37
        # bearing = atan2(30.3, 37) ~= 39 degrees (NE)
        assert 20.0 < bearing < 60.0  # northeast-ish


# =============================================================================
# update() — full cycle integration
# =============================================================================

class TestUpdate:
    def test_cycle_count_increments(self):
        tt = _make_tracker()
        result = _make_radar_result()
        tt.update(result, T0)
        assert tt.state.cycle_count == 1
        tt.update(result, T0 + timedelta(minutes=5))
        assert tt.state.cycle_count == 2

    def test_hail_cells_cycled(self):
        """Hail cells should rotate: current -> previous each cycle."""
        hail = [HailCell(
            lat=35.0, lon=-97.0, distance_km=20.0, bearing_deg=180.0,
            vil_kg_m2=35.0, max_dbz=60.0, mesh_mm=25.0,
            hail_probability=0.85, hail_size_category="small",
            estimated_size_mm=25.0, column_height_45dbz_m=8000.0,
            echo_top_m=12000.0, overshoot_m=4000.0,
        )]
        tt = _make_tracker()

        # Cycle 1: hail present
        r1 = _make_radar_result(hail_cells=hail)
        tt.update(r1, T0)
        assert tt.state.hail_cells == hail
        assert tt.state.previous_hail_cells is None

        # Cycle 2: no hail
        r2 = _make_radar_result(hail_cells=None)
        tt.update(r2, T0 + timedelta(minutes=5))
        assert tt.state.hail_cells is None
        assert tt.state.previous_hail_cells == hail

    def test_moderate_detections_stored(self):
        """Moderate rotation detections should be stored on state."""
        moderate = [_make_detection(shear=30.0)]
        result = _make_radar_result(moderate=moderate)
        tt = _make_tracker()
        tt.update(result, T0)
        assert tt.state.moderate_rotation_detections == moderate

    def test_strong_detections_trigger_tracking(self):
        """Strong detections should create tracked mesocyclones."""
        strong = [_make_detection(shear=55.0)]
        result = _make_radar_result(strong=strong)
        tt = _make_tracker()
        tracked = tt.update(result, T0)
        assert len(tracked) == 1
        assert tracked[0].id == "MESO-1"

    def test_no_detections_returns_empty(self):
        """No detections should return empty list."""
        result = _make_radar_result()
        tt = _make_tracker()
        tracked = tt.update(result, T0)
        assert tracked == []

    def test_regime_classified_even_without_strong(self):
        """Even without strong detections, regime classification should run."""
        state = _seeded_state(cycle_count=2)  # Will become 3 after update
        tt = _make_tracker(state=state)
        result = _make_radar_result()
        tt.update(result, T0)
        # Classify ran (no error), cycle_count is 3
        assert tt.state.cycle_count == 3

    def test_multi_cycle_tracking(self):
        """Run 3 cycles with a moving meso, verify continuous tracking."""
        tt = _make_tracker()

        # Cycle 1
        r1 = _make_radar_result(strong=[_make_detection(lat=35.0, lon=-97.0, shear=50.0, dist_km=30.0)])
        tracked = tt.update(r1, T0)
        assert len(tracked) == 1
        assert tracked[0].id == "MESO-1"

        # Cycle 2 - slightly moved
        t2 = T0 + timedelta(minutes=5)
        r2 = _make_radar_result(strong=[_make_detection(lat=35.02, lon=-97.01, shear=52.0, dist_km=28.0)])
        tracked = tt.update(r2, t2)
        assert len(tracked) == 1
        assert tracked[0].id == "MESO-1"
        assert tracked[0].cycle_count == 2

        # Cycle 3 - continued movement
        t3 = T0 + timedelta(minutes=10)
        r3 = _make_radar_result(strong=[_make_detection(lat=35.04, lon=-97.02, shear=55.0, dist_km=26.0)])
        tracked = tt.update(r3, t3)
        assert len(tracked) == 1
        assert tracked[0].id == "MESO-1"
        assert tracked[0].cycle_count == 3


# =============================================================================
# get_primary_threat
# =============================================================================

class TestGetPrimaryThreat:
    def test_no_mesos_returns_none(self):
        tt = _make_tracker()
        assert tt.get_primary_threat() is None

    def test_single_meso(self):
        meso = _make_tracked_meso(id="MESO-1", threat_score=0.8)
        state = _seeded_state(tracked_mesocyclones=[meso])
        tt = _make_tracker(state=state)
        assert tt.get_primary_threat().id == "MESO-1"

    def test_highest_threat_score_wins(self):
        low = _make_tracked_meso(id="MESO-1", threat_score=0.5)
        high = _make_tracked_meso(id="MESO-2", threat_score=0.9)
        state = _seeded_state(tracked_mesocyclones=[low, high])
        tt = _make_tracker(state=state)
        assert tt.get_primary_threat().id == "MESO-2"

    def test_three_way_comparison(self):
        m1 = _make_tracked_meso(id="MESO-1", threat_score=0.3)
        m2 = _make_tracked_meso(id="MESO-2", threat_score=0.7)
        m3 = _make_tracked_meso(id="MESO-3", threat_score=0.5)
        state = _seeded_state(tracked_mesocyclones=[m1, m2, m3])
        tt = _make_tracker(state=state)
        assert tt.get_primary_threat().id == "MESO-2"


# =============================================================================
# get_primary_detection_dict
# =============================================================================

class TestGetPrimaryDetectionDict:
    def test_none_when_empty(self):
        tt = _make_tracker()
        assert tt.get_primary_detection_dict() is None

    def test_dict_has_expected_keys(self):
        raw = _make_detection(range_km=45.0, azimuth_deg=270.0)
        meso = _make_tracked_meso(
            id="MESO-1", lat=35.0, lon=-97.0,
            distance_km=30.0, shear=55.0, threat_score=0.9,
        )
        meso.raw_detection = raw
        state = _seeded_state(tracked_mesocyclones=[meso])
        tt = _make_tracker(state=state)

        d = tt.get_primary_detection_dict()
        assert d["latitude"] == 35.0
        assert d["longitude"] == -97.0
        assert d["distance_to_station_km"] == 30.0
        assert d["max_shear"] == 55.0
        assert d["threat_score"] == 0.9
        assert d["meso_id"] == "MESO-1"
        assert d["range_km"] == 45.0
        assert d["azimuth_deg"] == 270.0

    def test_dict_without_raw_detection(self):
        """When raw_detection is None, range_km and azimuth_deg default to 0."""
        meso = _make_tracked_meso(id="MESO-1", threat_score=0.8)
        meso.raw_detection = None
        state = _seeded_state(tracked_mesocyclones=[meso])
        tt = _make_tracker(state=state)

        d = tt.get_primary_detection_dict()
        assert d["range_km"] == 0
        assert d["azimuth_deg"] == 0


# =============================================================================
# _get_regime_parameters
# =============================================================================

class TestGetRegimeParameters:
    def test_returns_correct_params_for_regime(self):
        for regime in StormRegime:
            state = _seeded_state(current_regime=regime)
            tt = _make_tracker(state=state)
            params = tt._get_regime_parameters()
            assert params == REGIME_PARAMS[regime]

    def test_unknown_fallback(self):
        """If regime somehow not in map, falls back to UNKNOWN."""
        tt = _make_tracker()
        # Default regime is UNKNOWN
        params = tt._get_regime_parameters()
        assert params == REGIME_PARAMS[StormRegime.UNKNOWN]


# =============================================================================
# _predict_position
# =============================================================================

class TestPredictPosition:
    def test_no_motion_vector(self):
        tt = _make_tracker()
        meso = _make_tracked_meso(motion_speed_kmh=None, motion_bearing_deg=None)
        lat, lon = tt._predict_position(meso, 1.0)
        assert lat is None
        assert lon is None

    def test_slow_returns_current_position(self):
        """Speed < 1 km/h should return current position."""
        tt = _make_tracker()
        meso = _make_tracked_meso(
            lat=35.0, lon=-97.0,
            motion_speed_kmh=0.5, motion_bearing_deg=90.0,
        )
        lat, lon = tt._predict_position(meso, 1.0)
        assert lat == 35.0
        assert lon == -97.0

    def test_northward_prediction(self):
        """50 km/h northward for 1 hour should move ~0.45 degrees lat."""
        tt = _make_tracker()
        meso = _make_tracked_meso(
            lat=35.0, lon=-97.0,
            motion_speed_kmh=50.0, motion_bearing_deg=0.0,  # due north
        )
        lat, lon = tt._predict_position(meso, 1.0)
        assert lat > 35.4  # ~50/111 = 0.45 degrees
        assert abs(lon - (-97.0)) < 0.01  # negligible east-west change

    def test_eastward_prediction(self):
        """50 km/h eastward for 1 hour should move east."""
        tt = _make_tracker()
        meso = _make_tracked_meso(
            lat=35.0, lon=-97.0,
            motion_speed_kmh=50.0, motion_bearing_deg=90.0,  # due east
        )
        lat, lon = tt._predict_position(meso, 1.0)
        assert abs(lat - 35.0) < 0.05  # negligible north-south
        assert lon > -97.0  # moved east


# =============================================================================
# DEFAULT_CYCLE_INTERVAL_SEC
# =============================================================================

class TestConstants:
    def test_default_cycle_interval(self):
        assert DEFAULT_CYCLE_INTERVAL_SEC == 300


# =============================================================================
# HELPER: QLCSLine factory
# =============================================================================

def _make_qlcs_line(
    centroid_lat=35.0,
    centroid_lon=-97.0,
    distance_km=20.0,
    approach_bearing=270.0,
    axis_bearing=0.0,
    length_km=50.0,
):
    """Create a QLCSLine with sensible defaults."""
    return QLCSLine(
        leading_edge_points=[(centroid_lat, centroid_lon)],
        centroid_lat=centroid_lat,
        centroid_lon=centroid_lon,
        axis_bearing_deg=axis_bearing,
        length_km=length_km,
        distance_to_station_km=distance_km,
        approach_bearing_deg=approach_bearing,
    )


# =============================================================================
# track_qlcs_line
# =============================================================================

class TestTrackQlcsLine:
    def test_first_line_initializes_history(self):
        tt = _make_tracker()
        line = _make_qlcs_line()
        tt.track_qlcs_line(line, T0)
        stored = tt.state.tracked_qlcs_line
        assert stored is line
        assert len(stored.centroid_history) == 1
        assert stored.centroid_history[0][1] == 35.0
        assert stored.centroid_history[0][2] == -97.0

    def test_first_line_no_motion_vector(self):
        """Single centroid entry — not enough to compute motion."""
        tt = _make_tracker()
        tt.track_qlcs_line(_make_qlcs_line(), T0)
        stored = tt.state.tracked_qlcs_line
        assert stored.motion_speed_kmh is None
        assert stored.motion_bearing_deg is None
        assert stored.eta_minutes is None

    def test_second_line_inherits_history(self):
        tt = _make_tracker()
        tt.track_qlcs_line(_make_qlcs_line(centroid_lat=35.0), T0)
        t2 = T0 + timedelta(minutes=5)
        tt.track_qlcs_line(_make_qlcs_line(centroid_lat=35.05), t2)
        stored = tt.state.tracked_qlcs_line
        assert len(stored.centroid_history) == 2

    def test_motion_vector_due_east(self):
        """Line centroid moving east should produce ~90 deg bearing."""
        tt = _make_tracker()
        tt.track_qlcs_line(_make_qlcs_line(centroid_lon=-97.5), T0)
        t2 = T0 + timedelta(hours=1)
        tt.track_qlcs_line(_make_qlcs_line(centroid_lon=-97.0), t2)
        stored = tt.state.tracked_qlcs_line
        assert stored.motion_speed_kmh is not None
        assert stored.motion_speed_kmh > 10.0
        assert abs(stored.motion_bearing_deg - 90.0) < 5.0

    def test_motion_vector_due_north(self):
        """Line centroid moving north should produce ~0 deg bearing."""
        tt = _make_tracker()
        tt.track_qlcs_line(_make_qlcs_line(centroid_lat=35.0), T0)
        t2 = T0 + timedelta(hours=1)
        tt.track_qlcs_line(_make_qlcs_line(centroid_lat=35.5), t2)
        stored = tt.state.tracked_qlcs_line
        # Bearing should be near 0 (north)
        assert stored.motion_bearing_deg < 5.0 or stored.motion_bearing_deg > 355.0

    def test_eta_computed_when_fast(self):
        """ETA should be distance / speed * 60."""
        tt = _make_tracker()
        tt.track_qlcs_line(_make_qlcs_line(centroid_lon=-97.5, distance_km=50.0), T0)
        t2 = T0 + timedelta(hours=1)
        tt.track_qlcs_line(_make_qlcs_line(centroid_lon=-97.0, distance_km=50.0), t2)
        stored = tt.state.tracked_qlcs_line
        assert stored.eta_minutes is not None
        expected = 50.0 / stored.motion_speed_kmh * 60
        assert abs(stored.eta_minutes - expected) < 0.1

    def test_eta_none_when_stationary(self):
        """ETA should be None when speed < 1 km/h."""
        tt = _make_tracker()
        tt.track_qlcs_line(_make_qlcs_line(centroid_lat=35.0), T0)
        t2 = T0 + timedelta(hours=1)
        # Barely moved (0.00001 deg ~ 1 meter)
        tt.track_qlcs_line(_make_qlcs_line(centroid_lat=35.00001), t2)
        stored = tt.state.tracked_qlcs_line
        assert stored.eta_minutes is None

    def test_history_capped_at_8(self):
        tt = _make_tracker()
        for i in range(10):
            t = T0 + timedelta(minutes=5 * i)
            tt.track_qlcs_line(_make_qlcs_line(centroid_lat=35.0 + i * 0.01), t)
        stored = tt.state.tracked_qlcs_line
        assert len(stored.centroid_history) == 8

    def test_weighted_motion_favors_recent(self):
        """With 3 entries where direction changes, result should favor recent."""
        tt = _make_tracker()
        # First: at origin
        tt.track_qlcs_line(_make_qlcs_line(centroid_lat=35.0, centroid_lon=-97.0), T0)
        # Second: moved north (5 min later)
        t2 = T0 + timedelta(minutes=5)
        tt.track_qlcs_line(_make_qlcs_line(centroid_lat=35.1, centroid_lon=-97.0), t2)
        # Third: moved east (another 5 min), slight north
        t3 = T0 + timedelta(minutes=10)
        tt.track_qlcs_line(_make_qlcs_line(centroid_lat=35.12, centroid_lon=-96.9), t3)
        stored = tt.state.tracked_qlcs_line
        # Recent motion is mostly east — bearing should be more toward east than pure north
        assert stored.motion_bearing_deg > 30.0  # not pure north
        assert stored.motion_bearing_deg < 150.0  # but not south

    def test_new_line_replaces_previous(self):
        tt = _make_tracker()
        line1 = _make_qlcs_line(distance_km=30.0)
        line2 = _make_qlcs_line(distance_km=20.0)
        tt.track_qlcs_line(line1, T0)
        tt.track_qlcs_line(line2, T0 + timedelta(minutes=5))
        assert tt.state.tracked_qlcs_line.distance_to_station_km == 20.0


# =============================================================================
# compute_threat_corridor
# =============================================================================

class TestComputeThreatCorridor:
    def test_no_detections_no_history_returns_none(self):
        tt = _make_tracker()
        result = tt.compute_threat_corridor([], T0)
        assert result is None

    def test_single_detection_creates_corridor(self):
        tt = _make_tracker()
        det = _make_detection(lat=35.0, lon=-97.0, shear=45.0, dist_km=30.0)
        result = tt.compute_threat_corridor([det], T0)
        assert result is not None
        assert result.rotation_count_30min == 1
        assert result.max_shear_30min == 45.0
        assert result.has_active_rotation is True

    def test_detections_accumulate_across_cycles(self):
        tt = _make_tracker()
        det1 = _make_detection(lat=35.0, lon=-97.0, shear=40.0, dist_km=30.0)
        det2 = _make_detection(lat=35.01, lon=-97.0, shear=50.0, dist_km=28.0)
        tt.compute_threat_corridor([det1], T0)
        tt.compute_threat_corridor([det2], T0 + timedelta(minutes=5))
        result = tt.compute_threat_corridor([], T0 + timedelta(minutes=10))
        assert result.rotation_count_30min >= 2

    def test_old_detections_pruned(self):
        """Detections older than 30 min should be dropped."""
        tt = _make_tracker()
        det = _make_detection(lat=35.0, lon=-97.0, shear=40.0, dist_km=30.0)
        tt.compute_threat_corridor([det], T0)
        # 31 minutes later — old detection should be pruned
        result = tt.compute_threat_corridor([], T0 + timedelta(minutes=31))
        assert result is None

    def test_max_shear_tracked(self):
        tt = _make_tracker()
        dets = [
            _make_detection(shear=30.0, dist_km=30.0),
            _make_detection(shear=55.0, dist_km=25.0),
            _make_detection(shear=40.0, dist_km=20.0),
        ]
        result = tt.compute_threat_corridor(dets, T0)
        assert result.max_shear_30min == 55.0

    def test_nearest_rotation_tracked(self):
        tt = _make_tracker()
        dets = [
            _make_detection(lat=35.0, lon=-97.0, shear=30.0, dist_km=30.0),
            _make_detection(lat=35.15, lon=-97.0, shear=50.0, dist_km=10.0),
            _make_detection(lat=35.1, lon=-97.0, shear=40.0, dist_km=20.0),
        ]
        result = tt.compute_threat_corridor(dets, T0)
        assert result.nearest_rotation_km == 10.0

    def test_has_active_rotation_true_within_10min(self):
        tt = _make_tracker()
        det = _make_detection(dist_km=20.0)
        tt.compute_threat_corridor([det], T0)
        result = tt.compute_threat_corridor([], T0 + timedelta(minutes=9))
        assert result.has_active_rotation is True

    def test_has_active_rotation_false_after_10min(self):
        tt = _make_tracker()
        det = _make_detection(dist_km=20.0)
        tt.compute_threat_corridor([det], T0)
        result = tt.compute_threat_corridor([], T0 + timedelta(minutes=11))
        # Detection is within 30 min (still in history) but not within 10 min
        assert result is not None
        assert result.has_active_rotation is False

    def test_with_qlcs_line_uses_line_bearing(self):
        """When QLCS line exists, corridor axis should use line's approach bearing."""
        tt = _make_tracker()
        line = _make_qlcs_line(approach_bearing=270.0)
        tt.state.tracked_qlcs_line = line
        # Detection on approach axis (due west of station)
        det = _make_detection(lat=35.2, lon=-97.8, shear=45.0, dist_km=30.0)
        result = tt.compute_threat_corridor([det], T0)
        assert result.rotation_count_30min >= 1

    def test_cross_track_filtering_excludes_far_detections(self):
        """Detections >15 km off-axis should be excluded."""
        tt = _make_tracker()
        # Station is at 35.2, -97.4. Set up corridor axis along due north (0 deg)
        line = _make_qlcs_line(approach_bearing=0.0)
        tt.state.tracked_qlcs_line = line
        # Detection due east of station — 50km away at bearing 90
        # Cross-track from a 0-deg axis = dist * sin(90 - 0) = 50 km
        det_far_off = _make_detection(lat=35.2, lon=-96.8, shear=50.0, dist_km=50.0)
        result = tt.compute_threat_corridor([det_far_off], T0)
        # The detection is way off-axis, should be filtered
        assert result.rotation_count_30min == 0

    def test_nearest_rotation_age(self):
        tt = _make_tracker()
        det = _make_detection(dist_km=20.0, shear=45.0)
        tt.compute_threat_corridor([det], T0)
        t2 = T0 + timedelta(minutes=7)
        result = tt.compute_threat_corridor([], t2)
        assert result.nearest_rotation_age_min is not None
        assert abs(result.nearest_rotation_age_min - 7.0) < 0.1

    def test_empty_corridor_when_all_off_axis(self):
        """When all detections are outside corridor width, return empty corridor."""
        tt = _make_tracker()
        line = _make_qlcs_line(approach_bearing=0.0)  # corridor along N-S
        tt.state.tracked_qlcs_line = line
        # Put detection far to the east (off-axis)
        det = _make_detection(lat=35.2, lon=-96.5, shear=50.0, dist_km=75.0)
        result = tt.compute_threat_corridor([det], T0)
        assert result.rotation_count_30min == 0
        assert result.has_active_rotation is False
