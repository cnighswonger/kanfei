"""GET /api/history - Historical time-series data."""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query, Depends
from sqlalchemy import and_, case, func, Integer
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.sensor_reading import SensorReadingModel
from ..models.sensor_meta import (
    SENSOR_COLUMNS,
    SENSOR_UNITS,
    SENSOR_ALIASES,
    SENSOR_BOUNDS,
    SENSOR_SPIKE_THRESHOLDS,
    convert,
)

router = APIRouter()


@router.get("/history")
def get_history(
    sensor: str = Query(default="outside_temp", description="Sensor name"),
    start: str = Query(default=None, description="Start time ISO format"),
    end: str = Query(default=None, description="End time ISO format"),
    resolution: str = Query(default="raw", description="raw, hourly, or daily"),
    db: Session = Depends(get_db),
):
    """Return time-series data for a sensor."""
    # Resolve frontend display names to DB column names
    sensor = SENSOR_ALIASES.get(sensor, sensor)

    if sensor not in SENSOR_COLUMNS:
        return {"error": f"Unknown sensor: {sensor}", "available": list(SENSOR_COLUMNS.keys())}

    # Default time range: last 24 hours
    now = datetime.now(timezone.utc)
    if end:
        end_dt = datetime.fromisoformat(end)
    else:
        end_dt = now

    if start:
        start_dt = datetime.fromisoformat(start)
    else:
        start_dt = end_dt - timedelta(hours=24)

    column = SENSOR_COLUMNS[sensor]
    bounds = SENSOR_BOUNDS.get(sensor)
    spike_threshold = SENSOR_SPIKE_THRESHOLDS.get(sensor)

    if resolution == "raw":
        # Build CASE conditions: bounds check, then spike detection
        conditions: list[tuple] = []
        if bounds:
            conditions.append((~column.between(bounds[0], bounds[1]), None))
        if spike_threshold:
            lag_col = func.lag(column, 1).over(order_by=SensorReadingModel.timestamp)
            lead_col = func.lead(column, 1).over(order_by=SensorReadingModel.timestamp)
            conditions.append((
                and_(
                    func.abs(column - lag_col) > spike_threshold,
                    func.abs(column - lead_col) > spike_threshold,
                ),
                None,
            ))
        value_expr = case(*conditions, else_=column) if conditions else column

        results = (
            db.query(SensorReadingModel.timestamp, value_expr)
            .filter(SensorReadingModel.timestamp >= start_dt)
            .filter(SensorReadingModel.timestamp <= end_dt)
            .filter(column.isnot(None))
            .order_by(SensorReadingModel.timestamp)
            .all()
        )
        data = [
            {
                "timestamp": r[0].isoformat() + "Z",
                "value": convert(sensor, r[1]),
            }
            for r in results
        ]
    else:
        # For hourly/daily, return averages (bad values excluded)
        data = _aggregate(db, sensor, column, start_dt, end_dt, resolution,
                          bounds, spike_threshold)

    # Compute summary stats from the returned points
    if resolution == "raw":
        vals = [pt["value"] for pt in data if pt["value"] is not None]
    else:
        # Use per-bucket min/max for true extremes
        vals_min = [pt["min"] for pt in data if pt["min"] is not None]
        vals_max = [pt["max"] for pt in data if pt["max"] is not None]
        vals_avg = [pt["value"] for pt in data if pt["value"] is not None]
        vals = vals_avg  # for avg/count

    if resolution == "raw":
        summary = {
            "min": min(vals) if vals else None,
            "max": max(vals) if vals else None,
            "avg": round(sum(vals) / len(vals), 2) if vals else None,
            "count": len(vals),
        }
    else:
        summary = {
            "min": min(vals_min) if vals_min else None,
            "max": max(vals_max) if vals_max else None,
            "avg": round(sum(vals_avg) / len(vals_avg), 2) if vals_avg else None,
            "count": len(data),
        }

    return {
        "sensor": sensor,
        "unit": SENSOR_UNITS.get(sensor, ""),
        "start": start_dt.isoformat() + ("" if start_dt.tzinfo else "Z"),
        "end": end_dt.isoformat() + ("" if end_dt.tzinfo else "Z"),
        "resolution": resolution,
        "summary": summary,
        "points": data,
    }


def _aggregate(db, sensor, column, start_dt, end_dt, resolution,
               bounds=None, spike_threshold=None):
    """Aggregate readings by 5-minute, hourly, or daily buckets.

    SQLite forbids window functions (LAG/LEAD) inside GROUP BY queries,
    so when spike detection is needed we use a subquery: first compute
    clean values with window functions, then aggregate the result.
    """
    # --- Build clean-value expression (bounds + spike detection) ---
    conditions: list[tuple] = []
    if bounds:
        conditions.append((~column.between(bounds[0], bounds[1]), None))
    if spike_threshold:
        lag_col = func.lag(column, 1).over(order_by=SensorReadingModel.timestamp)
        lead_col = func.lead(column, 1).over(order_by=SensorReadingModel.timestamp)
        conditions.append((
            and_(
                func.abs(column - lag_col) > spike_threshold,
                func.abs(column - lead_col) > spike_threshold,
            ),
            None,
        ))

    need_subquery = spike_threshold is not None

    if need_subquery:
        # Subquery: compute clean values with window functions (no GROUP BY)
        clean_col = case(*conditions, else_=column) if conditions else column
        subq = (
            db.query(
                SensorReadingModel.timestamp.label("ts"),
                clean_col.label("val"),
            )
            .filter(SensorReadingModel.timestamp >= start_dt)
            .filter(SensorReadingModel.timestamp <= end_dt)
            .filter(column.isnot(None))
        ).subquery()

        ts_col = subq.c.ts
        val_col = subq.c.val
    else:
        # No window functions needed — query the table directly
        ts_col = SensorReadingModel.timestamp
        val_col = case(*conditions, else_=column) if conditions else column

    # --- Time bucket grouping ---
    if resolution == "5m":
        bucket = func.cast(func.strftime("%s", ts_col), Integer) / 300
        time_label = func.strftime("%Y-%m-%dT%H:%M:00", ts_col)
        group_key = bucket
    elif resolution == "hourly":
        group_key = func.strftime("%Y-%m-%dT%H:00:00", ts_col)
        time_label = group_key
    else:  # daily
        group_key = func.strftime("%Y-%m-%dT00:00:00", ts_col)
        time_label = group_key

    query = db.query(time_label, func.avg(val_col), func.min(val_col), func.max(val_col))

    if not need_subquery:
        # Apply filters directly (subquery already has them baked in)
        query = (
            query
            .filter(SensorReadingModel.timestamp >= start_dt)
            .filter(SensorReadingModel.timestamp <= end_dt)
            .filter(column.isnot(None))
        )

    results = query.group_by(group_key).order_by(group_key).all()

    return [
        {
            "timestamp": r[0] + "Z",
            "value": convert(sensor, r[1]),
            "min": convert(sensor, r[2]),
            "max": convert(sensor, r[3]),
        }
        for r in results
    ]
