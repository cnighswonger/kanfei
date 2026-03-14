"""
Tests for MRMS cross-validation models, knowledge formatting, and loader logic.

Unit tests run without S3/cfgrib dependencies.
Integration tests (marked with pytest.mark.skipif) require S3 + cfgrib.
"""

import math
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# --------------------------------------------------------------------------- #
# Data model tests (no external deps)
# --------------------------------------------------------------------------- #


class TestMRMSDataModels:
    """Test MRMSPointExtraction and MRMSSnapshot dataclasses."""

    def test_point_extraction_defaults(self):
        from app.models.radar_threats import MRMSPointExtraction

        pt = MRMSPointExtraction(lat=35.2, lon=-97.4)
        assert pt.lat == 35.2
        assert pt.lon == -97.4
        assert pt.azshear_0_2km is None
        assert pt.azshear_3_6km is None
        assert pt.rot_track_30min is None
        assert pt.mesh_mm is None
        assert pt.vil_kg_m2 is None

    def test_point_extraction_with_values(self):
        from app.models.radar_threats import MRMSPointExtraction

        pt = MRMSPointExtraction(
            lat=35.2, lon=-97.4,
            azshear_0_2km=48.0, azshear_3_6km=32.0,
            rot_track_30min=55.0, mesh_mm=52.0, vil_kg_m2=48.0,
        )
        assert pt.azshear_0_2km == 48.0
        assert pt.mesh_mm == 52.0

    def test_snapshot_construction(self):
        from app.models.radar_threats import MRMSPointExtraction, MRMSSnapshot

        ts = datetime(2024, 5, 1, 18, 0, 0, tzinfo=timezone.utc)
        snap = MRMSSnapshot(timestamp=ts, data_age_seconds=2.5)
        assert snap.timestamp == ts
        assert snap.data_age_seconds == 2.5
        assert snap.meso_validations == []
        assert snap.hail_validations == []
        assert snap.mrms_only_detections == []

    def test_snapshot_with_validations(self):
        from app.models.radar_threats import MRMSPointExtraction, MRMSSnapshot

        ts = datetime(2024, 5, 1, 18, 0, 0, tzinfo=timezone.utc)
        mrms_pt = MRMSPointExtraction(lat=35.2, lon=-97.4, azshear_0_2km=48.0)

        snap = MRMSSnapshot(
            timestamp=ts,
            data_age_seconds=3.0,
            meso_validations=[{
                'meso_id': 'MESO-1', 'lat': 35.2, 'lon': -97.4,
                'mrms': mrms_pt, 'verdict': 'CONFIRMED',
            }],
            hail_validations=[{
                'lat': 35.18, 'lon': -97.35,
                'level2_mesh_mm': 45.0,
                'mrms': MRMSPointExtraction(lat=35.18, lon=-97.35, mesh_mm=52.0),
                'verdict': 'AGREES',
            }],
            mrms_only_detections=[{
                'lat': 35.3, 'lon': -97.5,
                'azshear_0_2km': 35.0,
                'distance_km': 22.0,
                'bearing_cardinal': 'NW',
            }],
        )
        assert len(snap.meso_validations) == 1
        assert snap.meso_validations[0]['verdict'] == 'CONFIRMED'
        assert len(snap.hail_validations) == 1
        assert len(snap.mrms_only_detections) == 1


# --------------------------------------------------------------------------- #
# Knowledge formatter tests
# --------------------------------------------------------------------------- #


class TestFormatMRMSKnowledge:
    """Test format_mrms_knowledge() with synthetic snapshots."""

    def test_none_returns_none(self):
        from app.services.knowledge_formatter import format_mrms_knowledge
        assert format_mrms_knowledge(None) is None

    def test_empty_snapshot_returns_none(self):
        from app.models.radar_threats import MRMSSnapshot
        from app.services.knowledge_formatter import format_mrms_knowledge

        snap = MRMSSnapshot(
            timestamp=datetime(2024, 5, 1, 18, 0, tzinfo=timezone.utc),
            data_age_seconds=1.0,
        )
        assert format_mrms_knowledge(snap) is None

    def test_meso_confirmed(self):
        from app.models.radar_threats import MRMSPointExtraction, MRMSSnapshot
        from app.services.knowledge_formatter import format_mrms_knowledge

        snap = MRMSSnapshot(
            timestamp=datetime(2024, 5, 1, 18, 0, tzinfo=timezone.utc),
            data_age_seconds=2.0,
            meso_validations=[{
                'meso_id': 'MESO-1',
                'lat': 35.20, 'lon': -97.40,
                'mrms': MRMSPointExtraction(
                    lat=35.20, lon=-97.40,
                    azshear_0_2km=48.0, azshear_3_6km=32.0,
                    rot_track_30min=55.0,
                ),
                'verdict': 'CONFIRMED',
            }],
        )
        result = format_mrms_knowledge(snap)
        assert result is not None
        assert 'MRMS CROSS-VALIDATION' in result
        assert 'MESO-1' in result
        assert 'CONFIRMED' in result
        assert 'AzShear 0-2km=48' in result

    def test_meso_weak(self):
        from app.models.radar_threats import MRMSPointExtraction, MRMSSnapshot
        from app.services.knowledge_formatter import format_mrms_knowledge

        snap = MRMSSnapshot(
            timestamp=datetime(2024, 5, 1, 18, 0, tzinfo=timezone.utc),
            data_age_seconds=2.0,
            meso_validations=[{
                'meso_id': 'MESO-2',
                'lat': 35.15, 'lon': -97.35,
                'mrms': MRMSPointExtraction(
                    lat=35.15, lon=-97.35,
                    azshear_0_2km=15.0, azshear_3_6km=5.0,
                ),
                'verdict': 'WEAK',
            }],
        )
        result = format_mrms_knowledge(snap)
        assert 'WEAK' in result
        assert 'possible false positive' in result

    def test_meso_absent(self):
        from app.models.radar_threats import MRMSPointExtraction, MRMSSnapshot
        from app.services.knowledge_formatter import format_mrms_knowledge

        snap = MRMSSnapshot(
            timestamp=datetime(2024, 5, 1, 18, 0, tzinfo=timezone.utc),
            data_age_seconds=2.0,
            meso_validations=[{
                'meso_id': 'MESO-3',
                'lat': 35.10, 'lon': -97.30,
                'mrms': MRMSPointExtraction(
                    lat=35.10, lon=-97.30,
                    azshear_0_2km=5.0,
                ),
                'verdict': 'ABSENT',
            }],
        )
        result = format_mrms_knowledge(snap)
        assert 'ABSENT' in result
        assert 'NOT confirmed' in result

    def test_hail_agrees(self):
        from app.models.radar_threats import MRMSPointExtraction, MRMSSnapshot
        from app.services.knowledge_formatter import format_mrms_knowledge

        snap = MRMSSnapshot(
            timestamp=datetime(2024, 5, 1, 18, 0, tzinfo=timezone.utc),
            data_age_seconds=2.0,
            hail_validations=[{
                'lat': 35.18, 'lon': -97.35,
                'level2_mesh_mm': 45.0,
                'mrms': MRMSPointExtraction(
                    lat=35.18, lon=-97.35,
                    mesh_mm=52.0, vil_kg_m2=48.0,
                ),
                'verdict': 'AGREES',
            }],
        )
        result = format_mrms_knowledge(snap)
        assert 'Hail cross-validation' in result
        assert 'L2 MESH=45mm' in result
        assert 'MRMS MESH=52mm' in result
        assert 'AGREES' in result
        assert 'CONFIRMED by independent multi-radar' in result
        # Summary line present
        assert 'SUMMARY' in result
        assert 'Hail: 1/1 AGREES' in result

    def test_hail_mrms_higher(self):
        from app.models.radar_threats import MRMSPointExtraction, MRMSSnapshot
        from app.services.knowledge_formatter import format_mrms_knowledge

        snap = MRMSSnapshot(
            timestamp=datetime(2024, 5, 1, 18, 0, tzinfo=timezone.utc),
            data_age_seconds=2.0,
            hail_validations=[
                {
                    'lat': 35.18, 'lon': -97.35,
                    'level2_mesh_mm': 30.0,
                    'mrms': MRMSPointExtraction(
                        lat=35.18, lon=-97.35, mesh_mm=55.0, vil_kg_m2=50.0,
                    ),
                    'verdict': 'MRMS_HIGHER',
                },
                {
                    'lat': 35.20, 'lon': -97.40,
                    'level2_mesh_mm': 40.0,
                    'mrms': MRMSPointExtraction(
                        lat=35.20, lon=-97.40, mesh_mm=42.0,
                    ),
                    'verdict': 'AGREES',
                },
            ],
        )
        result = format_mrms_knowledge(snap)
        assert 'MRMS_HIGHER' in result
        assert 'MRMS sees LARGER hail' in result
        assert 'use higher value' in result
        # Summary shows counts
        assert 'Hail: 1/2 AGREES' in result
        assert '1 MRMS_HIGHER' in result

    def test_mrms_only_detection(self):
        from app.models.radar_threats import MRMSSnapshot
        from app.services.knowledge_formatter import format_mrms_knowledge

        snap = MRMSSnapshot(
            timestamp=datetime(2024, 5, 1, 18, 0, tzinfo=timezone.utc),
            data_age_seconds=2.0,
            mrms_only_detections=[{
                'lat': 35.30, 'lon': -97.50,
                'azshear_0_2km': 35.0,
                'distance_km': 22.0,
                'bearing_cardinal': 'NW',
            }],
        )
        result = format_mrms_knowledge(snap)
        assert 'MRMS-ONLY ROTATION' in result
        assert 'cone-of-silence' in result
        assert '22 km NW' in result
        assert 'NOT in Level II' in result
        assert 'single-radar may NOT see' in result

    def test_full_snapshot_all_sections(self):
        from app.models.radar_threats import MRMSPointExtraction, MRMSSnapshot
        from app.services.knowledge_formatter import format_mrms_knowledge

        snap = MRMSSnapshot(
            timestamp=datetime(2024, 5, 1, 18, 0, tzinfo=timezone.utc),
            data_age_seconds=3.0,
            meso_validations=[{
                'meso_id': 'MESO-1', 'lat': 35.20, 'lon': -97.40,
                'mrms': MRMSPointExtraction(
                    lat=35.20, lon=-97.40, azshear_0_2km=48.0,
                ),
                'verdict': 'CONFIRMED',
            }],
            hail_validations=[{
                'lat': 35.18, 'lon': -97.35, 'level2_mesh_mm': 45.0,
                'mrms': MRMSPointExtraction(
                    lat=35.18, lon=-97.35, mesh_mm=52.0,
                ),
                'verdict': 'AGREES',
            }],
            mrms_only_detections=[{
                'lat': 35.30, 'lon': -97.50,
                'azshear_0_2km': 35.0,
                'distance_km': 22.0,
                'bearing_cardinal': 'NW',
            }],
        )
        result = format_mrms_knowledge(snap)
        # Summary line at top
        assert 'SUMMARY' in result
        assert 'Rotation: 1/1 CONFIRMED' in result
        assert 'Hail: 1/1 AGREES' in result
        assert '1 MRMS-only' in result
        # All three sections present
        assert 'Rotation cross-validation' in result
        assert 'Hail cross-validation' in result
        assert 'MRMS-ONLY ROTATION' in result


# --------------------------------------------------------------------------- #
# Verdict logic tests
# --------------------------------------------------------------------------- #


class TestMRMSVerdicts:
    """Test verdict threshold logic in MRMSLoader."""

    def test_meso_verdict_confirmed(self):
        from app.models.radar_threats import MRMSPointExtraction
        from app.services.mrms_loader import MRMSLoader

        # Threshold is 10 (calibrated from observed MRMS during EF3-EF5 tornadoes)
        pt = MRMSPointExtraction(lat=0, lon=0, azshear_0_2km=10.0)
        assert MRMSLoader._meso_verdict(pt) == 'CONFIRMED'

        pt2 = MRMSPointExtraction(lat=0, lon=0, azshear_0_2km=19.0)
        assert MRMSLoader._meso_verdict(pt2) == 'CONFIRMED'

    def test_meso_verdict_weak(self):
        from app.models.radar_threats import MRMSPointExtraction
        from app.services.mrms_loader import MRMSLoader

        # Weak range: 4 ≤ azshear < 10
        pt = MRMSPointExtraction(lat=0, lon=0, azshear_0_2km=4.0)
        assert MRMSLoader._meso_verdict(pt) == 'WEAK'

        pt2 = MRMSPointExtraction(lat=0, lon=0, azshear_0_2km=9.0)
        assert MRMSLoader._meso_verdict(pt2) == 'WEAK'

    def test_meso_verdict_absent(self):
        from app.models.radar_threats import MRMSPointExtraction
        from app.services.mrms_loader import MRMSLoader

        pt = MRMSPointExtraction(lat=0, lon=0, azshear_0_2km=3.0)
        assert MRMSLoader._meso_verdict(pt) == 'ABSENT'

        pt2 = MRMSPointExtraction(lat=0, lon=0, azshear_0_2km=0.0)
        assert MRMSLoader._meso_verdict(pt2) == 'ABSENT'

    def test_meso_verdict_no_data(self):
        from app.models.radar_threats import MRMSPointExtraction
        from app.services.mrms_loader import MRMSLoader

        pt = MRMSPointExtraction(lat=0, lon=0)  # azshear_0_2km is None
        assert MRMSLoader._meso_verdict(pt) == 'NO_DATA'

    def test_hail_verdict_agrees(self):
        from app.models.radar_threats import MRMSPointExtraction
        from app.services.mrms_loader import MRMSLoader

        pt = MRMSPointExtraction(lat=0, lon=0, mesh_mm=45.0)
        assert MRMSLoader._hail_verdict(40.0, pt) == 'AGREES'

    def test_hail_verdict_mrms_higher(self):
        from app.models.radar_threats import MRMSPointExtraction
        from app.services.mrms_loader import MRMSLoader

        pt = MRMSPointExtraction(lat=0, lon=0, mesh_mm=80.0)
        assert MRMSLoader._hail_verdict(40.0, pt) == 'MRMS_HIGHER'

    def test_hail_verdict_mrms_lower(self):
        from app.models.radar_threats import MRMSPointExtraction
        from app.services.mrms_loader import MRMSLoader

        pt = MRMSPointExtraction(lat=0, lon=0, mesh_mm=10.0)
        assert MRMSLoader._hail_verdict(40.0, pt) == 'MRMS_LOWER'

    def test_hail_verdict_absent(self):
        from app.models.radar_threats import MRMSPointExtraction
        from app.services.mrms_loader import MRMSLoader

        pt = MRMSPointExtraction(lat=0, lon=0, mesh_mm=0.0)
        assert MRMSLoader._hail_verdict(40.0, pt) == 'ABSENT'

    def test_hail_verdict_no_data(self):
        from app.models.radar_threats import MRMSPointExtraction
        from app.services.mrms_loader import MRMSLoader

        pt = MRMSPointExtraction(lat=0, lon=0)  # mesh_mm is None
        assert MRMSLoader._hail_verdict(40.0, pt) == 'NO_DATA'


# --------------------------------------------------------------------------- #
# build_knowledge_entries integration
# --------------------------------------------------------------------------- #


class TestBuildKnowledgeEntriesWithMRMS:
    """Test that mrms_snapshot parameter flows through build_knowledge_entries."""

    def test_none_mrms_no_change(self):
        from app.models.radar_threats import ThreatTrackerState
        from app.services.knowledge_formatter import build_knowledge_entries

        state = ThreatTrackerState()
        result = build_knowledge_entries(tracker_state=state, mrms_snapshot=None)
        # No MRMS block in output
        for entry in result:
            assert 'MRMS' not in entry

    def test_mrms_snapshot_included(self):
        from app.models.radar_threats import (
            MRMSPointExtraction, MRMSSnapshot, ThreatTrackerState,
        )
        from app.services.knowledge_formatter import build_knowledge_entries

        snap = MRMSSnapshot(
            timestamp=datetime(2024, 5, 1, 18, 0, tzinfo=timezone.utc),
            data_age_seconds=2.0,
            meso_validations=[{
                'meso_id': 'MESO-1', 'lat': 35.20, 'lon': -97.40,
                'mrms': MRMSPointExtraction(
                    lat=35.20, lon=-97.40, azshear_0_2km=48.0,
                ),
                'verdict': 'CONFIRMED',
            }],
        )
        state = ThreatTrackerState()
        result = build_knowledge_entries(tracker_state=state, mrms_snapshot=snap)
        mrms_entries = [e for e in result if 'MRMS' in e]
        assert len(mrms_entries) == 1
        assert 'CONFIRMED' in mrms_entries[0]


# --------------------------------------------------------------------------- #
# Extract point tests (with synthetic numpy arrays)
# --------------------------------------------------------------------------- #

try:
    import numpy as np
    import xarray as xr
    HAS_XARRAY = True
except ImportError:
    HAS_XARRAY = False


@pytest.mark.skipif(not HAS_XARRAY, reason="xarray/numpy not installed")
class TestExtractPoint:
    """Test extract_point() with synthetic xarray DataArrays."""

    def _make_loader(self):
        """Create an MRMSLoader with mocked S3 client."""
        from app.services.mrms_loader import MRMSLoader
        with patch('app.services.mrms_loader.boto3') as mock_boto:
            mock_boto.client.return_value = MagicMock()
            loader = MRMSLoader.__new__(MRMSLoader)
            loader.cache_dir = None
            loader.log = lambda msg: None
            loader.s3 = None
        return loader

    def _make_grid(self, lat_range, lon_range, values):
        """Create a synthetic xarray DataArray."""
        lats = np.linspace(lat_range[0], lat_range[1], values.shape[0])
        lons = np.linspace(lon_range[0], lon_range[1], values.shape[1])
        return xr.DataArray(
            values,
            dims=['latitude', 'longitude'],
            coords={'latitude': lats, 'longitude': lons},
        )

    def test_extract_center(self):
        loader = self._make_loader()
        data = np.zeros((100, 100))
        data[50, 50] = 42.0
        grid = self._make_grid((34.0, 36.0), (-98.0, -96.0), data)

        # Extract at center of a cell near (50,50)
        val = loader.extract_point(grid, 35.0, -97.0)
        assert val is not None
        assert val == pytest.approx(42.0, abs=0.1)

    def test_extract_out_of_bounds(self):
        loader = self._make_loader()
        data = np.ones((10, 10)) * 5.0
        grid = self._make_grid((34.0, 36.0), (-98.0, -96.0), data)

        # Point within grid should work
        val = loader.extract_point(grid, 35.0, -97.0)
        assert val is not None

    def test_extract_none_grid(self):
        loader = self._make_loader()
        val = loader.extract_point(None, 35.0, -97.0)
        assert val is None

    def test_extract_missing_value(self):
        loader = self._make_loader()
        data = np.full((10, 10), np.nan)
        grid = self._make_grid((34.0, 36.0), (-98.0, -96.0), data)

        val = loader.extract_point(grid, 35.0, -97.0)
        assert val is None


@pytest.mark.skipif(not HAS_XARRAY, reason="xarray/numpy not installed")
class TestExtractNeighborhoodMax:
    """Test extract_neighborhood_max() with synthetic data."""

    def _make_loader(self):
        from app.services.mrms_loader import MRMSLoader
        with patch('app.services.mrms_loader.boto3') as mock_boto:
            mock_boto.client.return_value = MagicMock()
            loader = MRMSLoader.__new__(MRMSLoader)
            loader.cache_dir = None
            loader.log = lambda msg: None
            loader.s3 = None
        return loader

    def _make_grid(self, lat_range, lon_range, values):
        lats = np.linspace(lat_range[0], lat_range[1], values.shape[0])
        lons = np.linspace(lon_range[0], lon_range[1], values.shape[1])
        return xr.DataArray(
            values,
            dims=['latitude', 'longitude'],
            coords={'latitude': lats, 'longitude': lons},
        )

    def test_captures_nearby_peak(self):
        """Peak 5 cells away from query point should be captured with radius=10."""
        loader = self._make_loader()
        data = np.zeros((100, 100))
        data[55, 50] = 19.0  # Peak offset 5 cells from center
        grid = self._make_grid((34.0, 36.0), (-98.0, -96.0), data)

        val = loader.extract_neighborhood_max(grid, 35.0, -97.0, radius_cells=10)
        assert val == 19.0

    def test_misses_distant_peak(self):
        """Peak 20 cells away should NOT be captured with radius=10."""
        loader = self._make_loader()
        data = np.zeros((100, 100))
        data[70, 50] = 19.0  # Peak 20 cells away
        grid = self._make_grid((34.0, 36.0), (-98.0, -96.0), data)

        val = loader.extract_neighborhood_max(grid, 35.0, -97.0, radius_cells=10)
        # Should return 0.0 (max of the neighborhood which is all zeros)
        assert val == 0.0

    def test_returns_max_not_nearest(self):
        """Should return max value in neighborhood, not nearest."""
        loader = self._make_loader()
        data = np.zeros((100, 100))
        data[50, 50] = 3.0   # At query point
        data[52, 48] = 15.0  # Nearby but higher
        grid = self._make_grid((34.0, 36.0), (-98.0, -96.0), data)

        val = loader.extract_neighborhood_max(grid, 35.0, -97.0, radius_cells=10)
        assert val == 15.0

    def test_excludes_negative_values(self):
        """Negative MRMS values (missing data) should be excluded."""
        loader = self._make_loader()
        data = np.full((100, 100), -3.0)  # All missing
        data[50, 50] = 5.0  # One valid cell
        grid = self._make_grid((34.0, 36.0), (-98.0, -96.0), data)

        val = loader.extract_neighborhood_max(grid, 35.0, -97.0, radius_cells=10)
        assert val == 5.0

    def test_all_missing_returns_none(self):
        """All negative values should return None."""
        loader = self._make_loader()
        data = np.full((100, 100), -999.0)
        grid = self._make_grid((34.0, 36.0), (-98.0, -96.0), data)

        val = loader.extract_neighborhood_max(grid, 35.0, -97.0, radius_cells=10)
        assert val is None

    def test_none_grid(self):
        loader = self._make_loader()
        val = loader.extract_neighborhood_max(None, 35.0, -97.0)
        assert val is None

    def test_lon_360_conversion(self):
        """Grid in 0-360 longitude, query in -180..180."""
        loader = self._make_loader()
        data = np.zeros((100, 100))
        data[50, 50] = 12.0
        # Grid uses 0-360 longitudes (262-264 = -98 to -96)
        grid = self._make_grid((34.0, 36.0), (262.0, 264.0), data)

        val = loader.extract_neighborhood_max(grid, 35.0, -97.0, radius_cells=10)
        assert val == 12.0


@pytest.mark.skipif(not HAS_XARRAY, reason="xarray/numpy not installed")
class TestFindPeaks:
    """Test find_peaks_in_region() with synthetic data."""

    def _make_loader(self):
        from app.services.mrms_loader import MRMSLoader
        loader = MRMSLoader.__new__(MRMSLoader)
        loader.cache_dir = None
        loader.log = lambda msg: None
        loader.s3 = None
        return loader

    def _make_grid(self, lat_range, lon_range, values):
        lats = np.linspace(lat_range[0], lat_range[1], values.shape[0])
        lons = np.linspace(lon_range[0], lon_range[1], values.shape[1])
        return xr.DataArray(
            values,
            dims=['latitude', 'longitude'],
            coords={'latitude': lats, 'longitude': lons},
        )

    def test_single_peak(self):
        loader = self._make_loader()
        data = np.zeros((100, 100))
        data[50, 50] = 45.0  # One peak at ~center
        grid = self._make_grid((34.0, 36.0), (-98.0, -96.0), data)

        peaks = loader.find_peaks_in_region(
            grid, threshold=30.0,
            station_lat=35.0, station_lon=-97.0,
        )
        assert len(peaks) == 1
        assert peaks[0]['value'] == 45.0

    def test_no_peaks_below_threshold(self):
        loader = self._make_loader()
        data = np.ones((100, 100)) * 10.0
        grid = self._make_grid((34.0, 36.0), (-98.0, -96.0), data)

        peaks = loader.find_peaks_in_region(
            grid, threshold=30.0,
            station_lat=35.0, station_lon=-97.0,
        )
        assert len(peaks) == 0

    def test_peaks_beyond_range_excluded(self):
        loader = self._make_loader()
        data = np.zeros((100, 100))
        # Place peak far from station
        data[0, 0] = 50.0  # At ~(34.0, -98.0) — ~150km from station at (35, -97)
        grid = self._make_grid((34.0, 36.0), (-98.0, -96.0), data)

        peaks = loader.find_peaks_in_region(
            grid, threshold=30.0,
            station_lat=35.0, station_lon=-97.0,
            max_range_km=50.0,  # Very short range
        )
        # Peak at (34.0, -98.0) is ~140km from (35, -97), should be excluded
        assert len(peaks) == 0

    def test_none_grid(self):
        loader = self._make_loader()
        peaks = loader.find_peaks_in_region(
            None, threshold=30.0,
            station_lat=35.0, station_lon=-97.0,
        )
        assert peaks == []
