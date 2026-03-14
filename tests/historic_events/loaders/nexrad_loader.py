"""
NEXRAD Level II Data Loader.

Retrieves historic NEXRAD Level II data from AWS S3 and processes it using Py-ART
to generate radar products (reflectivity, velocity, derived products).
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import tempfile

try:
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config
except ImportError:
    boto3 = None

try:
    import pyart
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
except ImportError:
    pyart = None
    np = None
    plt = None


import math as _math

def _haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points in km."""
    R = 6371.0
    dlat = _math.radians(lat2 - lat1)
    dlon = _math.radians(lon2 - lon1)
    a = _math.sin(dlat / 2) ** 2 + _math.cos(_math.radians(lat1)) * _math.cos(_math.radians(lat2)) * _math.sin(dlon / 2) ** 2
    return R * 2 * _math.atan2(_math.sqrt(a), _math.sqrt(1 - a))


class NEXRADLoader:
    """
    Loads and processes NEXRAD Level II data from AWS S3.

    The AWS S3 bucket 'unidata-nexrad-level2' contains the full archive from 1991-present.
    Data is organized as: s3://unidata-nexrad-level2/YYYY/MM/DD/SITE/SITE_YYYYMMDD_HHMMSS_V06

    Note: Migrated from noaa-nexrad-level2 (deprecated Sept 2025) to unidata-nexrad-level2
    """

    BUCKET = 'unidata-nexrad-level2'

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize the NEXRAD loader.

        Args:
            cache_dir: Directory to cache downloaded Level II files
        """
        if boto3 is None:
            raise ImportError(
                "boto3 is required for NEXRAD data download. "
                "Install with: pip install boto3"
            )
        if pyart is None:
            raise ImportError(
                "Py-ART is required for NEXRAD processing. "
                "Install with: pip install arm-pyart"
            )

        self.cache_dir = cache_dir or Path('.test_cache') / 'nexrad'
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # S3 client with no-sign-request (public bucket)
        self.s3_client = boto3.client(
            's3',
            config=Config(signature_version=UNSIGNED)
        )

    def list_files(
        self,
        site: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[str]:
        """
        List available NEXRAD files for a site within a time range.

        Args:
            site: 4-letter radar site code (e.g., "KTLX", "KOUN")
            start_time: Start of time range (UTC)
            end_time: End of time range (UTC)

        Returns:
            List of S3 keys for matching files
        """
        site = site.upper()
        keys = []

        # Iterate through each day in the range
        current_date = start_time.date()
        end_date = end_time.date()

        while current_date <= end_date:
            prefix = f"{current_date.year}/{current_date.month:02d}/{current_date.day:02d}/{site}/"

            try:
                response = self.s3_client.list_objects_v2(
                    Bucket=self.BUCKET,
                    Prefix=prefix
                )

                if 'Contents' in response:
                    for obj in response['Contents']:
                        key = obj['Key']
                        # Parse timestamp from filename
                        file_time = self._parse_filename_timestamp(key)
                        if file_time and start_time <= file_time <= end_time:
                            keys.append(key)

            except Exception as e:
                print(f"Warning: Error listing files for {prefix}: {e}")

            # Next day
            from datetime import timedelta
            current_date += timedelta(days=1)

        return sorted(keys)

    def _parse_filename_timestamp(self, s3_key: str) -> Optional[datetime]:
        """
        Parse timestamp from NEXRAD filename.

        Format: SITEYYYYMMDD_HHMMSS_V06.gz or SITEYYYYMMDD_HHMMSS_V06

        Args:
            s3_key: S3 object key

        Returns:
            Datetime in UTC, or None if parsing fails
        """
        try:
            filename = s3_key.split('/')[-1]
            # Remove .gz extension if present
            if filename.endswith('.gz'):
                filename = filename[:-3]

            parts = filename.split('_')
            if len(parts) >= 2:
                # parts[0] = SITEYYYYMMDD (e.g., KTLX20130520)
                # parts[1] = HHMMSS (e.g., 194500)
                site_and_date = parts[0]
                time_str = parts[1]

                # Extract date from end of parts[0] (last 8 characters)
                if len(site_and_date) >= 8:
                    date_str = site_and_date[-8:]  # YYYYMMDD
                    dt = datetime.strptime(
                        f"{date_str}_{time_str}",
                        "%Y%m%d_%H%M%S"
                    )
                    return dt.replace(tzinfo=timezone.utc)
        except Exception as e:
            pass
        return None

    def download_file(self, s3_key: str, force: bool = False) -> Path:
        """
        Download a NEXRAD Level II file from S3.

        Args:
            s3_key: S3 object key
            force: Force re-download even if cached

        Returns:
            Path to downloaded file
        """
        filename = s3_key.split('/')[-1]
        local_path = self.cache_dir / filename

        if local_path.exists() and not force:
            return local_path

        print(f"Downloading: {s3_key}")
        self.s3_client.download_file(self.BUCKET, s3_key, str(local_path))
        return local_path

    def read_radar(self, file_path: Path) -> Any:
        """
        Read NEXRAD Level II file using Py-ART.

        Args:
            file_path: Path to Level II file

        Returns:
            Py-ART Radar object
        """
        radar = pyart.io.read_nexrad_archive(str(file_path))
        return radar

    def extract_products(
        self,
        radar: Any,
        products: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Extract radar products from Py-ART Radar object.

        Args:
            radar: Py-ART Radar object
            products: List of products to extract. Defaults to:
                     ['reflectivity', 'velocity', 'spectrum_width',
                      'differential_reflectivity', 'correlation_coefficient']

        Returns:
            Dictionary mapping product names to data arrays
        """
        if products is None:
            products = [
                'reflectivity',
                'velocity',
                'spectrum_width',
                'differential_reflectivity',
                'correlation_coefficient',
                'differential_phase'
            ]

        result = {}

        # Py-ART field name mapping
        field_mapping = {
            'reflectivity': 'reflectivity',
            'velocity': 'velocity',
            'spectrum_width': 'spectrum_width',
            'differential_reflectivity': 'differential_reflectivity',
            'correlation_coefficient': 'cross_correlation_ratio',
            'differential_phase': 'differential_phase'
        }

        for product in products:
            field_name = field_mapping.get(product)
            if field_name and field_name in radar.fields:
                result[product] = radar.fields[field_name]
            else:
                print(f"Warning: Product '{product}' not available in radar data")

        return result

    def grid_to_cartesian(
        self,
        radar: Any,
        grid_shape: Tuple[int, int, int] = (20, 241, 241),
        grid_limits: Optional[Dict[str, Tuple[float, float]]] = None
    ) -> Any:
        """
        Grid radar data to Cartesian coordinates.

        This is the critical step for volumetric rendering - converts polar
        radar data to a regular 3D grid (z, y, x).

        Args:
            radar: Py-ART Radar object
            grid_shape: (nz, ny, nx) - number of points in each dimension
            grid_limits: Limits for each dimension in meters:
                        {'z': (min, max), 'y': (min, max), 'x': (min, max)}
                        Defaults to 20km height, 120km x 120km horizontal

        Returns:
            Py-ART Grid object
        """
        if grid_limits is None:
            grid_limits = {
                'z': (500, 20000),      # 0.5 to 20 km height
                'y': (-120000, 120000),  # 240 km N-S
                'x': (-120000, 120000)   # 240 km E-W
            }

        grid = pyart.map.grid_from_radars(
            [radar],
            grid_shape=grid_shape,
            grid_limits=(
                grid_limits['z'],
                grid_limits['y'],
                grid_limits['x']
            ),
            fields=list(radar.fields.keys())
        )

        return grid

    def calculate_rotation(
        self,
        radar: Any,
        elevation_index: int = 0
    ) -> Optional[np.ndarray]:
        """
        Calculate azimuthal shear for mesocyclone detection.

        This computes the local linear least squares derivative (LLSD)
        of velocity in the azimuthal direction - the key signature for
        mesocyclone detection.

        Args:
            radar: Py-ART Radar object
            elevation_index: Which elevation angle to analyze (0 = lowest)

        Returns:
            Azimuthal shear array, or None if velocity not available
        """
        if 'velocity' not in radar.fields:
            return None

        # Get velocity data for this elevation
        sweep_start = radar.sweep_start_ray_index['data'][elevation_index]
        sweep_end = radar.sweep_end_ray_index['data'][elevation_index]

        velocity = radar.fields['velocity']['data'][sweep_start:sweep_end + 1]

        # Simple azimuthal derivative (difference between adjacent radials)
        # Real LLSD is more sophisticated, but this gives the basic signature
        shear = np.diff(velocity, axis=0)

        return shear

    def detect_mesocyclone_candidates(
        self,
        radar: Any,
        shear_threshold: float = 0.01,  # s^-1
        min_diameter: float = 2000,      # meters (2 km)
        max_diameter: float = 6000       # meters (6 km)
    ) -> List[Dict[str, Any]]:
        """
        Detect ALL mesocyclone signatures using multi-peak detection.

        Uses local maxima detection + DBSCAN clustering to find multiple
        distinct mesocyclones simultaneously (e.g., Moore + Kansas storms).

        Algorithm:
          1. Find all local maxima (peaks) in shear field
          2. Filter to peaks >= threshold (40 s^-1 = TVS-capable)
          3. Cluster nearby peaks (within 5 km = same mesocyclone)
          4. Return strongest peak from each cluster

        Args:
            radar: Py-ART Radar object
            shear_threshold: Minimum azimuthal shear (s^-1), default 40 s^-1
            min_diameter: Minimum mesocyclone diameter (meters) [unused currently]
            max_diameter: Maximum mesocyclone diameter (meters) [unused currently]

        Returns:
            List of ALL strong mesocyclone detections, ordered by strength.
            Each detection includes:
              - elevation_index, elevation_angle, max_shear, timestamp
              - azimuth_deg: azimuth angle of detection (degrees)
              - range_km: range from radar (km)
              - latitude, longitude: geographic location of detection
        """
        import math
        from scipy import ndimage
        from sklearn.cluster import DBSCAN

        detections = []

        # Get radar location
        radar_lat = float(radar.latitude['data'][0])
        radar_lon = float(radar.longitude['data'][0])

        # Range-corrected azimuthal shear (RCAS)
        # At greater range, beam broadening smears velocity couplets across wider
        # physical distance, reducing measured shear. Correct by scaling with
        # range relative to reference (60 km, where 1° beam ≈ 1 km).
        ranges = radar.range['data']  # meters
        reference_range_m = 60000.0  # 60 km reference range
        range_correction = np.clip(ranges / reference_range_m, 1.0, 2.5)

        # Analyze lowest few elevations
        for elev_idx in range(min(3, radar.nsweeps)):
            shear = self.calculate_rotation(radar, elev_idx)
            if shear is None:
                continue

            # Apply RCAS: amplify shear at range to compensate for beam broadening
            # shear shape is (n_azi-1, n_gates), range_correction is (n_gates,)
            shear = shear * range_correction[np.newaxis, :]

            # MULTI-PEAK DETECTION: Find ALL local maxima, not just global max

            # Step 1: Find local maxima (peaks where value > all 8 neighbors)
            local_max_mask = ndimage.maximum_filter(np.abs(shear), size=3) == np.abs(shear)

            # Step 2: Filter to strong peaks only (>= threshold)
            # Convert threshold from s^-1 to array units if needed
            strong_peaks_mask = (np.abs(shear) >= shear_threshold) & local_max_mask

            # Step 3: Get coordinates of all strong peaks
            peak_coords = np.argwhere(strong_peaks_mask)  # Returns (azi_idx, range_idx) pairs

            if len(peak_coords) == 0:
                continue  # No strong peaks at this elevation

            # Get sweep data for coordinate conversion
            sweep_start = radar.sweep_start_ray_index['data'][elev_idx]
            sweep_end = radar.sweep_end_ray_index['data'][elev_idx]
            azimuths = radar.azimuth['data'][sweep_start:sweep_end + 1]
            ranges = radar.range['data']

            # Step 4: Cluster nearby peaks (same mesocyclone vs different storms)
            # Convert peak coordinates to physical distances (km) for clustering
            peak_locations_km = []
            valid_peak_coords = []

            for azi_idx, range_idx in peak_coords:
                if azi_idx < len(azimuths) and range_idx < len(ranges):
                    azimuth_deg = float(azimuths[azi_idx])
                    range_km = float(ranges[range_idx]) / 1000.0

                    # Convert to X,Y coordinates (km) for clustering
                    # X = range * sin(azimuth), Y = range * cos(azimuth)
                    azimuth_rad = math.radians(azimuth_deg)
                    x_km = range_km * math.sin(azimuth_rad)
                    y_km = range_km * math.cos(azimuth_rad)

                    peak_locations_km.append([x_km, y_km])
                    valid_peak_coords.append((azi_idx, range_idx))

            if len(peak_locations_km) == 0:
                continue  # No valid peaks

            # DBSCAN clustering: Group peaks within 5 km (eps=5)
            # Peaks closer than 5 km = same mesocyclone
            # min_samples=1 means every peak gets assigned to a cluster
            clustering = DBSCAN(eps=5.0, min_samples=1, metric='euclidean').fit(peak_locations_km)

            # Step 5: For each cluster, find the STRONGEST peak and report it
            for cluster_id in set(clustering.labels_):
                # Get all peaks in this cluster
                cluster_mask = clustering.labels_ == cluster_id
                cluster_peak_indices = [i for i, mask in enumerate(cluster_mask) if mask]

                # Find strongest peak in cluster
                cluster_shear_values = []
                for idx in cluster_peak_indices:
                    azi_idx, range_idx = valid_peak_coords[idx]
                    cluster_shear_values.append(abs(shear[azi_idx, range_idx]))

                strongest_idx = np.argmax(cluster_shear_values)
                strongest_peak_idx = cluster_peak_indices[strongest_idx]
                azi_idx, range_idx = valid_peak_coords[strongest_peak_idx]

                # Get sweep data
                sweep_start = radar.sweep_start_ray_index['data'][elev_idx]
                sweep_end = radar.sweep_end_ray_index['data'][elev_idx]

                # Get azimuth, range, and shear for this peak
                azimuth_deg = float(azimuths[azi_idx])
                range_m = float(ranges[range_idx])
                range_km = range_m / 1000.0
                peak_shear = float(cluster_shear_values[strongest_idx])

                # Convert azimuth/range to lat/lon
                # Using simple great circle calculation
                # azimuth is clockwise from north, range is in meters
                R_earth = 6371000  # Earth radius in meters
                bearing_rad = math.radians(azimuth_deg)

                lat1_rad = math.radians(radar_lat)
                lon1_rad = math.radians(radar_lon)

                lat2_rad = math.asin(
                    math.sin(lat1_rad) * math.cos(range_m / R_earth) +
                    math.cos(lat1_rad) * math.sin(range_m / R_earth) * math.cos(bearing_rad)
                )

                lon2_rad = lon1_rad + math.atan2(
                    math.sin(bearing_rad) * math.sin(range_m / R_earth) * math.cos(lat1_rad),
                    math.cos(range_m / R_earth) - math.sin(lat1_rad) * math.sin(lat2_rad)
                )

                detection_lat = math.degrees(lat2_rad)
                detection_lon = math.degrees(lon2_rad)

                # Compute RCAS correction factor for this detection
                rcas_factor = float(min(2.5, max(1.0, range_km / 60.0)))

                # Add this cluster's detection to the list
                detections.append({
                    'elevation_index': elev_idx,
                    'elevation_angle': radar.fixed_angle['data'][elev_idx],
                    'max_shear': peak_shear,  # Range-corrected shear
                    'raw_shear': peak_shear / rcas_factor,  # Original uncorrected shear
                    'range_correction_factor': rcas_factor,
                    'timestamp': radar.time['units'],
                    'azimuth_deg': azimuth_deg,
                    'range_km': range_km,
                    'latitude': detection_lat,
                    'longitude': detection_lon,
                    'cluster_id': int(cluster_id),  # Track which cluster this came from
                    'cluster_size': int(np.sum(cluster_mask)),  # How many peaks in cluster
                })

        # Sort by strength (strongest first) for consistency
        detections.sort(key=lambda d: d['max_shear'], reverse=True)

        return detections

    def detect_hail_signatures(
        self,
        radar: Any,
        station_lat: float,
        station_lon: float,
        freezing_level_m: float = 4000,
        max_range_km: float = 80,
        min_dbz: float = 45.0,
        min_cell_gates: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Detect hail signatures from multi-sweep reflectivity analysis.

        Computes VIL, MESH, column heights, and hail probability for each
        storm cell. Works with single-pol (reflectivity only) data.

        Args:
            radar: Py-ART radar object
            station_lat: Test station latitude
            station_lon: Test station longitude
            freezing_level_m: Height of 0°C isotherm (meters AGL)
            max_range_km: Maximum range from station to consider
            min_dbz: Minimum reflectivity threshold for gate collection
            min_cell_gates: Minimum gates to form a valid cell

        Returns:
            List of hail cell detection dicts, sorted by MESH descending.
        """
        import math
        from sklearn.cluster import DBSCAN

        radar_lat = float(radar.latitude['data'][0])
        radar_lon = float(radar.longitude['data'][0])
        R_earth = 6371000  # meters
        Re = 8493000  # Effective Earth radius (4/3 model for beam propagation)

        # Step 1: Collect all gates with significant reflectivity across all sweeps
        gate_data = []  # (lat, lon, height_m, dbz_value, x_km, y_km)

        for elev_idx in range(radar.nsweeps):
            elevation_deg = float(radar.fixed_angle['data'][elev_idx])
            elevation_rad = math.radians(elevation_deg)

            sweep_start = int(radar.sweep_start_ray_index['data'][elev_idx])
            sweep_end = int(radar.sweep_end_ray_index['data'][elev_idx])

            ref_data = radar.fields['reflectivity']['data'][sweep_start:sweep_end + 1]
            azimuths = radar.azimuth['data'][sweep_start:sweep_end + 1]
            ranges = radar.range['data']  # meters

            # Fill masked values
            ref_filled = np.ma.filled(ref_data, fill_value=-999.0)

            # Find gates above threshold
            az_indices, rng_indices = np.where(ref_filled >= min_dbz)

            for ai, ri in zip(az_indices, rng_indices):
                range_m = float(ranges[ri])
                range_km = range_m / 1000.0

                if range_km > max_range_km * 1.5:  # Allow wider range for cells, filter by station distance later
                    continue

                # Height using standard beam propagation
                height_m = range_m * math.sin(elevation_rad) + (range_m ** 2) / (2 * Re)

                # Convert to lat/lon (great circle, same as mesocyclone detection)
                azimuth_deg = float(azimuths[ai])
                bearing_rad = math.radians(azimuth_deg)
                lat1_rad = math.radians(radar_lat)
                lon1_rad = math.radians(radar_lon)

                lat2_rad = math.asin(
                    math.sin(lat1_rad) * math.cos(range_m / R_earth) +
                    math.cos(lat1_rad) * math.sin(range_m / R_earth) * math.cos(bearing_rad)
                )
                lon2_rad = lon1_rad + math.atan2(
                    math.sin(bearing_rad) * math.sin(range_m / R_earth) * math.cos(lat1_rad),
                    math.cos(range_m / R_earth) - math.sin(lat1_rad) * math.sin(lat2_rad)
                )

                gate_lat = math.degrees(lat2_rad)
                gate_lon = math.degrees(lon2_rad)
                dbz_val = float(ref_filled[ai, ri])

                # X/Y for clustering (km from radar)
                az_rad = math.radians(azimuth_deg)
                x_km = range_km * math.sin(az_rad)
                y_km = range_km * math.cos(az_rad)

                gate_data.append((gate_lat, gate_lon, height_m, dbz_val, x_km, y_km))

        if len(gate_data) < min_cell_gates:
            return []

        # Step 2: DBSCAN cluster on horizontal coordinates
        coords_km = np.array([[g[4], g[5]] for g in gate_data])
        clustering = DBSCAN(eps=5.0, min_samples=min_cell_gates, metric='euclidean').fit(coords_km)

        # Step 3: Per-cell analysis
        detections = []
        h_m20 = freezing_level_m + 2500  # Approximate -20°C level

        for cluster_id in set(clustering.labels_):
            if cluster_id == -1:
                continue  # Skip noise

            cluster_mask = clustering.labels_ == cluster_id
            cell_gates = [gate_data[i] for i in range(len(gate_data)) if cluster_mask[i]]

            if len(cell_gates) < min_cell_gates:
                continue

            # For large clusters (QLCS lines), extract the densest 3km-radius
            # core to prevent entire-line integration inflating VIL/MESH.
            max_core_radius_km = 3.0
            if len(cell_gates) > 2000:
                # Find the gate with highest dBZ as core center
                best_gate = max(cell_gates, key=lambda g: g[3])
                core_x, core_y = best_gate[4], best_gate[5]
                cell_gates = [
                    g for g in cell_gates
                    if math.sqrt((g[4] - core_x)**2 + (g[5] - core_y)**2) <= max_core_radius_km
                ]
                if len(cell_gates) < min_cell_gates:
                    continue

            # Cell centroid
            centroid_lat = np.mean([g[0] for g in cell_gates])
            centroid_lon = np.mean([g[1] for g in cell_gates])

            # Distance to station
            dist_to_station = _haversine_km(station_lat, station_lon, centroid_lat, centroid_lon)
            if dist_to_station > max_range_km:
                continue

            # Group by height level, collect all dBZ values per level
            height_dbz_lists = {}
            for lat, lon, h, dbz, x, y in cell_gates:
                h_rounded = round(h / 500) * 500  # Round to nearest 500m (reduce noise)
                if h_rounded not in height_dbz_lists:
                    height_dbz_lists[h_rounded] = []
                height_dbz_lists[h_rounded].append(dbz)

            # Use 90th-percentile dBZ at each height (prevents single hot gate
            # from inflating VIL/MESH across the entire cluster)
            height_dbz = {}
            for h, dbz_vals in height_dbz_lists.items():
                sorted_vals = sorted(dbz_vals)
                idx = int(len(sorted_vals) * 0.9)
                idx = min(idx, len(sorted_vals) - 1)
                height_dbz[h] = sorted_vals[idx]

            sorted_heights = sorted(height_dbz.keys())
            if len(sorted_heights) < 2:
                continue

            # --- VIL computation ---
            vil = 0.0
            max_dbz = -999.0
            max_dbz_height = 0.0
            column_top_45 = 0.0
            echo_top = 0.0

            for i, h in enumerate(sorted_heights):
                dbz = height_dbz[h]
                Z = 10.0 ** (dbz / 10.0)  # Linear reflectivity

                if dbz > max_dbz:
                    max_dbz = dbz
                    max_dbz_height = h

                if dbz >= 45.0:
                    column_top_45 = max(column_top_45, h)

                echo_top = max(echo_top, h)

                # Trapezoidal VIL integration
                if i > 0:
                    h_lower = sorted_heights[i - 1]
                    dbz_lower = height_dbz[h_lower]
                    Z_lower = 10.0 ** (dbz_lower / 10.0)
                    delta_h = h - h_lower
                    vil += 3.44e-6 * ((Z_lower ** (4.0 / 7.0) + Z ** (4.0 / 7.0)) / 2.0) * delta_h

            # --- SHI / MESH computation ---
            shi = 0.0
            for i in range(1, len(sorted_heights)):
                h = sorted_heights[i]
                if h <= freezing_level_m:
                    continue

                dbz = height_dbz[h]
                Z = 10.0 ** (dbz / 10.0)

                # Weight function
                if h >= h_m20:
                    W = 1.0
                else:
                    W = (h - freezing_level_m) / (h_m20 - freezing_level_m)

                h_lower = sorted_heights[i - 1]
                delta_h = h - max(h_lower, freezing_level_m)
                if delta_h <= 0:
                    continue

                shi += 0.1 * W * 5e-6 * Z * delta_h

            mesh_mm_raw = 2.54 * (shi ** 0.5) if shi > 0 else 0.0

            # --- Overshoot-based MESH cap ---
            # Hail size is physically limited by updraft strength.
            # The height of the 45+ dBZ echo above the freezing level
            # (overshoot) is a proxy for updraft intensity.
            # Cap raw MESH based on what the updraft can physically support.
            overshoot_m = max(0, column_top_45 - freezing_level_m)
            overshoot_km = overshoot_m / 1000.0

            if overshoot_km <= 0:
                # No reflectivity above freezing → no significant hail
                mesh_cap = 10.0
            elif overshoot_km < 2.0:
                # Weak updraft — pea/penny at most
                mesh_cap = 25.0
            elif overshoot_km < 4.0:
                # Moderate updraft — up to golf ball
                mesh_cap = 50.0 + (overshoot_km - 2.0) * 12.5  # 50-75mm
            elif overshoot_km < 6.0:
                # Strong updraft — up to ping pong/tennis
                mesh_cap = 75.0 + (overshoot_km - 4.0) * 25.0  # 75-125mm
            elif overshoot_km < 8.0:
                # Very strong updraft — up to baseball
                mesh_cap = 125.0 + (overshoot_km - 6.0) * 37.5  # 125-200mm
            else:
                # Extreme updraft (>8km overshoot) — no practical cap
                mesh_cap = 999.0

            mesh_mm = min(mesh_mm_raw, mesh_cap)

            # --- VIL density ---
            echo_top_km = echo_top / 1000.0
            vil_density = (vil / echo_top_km) if echo_top_km > 0 else 0.0

            # --- Hail probability (multi-factor, take max) ---
            prob = 0.0
            if mesh_mm >= 25:
                prob = max(prob, 0.9)
            elif mesh_mm >= 15:
                prob = max(prob, 0.7)
            elif mesh_mm >= 10:
                prob = max(prob, 0.5)
            elif mesh_mm >= 5:
                prob = max(prob, 0.3)

            if vil_density >= 3.5:
                prob = max(prob, 0.8)
            elif vil_density >= 2.5:
                prob = max(prob, 0.5)

            if max_dbz >= 65:
                prob = max(prob, 0.85)
            elif max_dbz >= 60:
                prob = max(prob, 0.6)
            elif max_dbz >= 55:
                prob = max(prob, 0.4)

            prob = min(1.0, prob)

            # Skip low-probability detections
            if prob < 0.3:
                continue

            # --- Size category ---
            # MESH thresholds adjusted for documented ~2x overestimation bias
            # (Witt et al. 1998 formula is a 95th-percentile maximum estimate).
            # Thresholds doubled vs observed hail diameters so categories
            # reflect likely *observed* size, not raw MESH.
            if mesh_mm > 150:
                category = "giant (baseball+)"
            elif mesh_mm > 100:
                category = "significant (tennis ball)"
            elif mesh_mm > 75:
                category = "large (ping pong ball)"
            elif mesh_mm > 50:
                category = "moderate (golf ball)"
            elif mesh_mm > 20:
                category = "small (penny/quarter)"
            else:
                category = "marginal (pea-sized)"

            # --- Bearing from station ---
            bearing_deg = math.degrees(math.atan2(
                math.radians(centroid_lon - station_lon) * math.cos(math.radians(station_lat)),
                math.radians(centroid_lat - station_lat)
            ))
            bearing_deg = (bearing_deg + 360) % 360

            detections.append({
                'latitude': float(centroid_lat),
                'longitude': float(centroid_lon),
                'distance_to_station_km': float(dist_to_station),
                'bearing_deg': float(bearing_deg),
                'vil_kg_m2': float(vil),
                'vil_density_g_m3': float(vil_density),
                'max_dbz': float(max_dbz),
                'max_dbz_height_m': float(max_dbz_height),
                'column_height_45dbz_m': float(column_top_45),
                'echo_top_m': float(echo_top),
                'mesh_mm': float(mesh_mm),
                'mesh_mm_raw': float(mesh_mm_raw),
                'shi': float(shi),
                'overshoot_m': float(overshoot_m),
                'hail_probability': float(prob),
                'hail_size_category': category,
                'estimated_size_mm': float(mesh_mm),
                'num_gates': len(cell_gates),
            })

        # Sort by MESH descending (largest hail first)
        detections.sort(key=lambda d: d['mesh_mm'], reverse=True)

        return detections

    def generate_radar_image(
        self,
        radar: Any,
        product: str = 'reflectivity',
        elevation_index: int = 0,
        range_km: float = 120,
        size_px: int = 800
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a PNG image of a radar product.

        Args:
            radar: Py-ART Radar object
            product: Product to render ('reflectivity' or 'velocity')
            elevation_index: Which elevation angle (0 = lowest sweep)
            range_km: Maximum range to display (km)
            size_px: Image size in pixels (square)

        Returns:
            Dictionary with:
              - png_bytes: PNG image as bytes
              - width: Image width
              - height: Image height
              - bbox: Geographic bounds (lon_min, lat_min, lon_max, lat_max)
              - product_id: Product identifier
              - label: Human-readable label
            Or None if product not available
        """
        if plt is None:
            raise ImportError("matplotlib is required for image generation")

        # Map product names to Py-ART field names
        field_mapping = {
            'reflectivity': 'reflectivity',
            'velocity': 'velocity',
            'spectrum_width': 'spectrum_width'
        }

        field_name = field_mapping.get(product)
        if not field_name or field_name not in radar.fields:
            print(f"Warning: Product '{product}' not available")
            return None

        # Create figure
        fig = plt.figure(figsize=(8, 8), dpi=100)
        ax = fig.add_subplot(111, projection='polar')

        # Get sweep data
        sweep_start = radar.sweep_start_ray_index['data'][elevation_index]
        sweep_end = radar.sweep_end_ray_index['data'][elevation_index] + 1

        # Extract data for this sweep
        data = radar.fields[field_name]['data'][sweep_start:sweep_end]
        azimuths = radar.azimuth['data'][sweep_start:sweep_end]
        ranges = radar.range['data'] / 1000.0  # Convert to km

        # Filter to max range
        range_mask = ranges <= range_km
        ranges = ranges[range_mask]
        data = data[:, range_mask]

        # Convert azimuth to radians
        az_rad = np.deg2rad(azimuths)

        # Create meshgrid
        Az, R = np.meshgrid(az_rad, ranges)

        # Plot based on product type
        if product == 'reflectivity':
            # Reflectivity color scale (dBZ)
            vmin, vmax = -10, 70
            try:
                # Try to use Py-ART colormaps
                from pyart.graph import cm
                cmap = cm.NWSRef
            except:
                import matplotlib.cm as mpl_cm
                cmap = mpl_cm.get_cmap('jet')  # Fallback

            # Handle masked data: set masked/invalid values to gray
            if isinstance(cmap, str):
                import matplotlib.cm as mpl_cm
                cmap = mpl_cm.get_cmap(cmap)
            cmap = cmap.copy()  # Don't modify the original
            cmap.set_bad(color='#CCCCCC', alpha=1.0)  # Light gray for no data

            label = 'NEXRAD Reflectivity'
            unit = 'dBZ'

        elif product == 'velocity':
            # Velocity color scale (m/s) - use tighter range for better contrast
            # Typical mesocyclone velocities are ±10-15 m/s, not ±30
            vmin, vmax = -15, 15
            try:
                from pyart.graph import cm
                cmap = cm.NWSVel
            except:
                import matplotlib.cm as mpl_cm
                cmap = mpl_cm.get_cmap('RdBu_r')  # Fallback

            # Handle masked data: set masked/invalid values to gray instead of white
            # This makes it clear what's "no data" vs "zero velocity"
            if isinstance(cmap, str):
                import matplotlib.cm as mpl_cm
                cmap = mpl_cm.get_cmap(cmap)
            cmap = cmap.copy()  # Don't modify the original
            cmap.set_bad(color='#CCCCCC', alpha=1.0)  # Light gray for no data

            label = 'NEXRAD Velocity'
            unit = 'm/s'

        else:
            vmin, vmax = None, None
            cmap = 'viridis'
            label = f'NEXRAD {product.title()}'
            unit = ''

        # Plot
        mesh = ax.pcolormesh(Az.T, R.T, data, cmap=cmap, vmin=vmin, vmax=vmax,
                              shading='auto')

        # Styling
        ax.set_theta_zero_location('N')
        ax.set_theta_direction(-1)  # Clockwise
        ax.set_ylim(0, range_km)
        ax.set_title(f"{label}\n{radar.metadata['instrument_name']} "
                     f"{radar.fixed_angle['data'][elevation_index]:.1f}°",
                     pad=20)

        # Add colorbar
        cbar = plt.colorbar(mesh, ax=ax, pad=0.1, shrink=0.8)
        if unit:
            cbar.set_label(unit)

        # Render to PNG bytes
        import io
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        plt.close(fig)
        buf.seek(0)
        png_bytes = buf.read()

        # Calculate geographic bounding box
        # Approximate - this is a polar projection centered at radar site
        radar_lat = radar.latitude['data'][0]
        radar_lon = radar.longitude['data'][0]

        # Convert range_km to degrees (rough approximation)
        # 1 degree latitude ≈ 111 km
        lat_delta = range_km / 111.0
        lon_delta = range_km / (111.0 * np.cos(np.radians(radar_lat)))

        bbox = (
            radar_lon - lon_delta,  # lon_min
            radar_lat - lat_delta,  # lat_min
            radar_lon + lon_delta,  # lon_max
            radar_lat + lat_delta   # lat_max
        )

        return {
            'png_bytes': png_bytes,
            'width': size_px,
            'height': size_px,
            'bbox': bbox,
            'product_id': f'nexrad_{product}',
            'label': label
        }

    def generate_radar_images_for_time(
        self,
        site: str,
        target_time: datetime,
        products: Optional[List[str]] = None,
        max_age_minutes: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Generate radar images for products closest to a target time.

        This is the main method for simulation integration.

        Args:
            site: 4-letter radar site code (e.g., "KTLX")
            target_time: Desired time (UTC)
            products: List of products to generate (default: ['reflectivity', 'velocity'])
            max_age_minutes: Maximum age of radar data to accept

        Returns:
            List of image dictionaries (empty if no data available)
        """
        if products is None:
            products = ['reflectivity', 'velocity']

        # Find NEXRAD file closest to target time
        start_time = target_time - timedelta(minutes=max_age_minutes)
        end_time = target_time + timedelta(minutes=max_age_minutes)

        keys = self.list_files(site, start_time, end_time)
        if not keys:
            print(f"Warning: No NEXRAD files found for {site} near {target_time}")
            return []

        # Find closest file
        def time_diff(key):
            file_time = self._parse_filename_timestamp(key)
            if file_time:
                return abs((file_time - target_time).total_seconds())
            return float('inf')

        closest_key = min(keys, key=time_diff)
        file_time = self._parse_filename_timestamp(closest_key)

        print(f"  Using NEXRAD file: {closest_key.split('/')[-1]} ({file_time})")

        # Download and read radar file
        try:
            file_path = self.download_file(closest_key)
            radar = self.read_radar(file_path)
        except Exception as e:
            print(f"Warning: Failed to load NEXRAD file: {e}")
            return []

        # Generate images for each product
        images = []
        for product in products:
            try:
                img_data = self.generate_radar_image(radar, product=product)
                if img_data:
                    img_data['source_url'] = f"s3://{self.BUCKET}/{closest_key}"
                    img_data['file_time'] = file_time
                    images.append(img_data)
            except Exception as e:
                print(f"Warning: Failed to generate {product} image: {e}")

        return images
