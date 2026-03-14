"""GET /api/export - CSV download of historical sensor data."""

import csv
import io
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.sensor_reading import SensorReadingModel
from ..models.sensor_meta import (
    SENSOR_COLUMNS,
    SENSOR_DIVISORS,
    SENSOR_UNITS,
    SENSOR_ALIASES,
    SENSOR_BOUNDS,
)
from .history import _aggregate

router = APIRouter()


@router.get("/export")
def export_csv(
    sensors: str = Query(default="outside_temp", description="Comma-separated sensor names"),
    start: str = Query(default=None, description="Start time ISO format"),
    end: str = Query(default=None, description="End time ISO format"),
    resolution: str = Query(default="raw", description="raw, 5m, hourly, or daily"),
    db: Session = Depends(get_db),
):
    """Export historical data as a CSV file download."""
    # Parse time range
    now = datetime.now(timezone.utc)
    end_dt = datetime.fromisoformat(end) if end else now
    start_dt = datetime.fromisoformat(start) if start else end_dt - timedelta(hours=24)

    # Resolve sensor names
    raw_names = [s.strip() for s in sensors.split(",") if s.strip()]
    resolved = []
    for name in raw_names:
        canonical = SENSOR_ALIASES.get(name, name)
        if canonical in SENSOR_COLUMNS:
            resolved.append(canonical)

    if not resolved:
        return {"error": "No valid sensors specified", "available": list(SENSOR_COLUMNS.keys())}

    # Build CSV in memory via streaming generator
    def generate():
        output = io.StringIO()
        writer = csv.writer(output)

        # Header row
        headers = ["timestamp"]
        for s in resolved:
            unit = SENSOR_UNITS.get(s, "")
            headers.append(f"{s} ({unit})" if unit else s)
        writer.writerow(headers)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        if resolution == "raw":
            # Single query for all requested columns
            columns = [SensorReadingModel.timestamp] + [SENSOR_COLUMNS[s] for s in resolved]
            results = (
                db.query(*columns)
                .filter(SensorReadingModel.timestamp >= start_dt)
                .filter(SensorReadingModel.timestamp <= end_dt)
                .order_by(SensorReadingModel.timestamp)
                .all()
            )

            for row in results:
                ts = row[0].isoformat() + "Z" if row[0] else ""
                values = [ts]
                for i, s in enumerate(resolved):
                    raw = row[i + 1]
                    if raw is None:
                        values.append("")
                    else:
                        bounds = SENSOR_BOUNDS.get(s)
                        if bounds and not (bounds[0] <= raw <= bounds[1]):
                            values.append("")
                        else:
                            divisor = SENSOR_DIVISORS.get(s, 1)
                            values.append(str(round(raw / divisor, 2)))
                writer.writerow(values)
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)
        else:
            # Aggregated: query each sensor separately, merge on timestamp
            sensor_data: dict[str, dict[str, float | None]] = {}
            all_timestamps: set[str] = set()

            for s in resolved:
                column = SENSOR_COLUMNS[s]
                divisor = SENSOR_DIVISORS.get(s, 1)
                agg = _aggregate(db, column, start_dt, end_dt, resolution, divisor)
                sensor_data[s] = {pt["timestamp"]: pt["value"] for pt in agg}
                all_timestamps.update(sensor_data[s].keys())

            for ts in sorted(all_timestamps):
                values = [ts]
                for s in resolved:
                    val = sensor_data[s].get(ts)
                    values.append(str(val) if val is not None else "")
                writer.writerow(values)
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

    date_str = start_dt.strftime("%Y-%m-%d")
    filename = f"weather_export_{date_str}.csv"

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
