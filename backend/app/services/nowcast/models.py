"""
Shared data models for radar threat detection, tracking, and surface analysis.

These models are used by both the production nowcast service and the
historic event simulation framework. They contain no external dependencies
beyond the Python standard library.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two lat/lon points using haversine formula."""
    R = 6371  # Earth radius in km
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate bearing from point 1 to point 2 in degrees (0=N, 90=E)."""
    dlon = math.radians(lon2 - lon1)
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon) * math.cos(lat2_r)
    y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


def bearing_to_cardinal(bearing_deg: float) -> str:
    """Convert bearing degrees to cardinal direction (N, NE, E, etc.)"""
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    idx = int((bearing_deg + 11.25) / 22.5) % 16
    return directions[idx]


# =============================================================================
# QLCS LINE TRACKING
# =============================================================================

@dataclass
class QLCSLine:
    """Tracked convective line (QLCS leading edge)."""
    leading_edge_points: list       # [(lat, lon), ...] — 40+ dBZ points closest to station
    centroid_lat: float             # Centroid of leading edge
    centroid_lon: float
    axis_bearing_deg: float         # Line orientation (PCA first component, 0=N-S, 90=E-W)
    length_km: float                # Extent of the line
    distance_to_station_km: float   # Closest leading edge point to station
    approach_bearing_deg: float     # Bearing FROM station TO closest line point

    # Motion (computed from centroid history)
    motion_speed_kmh: float = None
    motion_bearing_deg: float = None
    eta_minutes: float = None

    # History for motion computation
    centroid_history: list = None    # [(iso_timestamp, lat, lon), ...] capped at 8


@dataclass
class ThreatCorridor:
    """Threat corridor — segment of QLCS line aimed at station."""
    corridor_half_width_km: float = 15.0   # ±15km perpendicular to approach vector
    rotation_detections: list = None        # [(timestamp, lat, lon, shear, dist_to_station), ...]
    rotation_count_30min: int = 0
    max_shear_30min: float = 0.0
    nearest_rotation_km: float = None       # Closest rotation detection to station
    nearest_rotation_age_min: float = None  # How many minutes ago
    has_active_rotation: bool = False       # Any rotation in corridor in last 2 cycles (10 min)


# =============================================================================
# HAIL DETECTION
# =============================================================================

@dataclass
class HailCell:
    """Detected hail signature for current cycle."""
    lat: float
    lon: float
    distance_km: float
    bearing_deg: float
    vil_kg_m2: float
    max_dbz: float
    mesh_mm: float
    hail_probability: float
    hail_size_category: str
    estimated_size_mm: float
    column_height_45dbz_m: float
    echo_top_m: float
    overshoot_m: float  # Height of 45+ dBZ above freezing level (updraft proxy)


# =============================================================================
# MRMS CROSS-VALIDATION
# =============================================================================

@dataclass
class MRMSPointExtraction:
    """MRMS values extracted at a single geographic point."""
    lat: float
    lon: float
    azshear_0_2km: Optional[float] = None   # ×10⁻³ s⁻¹
    azshear_3_6km: Optional[float] = None
    rot_track_30min: Optional[float] = None
    mesh_mm: Optional[float] = None
    vil_kg_m2: Optional[float] = None


@dataclass
class MRMSSnapshot:
    """Single-cycle MRMS cross-validation results."""
    timestamp: datetime
    data_age_seconds: float

    # Per-detection cross-validation
    meso_validations: List[dict] = field(default_factory=list)
    # {meso_id, lat, lon, mrms: MRMSPointExtraction, verdict: str}

    hail_validations: List[dict] = field(default_factory=list)
    # {lat, lon, level2_mesh_mm, mrms: MRMSPointExtraction, verdict: str}

    # MRMS rotation not matching any Level II detection
    mrms_only_detections: List[dict] = field(default_factory=list)
    # {lat, lon, azshear_0_2km, distance_km, bearing_cardinal}


# =============================================================================
# STORM REGIME CLASSIFICATION
# =============================================================================

class StormRegime(Enum):
    """Storm environment classification for adaptive tracking parameters."""
    UNKNOWN = "unknown"           # Initial state, not enough data
    DISCRETE = "discrete"         # Isolated supercells, slow (15-30 mph), persistent mesos
    QLCS = "qlcs"                 # Squall line / QLCS, fast (40-60+ mph), embedded rotation
    OUTBREAK = "outbreak"         # Multiple simultaneous supercells, moderate speed


@dataclass
class RegimeParameters:
    """Tracking parameters adapted to the current storm regime."""
    persistence_threshold_km: float   # Max distance for raw-position matching
    predicted_match_km: float         # Max distance for predicted-position matching
    dissipation_cycles: int           # Missed cycles before removal
    speed_outlier_kmh: float          # Threshold for flagging outlier speeds
    speed_implausible_kmh: float      # Threshold for flagging implausible speeds
    history_cap: int                  # Max entries in distance/position history
    association_threshold_km: float   # Max distance for cross-meso association
    association_window_cycles: int    # How recent a dissipation must be for association


# Default parameter sets per storm regime
REGIME_PARAMS: Dict[StormRegime, RegimeParameters] = {
    StormRegime.UNKNOWN: RegimeParameters(
        persistence_threshold_km=25.0, predicted_match_km=15.0,
        dissipation_cycles=2, speed_outlier_kmh=80, speed_implausible_kmh=130,
        history_cap=6, association_threshold_km=15.0, association_window_cycles=3,
    ),
    StormRegime.DISCRETE: RegimeParameters(
        persistence_threshold_km=20.0, predicted_match_km=12.0,
        dissipation_cycles=2, speed_outlier_kmh=70, speed_implausible_kmh=100,
        history_cap=6, association_threshold_km=10.0, association_window_cycles=2,
    ),
    StormRegime.QLCS: RegimeParameters(
        persistence_threshold_km=40.0, predicted_match_km=20.0,
        dissipation_cycles=3, speed_outlier_kmh=120, speed_implausible_kmh=180,
        history_cap=8, association_threshold_km=30.0, association_window_cycles=4,
    ),
    StormRegime.OUTBREAK: RegimeParameters(
        persistence_threshold_km=30.0, predicted_match_km=15.0,
        dissipation_cycles=2, speed_outlier_kmh=90, speed_implausible_kmh=150,
        history_cap=6, association_threshold_km=20.0, association_window_cycles=3,
    ),
}


# =============================================================================
# MESOCYCLONE TRACKING
# =============================================================================

@dataclass
class TrackedMesocyclone:
    """Represents a mesocyclone being tracked across multiple cycles."""
    id: str  # "MESO-1", "MESO-2", etc.
    first_detected: datetime
    last_seen: datetime
    cycle_count: int  # Number of cycles tracked

    # Current state
    lat: float
    lon: float
    distance_km: float
    bearing_deg: float
    shear: float
    threat_score: float
    elevation_angle: float

    # Previous state (for movement tracking)
    prev_distance_km: float = None
    prev_shear: float = None

    # Distance history for multi-cycle sliding window speed calculation
    # List of (iso_timestamp, distance_km) tuples
    distance_history: list = None

    # Position history for motion vector computation
    # List of (iso_timestamp, lat, lon) tuples
    position_history: list = None

    # Computed motion vector
    motion_speed_kmh: float = None   # Speed in km/hr
    motion_bearing_deg: float = None  # Bearing in degrees (0=N, 90=E)

    # Association lineage (if this meso absorbed dissipated ones)
    absorbed_ids: list = None  # ["MESO-5", "MESO-12", ...]

    # Lifecycle status
    status: str = "tracking"  # "tracking", "dissipating", "intensifying", "new"

    # Raw detection data
    raw_detection: dict = None


# =============================================================================
# SURFACE OBSERVATION TRACKING
# =============================================================================

@dataclass
class CWOPReading:
    """Single CWOP station reading at a point in time, stored for cycle-to-cycle trending."""
    timestamp: datetime
    pressure_inhg: Optional[float] = None
    temp_f: Optional[float] = None
    dew_point_f: Optional[float] = None
    wind_speed_mph: Optional[float] = None
    wind_dir_deg: Optional[int] = None
    distance_miles: float = 0.0
    bearing_cardinal: str = ""
    lat: float = 0.0
    lon: float = 0.0


@dataclass
class StationTrend:
    """Pre-computed trend for one CWOP station across cycles (rates only, no conclusions)."""
    station_id: str
    distance_miles: float
    bearing_cardinal: str
    lat: float
    lon: float
    pressure_rate_inhg_hr: Optional[float] = None  # negative = falling
    temp_rate_f_hr: Optional[float] = None          # negative = cooling
    wind_shift_deg: Optional[float] = None          # absolute change in direction
    latest_pressure: Optional[float] = None
    latest_temp: Optional[float] = None
    latest_wind_dir: Optional[int] = None
    latest_wind_speed: Optional[float] = None
    oldest_temp: Optional[float] = None
    oldest_wind_dir: Optional[int] = None
    readings_count: int = 0
    time_span_min: float = 0.0
    recent_pressure_change: Optional[float] = None  # inHg change in last 15 min
    recent_temp_change: Optional[float] = None       # °F change in last 15 min


# =============================================================================
# MODULE STATE CONTAINERS
# =============================================================================

@dataclass
class ThreatTrackerState:
    """Persistent state for the threat tracking system across cycles."""
    # Cycle counter (for regime classification hysteresis)
    cycle_count: int = 0

    # Mesocyclone tracking
    tracked_mesocyclones: List[TrackedMesocyclone] = field(default_factory=list)
    next_meso_id: int = 1
    dissipated_mesocyclones: List[TrackedMesocyclone] = field(default_factory=list)

    # Storm regime
    current_regime: StormRegime = field(default=StormRegime.UNKNOWN)
    regime_candidate: Optional[StormRegime] = None
    regime_candidate_count: int = 0
    last_valid_displacement: float = 0.0

    # QLCS
    tracked_qlcs_line: Optional[QLCSLine] = None
    threat_corridor: Optional[ThreatCorridor] = None
    rotation_history: list = field(default_factory=list)

    # Hail
    hail_cells: Optional[List[HailCell]] = None
    previous_hail_cells: Optional[List[HailCell]] = None
    moderate_rotation_detections: list = field(default_factory=list)


@dataclass
class SurfaceAnalyzerState:
    """Persistent state for surface trend analysis across cycles."""
    cwop_station_history: Dict[str, List[CWOPReading]] = field(default_factory=dict)
    meso_cwop_station_history: Dict[str, List[CWOPReading]] = field(default_factory=dict)
    corridor_cwop_station_history: Dict[str, List[CWOPReading]] = field(default_factory=dict)


@dataclass
class RadarProcessingResult:
    """Result of processing a single radar volume through all detection algorithms."""
    all_detections: List[dict]          # All meso candidates from NEXRAD
    strong_detections: List[dict]       # Filtered >40 s^-1 within range
    moderate_detections: List[dict]     # 20-40 s^-1 for hail-rotation collocation
    hail_cells: Optional[List[HailCell]]
    qlcs_line: Optional[QLCSLine]
    primary_detection: Optional[dict]   # Legacy single-meso format (highest threat)
    radar_timestamp: Optional[datetime]
    radar_site: str
    radar_lat: float = 0.0
    radar_lon: float = 0.0
    radar_station_dist_km: float = 0.0
