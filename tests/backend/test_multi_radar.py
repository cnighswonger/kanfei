"""Tests for multi-radar NEXRAD processing — nearby radar lookup and detection merging."""

import math
from datetime import datetime, timezone

import pytest

from app.models.radar_threats import (
    HailCell,
    QLCSLine,
    RadarProcessingResult,
)
from app.services.multi_radar import (
    MERGE_PROXIMITY_KM,
    MULTI_RADAR_CONFIDENCE_BOOST,
    find_nearby_radars,
    merge_radar_results,
    _merge_detections,
    _merge_hail_cells,
)


# =============================================================================
# HELPERS
# =============================================================================

T0 = datetime(2026, 3, 12, 18, 0, 0, tzinfo=timezone.utc)


def _det(lat=35.0, lon=-97.0, shear=50.0, dist_km=30.0, threat=0.8,
         elev=0.5, range_km=40.0, az=270.0):
    return {
        "latitude": lat, "longitude": lon, "max_shear": shear,
        "distance_to_station_km": dist_km, "threat_score": threat,
        "elevation_angle": elev, "range_km": range_km, "azimuth_deg": az,
    }


def _result(strong=None, moderate=None, hail=None, qlcs=None,
            site="KTLX", rlat=35.33, rlon=-97.28, rdist=20.0):
    strong = strong or []
    moderate = moderate or []
    return RadarProcessingResult(
        all_detections=strong + moderate,
        strong_detections=strong,
        moderate_detections=moderate,
        hail_cells=hail,
        qlcs_line=qlcs,
        primary_detection=strong[0] if strong else None,
        radar_timestamp=T0,
        radar_site=site,
        radar_lat=rlat,
        radar_lon=rlon,
        radar_station_dist_km=rdist,
    )


def _hail(lat=35.0, lon=-97.0, dist=20.0, bearing=180.0, vil=35.0,
          dbz=60.0, mesh=25.0, prob=0.85, size_cat="small", size_mm=25.0):
    return HailCell(
        lat=lat, lon=lon, distance_km=dist, bearing_deg=bearing,
        vil_kg_m2=vil, max_dbz=dbz, mesh_mm=mesh, hail_probability=prob,
        hail_size_category=size_cat, estimated_size_mm=size_mm,
        column_height_45dbz_m=8000.0, echo_top_m=12000.0, overshoot_m=4000.0,
    )


# =============================================================================
# find_nearby_radars
# =============================================================================

class TestFindNearbyRadars:
    def test_returns_sorted_by_distance(self):
        """Results should be nearest-first."""
        radars = find_nearby_radars(35.2, -97.4)
        assert len(radars) > 0
        distances = [d for _, d in radars]
        assert distances == sorted(distances)

    def test_max_count_limits_results(self):
        radars = find_nearby_radars(35.2, -97.4, max_count=2)
        assert len(radars) <= 2

    def test_max_range_filters(self):
        radars = find_nearby_radars(35.2, -97.4, max_range_km=50)
        for _, dist in radars:
            assert dist <= 50

    def test_known_location_oklahoma(self):
        """Norman OK should find KTLX within top 3 (KCRI research radar may be closer)."""
        radars = find_nearby_radars(35.22, -97.44)
        sites = [code for code, _ in radars]
        assert "KTLX" in sites
        assert radars[0][1] < 25  # Nearest should be very close

    def test_known_location_hattiesburg(self):
        """Hattiesburg MS should find KDGX, KLIX, KMOB within 150 km."""
        radars = find_nearby_radars(31.35, -89.37, max_range_km=150)
        sites = [code for code, _ in radars]
        assert "KDGX" in sites
        assert len(radars) >= 2  # At least 2 radars within 150 km

    def test_known_location_harnett(self):
        """Harnett County NC should find KRAX as nearest."""
        radars = find_nearby_radars(35.32, -78.56)
        assert radars[0][0] == "KRAX"
        assert radars[0][1] < 45  # ~39 km

    def test_remote_location_returns_empty(self):
        """Middle of Pacific should find nothing within 200 km."""
        radars = find_nearby_radars(0.0, -150.0, max_range_km=200)
        assert len(radars) == 0

    def test_returns_tuples(self):
        radars = find_nearby_radars(35.2, -97.4, max_count=1)
        assert len(radars) == 1
        code, dist = radars[0]
        assert isinstance(code, str)
        assert isinstance(dist, float)


# =============================================================================
# _merge_detections
# =============================================================================

class TestMergeDetections:
    def test_empty_input(self):
        assert _merge_detections([]) == []

    def test_single_detection_passthrough(self):
        dets = [_det(shear=45.0)]
        merged = _merge_detections(dets)
        assert len(merged) == 1
        assert merged[0]["max_shear"] == 45.0
        assert merged[0]["multi_radar_confirmed"] is False
        assert merged[0]["contributing_radar_count"] == 1

    def test_distant_detections_not_merged(self):
        """Detections far apart should remain separate."""
        d1 = _det(lat=35.0, lon=-97.0, shear=50.0)
        d2 = _det(lat=36.0, lon=-96.0, shear=45.0)  # ~130 km away
        merged = _merge_detections([d1, d2])
        assert len(merged) == 2

    def test_nearby_detections_merged(self):
        """Detections within MERGE_PROXIMITY_KM should merge."""
        d1 = _det(lat=35.000, lon=-97.000, shear=50.0, dist_km=30.0)
        d2 = _det(lat=35.002, lon=-97.001, shear=45.0, dist_km=28.0)  # ~0.3 km away
        merged = _merge_detections([d1, d2])
        assert len(merged) == 1
        assert merged[0]["multi_radar_confirmed"] is True
        assert merged[0]["contributing_radar_count"] == 2

    def test_merged_takes_max_shear(self):
        d1 = _det(lat=35.0, lon=-97.0, shear=50.0)
        d2 = _det(lat=35.001, lon=-97.0, shear=60.0)
        merged = _merge_detections([d1, d2])
        assert merged[0]["max_shear"] == 60.0

    def test_merged_averages_position(self):
        d1 = _det(lat=35.000, lon=-97.000)
        d2 = _det(lat=35.010, lon=-97.000)
        merged = _merge_detections([d1, d2])
        assert abs(merged[0]["latitude"] - 35.005) < 0.002

    def test_merged_keeps_closer_distance(self):
        d1 = _det(lat=35.0, lon=-97.0, dist_km=30.0, range_km=40.0)
        d2 = _det(lat=35.001, lon=-97.0, dist_km=25.0, range_km=35.0)
        merged = _merge_detections([d1, d2])
        assert merged[0]["distance_to_station_km"] == 25.0

    def test_confidence_boost_applied(self):
        d1 = _det(lat=35.0, lon=-97.0, threat=0.8)
        d2 = _det(lat=35.001, lon=-97.0, threat=0.7)
        merged = _merge_detections([d1, d2])
        assert merged[0]["threat_score"] == min(1.0, 0.8 * MULTI_RADAR_CONFIDENCE_BOOST)

    def test_threat_score_capped_at_one(self):
        d1 = _det(lat=35.0, lon=-97.0, threat=0.95)
        d2 = _det(lat=35.001, lon=-97.0, threat=0.95)
        merged = _merge_detections([d1, d2])
        assert merged[0]["threat_score"] <= 1.0

    def test_three_radars_merge(self):
        """Three detections of the same feature should merge into one."""
        d1 = _det(lat=35.000, lon=-97.000, shear=45.0)
        d2 = _det(lat=35.002, lon=-97.001, shear=50.0)
        d3 = _det(lat=35.001, lon=-96.999, shear=48.0)
        merged = _merge_detections([d1, d2, d3])
        assert len(merged) == 1
        assert merged[0]["contributing_radar_count"] == 3
        assert merged[0]["max_shear"] == 50.0

    def test_mixed_merge_and_unique(self):
        """Two nearby + one distant = 2 merged results."""
        d1 = _det(lat=35.000, lon=-97.000, shear=50.0)
        d2 = _det(lat=35.001, lon=-97.000, shear=45.0)  # near d1
        d3 = _det(lat=36.000, lon=-96.000, shear=40.0)  # far away
        merged = _merge_detections([d1, d2, d3])
        assert len(merged) == 2
        confirmed = [m for m in merged if m["multi_radar_confirmed"]]
        assert len(confirmed) == 1


# =============================================================================
# _merge_hail_cells
# =============================================================================

class TestMergeHailCells:
    def test_empty_input(self):
        assert _merge_hail_cells([]) == []

    def test_single_cell_passthrough(self):
        cells = [_hail(mesh=30.0)]
        merged = _merge_hail_cells(cells)
        assert len(merged) == 1
        assert merged[0].mesh_mm == 30.0

    def test_nearby_cells_merged(self):
        c1 = _hail(lat=35.000, lon=-97.000, mesh=25.0, vil=30.0)
        c2 = _hail(lat=35.002, lon=-97.001, mesh=35.0, vil=40.0)
        merged = _merge_hail_cells([c1, c2])
        assert len(merged) == 1

    def test_merged_takes_worst_case(self):
        c1 = _hail(lat=35.0, lon=-97.0, mesh=25.0, vil=30.0, dbz=55.0, prob=0.7)
        c2 = _hail(lat=35.001, lon=-97.0, mesh=35.0, vil=40.0, dbz=60.0, prob=0.9)
        merged = _merge_hail_cells([c1, c2])
        assert merged[0].mesh_mm == 35.0
        assert merged[0].vil_kg_m2 == 40.0
        assert merged[0].max_dbz == 60.0
        assert merged[0].hail_probability == 0.9

    def test_distant_cells_not_merged(self):
        c1 = _hail(lat=35.0, lon=-97.0)
        c2 = _hail(lat=36.0, lon=-96.0)
        merged = _merge_hail_cells([c1, c2])
        assert len(merged) == 2

    def test_merged_keeps_closer_distance(self):
        c1 = _hail(lat=35.0, lon=-97.0, dist=30.0, bearing=270.0)
        c2 = _hail(lat=35.001, lon=-97.0, dist=20.0, bearing=265.0)
        merged = _merge_hail_cells([c1, c2])
        assert merged[0].distance_km == 20.0

    def test_merged_takes_larger_estimated_size(self):
        c1 = _hail(lat=35.0, lon=-97.0, size_mm=20.0, size_cat="small")
        c2 = _hail(lat=35.001, lon=-97.0, size_mm=40.0, size_cat="large")
        merged = _merge_hail_cells([c1, c2])
        assert merged[0].estimated_size_mm == 40.0
        assert merged[0].hail_size_category == "large"


# =============================================================================
# merge_radar_results
# =============================================================================

class TestMergeRadarResults:
    def test_empty_list(self):
        result = merge_radar_results([])
        assert result.all_detections == []
        assert result.radar_site == ""

    def test_single_result_passthrough(self):
        r = _result(strong=[_det(shear=50.0)], site="KRAX")
        merged = merge_radar_results([r])
        assert merged is r  # Should return same object

    def test_uses_primary_radar_metadata(self):
        r1 = _result(site="KRAX", rlat=35.67, rlon=-78.49, rdist=39.0)
        r2 = _result(site="KLTX", rlat=33.99, rlon=-78.43, rdist=148.0)
        merged = merge_radar_results([r1, r2])
        assert merged.radar_site == "KRAX"
        assert merged.radar_lat == 35.67
        assert merged.radar_station_dist_km == 39.0

    def test_detections_from_both_radars_included(self):
        d1 = _det(lat=35.0, lon=-97.0, shear=50.0)
        d2 = _det(lat=36.0, lon=-96.0, shear=40.0)
        r1 = _result(strong=[d1], site="KTLX")
        r2 = _result(strong=[d2], site="KOUN")
        merged = merge_radar_results([r1, r2])
        assert len(merged.all_detections) == 2

    def test_overlapping_detections_merged(self):
        d1 = _det(lat=35.0, lon=-97.0, shear=50.0, threat=0.8)
        d2 = _det(lat=35.001, lon=-97.0, shear=55.0, threat=0.7)
        r1 = _result(strong=[d1], site="KTLX")
        r2 = _result(strong=[d2], site="KOUN")
        merged = merge_radar_results([r1, r2])
        assert len(merged.all_detections) == 1
        assert merged.all_detections[0]["max_shear"] == 55.0
        assert merged.all_detections[0]["multi_radar_confirmed"] is True

    def test_hail_cells_merged(self):
        h1 = _hail(lat=35.0, lon=-97.0, mesh=25.0)
        h2 = _hail(lat=35.001, lon=-97.0, mesh=35.0)
        r1 = _result(hail=[h1], site="KTLX")
        r2 = _result(hail=[h2], site="KOUN")
        merged = merge_radar_results([r1, r2])
        assert len(merged.hail_cells) == 1
        assert merged.hail_cells[0].mesh_mm == 35.0

    def test_qlcs_from_first_radar_used(self):
        line = QLCSLine(
            leading_edge_points=[], centroid_lat=35.0, centroid_lon=-97.0,
            axis_bearing_deg=90.0, length_km=50.0,
            distance_to_station_km=10.0, approach_bearing_deg=270.0,
        )
        r1 = _result(qlcs=line, site="KTLX")
        r2 = _result(site="KOUN")
        merged = merge_radar_results([r1, r2])
        assert merged.qlcs_line is line

    def test_strong_moderate_reclassified(self):
        """After merge, detections are re-classified by threat_score."""
        d_high = _det(shear=55.0, threat=0.8)
        d_low = _det(lat=36.0, lon=-96.0, shear=30.0, threat=0.3)
        r1 = _result(strong=[d_high], site="KTLX")
        r2 = _result(moderate=[d_low], site="KOUN")
        merged = merge_radar_results([r1, r2])
        assert len(merged.strong_detections) == 1
        assert len(merged.moderate_detections) == 1

    def test_timestamp_from_primary(self):
        r1 = _result(site="KRAX")
        r2 = _result(site="KLTX")
        merged = merge_radar_results([r1, r2])
        assert merged.radar_timestamp == T0
