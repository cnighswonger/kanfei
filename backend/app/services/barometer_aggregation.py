"""Distance-weighted multi-station barometer calibration aggregation.

Rewrites the reference side of the barometer-calibration workflow from
"pick the nearest METAR at face value" to "weight several METARs by
proximity, refuse to write when they disagree, and offer an operator
override on HOLD".  A single anomalous METAR (sensor gust, transient
reporting error, station drift) would otherwise silently pin the
console's persistent barometer offset to a wrong value.

Originally ported from ``kanfei-phone-sensor``'s
``calibration_recompute_job.py`` (Phase 4.7 PR-B) for issue #298.
Reworked for issue #307 after the beta27 vsits-02 smoke showed that
phone-sensor's plain median-of-medians with a 0.4 hPa max−min gate
does not survive contact with METAR-across-a-county: phone-sensor is
calibrated on a top-3 CWOP mesh where max−min is a fair statistic;
Kanfei is METAR-only with a 47-mile reach where a real synoptic
gradient can easily push max−min above 0.4 hPa on quiet days.

Current algorithm:

1. **Sample side** — pull the last ``CONSOLE_WINDOW_MINUTES`` of the
   console's barometer readings from the DB, take the median.  Refuse
   to recommend a write when fewer than ``MIN_CONSOLE_SAMPLES`` are
   available.
2. **Reference side (per station)** — for each METAR station within
   ``MAX_STATION_DISTANCE_MILES`` and returned by the aviationweather
   feed's 2 h window, take the median of that station's altimeter
   observations.  Guards against a station-specific transient.
3. **Optional station-count cap** — ``STATION_LIMIT_FOR_CALIBRATION``
   (default None → all in bbox).  Set to 3 to reproduce phone-sensor's
   top-3-nearest algorithm exactly.  Applied first, on the distance-
   sorted list, so subsequent processing operates on that slice.
4. **Weather-quiescence gate 1 (console-side)** — if
   ``ConsoleSample.stdev_hpa`` over the reading window exceeds
   ``CONSOLE_STDEV_THRESHOLD_HPA``, the local pressure is moving
   faster than any calibration would remain valid for.  Returns
   ``SKIP_UNSETTLED_CONSOLE`` and never gets to the station side.
   No operator override — the operator cannot see through the
   transient from the UI.
5. **Iterated MAD outlier rejection** — mark stations whose median
   sits more than ``MAD_REJECTION_MULTIPLIER × (1.4826 × MAD)`` from
   the group median, floored by ``MAD_MIN_SCALE_HPA``.  Rerun on
   survivors each pass until nothing new is rejected or
   ``MAD_MAX_ITERATIONS`` is reached.  Excluded stations still ride
   along in the returned list with ``is_outlier=True`` so the panel
   can show why the count dropped.
6. **Weather-quiescence gate 2 (regional)** — if ≥
   ``RAPID_TREND_STATION_FRACTION`` of MAD survivors carry a
   ``PRESRR`` / ``PRESFR`` remark on their *newest* observation
   (FMH-1 trend groups meaning ≥0.06 inHg/hr rising/falling), the
   whole area is moving.  Requires ``n_used ≥ MIN_STATIONS`` before
   the fraction check runs, so a lone survivor cannot trip the
   gate at 100%.  Returns ``SKIP_UNSETTLED_REGIONAL``; no override.
7. **Cross-station aggregation — inverse-distance-squared weighting**.
   The operator's console is at *their* location, not the county
   average, so nearer stations carry more evidence about the pressure
   at that location.  ``w_i = 1 / (d_i² + ε²)`` with a 1.0 mi floor
   (``DISTANCE_WEIGHT_EPSILON_MILES``) so a co-located station cannot
   divide by zero or dominate unboundedly.  The write value is the
   weighted median over survivors.
8. **Two gates**:
   - **Min-stations**: refuse when fewer than ``MIN_STATIONS``
     survived MAD.  A single reference cannot cross-check itself, and
     counting on survivors (not raw candidates) means a hostile
     drifted station cannot inflate the count past the gate.
   - **Weighted spread**: ``2 × sqrt(weighted variance around the
     weighted median)``.  The 2× factor makes the number read on the
     same scale as an ordinary max−min for well-behaved data, so
     operators do not need units retraining.  If greater than
     ``CROSS_STATION_SPREAD_THRESHOLD_HPA`` (0.7 hPa post-#307),
     **HOLD** — but see (9).
9. **Override on HOLD** — when the spread gate fires,
   ``Recommendation.hold_override_allowed=True`` and the weighted
   median IS still returned to the caller.  The UI may render an
   explicit "Accept anyway" button that commits to the SAME
   weighted-median value the algorithm computed.  The multi-station
   cross-check still governs the WRITE VALUE; only the write DECISION
   is delegated to the operator.  This is a fundamentally different
   affordance from the pre-#298 picker (removed in #306), which let
   the operator commit to any nearby METAR at face value.

Reduction-method note.  A Vantage console reports barometric reduction
method 1 (Altimeter Setting), which is what METAR's ``Axxxx`` group
carries.  So a like-for-like comparison against the console's own
sea-level pressure is the whole basis for using METARs here at all.
See ``metar_reference.py``'s module docstring for the full argument.

Not ported yet: CWOP as a second source (issue #303).  The aggregation
is source-agnostic — a ``StationMedian`` from any origin would slot in
— but adding CWOP means porting the per-station quality gates from
``kanfei-nowcast`` (drift, noise, station-pressure-vs-SLP detection),
which is a separate PR.
"""

import logging
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# Compiled once at import time; used by ``_aggregate_per_station`` to
# tag stations whose latest report carries a rapid-pressure-trend
# remark.  See ``has_rapid_trend`` on ``StationMedian``.
_RAPID_TREND_RE = re.compile(r"\bPRES(?:RR|FR)\b")

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

# HOLD gate on cross-station disagreement.  Computed AFTER the MAD
# outlier rejection below and using INVERSE-DISTANCE-SQUARED WEIGHTING
# — the operator's console is at *their* location, not the county
# average, so nearer stations carry more evidence about the pressure
# at that location than distant ones.  See #307 for the derivation.
#
# The value on the wire is a "weighted spread" — 2× the weighted
# standard deviation around the weighted median — which reads on the
# same scale as max−min for reasonably-populated station sets but
# does not blow up in the presence of a natural synoptic gradient
# across the reference radius.
#
# Threshold value: 0.7 hPa.  Android-agent's #307 read: phone-sensor's
# 0.4 hPa on a top-3 CWOP mesh is not the same statistic; Kanfei's
# weighting compresses the natural gradient so the effective range
# should behave closer to phone-sensor's after the compression.
# Landed at 0.7 hPa as the middle of the 0.6-0.8 hPa suggested range.
CROSS_STATION_SPREAD_THRESHOLD_HPA = 0.7

# Inverse-distance-squared weighting.  Standard spatial-interpolation
# form (essentially kriging without the fanciness): weight ∝ 1/(d²+ε)
# where d is the great-circle distance from the operator's location
# to the station.  ε (a small "distance floor") keeps a station right
# next door from dividing by zero and dominating everything else; it
# also caps how much a co-located CWOP station could weigh under
# #303's future integration.
DISTANCE_WEIGHT_EPSILON_MILES = 1.0

# Optional cap on the reference set size.  Phone-sensor uses top-3
# nearest and its 0.4 hPa max−min gate is calibrated for that shape.
# Kanfei defaults to "everything in bbox" because METAR density is
# lower and cutting the set that small would leave sparse regions
# with 0-2 stations.  Operators can set this to 3 (or any positive
# integer) to reproduce phone-sensor behaviour exactly.
STATION_LIMIT_FOR_CALIBRATION: Optional[int] = None

# Weather-quiescence pre-gates (#307 android-agent follow-up).  A HOLD
# on a genuinely stormy afternoon should not read as "stations
# disagree" — the honest answer is "weather is dynamic right now, try
# again in a calmer window".  Two cheap detectors on data we already
# have locally:
#
# CONSOLE_STDEV_THRESHOLD_HPA — if the console's own barometer moved
#   by more than this over the last CONSOLE_WINDOW_MINUTES, the local
#   pressure is unstable and anchoring a persistent offset to that
#   window is a bad idea.  0.2 hPa is roughly a passing squall's
#   footprint over 15 minutes (real quiet-hour σ is well under 0.1
#   hPa; typical fair-weather cycling is 0.1 hPa; a σ above 0.2 hPa
#   means the pressure is moving noticeably faster than baseline).
#
# RAPID_TREND_STATION_FRACTION — fraction of surviving reference
#   stations whose latest report carries a PRESRR/PRESFR remark
#   (FMH-1 defines these as ≥0.06 inHg/hr rise/fall).  A single
#   station firing is noise; a third of the regional set firing is
#   the whole area moving.  0.30 chosen to trip when 3 of 10 or 2 of
#   6 stations report rapid change — high enough to require
#   corroboration, low enough to fire on real regional fronts.
CONSOLE_STDEV_THRESHOLD_HPA = 0.2
RAPID_TREND_STATION_FRACTION = 0.30

# Retrospective "recent-unsettled" signal.  Wq1/Wq2 above answer the
# instantaneous question ("is weather dynamic RIGHT NOW"); this
# addendum answers "has weather been dynamic RECENTLY".  The gate
# does not itself refuse a write — the operator has already been
# refused by cross_station_disagreement or another gate — but its
# result rides in the API response so the panel can add a sentence
# to the HOLD diagnostic like "local pressure has been unsettled
# over the last 24 h (σ = X hPa)".  The operator sees WHY reference
# stations may be disagreeing beyond the algorithm's tolerance
# instead of just "stations disagree".
#
# 24 h captures a full daily cycle; shorter (say 6 h) can miss "the
# last few days" complaints, longer averages calm nights back into
# the noisy afternoons.  Quiet-baseline σ over 24 h is typically
# 0.3 hPa (diurnal + minor fluctuation); 0.5 hPa says the weather
# is contributing measurably beyond that baseline.
RECENT_WINDOW_HOURS = 24
RECENT_UNSETTLED_STDEV_THRESHOLD_HPA = 0.5
# Minimum samples in the retrospective window before we trust the σ.
# 24 h at the default 10 s poll cadence is thousands of samples; a
# very low floor covers the "poller has only run for an hour" case
# without inviting a wild σ estimate from 3 readings.
MIN_RECENT_SAMPLES = 60

# Per-station outlier rejection before the spread gate.  Phone-sensor
# ran on a dense CWOP mesh where max−min was a fair statistic; Kanfei
# is METAR-only with a 47-mile reach into rural areas where a single
# miscalibrated AWOS at a small airfield poisons the whole spread.
#
# We reject any station whose median lies more than
# ``MAD_REJECTION_MULTIPLIER`` * (1.4826 * MAD) away from the group
# median — the 1.4826 factor is the classical normal-consistent scale
# estimator (so k=3 approximates 3σ under a Gaussian assumption while
# staying robust to the outliers themselves).  Only survivors count
# for the spread gate and the median-of-medians write recommendation;
# excluded stations still ride along in the response so the UI can
# show WHY the count dropped.
# k=2.5 is the "moderate" default in the applied stats literature (Leys
# et al., 2013).  The classical k=3 is calibrated on Gaussian data;
# METAR-across-a-county has heavier tails, and k=3 leaves obvious
# multi-hPa outliers inside the acceptance band because they themselves
# inflate the MAD.  On the beta27 smoke wire data (14 stations, KGSB
# and KSOP both clearly drifted) k=3 rejected nothing; k=2.5 with
# iteration removes both.
MAD_REJECTION_MULTIPLIER = 2.5

# Iterated rather than single-pass.  Removing one outlier tightens the
# group MAD and can bring the *next* outlier into rejection range.  On
# the smoke data KGSB goes out on pass 1 (MAD=0.42 hPa) and KSOP on
# pass 2 (MAD tightens to 0.34 hPa).  Bounded so a pathological input
# cannot loop forever; in practice convergence is 1–3 passes.
MAD_MAX_ITERATIONS = 10

# Floor on the effective scale used by MAD rejection.  With a very
# calm reference set (say 12 stations all within 0.05 hPa of each
# other), 1.4826 * MAD collapses to near zero and a station 0.15 hPa
# away — still consistent with real barometric noise — would look
# like an outlier.  The floor caps that: no station is rejected when
# it is within this many hPa of the group median, even if the MAD
# says otherwise.  0.15 hPa is roughly one thousandth of inHg — the
# granularity of the wire values themselves.
MAD_MIN_SCALE_HPA = 0.15

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
# Weather-quiescence pre-gate outcomes.  Distinct from the "stations
# disagree" outcome because they are answering a different question:
# not "which of these values is right" but "is the local weather
# stable enough for any snapshot to represent a persistent state".
SKIP_UNSETTLED_CONSOLE = "unsettled_console"
SKIP_UNSETTLED_REGIONAL = "unsettled_regional"


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
    # Set by ``compute_aggregate_recommendation`` on stations rejected
    # by the MAD outlier filter.  The aggregation still returns them
    # so the UI can show the excluded stations struck out or in a
    # separate section — hiding them would surprise an operator whose
    # station count "dropped for no visible reason".  ``fetch_station_medians``
    # always leaves this False; only the aggregator can set it True.
    is_outlier: bool = False
    # True when at least one observation for this station in the
    # window carried a ``PRESRR`` (pressure rising rapidly) or
    # ``PRESFR`` (pressure falling rapidly) remark.  These are the
    # standard METAR trend-group signals defined in FMH-1: a change
    # of at least 0.06 inHg per hour, either up or down.  When enough
    # nearby stations show this, the whole region is in a dynamic
    # weather regime and pinning the console's persistent offset to
    # any snapshot of it is a bad idea.  Set at parse time by
    # ``_aggregate_per_station`` from the raw report text; the
    # aggregator's weather-quiescence gate reads it.
    has_rapid_trend: bool = False


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
    # Standard deviation over the *retrospective* window
    # (``RECENT_WINDOW_HOURS``, default 24 h) — distinct from
    # ``stdev_hpa`` which measures the current 15 min.  Used to
    # answer "has weather been unsettled RECENTLY" even when the
    # instantaneous snapshot looks calm.  ``None`` when fewer than
    # ``MIN_RECENT_SAMPLES`` readings are available in the window
    # (freshly-set-up station, DB reset, poller silent).
    stdev_hpa_recent: Optional[float] = None
    n_samples_recent: int = 0
    recent_window_hours: int = 24


@dataclass
class Recommendation:
    """The write decision + everything the UI needs to render it.

    Semantics shift in the weighted-algorithm rework (#307): the
    ``median_of_medians_*`` and ``offset_*`` fields are now populated
    WHENEVER we have enough survivors + console data to compute them,
    regardless of whether the gates passed.  ``should_apply`` still
    tells the caller whether the algorithm-only path would fire the
    write; ``hold_override_allowed`` says whether the operator UI may
    offer an "Accept anyway" button that writes the same recommended
    value with an audit-trail marker.  The two are mutually exclusive
    for the UI's purposes — if the algorithm says apply, no override
    is needed; if it says HOLD but the operator overrides, the write
    goes to the algorithm-recommended value, not to some arbitrary
    station.  This preserves the multi-station cross-check even under
    override.
    """

    should_apply: bool
    # None when should_apply=True; one of the SKIP_* constants above
    # otherwise.  Chosen so a frontend switch/case reads cleanly.
    skip_reason: Optional[str]
    # WEIGHTED median-of-medians using inverse-distance-squared.  The
    # value the console should be told to display, in the units the
    # BAR= command consumes (thousandths inHg).  None only when the
    # reference side is unusable (no METAR, insufficient stations, or
    # console has no readings to solve against).
    median_of_medians_thousandths_inhg: Optional[int] = None
    # Convenience view.  Kept alongside because the UI shows inches
    # with three decimals.
    median_of_medians_inhg: Optional[float] = None
    # Signed thousandths delta the console would need to apply to bring
    # its current reading into agreement with the recommendation.
    offset_thousandths_inhg: Optional[int] = None
    offset_inhg: Optional[float] = None
    # True when should_apply=False AND we have a valid recommended
    # value the operator can commit to as an override.  Only the
    # cross-station-disagreement skip qualifies — the "no console
    # data" and "no METAR data" skips have no recommendation to
    # override to.  UI reads this to decide whether to render the
    # "Accept anyway" button; backend accepts the write regardless
    # (the audit trail is what records auto vs override).
    hold_override_allowed: bool = False


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
    # After MAD outlier rejection.  n_stations_considered - n_stations_used
    # is the count of stations flagged with ``is_outlier=True``.  Both are
    # returned so the UI can show "12 of 14 stations agree" instead of a
    # bare survivor count that hides the discard.
    n_stations_used: int = 0
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
        "mad_rejection_multiplier": MAD_REJECTION_MULTIPLIER,
        "mad_min_scale_hpa": MAD_MIN_SCALE_HPA,
        "mad_max_iterations": MAD_MAX_ITERATIONS,
        "distance_weight_epsilon_miles": DISTANCE_WEIGHT_EPSILON_MILES,
        "station_limit_for_calibration": STATION_LIMIT_FOR_CALIBRATION,
        "console_stdev_threshold_hpa": CONSOLE_STDEV_THRESHOLD_HPA,
        "rapid_trend_station_fraction": RAPID_TREND_STATION_FRACTION,
        "recent_window_hours": RECENT_WINDOW_HOURS,
        "recent_unsettled_stdev_threshold_hpa":
            RECENT_UNSETTLED_STDEV_THRESHOLD_HPA,
    }


# ---------------------------------------------------------------------------
# Weighted statistics (inverse-distance-squared)
# ---------------------------------------------------------------------------


def _distance_weight(distance_miles: float) -> float:
    """Inverse-distance-squared with a floor to keep co-located
    stations from dominating.

    ``w = 1 / (d² + ε)`` where ε = ``DISTANCE_WEIGHT_EPSILON_MILES``².
    The +ε term is what stops a station right next door from getting
    an unbounded weight; it also caps how much a hypothetical
    co-located CWOP station (#303 future) could weigh.
    """
    eps_sq = DISTANCE_WEIGHT_EPSILON_MILES * DISTANCE_WEIGHT_EPSILON_MILES
    return 1.0 / (distance_miles * distance_miles + eps_sq)


def _weighted_median(values: list[float], weights: list[float]) -> float:
    """Weighted median: the value at which the cumulative weight
    crosses half the total.  With equal weights this reduces to the
    ordinary median (interpolated at the midpoint for even N).
    """
    if not values:
        raise ValueError("_weighted_median: empty input")
    if len(values) != len(weights):
        raise ValueError("_weighted_median: length mismatch")

    pairs = sorted(zip(values, weights))
    total = sum(w for _, w in pairs)
    half = total / 2.0
    running = 0.0
    for i, (v, w) in enumerate(pairs):
        running += w
        if running > half:
            return v
        if running == half:
            # Boundary case: cumulative weight lands exactly at half —
            # the classic even-N ordinary-median situation.  Return
            # the midpoint of this value and the next, if a next
            # exists; otherwise this value is the only survivor of
            # its half and stands.
            if i + 1 < len(pairs):
                return (v + pairs[i + 1][0]) / 2.0
            return v
    return pairs[-1][0]  # pragma: no cover — reachable only on empty


def _weighted_spread_hpa(values: list[float], weights: list[float]) -> float:
    """"Weighted spread": 2× the weighted standard deviation around
    the weighted median.  The 2× factor makes the number read on the
    same scale as an ordinary max−min for well-behaved data (roughly
    the 68% central range on Gaussian input), so the operator can
    interpret it without a units retraining.

    Returns 0.0 for the single-station and identical-values cases.
    """
    if not values or len(values) < 2:
        return 0.0
    wmed = _weighted_median(values, weights)
    total_w = sum(weights)
    if total_w == 0.0:
        return 0.0
    weighted_var = sum(
        w * (v - wmed) * (v - wmed) for v, w in zip(values, weights)
    ) / total_w
    return 2.0 * (weighted_var ** 0.5)


def _mark_mad_outliers(
    stations: list[StationMedian],
) -> list[StationMedian]:
    """Return the input list with ``is_outlier`` set on rejected stations.

    Iterated MAD rejection: on each pass the group MAD is recomputed
    from the currently-accepted survivors, and any station outside
    ``MAD_REJECTION_MULTIPLIER * max(1.4826 * MAD, MAD_MIN_SCALE_HPA)``
    from the group median is marked as an outlier and dropped from
    the next pass.  The loop terminates when a pass rejects nothing
    or ``MAD_MAX_ITERATIONS`` is reached.

    Why iterate: single-pass MAD leaves obvious outliers inside the
    band because they inflate the MAD themselves — the beta27 smoke
    wire data has two ~52-thousandths-inHg outliers that both fit
    inside a first-pass 55-thousandth band, but removing one tightens
    the band enough to catch the other.

    Non-mutating: returns fresh ``StationMedian`` instances via
    ``dataclasses.replace`` so the caller's list is preserved.  With
    fewer than two stations the input passes through untouched — MAD
    of a singleton is zero and rejecting-against-oneself is nonsense.
    """
    from dataclasses import replace

    if len(stations) < 2:
        return list(stations)

    values_hpa = [
        _thousandths_inhg_to_hpa(s.median_altimeter_thousandths_inhg)
        for s in stations
    ]
    # `active[i]` = True means station i is still in the reference
    # group.  We flip to False as we reject; the returned copy carries
    # ``is_outlier = not active[i]``.
    active = [True] * len(stations)

    for _ in range(MAD_MAX_ITERATIONS):
        live_values = [
            v for v, keep in zip(values_hpa, active) if keep
        ]
        if len(live_values) < 2:
            break
        group_median_hpa = statistics.median(live_values)
        mad_hpa = statistics.median(
            [abs(v - group_median_hpa) for v in live_values]
        )
        effective_scale_hpa = max(1.4826 * mad_hpa, MAD_MIN_SCALE_HPA)
        threshold_hpa = MAD_REJECTION_MULTIPLIER * effective_scale_hpa

        rejected_this_pass = False
        for i, (v, keep) in enumerate(zip(values_hpa, active)):
            if not keep:
                continue
            if abs(v - group_median_hpa) > threshold_hpa:
                active[i] = False
                rejected_this_pass = True
        if not rejected_this_pass:
            break

    return [
        replace(s, is_outlier=not keep)
        for s, keep in zip(stations, active)
    ]


def read_console_barometer_median(
    db: Session,
    window_minutes: int = CONSOLE_WINDOW_MINUTES,
    recent_window_hours: int = RECENT_WINDOW_HOURS,
) -> Optional[ConsoleSample]:
    """Median of the console's own barometer over the last ``window_minutes``.

    Also computes σ over the longer retrospective window
    (``recent_window_hours``) so the caller can surface "weather has
    been unsettled recently" on top of any HOLD diagnostic.  The
    retrospective σ is optional — populated only when at least
    ``MIN_RECENT_SAMPLES`` readings are present in the window.

    Returns None only when the DB query itself fails.  A window with
    zero samples in it (station just came online, or poller silent)
    returns a ``ConsoleSample`` with ``n_samples=0`` — the aggregator
    upstream is what turns that into ``SKIP_NO_CONSOLE_SAMPLES``.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=window_minutes)
    recent_start = end - timedelta(hours=recent_window_hours)

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

    # Retrospective window is a separate query so it can span data
    # older than ``window_minutes``.  Failure is non-fatal — a σ we
    # cannot compute becomes ``None`` and the UI addendum falls silent.
    try:
        recent_rows = (
            db.query(SensorReadingModel.barometer)
            .filter(SensorReadingModel.timestamp >= recent_start)
            .filter(SensorReadingModel.timestamp <= end)
            .filter(SensorReadingModel.barometer.isnot(None))
            .all()
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "read_console_barometer_median: recent-window DB query failed: %s", exc,
        )
        recent_rows = []

    # SensorReadingModel.barometer is stored as TENTHS of hPa (integer),
    # per `poller.py`'s `round(snapshot.barometer * 10)` — not hPa.
    # Divide here so the rest of the module works in hPa.
    values = [r[0] / 10.0 for r in rows if r[0] is not None]
    recent_values = [r[0] / 10.0 for r in recent_rows if r[0] is not None]
    stdev_hpa_recent: Optional[float] = None
    if len(recent_values) >= MIN_RECENT_SAMPLES:
        stdev_hpa_recent = round(statistics.pstdev(recent_values), 3)

    if not values:
        return ConsoleSample(
            median_hpa=0.0,
            n_samples=0,
            window_minutes=window_minutes,
            stdev_hpa=0.0,
            window_start=start.isoformat(),
            window_end=end.isoformat(),
            stdev_hpa_recent=stdev_hpa_recent,
            n_samples_recent=len(recent_values),
            recent_window_hours=recent_window_hours,
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
        stdev_hpa_recent=stdev_hpa_recent,
        n_samples_recent=len(recent_values),
        recent_window_hours=recent_window_hours,
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
        newest_raw = ""
        for obs_time, obs in obs_list:
            raw = obs.get("rawOb") or ""
            t = parse_altimeter_thousandths(raw)
            if t is None:
                continue
            thousandths_series.append(t)
            if obs_time > newest_time:
                newest_time = obs_time
                newest_ref = _to_reference(obs, lat, lon)
                # PRESRR / PRESFR is derived from the *newest* obs
                # only, not any obs in the window (Codex R1 blocker
                # on #310): the gate answers "is regional pressure
                # moving RIGHT NOW", so a 90-minute-old remark from
                # a station whose latest report has cleared should
                # not keep it flagged.  METAR trend groups (FMH-1)
                # are "≥0.06 inHg per hour rising/falling"; word
                # boundaries on the regex pin the match so a
                # substring like `PRESIDENTIAL` does not
                # false-positive.
                newest_raw = raw
        has_rapid_trend = bool(_RAPID_TREND_RE.search(newest_raw))

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
                has_rapid_trend=has_rapid_trend,
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

    # If a station-count cap is configured, apply it BEFORE any other
    # processing — the whole point of the cap is to reproduce a
    # top-N-nearest algorithm.  ``fetch_station_medians`` already
    # returns rows sorted by distance ascending, so we can slice.
    if (
        STATION_LIMIT_FOR_CALIBRATION is not None
        and STATION_LIMIT_FOR_CALIBRATION > 0
        and len(per_station_medians) > STATION_LIMIT_FOR_CALIBRATION
    ):
        per_station_medians = per_station_medians[:STATION_LIMIT_FOR_CALIBRATION]

    n_considered = len(per_station_medians)

    # G0: no console data at all → cannot compute an offset regardless.
    # Reported before touching the reference side so a "console silent"
    # story is not conflated with a reference-side skip.
    if console is None:
        return AggregationResult(
            console=None,
            per_station_medians=per_station_medians,
            n_stations_considered=n_considered,
            n_stations_used=0,
            cross_station_spread_hpa=None,
            recommendation=Recommendation(
                should_apply=False, skip_reason=SKIP_NO_CONSOLE_SAMPLES,
            ),
            thresholds=thresholds,
        )

    if console.n_samples == 0:
        return AggregationResult(
            console=console,
            per_station_medians=per_station_medians,
            n_stations_considered=n_considered,
            n_stations_used=0,
            cross_station_spread_hpa=None,
            recommendation=Recommendation(
                should_apply=False, skip_reason=SKIP_NO_CONSOLE_SAMPLES,
            ),
            thresholds=thresholds,
        )

    if console.n_samples < MIN_CONSOLE_SAMPLES:
        return AggregationResult(
            console=console,
            per_station_medians=per_station_medians,
            n_stations_considered=n_considered,
            n_stations_used=0,
            cross_station_spread_hpa=None,
            recommendation=Recommendation(
                should_apply=False,
                skip_reason=SKIP_INSUFFICIENT_CONSOLE_SAMPLES,
            ),
            thresholds=thresholds,
        )

    # Wq1: console-side quiescence gate.  ``ConsoleSample.stdev_hpa``
    # is the σ over the last CONSOLE_WINDOW_MINUTES of raw readings;
    # if it is above the threshold the local pressure is moving too
    # fast to represent a stable state and anchoring a persistent
    # offset to any snapshot of it would be bad.  Distinct from
    # cross-station disagreement: this fires even when a lone
    # console+reference agree, because the AGREEMENT itself would be
    # ephemeral.  No override — the operator cannot know from the UI
    # that their console is or is not still moving.
    if console.stdev_hpa > CONSOLE_STDEV_THRESHOLD_HPA:
        return AggregationResult(
            console=console,
            per_station_medians=per_station_medians,
            n_stations_considered=n_considered,
            n_stations_used=0,
            cross_station_spread_hpa=None,
            recommendation=Recommendation(
                should_apply=False, skip_reason=SKIP_UNSETTLED_CONSOLE,
            ),
            thresholds=thresholds,
        )

    # G1: no reference data at all.
    if n_considered == 0:
        return AggregationResult(
            console=console,
            per_station_medians=per_station_medians,
            n_stations_considered=0,
            n_stations_used=0,
            cross_station_spread_hpa=None,
            recommendation=Recommendation(
                should_apply=False, skip_reason=SKIP_NO_METAR_AVAILABLE,
            ),
            thresholds=thresholds,
        )

    # Outlier rejection.  Run BEFORE any station-count / spread gate so
    # a single drifted AWOS cannot poison the whole recommendation.
    # ``per_station_medians`` (all N with is_outlier set) is what we
    # return; ``survivors`` is what the gates and the weighted
    # calculation run against.
    per_station_medians = _mark_mad_outliers(per_station_medians)
    survivors = [s for s in per_station_medians if not s.is_outlier]
    n_used = len(survivors)

    # Compute the weighted median and weighted spread on survivors.
    # Both go into the response regardless of gate outcomes — the
    # median is what an override commits to; the spread is what the
    # panel displays as the diagnostic.
    weighted_median_thousandths: Optional[int] = None
    weighted_median_inhg: Optional[float] = None
    weighted_median_hpa: Optional[float] = None
    cross_station_spread_hpa: Optional[float] = None
    if n_used > 0:
        survivor_values_hpa = [
            _thousandths_inhg_to_hpa(s.median_altimeter_thousandths_inhg)
            for s in survivors
        ]
        survivor_weights = [
            _distance_weight(s.distance_miles) for s in survivors
        ]
        weighted_median_hpa = _weighted_median(
            survivor_values_hpa, survivor_weights,
        )
        weighted_median_thousandths = _hpa_to_thousandths_inhg(
            weighted_median_hpa,
        )
        weighted_median_inhg = round(
            weighted_median_thousandths / 1000, 3,
        )
        cross_station_spread_hpa = round(
            _weighted_spread_hpa(survivor_values_hpa, survivor_weights),
            3,
        )

    # Wq2: regional-quiescence gate.  Fraction of surviving stations
    # (post-MAD) whose newest report carries PRESRR / PRESFR — a
    # standard METAR remark meaning ≥0.06 inHg/hr rising or falling.
    # A single station firing is noise; a third of the regional set
    # firing IS the whole area moving, and pinning the console to any
    # snapshot of that would bake in whatever transient the front is
    # driving.  Ordered after MAD so a single miscalibrated station
    # reporting spurious trend groups (rare but real) cannot itself
    # trip the gate.  No override — same reasoning as Wq1: the
    # operator cannot see through the transient from the UI.
    #
    # Requires ``n_used >= MIN_STATIONS`` so a single lone survivor
    # cannot trip the gate at 100% (Codex R1 blocker on #310):
    # "single station is noise" is the whole point of the fraction
    # threshold, and one station == 1/1 == 100% would defeat it.
    # When n_used < MIN_STATIONS the min-stations gate below fires
    # instead — a more informative diagnostic than "unsettled".
    if n_used >= MIN_STATIONS:
        rapid_count = sum(1 for s in survivors if s.has_rapid_trend)
        if rapid_count / n_used >= RAPID_TREND_STATION_FRACTION:
            return AggregationResult(
                console=console,
                per_station_medians=per_station_medians,
                n_stations_considered=n_considered,
                n_stations_used=n_used,
                cross_station_spread_hpa=cross_station_spread_hpa,
                recommendation=Recommendation(
                    should_apply=False,
                    skip_reason=SKIP_UNSETTLED_REGIONAL,
                ),
                thresholds=thresholds,
            )

    # G2: fewer than MIN_STATIONS voted AFTER outlier rejection.  P0-1
    # in phone-sensor terms: refuse to write when only one reference is
    # present — a single reference cannot cross-check itself.  Counted
    # on survivors rather than raw candidates so a hostile drifted
    # station cannot inflate the count past the gate.  No override
    # allowed on this skip — with fewer than two references there is
    # no cross-check to speak of.
    if n_used < MIN_STATIONS:
        return AggregationResult(
            console=console,
            per_station_medians=per_station_medians,
            n_stations_considered=n_considered,
            n_stations_used=n_used,
            cross_station_spread_hpa=cross_station_spread_hpa,
            recommendation=Recommendation(
                should_apply=False, skip_reason=SKIP_INSUFFICIENT_STATIONS,
            ),
            thresholds=thresholds,
        )

    # We have a valid recommended value from here down.  Compute the
    # offset once so both the auto and the override branches use it.
    console_thousandths = _hpa_to_thousandths_inhg(console.median_hpa)
    offset_thousandths = (
        (weighted_median_thousandths or 0) - console_thousandths
    )

    # G3: surviving stations still disagree beyond tolerance (measured
    # on the WEIGHTED spread — inverse-distance-squared, so a distant
    # drifted station has little pull).  HOLD, but the panel is
    # allowed to offer an operator override this time — the algorithm
    # HAS produced a valid recommended value (the weighted median),
    # it is just below the confidence bar for autonomous write.
    # An override commits to that same weighted-median value, not to
    # any arbitrary operator-picked station: the multi-station
    # cross-check still governs the WRITE VALUE, only the write
    # DECISION is delegated to the operator.
    if (
        cross_station_spread_hpa is not None
        and cross_station_spread_hpa
        > CROSS_STATION_SPREAD_THRESHOLD_HPA
    ):
        return AggregationResult(
            console=console,
            per_station_medians=per_station_medians,
            n_stations_considered=n_considered,
            n_stations_used=n_used,
            cross_station_spread_hpa=cross_station_spread_hpa,
            recommendation=Recommendation(
                should_apply=False,
                skip_reason=SKIP_CROSS_STATION_DISAGREEMENT,
                median_of_medians_thousandths_inhg=weighted_median_thousandths,
                median_of_medians_inhg=weighted_median_inhg,
                offset_thousandths_inhg=offset_thousandths,
                offset_inhg=round(offset_thousandths / 1000, 3),
                hold_override_allowed=True,
            ),
            thresholds=thresholds,
        )

    # ---- All gates passed: recommend the weighted median for auto-write ----

    return AggregationResult(
        console=console,
        per_station_medians=per_station_medians,
        n_stations_considered=n_considered,
        n_stations_used=n_used,
        cross_station_spread_hpa=cross_station_spread_hpa,
        recommendation=Recommendation(
            should_apply=True,
            skip_reason=None,
            median_of_medians_thousandths_inhg=weighted_median_thousandths,
            median_of_medians_inhg=weighted_median_inhg,
            offset_thousandths_inhg=offset_thousandths,
            offset_inhg=round(offset_thousandths / 1000, 3),
        ),
        thresholds=thresholds,
    )
