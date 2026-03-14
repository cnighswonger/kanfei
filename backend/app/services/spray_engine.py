"""Rule-based spray constraint evaluation engine.

Evaluates spray product constraints against forecast data and current
observations to produce go/no-go recommendations and find optimal windows.
Also holds preset product definitions and seeding logic.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Open-Meteo forecast fetch (lightweight, independent of nowcast collector)
# ---------------------------------------------------------------------------

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_TIMEOUT = 15.0
SPRAY_HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "wind_gusts_10m",
]

# Simple in-memory forecast cache (15-minute TTL).
_forecast_cache: dict[str, Any] = {"data": None, "expires": 0.0}
FORECAST_CACHE_TTL = 900  # 15 minutes


async def fetch_hourly_forecast(
    lat: float, lon: float, hours: int = 48,
) -> dict[str, list]:
    """Fetch hourly forecast from Open-Meteo for spray evaluation.

    Returns a dict with keys matching SPRAY_HOURLY_VARS plus 'time',
    each containing a list of hourly values. Cached for 15 minutes.
    """
    now = time.time()
    if _forecast_cache["data"] is not None and now < _forecast_cache["expires"]:
        return _forecast_cache["data"]

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(SPRAY_HOURLY_VARS),
        "forecast_hours": hours,
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
    }
    try:
        async with httpx.AsyncClient(timeout=OPEN_METEO_TIMEOUT) as client:
            resp = await client.get(OPEN_METEO_URL, params=params)
            resp.raise_for_status()
            hourly = resp.json().get("hourly", {})
            _forecast_cache["data"] = hourly
            _forecast_cache["expires"] = now + FORECAST_CACHE_TTL
            return hourly
    except Exception as exc:
        logger.warning("Spray forecast fetch failed: %s", exc)
        # Return cached data if available even if expired.
        if _forecast_cache["data"] is not None:
            return _forecast_cache["data"]
        return {}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ConstraintCheck:
    """Result of checking a single constraint."""
    name: str           # "wind", "temperature", "rain_free", "humidity"
    passed: bool
    current_value: str  # Human-readable current/forecast value
    threshold: str      # Human-readable threshold
    detail: str         # Explanation


@dataclass
class SprayEvaluation:
    """Full evaluation result for a spray product."""
    go: bool
    constraints: list[ConstraintCheck]
    overall_detail: str
    optimal_window: Optional[dict] = None  # {"start": iso, "end": iso}
    confidence: str = "MEDIUM"  # HIGH, MEDIUM, LOW


@dataclass
class ProductConstraints:
    """Constraint values for a spray product (extracted from DB model)."""
    rain_free_hours: float = 2.0
    max_wind_mph: float = 10.0
    min_temp_f: float = 45.0
    max_temp_f: float = 85.0
    min_humidity_pct: Optional[float] = None
    max_humidity_pct: Optional[float] = None


# ---------------------------------------------------------------------------
# Preset products
# ---------------------------------------------------------------------------

PRESET_PRODUCTS = [
    {
        "name": "Herbicide (Contact)",
        "category": "herbicide_contact",
        "rain_free_hours": 1.5,
        "max_wind_mph": 10.0,
        "min_temp_f": 45.0,
        "max_temp_f": 85.0,
        "notes": "Contact herbicides need 1-2 hours rain-free for leaf absorption.",
    },
    {
        "name": "Herbicide (Systemic)",
        "category": "herbicide_systemic",
        "rain_free_hours": 4.0,
        "max_wind_mph": 10.0,
        "min_temp_f": 50.0,
        "max_temp_f": 85.0,
        "notes": "Systemic herbicides require 4+ hours for plant translocation.",
    },
    {
        "name": "Fungicide (Protectant)",
        "category": "fungicide_protectant",
        "rain_free_hours": 1.5,
        "max_wind_mph": 8.0,
        "min_temp_f": 40.0,
        "max_temp_f": 90.0,
        "notes": "Protectant fungicides coat leaf surfaces; need time to dry.",
    },
    {
        "name": "Fungicide (Systemic)",
        "category": "fungicide_systemic",
        "rain_free_hours": 3.0,
        "max_wind_mph": 8.0,
        "min_temp_f": 50.0,
        "max_temp_f": 85.0,
        "notes": "Systemic fungicides need absorption time before rain.",
    },
    {
        "name": "Insecticide (Contact)",
        "category": "insecticide_contact",
        "rain_free_hours": 2.0,
        "max_wind_mph": 8.0,
        "min_temp_f": 40.0,
        "max_temp_f": 90.0,
        "notes": "Contact insecticides require direct pest exposure.",
    },
    {
        "name": "Plant Growth Regulator",
        "category": "pgr",
        "rain_free_hours": 4.0,
        "max_wind_mph": 5.0,
        "min_temp_f": 50.0,
        "max_temp_f": 80.0,
        "notes": "PGRs are sensitive to drift; apply in very calm conditions.",
    },
]


def seed_presets(db) -> int:
    """Insert default spray products if none exist. Returns count seeded."""
    from ..models.spray import SprayProduct

    existing = db.query(SprayProduct).filter(SprayProduct.is_preset == 1).count()
    if existing > 0:
        return 0
    count = 0
    for preset in PRESET_PRODUCTS:
        product = SprayProduct(is_preset=1, **preset)
        db.add(product)
        count += 1
    db.commit()
    logger.info("Seeded %d preset spray products", count)
    return count


# ---------------------------------------------------------------------------
# Evaluation logic
# ---------------------------------------------------------------------------

def _check_wind(
    forecast_wind: Optional[float],
    forecast_gust: Optional[float],
    max_wind: float,
) -> ConstraintCheck:
    """Check wind speed constraint. Uses gust if available, else sustained."""
    effective = forecast_gust if forecast_gust is not None else forecast_wind
    if effective is None:
        return ConstraintCheck(
            name="wind", passed=True,
            current_value="N/A", threshold=f"<{max_wind} mph",
            detail="No wind data available; assuming OK.",
        )
    passed = effective <= max_wind
    label = "gust" if forecast_gust is not None else "sustained"
    return ConstraintCheck(
        name="wind", passed=passed,
        current_value=f"{effective:.0f} mph ({label})",
        threshold=f"<{max_wind} mph",
        detail=(
            f"Wind {effective:.0f} mph {'within' if passed else 'exceeds'} "
            f"{max_wind} mph limit."
        ),
    )


def _check_temperature(
    forecast_temp: Optional[float],
    min_temp: float,
    max_temp: float,
) -> ConstraintCheck:
    """Check temperature range constraint."""
    if forecast_temp is None:
        return ConstraintCheck(
            name="temperature", passed=True,
            current_value="N/A", threshold=f"{min_temp}-{max_temp}\u00B0F",
            detail="No temperature data available; assuming OK.",
        )
    passed = min_temp <= forecast_temp <= max_temp
    return ConstraintCheck(
        name="temperature", passed=passed,
        current_value=f"{forecast_temp:.0f}\u00B0F",
        threshold=f"{min_temp}-{max_temp}\u00B0F",
        detail=(
            f"Temperature {forecast_temp:.0f}\u00B0F {'within' if passed else 'outside'} "
            f"range {min_temp}-{max_temp}\u00B0F."
        ),
    )


def _check_humidity(
    forecast_humidity: Optional[float],
    min_hum: Optional[float],
    max_hum: Optional[float],
) -> Optional[ConstraintCheck]:
    """Check humidity constraint. Returns None if no humidity limits set."""
    if min_hum is None and max_hum is None:
        return None
    if forecast_humidity is None:
        return ConstraintCheck(
            name="humidity", passed=True,
            current_value="N/A",
            threshold=f"{min_hum or 'any'}-{max_hum or 'any'}%",
            detail="No humidity data available; assuming OK.",
        )
    low_ok = forecast_humidity >= min_hum if min_hum is not None else True
    high_ok = forecast_humidity <= max_hum if max_hum is not None else True
    passed = low_ok and high_ok
    lo = f"{min_hum:.0f}" if min_hum is not None else "any"
    hi = f"{max_hum:.0f}" if max_hum is not None else "any"
    return ConstraintCheck(
        name="humidity", passed=passed,
        current_value=f"{forecast_humidity:.0f}%",
        threshold=f"{lo}-{hi}%",
        detail=(
            f"Humidity {forecast_humidity:.0f}% {'within' if passed else 'outside'} "
            f"range {lo}-{hi}%."
        ),
    )


def _check_rain_free(
    hourly_precip: list[float],
    start_idx: int,
    rain_free_hours: float,
) -> ConstraintCheck:
    """Check that no precipitation is forecast for rain_free_hours after start."""
    hours_needed = int(rain_free_hours + 0.99)  # round up
    end_idx = min(start_idx + hours_needed, len(hourly_precip))
    window = hourly_precip[start_idx:end_idx]

    if not window:
        return ConstraintCheck(
            name="rain_free", passed=True,
            current_value="No forecast data",
            threshold=f"{rain_free_hours}h rain-free",
            detail="Insufficient forecast data for rain-free check.",
        )

    total_precip = sum(p for p in window if p is not None)
    rain_hours = sum(1 for p in window if p is not None and p > 0)
    passed = total_precip < 0.01  # essentially zero
    logger.info(
        "Rain-free check: start_idx=%d, window=%s, total=%.3f\", passed=%s",
        start_idx, window, total_precip, passed,
    )

    if passed:
        detail = f"No rain forecast for {len(window)}h after application."
    else:
        # Find first rain hour.
        first_rain = next(
            (i for i, p in enumerate(window) if p is not None and p > 0), 0
        )
        detail = (
            f"Rain expected {first_rain}h after application "
            f"({total_precip:.2f}\" in {rain_hours}h). "
            f"Need {rain_free_hours}h rain-free."
        )

    return ConstraintCheck(
        name="rain_free", passed=passed,
        current_value=f"{total_precip:.2f}\" in {len(window)}h",
        threshold=f"{rain_free_hours}h rain-free",
        detail=detail,
    )


def _find_hour_index(
    times: list[str], target: datetime,
) -> int:
    """Find the closest forecast hour index for a target datetime."""
    if not times:
        return 0
    target_str = target.strftime("%Y-%m-%dT%H:00")
    logger.info(
        "Rain-free lookup: target=%s, forecast range=%s..%s",
        target_str, times[0] if times else "?", times[-1] if times else "?",
    )
    for i, t in enumerate(times):
        if t >= target_str:
            return i
    return len(times) - 1


def evaluate_conditions(
    constraints: ProductConstraints,
    hourly: dict[str, list],
    planned_start: datetime,
    planned_end: datetime,
) -> SprayEvaluation:
    """Evaluate spray constraints against hourly forecast for a time window.

    Args:
        constraints: Product constraint values.
        hourly: Open-Meteo hourly forecast dict with 'time' and variable lists.
        planned_start: Start of planned application window (UTC).
        planned_end: End of planned application window (UTC).

    Returns:
        SprayEvaluation with per-constraint results and overall go/no-go.
    """
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    humidities = hourly.get("relative_humidity_2m", [])
    precips = hourly.get("precipitation", [])
    winds = hourly.get("wind_speed_10m", [])
    gusts = hourly.get("wind_gusts_10m", [])

    if not times:
        return SprayEvaluation(
            go=False,
            constraints=[],
            overall_detail="No forecast data available for evaluation.",
            confidence="LOW",
        )

    start_idx = _find_hour_index(times, planned_start)
    end_idx = _find_hour_index(times, planned_end)

    # Use worst-case values across the application window.
    window_slice = slice(start_idx, end_idx + 1)

    def _worst(values: list, fn):
        subset = values[window_slice] if values else []
        valid = [v for v in subset if v is not None]
        return fn(valid) if valid else None

    max_wind = _worst(winds, max)
    max_gust = _worst(gusts, max)
    # For temp, check both min and max across window.
    min_temp_val = _worst(temps, min)
    max_temp_val = _worst(temps, max)
    avg_humidity = _worst(humidities, lambda v: sum(v) / len(v))

    checks: list[ConstraintCheck] = []

    # Wind — use worst case.
    checks.append(_check_wind(max_wind, max_gust, constraints.max_wind_mph))

    # Temperature — check if any hour falls outside range.
    temp_passed = True
    temp_detail_parts = []
    if min_temp_val is not None and min_temp_val < constraints.min_temp_f:
        temp_passed = False
        temp_detail_parts.append(f"Low of {min_temp_val:.1f}\u00B0F below {constraints.min_temp_f}\u00B0F minimum.")
    if max_temp_val is not None and max_temp_val > constraints.max_temp_f:
        temp_passed = False
        temp_detail_parts.append(f"High of {max_temp_val:.1f}\u00B0F above {constraints.max_temp_f}\u00B0F maximum.")
    if temp_passed:
        temp_range_str = (
            f"{min_temp_val:.1f}-{max_temp_val:.1f}\u00B0F"
            if min_temp_val is not None and max_temp_val is not None
            else "N/A"
        )
        temp_detail_parts.append(f"Temperature {temp_range_str} within range.")

    checks.append(ConstraintCheck(
        name="temperature", passed=temp_passed,
        current_value=(
            f"{min_temp_val:.1f}-{max_temp_val:.1f}\u00B0F"
            if min_temp_val is not None and max_temp_val is not None
            else "N/A"
        ),
        threshold=f"{constraints.min_temp_f}-{constraints.max_temp_f}\u00B0F",
        detail=" ".join(temp_detail_parts),
    ))

    # Humidity.
    hum_check = _check_humidity(
        avg_humidity, constraints.min_humidity_pct, constraints.max_humidity_pct,
    )
    if hum_check:
        checks.append(hum_check)

    # Rain-free.
    checks.append(_check_rain_free(precips, start_idx, constraints.rain_free_hours))

    all_passed = all(c.passed for c in checks)
    failed = [c for c in checks if not c.passed]

    if all_passed:
        overall = "All constraints met — conditions favorable for spraying."
        confidence = "HIGH"
    elif len(failed) == 1:
        overall = f"One constraint not met: {failed[0].name}. {failed[0].detail}"
        confidence = "MEDIUM"
    else:
        names = ", ".join(c.name for c in failed)
        overall = f"Multiple constraints not met: {names}."
        confidence = "LOW"

    return SprayEvaluation(
        go=all_passed,
        constraints=checks,
        overall_detail=overall,
        confidence=confidence,
    )


def evaluate_current(
    constraints: ProductConstraints,
    current_obs: dict[str, Any],
) -> SprayEvaluation:
    """Instant check of current observations against product constraints."""
    checks: list[ConstraintCheck] = []

    wind = current_obs.get("wind_speed_mph")
    gust = current_obs.get("wind_gust_mph")
    checks.append(_check_wind(wind, gust, constraints.max_wind_mph))

    temp = current_obs.get("outside_temp_f")
    checks.append(_check_temperature(temp, constraints.min_temp_f, constraints.max_temp_f))

    hum = current_obs.get("outside_humidity_pct")
    hum_check = _check_humidity(
        hum, constraints.min_humidity_pct, constraints.max_humidity_pct,
    )
    if hum_check:
        checks.append(hum_check)

    # Rain-free can't be checked from current obs alone; check rain rate.
    rain_rate = current_obs.get("rain_rate_in_hr")
    if rain_rate is not None and rain_rate > 0:
        checks.append(ConstraintCheck(
            name="rain_free", passed=False,
            current_value=f"{rain_rate:.2f} in/hr",
            threshold="No active rain",
            detail=f"Currently raining at {rain_rate:.2f} in/hr.",
        ))
    else:
        checks.append(ConstraintCheck(
            name="rain_free", passed=True,
            current_value="No rain",
            threshold=f"{constraints.rain_free_hours}h rain-free (forecast needed)",
            detail="No current rain. Check forecast for rain-free window.",
        ))

    all_passed = all(c.passed for c in checks)
    failed = [c for c in checks if not c.passed]

    if all_passed:
        overall = "Current conditions favorable. Check forecast for rain-free window."
    else:
        names = ", ".join(c.name for c in failed)
        overall = f"Current conditions unfavorable: {names}."

    return SprayEvaluation(
        go=all_passed,
        constraints=checks,
        overall_detail=overall,
        confidence="MEDIUM",  # Current-only checks always medium (no forecast context)
    )


def find_optimal_window(
    constraints: ProductConstraints,
    hourly: dict[str, list],
    search_hours: int = 24,
    station_tz: str = "",
) -> Optional[dict]:
    """Find the next continuous window where all constraints are met.

    Returns {"start": iso_str, "end": iso_str, "duration_hours": N} or None.
    """
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    humidities = hourly.get("relative_humidity_2m", [])
    precips = hourly.get("precipitation", [])
    winds = hourly.get("wind_speed_10m", [])
    gusts = hourly.get("wind_gusts_10m", [])

    if not times:
        return None

    # Determine how many future hours to scan.
    limit = min(search_hours, len(times))

    # For each hour, check if all instantaneous constraints pass.
    ok_hours: list[bool] = []
    for i in range(limit):
        wind_ok = True
        w = gusts[i] if i < len(gusts) and gusts[i] is not None else (
            winds[i] if i < len(winds) else None
        )
        if w is not None:
            wind_ok = w <= constraints.max_wind_mph

        temp_ok = True
        t = temps[i] if i < len(temps) else None
        if t is not None:
            temp_ok = constraints.min_temp_f <= t <= constraints.max_temp_f

        hum_ok = True
        h = humidities[i] if i < len(humidities) else None
        if h is not None:
            if constraints.min_humidity_pct is not None:
                hum_ok = hum_ok and h >= constraints.min_humidity_pct
            if constraints.max_humidity_pct is not None:
                hum_ok = hum_ok and h <= constraints.max_humidity_pct

        # Rain-free: check no precip for rain_free_hours starting at this hour.
        rain_ok = True
        rf_hours = int(constraints.rain_free_hours + 0.99)
        for j in range(i, min(i + rf_hours, len(precips))):
            p = precips[j] if j < len(precips) else None
            if p is not None and p > 0:
                rain_ok = False
                break

        ok_hours.append(wind_ok and temp_ok and hum_ok and rain_ok)

    # Find the longest run of consecutive OK hours.
    best_start = -1
    best_len = 0
    run_start = -1
    run_len = 0
    for i, ok in enumerate(ok_hours):
        if ok:
            if run_start < 0:
                run_start = i
                run_len = 1
            else:
                run_len += 1
            if run_len > best_len:
                best_start = run_start
                best_len = run_len
        else:
            run_start = -1
            run_len = 0

    if best_len < 1 or best_start < 0:
        return None

    # Resolve timezone for display.
    tz: ZoneInfo | None = None
    if station_tz:
        try:
            tz = ZoneInfo(station_tz)
        except (KeyError, Exception):
            pass

    start_iso = times[best_start]
    end_idx = min(best_start + best_len - 1, len(times) - 1)
    end_iso = times[end_idx]

    # Convert to local time if timezone available.
    if tz:
        try:
            s = datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc).astimezone(tz)
            e = datetime.fromisoformat(end_iso).replace(tzinfo=timezone.utc).astimezone(tz)
            start_iso = s.isoformat()
            end_iso = e.isoformat()
        except (ValueError, Exception):
            pass

    return {
        "start": start_iso,
        "end": end_iso,
        "duration_hours": best_len,
    }


# ---------------------------------------------------------------------------
# Threshold tuning from outcome history
# ---------------------------------------------------------------------------

# Minimum positive outcomes required beyond a preset threshold before
# we consider relaxing that threshold.
_MIN_POSITIVE_OUTCOMES = 3
_MIN_EFFECTIVENESS = 4  # 4+ = "good" or "excellent"


@dataclass
class TunedConstraint:
    """A constraint threshold that may have been adjusted from outcomes."""
    name: str
    preset_value: float
    tuned_value: float | None  # None if unchanged
    outcome_count: int  # outcomes backing the tuned value
    annotation: str  # human-readable explanation


@dataclass
class TunedConstraints:
    """Product constraints with optional tuning from outcome history."""
    constraints: ProductConstraints  # original presets
    tuned: list[TunedConstraint]

    def effective_max_wind(self) -> float:
        for t in self.tuned:
            if t.name == "max_wind_mph" and t.tuned_value is not None:
                return t.tuned_value
        return self.constraints.max_wind_mph

    def effective_min_temp(self) -> float:
        for t in self.tuned:
            if t.name == "min_temp_f" and t.tuned_value is not None:
                return t.tuned_value
        return self.constraints.min_temp_f

    def effective_max_temp(self) -> float:
        for t in self.tuned:
            if t.name == "max_temp_f" and t.tuned_value is not None:
                return t.tuned_value
        return self.constraints.max_temp_f


def get_tuned_constraints(
    constraints: ProductConstraints,
    outcomes: list[dict],
) -> TunedConstraints:
    """Analyze past outcomes to compute effective thresholds.

    Only widens thresholds when there are 3+ positive outcomes (effectiveness
    >= 4) beyond the preset threshold.

    Args:
        constraints: Original product constraints.
        outcomes: List of outcome dicts with keys: effectiveness,
                  actual_wind_mph, actual_temp_f, drift_observed.

    Returns:
        TunedConstraints with adjusted limits and annotations.
    """
    tuned: list[TunedConstraint] = []

    # --- Wind threshold ---
    good_winds = [
        o["actual_wind_mph"] for o in outcomes
        if o.get("actual_wind_mph") is not None
        and o.get("effectiveness", 0) >= _MIN_EFFECTIVENESS
        and o["actual_wind_mph"] > constraints.max_wind_mph
    ]
    if len(good_winds) >= _MIN_POSITIVE_OUTCOMES:
        # Relax to the max observed wind with good results, rounded up.
        new_max = round(max(good_winds), 1)
        tuned.append(TunedConstraint(
            name="max_wind_mph",
            preset_value=constraints.max_wind_mph,
            tuned_value=new_max,
            outcome_count=len(good_winds),
            annotation=(
                f"Relaxed from {constraints.max_wind_mph} mph based on "
                f"{len(good_winds)} successful applications at up to "
                f"{new_max} mph"
            ),
        ))
    else:
        tuned.append(TunedConstraint(
            name="max_wind_mph",
            preset_value=constraints.max_wind_mph,
            tuned_value=None,
            outcome_count=0,
            annotation="",
        ))

    # --- Min temperature threshold ---
    good_low_temps = [
        o["actual_temp_f"] for o in outcomes
        if o.get("actual_temp_f") is not None
        and o.get("effectiveness", 0) >= _MIN_EFFECTIVENESS
        and o["actual_temp_f"] < constraints.min_temp_f
    ]
    if len(good_low_temps) >= _MIN_POSITIVE_OUTCOMES:
        new_min = round(min(good_low_temps), 1)
        tuned.append(TunedConstraint(
            name="min_temp_f",
            preset_value=constraints.min_temp_f,
            tuned_value=new_min,
            outcome_count=len(good_low_temps),
            annotation=(
                f"Lowered from {constraints.min_temp_f}\u00b0F based on "
                f"{len(good_low_temps)} successful applications down to "
                f"{new_min}\u00b0F"
            ),
        ))
    else:
        tuned.append(TunedConstraint(
            name="min_temp_f",
            preset_value=constraints.min_temp_f,
            tuned_value=None,
            outcome_count=0,
            annotation="",
        ))

    # --- Max temperature threshold ---
    good_high_temps = [
        o["actual_temp_f"] for o in outcomes
        if o.get("actual_temp_f") is not None
        and o.get("effectiveness", 0) >= _MIN_EFFECTIVENESS
        and o["actual_temp_f"] > constraints.max_temp_f
    ]
    if len(good_high_temps) >= _MIN_POSITIVE_OUTCOMES:
        new_max = round(max(good_high_temps), 1)
        tuned.append(TunedConstraint(
            name="max_temp_f",
            preset_value=constraints.max_temp_f,
            tuned_value=new_max,
            outcome_count=len(good_high_temps),
            annotation=(
                f"Raised from {constraints.max_temp_f}\u00b0F based on "
                f"{len(good_high_temps)} successful applications up to "
                f"{new_max}\u00b0F"
            ),
        ))
    else:
        tuned.append(TunedConstraint(
            name="max_temp_f",
            preset_value=constraints.max_temp_f,
            tuned_value=None,
            outcome_count=0,
            annotation="",
        ))

    return TunedConstraints(constraints=constraints, tuned=tuned)
