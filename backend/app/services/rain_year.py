"""
Year-to-date rainfall with console-reset detection.

The Vue's ``rain_yearly`` counter accumulates cumulatively across the
year — until an operator (or a firmware event, or a factory reset)
zeroes it mid-year.  When that happens, the console's value stops
reflecting year-to-date rainfall and starts counting from the reset
event forward.  Kanfei faithfully surfaces whatever the console
reports, so the dashboard's ``Year`` figure can silently understate
the real yearly total by an arbitrary amount.

This service adds two capabilities on top of the raw console value:

1. **Reset detection.**  Walk 30 days of stored ``rain_yearly``
   samples looking for a drop.  Rain accumulates monotonically inside
   a year, so any drop is either a reset or the natural end-of-season
   rollover.  A drop within ±24 h of the configured season boundary
   (``rain_year_start`` month) or of January 1 is legitimate; a drop
   outside those windows is a mid-year reset.

2. **Archive-derived recomputation.**  Sum each day's maximum
   ``rain_total`` (daily rain counter, which resets at station-local
   midnight) since the season boundary.  This is what an operator
   actually means by ``Year`` — how much rain fell year-to-date —
   independent of what the console currently shows.

Wiring choice is per-station via ``rain_yearly_source`` in
``station_config``: ``auto`` (fall back to archive when a reset is
detected, otherwise trust the console), ``console`` (always trust
the console), or ``archive`` (always sum from the archive).  The
returned dict carries the source and the detected reset timestamp
so the UI can annotate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TypedDict

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.sensor_reading import SensorReadingModel


class YearlyRainResult(TypedDict, total=False):
    """Return shape from ``compute_yearly_rain``.

    ``value`` is in storage units (tenths of a millimetre) so callers
    can hand it to the existing ``convert("rain_yearly", value)``
    display pipeline unchanged.  ``source`` is ``'console'`` or
    ``'archive'``.  ``detected_reset_at`` is an ISO-8601 UTC
    timestamp of the detected mid-year reset, or absent when none
    was detected.
    """
    value: int | None
    source: str
    detected_reset_at: str


# Minimum drop in tenths-mm to count as a reset.  A ~2.5 mm (0.1 in)
# floor rejects noise from any storage or rounding weirdness while
# still catching a real console zeroing (which drops by hundreds).
_RESET_THRESHOLD_TENTHS_MM = 25

# How wide a window around the legitimate reset boundary counts as
# "same event."  Rain-season boundaries fire at station-local
# midnight but sample cadence + timezone slop means the drop can
# actually land anywhere in the surrounding day.
_BOUNDARY_WINDOW = timedelta(hours=24)


def _boundary_dates_this_year(year: int, season_month: int | None) -> list[datetime]:
    """Return the set of legitimate reset dates for the given year.

    Always includes January 1.  If ``season_month`` is 2-12 (the
    Vue's rain-season start), the corresponding first-of-month date
    is added too — a station that runs on a July water year should
    not treat its August-1 rollover as an anomaly.
    """
    boundaries = [datetime(year, 1, 1, tzinfo=timezone.utc)]
    if season_month and 2 <= season_month <= 12:
        boundaries.append(datetime(year, season_month, 1, tzinfo=timezone.utc))
    return boundaries


def _is_near_boundary(when: datetime, season_month: int | None) -> bool:
    """True if ``when`` sits within ``±_BOUNDARY_WINDOW`` of any
    legitimate reset date (this year or last)."""
    candidates = (
        _boundary_dates_this_year(when.year, season_month)
        + _boundary_dates_this_year(when.year - 1, season_month)
    )
    return any(abs(when - b) <= _BOUNDARY_WINDOW for b in candidates)


def detect_yearly_reset(
    db: Session, season_month: int | None, lookback_days: int = 30
) -> datetime | None:
    """Return the timestamp of the most recent mid-year reset within
    the last ``lookback_days``, or None if the counter walked
    monotonically or only reset at a legitimate season boundary.

    Bins samples by local day and looks for the first day whose
    minimum is materially below the previous day's maximum.  Sample
    cadence is 10-30 s, so the daily min/max bracket is a robust
    signal without pulling every reading into memory.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=lookback_days)
    rows = (
        db.query(
            func.date(SensorReadingModel.timestamp).label("day"),
            func.min(SensorReadingModel.rain_yearly).label("day_min"),
            func.max(SensorReadingModel.rain_yearly).label("day_max"),
        )
        .filter(SensorReadingModel.timestamp >= since)
        .filter(SensorReadingModel.rain_yearly.isnot(None))
        .group_by(func.date(SensorReadingModel.timestamp))
        .order_by(func.date(SensorReadingModel.timestamp))
        .all()
    )
    prev_max: int | None = None
    latest_reset: datetime | None = None
    for row in rows:
        day_min = row.day_min
        day_max = row.day_max
        if day_min is None or day_max is None:
            prev_max = None
            continue
        if prev_max is not None and day_min < prev_max - _RESET_THRESHOLD_TENTHS_MM:
            # Localise the reset to midnight of ``row.day`` — the
            # SQLite ``date()`` cast returns a string; parse it back.
            reset_day = datetime.strptime(row.day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if not _is_near_boundary(reset_day, season_month):
                latest_reset = reset_day
        prev_max = day_max
    return latest_reset


def sum_daily_max_since(db: Session, since: datetime) -> int:
    """Sum each day's peak ``rain_total`` (day counter) since ``since``,
    inclusive.  ``rain_total`` resets at station-local midnight, so
    its per-day maximum is that day's total; summing across days gives
    year-to-date accumulation independent of the yearly counter.

    Returns tenths-mm to match ``rain_yearly``'s storage unit.  Callers
    hand the result to ``convert("rain_yearly", ...)`` unchanged.
    """
    # SQLAlchemy's aggregate-of-aggregate patterns are finicky under
    # SQLite.  Pull daily maxes as a list and sum in Python — cheap at
    # thirty-odd rows per month and easier to reason about.
    daily = (
        db.query(func.max(SensorReadingModel.rain_total))
        .filter(SensorReadingModel.timestamp >= since)
        .filter(SensorReadingModel.rain_total.isnot(None))
        .group_by(func.date(SensorReadingModel.timestamp))
        .all()
    )
    total = 0
    for (day_max,) in daily:
        if day_max is not None:
            total += day_max
    return total


def _season_start_for_now(season_month: int | None) -> datetime:
    """Compute the last season-boundary crossing before ``now`` (UTC).

    If ``season_month`` is January (or unset), that's January 1 of
    the current year.  For a hydrological ``season_month`` like 7,
    it's July 1 — of this year if we've already passed it, else July
    1 of last year (the current water year started nine months ago).
    """
    now = datetime.now(timezone.utc)
    month = season_month if (season_month and 1 <= season_month <= 12) else 1
    candidate = datetime(now.year, month, 1, tzinfo=timezone.utc)
    if candidate > now:
        candidate = datetime(now.year - 1, month, 1, tzinfo=timezone.utc)
    return candidate


def compute_yearly_rain(
    db: Session,
    console_raw: int | None,
    source_mode: str,
    season_month: int | None,
) -> YearlyRainResult:
    """Return the yearly rain figure the dashboard should display.

    ``source_mode`` is one of:

    - ``auto`` — trust the console, but fall back to the archive when a
      mid-year reset is detected in the last 30 days.  The default.
    - ``console`` — always the console value.  Matches raw device
      behaviour and is what an operator picks if they intentionally
      zero the counter and want that reflected in the UI.
    - ``archive`` — always the sum from the archive.  Robust against
      future console resets but only accurate as far back as the
      archive itself; a fresh install with no history returns 0.
    """
    reset_at = detect_yearly_reset(db, season_month)
    use_archive = source_mode == "archive" or (source_mode == "auto" and reset_at is not None)
    if use_archive:
        since = _season_start_for_now(season_month)
        value = sum_daily_max_since(db, since)
        result: YearlyRainResult = {"value": value, "source": "archive"}
    else:
        result = {"value": console_raw, "source": "console"}
    if reset_at is not None:
        result["detected_reset_at"] = reset_at.isoformat().replace("+00:00", "Z")
    return result
