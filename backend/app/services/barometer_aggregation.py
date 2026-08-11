"""Multi-station median-of-medians barometer calibration aggregation.

Rewrites the reference side of the barometer-calibration workflow from
"pick the nearest METAR at face value" to "aggregate several METARs
and refuse to write when they disagree".  A single anomalous METAR
(sensor gust, transient reporting error, station drift) would otherwise
silently pin the console's persistent barometer offset to a wrong value.

Ported from ``kanfei-phone-sensor``'s ``calibration_recompute_job.py``
(Phase 4.7 PR-B), which uses the same aggregation shape in production
for phone-sensor devices.  Thresholds match the phone-sensor config:
``MIN_STATIONS=2``, ``CROSS_STATION_SPREAD_THRESHOLD_HPA=0.4``.  See
issue #298 for the background.

Algorithm (per issue #298):

1. **Sample side** — pull the last ``CONSOLE_WINDOW_MINUTES`` of the
   console's barometer readings from the DB, take the median.  Refuse
   to recommend a write when fewer than ``MIN_CONSOLE_SAMPLES`` are
   available.
2. **Reference side (per station)** — for each METAR station within
   ``MAX_STATION_DISTANCE_MILES`` and returned by the aviationweather
   feed's 2 h window, take the median of that station's altimeter
   observations.  Guards against a station-specific transient.
3. **Cross-station aggregation** — ``offset = median(per_station_medians)``.
   Robust to a single outlier when ≥3 stations vote; the min-stations
   gate makes sure we always have at least one cross-check.
4. **Two gates**:
   - **Min-stations**: refuse when fewer than ``MIN_STATIONS`` voted.
     A single reference cannot cross-check itself.
   - **Cross-station spread**: literal ``max − min`` across per-station
     medians (not stddev, not IQR).  If greater than
     ``CROSS_STATION_SPREAD_THRESHOLD_HPA``, **HOLD** — do not
     recommend a write; show the per-station values so the operator
     can see why.

Reduction-method note.  A Vantage console reports barometric reduction
method 1 (Altimeter Setting), which is what METAR's ``Axxxx`` group
carries.  So a like-for-like comparison against the console's own
sea-level pressure is the whole basis for using METARs here at all.
See ``metar_reference.py``'s module docstring for the full argument.

Not ported yet: CWOP as a second source (issue #298 non-blocker).  The
aggregation is source-agnostic — a ``StationMedian`` from any origin
would slot in — but adding CWOP means porting the per-station quality
gates from ``kanfei-nowcast`` (drift, noise, station-pressure-vs-SLP
detection), which is a separate PR-B.
"""

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.sensor_reading import SensorReadingModel
from .metar_reference import (
    AVIATION_WEATHER_URL,
    REQUEST_TIMEOUT,
    _bounding_box,
    _haversine_miles,
    _to_reference,
    parse_altimeter_thousandths,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds — match kanfei-phone-sensor config.py in production.
# ---------------------------------------------------------------------------

# Minimum stations that must vote before a write recommendation is made.
# One reference cannot cross-check itself; two is the floor for the
# spread gate to have any meaning at all.  Reviewer P0-1 in phone-sensor.
MIN_STATIONS = 2

# HOLD gate on cross-station disagreement.  Defined as literal
# max(medians) - min(medians).  0.4 hPa is a tight tolerance — one
# station drifted or one sensor gust is enough to trip it, which is the
# point.  Same value as phone-sensor production.
CROSS_STATION_SPREAD_THRESHOLD_HPA = 0.4

# Console-side window.  Median over the last N minutes of the console's
# own barometer readings.  15 min aligns with the METAR feed's 5-min
# cache TTL — fresher than the reference, but not so short a spike
# dominates the median.
CONSOLE_WINDOW_MINUTES = 15

# Absolute floor on console samples.  A very sparse DB (freshly-set-up
# station, or a poller that has not caught up) must not be trusted to
# median a meaningful value.  20 samples at the default 5s poll interval
# is under 2 min of continuous polling, which is a low bar that rules
# out only the pathological case.
MIN_CONSOLE_SAMPLES = 20

# Distance floor for a station to count as a reference.  75 km in the
# phone-sensor config; the closer, the more like-for-like the altimeter
# setting is against the console's own sea-level.
MAX_STATION_DISTANCE_MILES = 47  # ≈ 75 km

# Aviation weather feed window per station.  This is the WINDOW the
# aviationweather API returns observations from, not the "how many
# stations" limit — that's a distance filter above.  2 h matches
# metar_reference's existing default.
STATION_WINDOW_HOURS = 2

# Skip-reason codes surfaced to the frontend so it can render a targeted
# diagnostic rather than a bag of booleans.  Kept as string constants so
# the API contract is greppable in one place.
SKIP_NO_CONSOLE_SAMPLES = "no_console_samples"
SKIP_INSUFFICIENT_CONSOLE_SAMPLES = "insufficient_console_samples"
SKIP_NO_METAR_AVAILABLE = "no_metar_available"
SKIP_INSUFFICIENT_STATIONS = "insufficient_stations"
SKIP_CROSS_STATION_DISAGREEMENT = "cross_station_disagreement"


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class StationMedian:
    """One METAR station's median altimeter over the fetch window.

    Distinct from ``MetarReference`` (which is one specific observation);
    this is the aggregate the multi-station gate votes on.
    """

    station_id: str
    station_name: str
    distance_miles: float
    bearing_cardinal: str
    n_obs: int
    # Both altimeter representations kept, same reason as MetarReference:
    # the console consumes thousandths (BAR= command), the UI displays
    # inches.  Keeping both here means no float round-trip at either
    # boundary.
    median_altimeter_thousandths_inhg: int
    median_altimeter_inhg: float
    # Range spanned by this station's observations over the window.
    # Diagnostic; not a gate.  Zero when only one obs was returned.
    obs_spread_thousandths_inhg: int
    # Newest observation timestamp, ISO 8601 UTC.  For "how stale is
    # this?" display alongside the running total.
    newest_observed_at: str


@dataclass
class ConsoleSample:
    """Aggregate of the console's own barometer readings over the window."""

    median_hpa: float
    n_samples: int
    window_minutes: int
    stdev_hpa: float
    # Ends of the window in ISO 8601 UTC.  If the poller is not writing,
    # the "n_samples=0" case is possible and the two are equal.
    window_start: str
    window_end: str


@dataclass
class Recommendation:
    """The write decision + everything the UI needs to render it."""

    should_apply: bool
    # None when should_apply=True; one of the SKIP_* constants above
    # otherwise.  Chosen so a frontend switch/case reads cleanly.
    skip_reason: Optional[str]
    # Populated only when should_apply=True; the median of per-station
    # medians, in the units the console consumes (thousandths inHg).
    median_of_medians_thousandths_inhg: Optional[int] = None
    # Convenience view of the same number.  Kept alongside because the
    # UI shows inches with three decimals.
    median_of_medians_inhg: Optional[float] = None
    # Signed thousandths delta the console would need to apply to bring
    # its current reading into agreement with the recommendation.
    # None when should_apply=False.
    offset_thousandths_inhg: Optional[int] = None
    offset_inhg: Optional[float] = None


@dataclass
class AggregationResult:
    """Everything the API returns for one calibration read.

    Aggregates the three subsystems — console side, reference side,
    the write decision — plus the thresholds in effect so the UI can
    present them without hard-coding.
    """

    console: Optional[ConsoleSample]
    per_station_medians: list[StationMedian] = field(default_factory=list)
    n_stations_considered: int = 0
    cross_station_spread_hpa: Optional[float] = None
    recommendation: Recommendation = field(
        default_factory=lambda: Recommendation(
            should_apply=False,
            skip_reason=SKIP_NO_METAR_AVAILABLE,
        )
    )
    # Thresholds in effect, snapshotted so the UI does not have to
    # know the constants — and so a bench operator running with tweaked
    # values still sees what the daemon actually did.
    thresholds: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Sample side — console median from DB
# ---------------------------------------------------------------------------


def _thresholds_snapshot() -> dict:
    """The gate values the caller can display alongside the result."""
    return {
        "min_stations": MIN_STATIONS,
        "cross_station_spread_threshold_hpa": CROSS_STATION_SPREAD_THRESHOLD_HPA,
        "console_window_minutes": CONSOLE_WINDOW_MINUTES,
        "min_console_samples": MIN_CONSOLE_SAMPLES,
        "max_station_distance_miles": MAX_STATION_DISTANCE_MILES,
        "station_window_hours": STATION_WINDOW_HOURS,
    }


def read_console_barometer_median(
    db: Session,
    window_minutes: int = CONSOLE_WINDOW_MINUTES,
) -> Optional[ConsoleSample]:
    """Median of the console's own barometer over the last ``window_minutes``.

    Returns None only when the DB query itself fails.  A window with
    zero samples in it (station just came online, or poller silent)
    returns a ``ConsoleSample`` with ``n_samples=0`` — the aggregator
    upstream is what turns that into ``SKIP_NO_CONSOLE_SAMPLES``.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=window_minutes)

    try:
        rows = (
            db.query(SensorReadingModel.barometer)
            .filter(SensorReadingModel.timestamp >= start)
            .filter(SensorReadingModel.timestamp <= end)
            .filter(SensorReadingModel.barometer.isnot(None))
            .all()
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("read_console_barometer_median: DB query failed: %s", exc)
        return None

    # SensorReadingModel.barometer is stored as TENTHS of hPa (integer),
    # per `poller.py`'s `round(snapshot.barometer * 10)` — not hPa.
    # Divide here so the rest of the module works in hPa.
    values = [r[0] / 10.0 for r in rows if r[0] is not None]
    if not values:
        return ConsoleSample(
            median_hpa=0.0,
            n_samples=0,
            window_minutes=window_minutes,
            stdev_hpa=0.0,
            window_start=start.isoformat(),
            window_end=end.isoformat(),
        )

    return ConsoleSample(
        median_hpa=round(statistics.median(values), 3),
        n_samples=len(values),
        window_minutes=window_minutes,
        stdev_hpa=(
            round(statistics.pstdev(values), 3) if len(values) > 1 else 0.0
        ),
        window_start=start.isoformat(),
        window_end=end.isoformat(),
    )


# ---------------------------------------------------------------------------
# Reference side — per-station medians from aviationweather
# ---------------------------------------------------------------------------


def _aggregate_per_station(
    observations: list[dict[str, Any]],
    lat: float,
    lon: float,
    radius_miles: float,
) -> list[StationMedian]:
    """Reduce many observations per airport to a per-station median.

    Distinct from ``_newest_per_station`` in ``metar_reference.py``:
    the newest-per-station reduce feeds the single-obs UI path, this one
    computes the median that the multi-station gate votes on.  The two
    coexist so the calibration panel can keep its per-station display
    row alongside the aggregate.
    """
    # Group by station_id first, then reduce each group to a StationMedian.
    per_station: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for obs in observations:
        try:
            obs_time = int(obs["obsTime"])
        except (KeyError, TypeError, ValueError):
            continue
        # _to_reference does the altimeter parse + distance + bearing.
        # We reuse it as the per-obs filter — a station that produced no
        # usable observations does not appear here at all.
        ref = _to_reference(obs, lat, lon)
        if ref is None or not ref.station_id:
            continue
        per_station.setdefault(ref.station_id, []).append((obs_time, obs))

    medians: list[StationMedian] = []
    for station_id, obs_list in per_station.items():
        # Parse altimeter from each obs — parse_altimeter_thousandths is
        # the wire-truth parser, matching what _to_reference used to
        # accept the obs upstream, so this loop never rejects one that
        # passed the filter above.
        thousandths_series: list[int] = []
        newest_time = 0
        newest_ref = None
        for obs_time, obs in obs_list:
            raw = obs.get("rawOb") or ""
            t = parse_altimeter_thousandths(raw)
            if t is None:
                continue
            thousandths_series.append(t)
            if obs_time > newest_time:
                newest_time = obs_time
                newest_ref = _to_reference(obs, lat, lon)

        if not thousandths_series or newest_ref is None:
            continue
        if newest_ref.distance_miles > radius_miles:
            continue

        median_thousandths = int(round(statistics.median(thousandths_series)))
        obs_spread = max(thousandths_series) - min(thousandths_series)

        medians.append(
            StationMedian(
                station_id=station_id,
                station_name=newest_ref.station_name,
                distance_miles=newest_ref.distance_miles,
                bearing_cardinal=newest_ref.bearing_cardinal,
                n_obs=len(thousandths_series),
                median_altimeter_thousandths_inhg=median_thousandths,
                median_altimeter_inhg=round(median_thousandths / 1000, 3),
                obs_spread_thousandths_inhg=obs_spread,
                newest_observed_at=newest_ref.observed_at,
            )
        )

    medians.sort(key=lambda s: s.distance_miles)
    return medians


async def fetch_station_medians(
    lat: float,
    lon: float,
    radius_miles: float = MAX_STATION_DISTANCE_MILES,
) -> list[StationMedian]:
    """Fetch aviationweather feed, aggregate per station.

    Empty list on any failure — same posture as
    ``metar_reference.fetch_metar_references``: a reference source is
    optional context, and the caller's ``no_metar_available`` skip
    reason surfaces the emptiness to the operator directly.
    """
    lat0, lon0, lat1, lon1 = _bounding_box(lat, lon, int(radius_miles))
    params = {
        "bbox": f"{lat0:.4f},{lon0:.4f},{lat1:.4f},{lon1:.4f}",
        "format": "json",
        "hours": STATION_WINDOW_HOURS,
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(AVIATION_WEATHER_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
        logger.warning("METAR aggregation fetch failed: %s", exc)
        return []

    if not isinstance(payload, list):
        logger.warning(
            "METAR aggregation: unexpected payload type %s", type(payload)
        )
        return []

    return _aggregate_per_station(payload, lat, lon, radius_miles)


# ---------------------------------------------------------------------------
# The gates + the recommendation
# ---------------------------------------------------------------------------


def _hpa_to_thousandths_inhg(hpa: float) -> int:
    # inHg = hPa / 33.86389 exactly (NIST).  Thousandths for the wire.
    return int(round(hpa / 33.86389 * 1000))


def _thousandths_inhg_to_hpa(t: int) -> float:
    return t / 1000 * 33.86389


def compute_aggregate_recommendation(
    console: Optional[ConsoleSample],
    per_station_medians: list[StationMedian],
) -> AggregationResult:
    """Evaluate the two gates against the console and reference medians.

    Behaviour matches ``kanfei_sensor_poc.calibration_recompute_job``
    lines 349–390 (per issue #298).  The gate ordering matters: report
    the first-fired reason rather than every failing gate at once, so the
    UI can highlight one thing to act on.
    """
    thresholds = _thresholds_snapshot()

    n_stations = len(per_station_medians)
    med_values_thousandths = [
        s.median_altimeter_thousandths_inhg for s in per_station_medians
    ]

    cross_station_spread_thousandths: Optional[int] = None
    cross_station_spread_hpa: Optional[float] = None
    if n_stations > 0:
        cross_station_spread_thousandths = (
            max(med_values_thousandths) - min(med_values_thousandths)
        )
        cross_station_spread_hpa = round(
            _thousandths_inhg_to_hpa(cross_station_spread_thousandths), 3
        )

    # ---- Gates, in order ----

    # G0: no console data at all → cannot compute an offset regardless.
    if console is None:
        return AggregationResult(
            console=None,
            per_station_medians=per_station_medians,
            n_stations_considered=n_stations,
            cross_station_spread_hpa=cross_station_spread_hpa,
            recommendation=Recommendation(
                should_apply=False, skip_reason=SKIP_NO_CONSOLE_SAMPLES,
            ),
            thresholds=thresholds,
        )

    if console.n_samples == 0:
        return AggregationResult(
            console=console,
            per_station_medians=per_station_medians,
            n_stations_considered=n_stations,
            cross_station_spread_hpa=cross_station_spread_hpa,
            recommendation=Recommendation(
                should_apply=False, skip_reason=SKIP_NO_CONSOLE_SAMPLES,
            ),
            thresholds=thresholds,
        )

    if console.n_samples < MIN_CONSOLE_SAMPLES:
        return AggregationResult(
            console=console,
            per_station_medians=per_station_medians,
            n_stations_considered=n_stations,
            cross_station_spread_hpa=cross_station_spread_hpa,
            recommendation=Recommendation(
                should_apply=False,
                skip_reason=SKIP_INSUFFICIENT_CONSOLE_SAMPLES,
            ),
            thresholds=thresholds,
        )

    # G1: no reference data at all.
    if n_stations == 0:
        return AggregationResult(
            console=console,
            per_station_medians=per_station_medians,
            n_stations_considered=0,
            cross_station_spread_hpa=None,
            recommendation=Recommendation(
                should_apply=False, skip_reason=SKIP_NO_METAR_AVAILABLE,
            ),
            thresholds=thresholds,
        )

    # G2: fewer than MIN_STATIONS voted.  P0-1 in phone-sensor: refuse
    # to write when only one reference is present — a single reference
    # cannot cross-check itself.
    if n_stations < MIN_STATIONS:
        return AggregationResult(
            console=console,
            per_station_medians=per_station_medians,
            n_stations_considered=n_stations,
            cross_station_spread_hpa=cross_station_spread_hpa,
            recommendation=Recommendation(
                should_apply=False, skip_reason=SKIP_INSUFFICIENT_STATIONS,
            ),
            thresholds=thresholds,
        )

    # G3: stations disagree beyond tolerance.  We cannot tell which is
    # drifted, so HOLD the existing offset rather than commit to one.
    if (
        cross_station_spread_hpa is not None
        and cross_station_spread_hpa
        > CROSS_STATION_SPREAD_THRESHOLD_HPA
    ):
        return AggregationResult(
            console=console,
            per_station_medians=per_station_medians,
            n_stations_considered=n_stations,
            cross_station_spread_hpa=cross_station_spread_hpa,
            recommendation=Recommendation(
                should_apply=False,
                skip_reason=SKIP_CROSS_STATION_DISAGREEMENT,
            ),
            thresholds=thresholds,
        )

    # ---- All gates passed: compute the recommendation ----

    median_of_medians_thousandths = int(
        round(statistics.median(med_values_thousandths))
    )
    median_of_medians_hpa = _thousandths_inhg_to_hpa(
        median_of_medians_thousandths
    )

    # Offset the console needs: reference minus the console's own reading.
    # Reported both ways for the same reason StationMedian holds both.
    console_thousandths = _hpa_to_thousandths_inhg(console.median_hpa)
    offset_thousandths = median_of_medians_thousandths - console_thousandths

    return AggregationResult(
        console=console,
        per_station_medians=per_station_medians,
        n_stations_considered=n_stations,
        cross_station_spread_hpa=cross_station_spread_hpa,
        recommendation=Recommendation(
            should_apply=True,
            skip_reason=None,
            median_of_medians_thousandths_inhg=median_of_medians_thousandths,
            median_of_medians_inhg=round(
                median_of_medians_thousandths / 1000, 3
            ),
            offset_thousandths_inhg=offset_thousandths,
            offset_inhg=round(offset_thousandths / 1000, 3),
        ),
        thresholds=thresholds,
    )
