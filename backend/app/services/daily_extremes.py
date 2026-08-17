"""Shared daily extremes query — used by both the REST API and the WebSocket poller."""

from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.sensor_reading import SensorReadingModel
from ..models.sensor_meta import convert, SENSOR_UNITS, SENSOR_BOUNDS


def get_month_extremes(db: Session) -> Optional[dict]:
    """First-of-month at local midnight → now."""
    now = datetime.now().astimezone()
    month_start = now.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    ).astimezone(timezone.utc)
    return get_period_extremes(db, month_start)


def get_year_extremes(db: Session) -> Optional[dict]:
    """Jan 1 at local midnight → now."""
    now = datetime.now().astimezone()
    year_start = now.replace(
        month=1, day=1, hour=0, minute=0, second=0, microsecond=0,
    ).astimezone(timezone.utc)
    return get_period_extremes(db, year_start)


def get_weekly_delta(db: Session, column, sensor_key: str) -> Optional[dict]:
    """Rolling 7-day accumulation of a year-to-date counter column.

    ``rain_yearly`` and ``et_yearly`` are running year-to-date totals in
    storage units (rain: hundredths of inches; ET: tenths of a mm).
    The last 7 days is simply the current value minus the value from
    ~7 days ago, no daily-reset gotcha the way a ``rain_daily`` diff
    would have.  Returned in display units via ``convert()``.

    Returns None if either endpoint is missing, or if the delta is
    negative (a Jan 1 wraparound bridges two years — infrequent, but
    the tile prefers a null / em-dash to a bogus figure that week).
    """
    now = datetime.now(timezone.utc)
    latest = (
        db.query(SensorReadingModel.timestamp, column)
        .filter(column.isnot(None))
        .order_by(SensorReadingModel.timestamp.desc())
        .first()
    )
    if latest is None or latest[1] is None:
        return None
    earlier = (
        db.query(column)
        .filter(SensorReadingModel.timestamp <= now - timedelta(days=7))
        .filter(column.isnot(None))
        .order_by(SensorReadingModel.timestamp.desc())
        .first()
    )
    if earlier is None or earlier[0] is None:
        return None
    delta_raw = latest[1] - earlier[0]
    if delta_raw < 0:
        return None
    display = convert(sensor_key, delta_raw)
    return {"value": display, "unit": SENSOR_UNITS.get(sensor_key, "")}


def _iso_z(ts: Optional[datetime]) -> Optional[str]:
    """Serialise a naive-UTC datetime (SQLite returns these) as ISO-8601 with Z.

    Frontend ``new Date(iso)`` requires an explicit timezone designator to
    parse as UTC; without it the value is interpreted as local time.
    """
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _val(column: str, raw, at: Optional[datetime] = None) -> Optional[dict]:
    if raw is None:
        return None
    return {
        "value": convert(column, raw),
        "unit": SENSOR_UNITS.get(column, ""),
        "at": _iso_z(at),
    }


def _clamp_hum(val: Optional[dict]) -> Optional[dict]:
    """Clamp humidity display to 0-100%."""
    if val is None or val["value"] is None:
        return val
    val["value"] = max(0, min(100, val["value"]))
    return val


def _in_bounds(column: str, raw) -> bool:
    """Whether a RAW (pre-conversion) reading is inside its declared range.

    SENSOR_BOUNDS already existed and is applied by history.py and
    export.py, so charts and CSV exports have always discarded
    out-of-range values.  Daily extremes did not consult it — which meant
    the *published* path was the least guarded one, since cwop.py and
    wunderground.py both source their gust from wind_speed_hi.

    That gap is how a 27-minute transmitter dropout on the bench Vue put a
    255 mph gust on APRS/findu for hours after the link recovered.  The
    instantaneous wind was correct throughout; only the daily maximum was
    poisoned, and an extreme outlives the outage that produced it.

    Checking the raw value matters: these bounds are in storage units, and
    the guard has to run before convert(), or the threshold would depend
    on whether the user displays mph, km/h or m/s.
    """
    if raw is None:
        return True
    bounds = SENSOR_BOUNDS.get(column)
    if bounds is None:
        return True
    return bounds[0] <= raw <= bounds[1]


def _bounded(column: str, raw, at_fn) -> Optional[dict]:
    """_val(), but discarding readings outside the sensor's declared range."""
    if not _in_bounds(column, raw):
        return None
    return _val(column, raw, at_fn())


def _at(db: Session, midnight: datetime, column, raw) -> Optional[datetime]:
    """Earliest timestamp at which ``column`` equalled ``raw`` since midnight.

    Returns ``None`` when ``raw`` is ``None``.  For tied extrema the earliest
    occurrence wins so the displayed time is the first time the peak was
    reached today.
    """
    if raw is None:
        return None
    S = SensorReadingModel
    row = (
        db.query(func.min(S.timestamp))
        .filter(S.timestamp >= midnight, column == raw)
        .first()
    )
    return row[0] if row is not None else None


def get_period_extremes(db: Session, since_utc: datetime) -> Optional[dict]:
    """Return temperature / barometer / gust extremes since ``since_utc``.

    Companion to ``get_daily_extremes`` for the Weather Nerd persona's
    month + year rows.  Same bounds guard; a much reduced shape (no
    inside temps, no humidity, no rain rate — those aren't rendered on
    the Weather Nerd extremes tile).  Returns ``None`` when the window
    has no rows at all.
    """
    S = SensorReadingModel

    # Bounded max/min per column: computed inside SQL so a single
    # out-of-range value (e.g., a startup zero, a hurricane-eye
    # sentinel from a glitched read) doesn't null the extreme for
    # the whole window.  Previously the query took a plain
    # ``func.max/min``, then ``_bounded()`` rejected the raw value
    # post-hoc — one 7781 hundredths-inHg row (25.5 inHg) was
    # nulling the entire year's ``barometer_lo``.
    def _bmax(column: str, model_col):
        bounds = SENSOR_BOUNDS.get(column)
        q = func.max(model_col)
        if bounds is not None:
            q = func.max(model_col).filter(model_col.between(bounds[0], bounds[1]))
        return q

    def _bmin(column: str, model_col):
        bounds = SENSOR_BOUNDS.get(column)
        q = func.min(model_col)
        if bounds is not None:
            q = func.min(model_col).filter(model_col.between(bounds[0], bounds[1]))
        return q

    row = (
        db.query(
            _bmax("outside_temp", S.outside_temp),
            _bmin("outside_temp", S.outside_temp),
            _bmax("wind_speed",   S.wind_speed),
            _bmax("barometer",    S.barometer),
            _bmin("barometer",    S.barometer),
        )
        .filter(S.timestamp >= since_utc)
        .first()
    )
    if row is None or all(v is None for v in row):
        return None

    def V(column, raw, model_col):
        # Values already in-bounds by construction; still route through
        # ``_val`` for the display-unit conversion and ``at`` lookup.
        if raw is None:
            return None
        return _val(column, raw, _at(db, since_utc, model_col, raw))

    return {
        "outside_temp_hi": V("outside_temp", row[0], S.outside_temp),
        "outside_temp_lo": V("outside_temp", row[1], S.outside_temp),
        "wind_speed_hi":   V("wind_speed",   row[2], S.wind_speed),
        "barometer_hi":    V("barometer",    row[3], S.barometer),
        "barometer_lo":    V("barometer",    row[4], S.barometer),
    }


def get_daily_extremes(db: Session) -> Optional[dict]:
    """Query today's high/low extremes from sensor_readings.

    Used by both GET /api/current and the WebSocket broadcast poller.
    """
    now = datetime.now().astimezone()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    S = SensorReadingModel
    row = (
        db.query(
            func.max(S.outside_temp), func.min(S.outside_temp),
            func.max(S.inside_temp), func.min(S.inside_temp),
            func.max(S.wind_speed),
            func.max(S.barometer), func.min(S.barometer),
            func.max(S.outside_humidity), func.min(S.outside_humidity),
            func.max(S.rain_rate),
            func.max(S.inside_humidity), func.min(S.inside_humidity),
        )
        .filter(S.timestamp >= midnight)
        .first()
    )

    if row is None or row[0] is None:
        return None

    # Every extreme goes through _bounded().  SENSOR_BOUNDS was already
    # applied by history.py and export.py; daily extremes were the gap,
    # and they are the ones that get PUBLISHED — cwop.py and
    # wunderground.py both source their gust from wind_speed_hi.
    def B(column, raw, model_col):
        return _bounded(column, raw, lambda: _at(db, midnight, model_col, raw))

    return {
        "outside_temp_hi": B("outside_temp", row[0], S.outside_temp),
        "outside_temp_lo": B("outside_temp", row[1], S.outside_temp),
        "inside_temp_hi": B("inside_temp", row[2], S.inside_temp),
        "inside_temp_lo": B("inside_temp", row[3], S.inside_temp),
        "wind_speed_hi": B("wind_speed", row[4], S.wind_speed),
        "barometer_hi": B("barometer", row[5], S.barometer),
        "barometer_lo": B("barometer", row[6], S.barometer),
        "humidity_hi": _clamp_hum(B("outside_humidity", row[7], S.outside_humidity)),
        "humidity_lo": _clamp_hum(B("outside_humidity", row[8], S.outside_humidity)),
        "rain_rate_hi": B("rain_rate", row[9], S.rain_rate),
        "inside_humidity_hi": _clamp_hum(B("inside_humidity", row[10], S.inside_humidity)),
        "inside_humidity_lo": _clamp_hum(B("inside_humidity", row[11], S.inside_humidity)),
    }
