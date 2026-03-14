"""Database administration API — stats, export, compact, and purge."""

import json
import math
import os
import sqlite3
import tempfile
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..config import settings
from ..models.database import get_db
from ..models.sensor_reading import SensorReadingModel
from ..models.archive_record import ArchiveRecordModel
from ..models.nowcast import NowcastHistory, NowcastVerification, NowcastKnowledge
from ..models.spray import SprayProduct, SpraySchedule, SprayOutcome
from ..models.station_config import StationConfigModel

router = APIRouter(prefix="/db-admin", tags=["db-admin"])

# ---------------------------------------------------------------------------
# Table registry: model class + timestamp column for date-range operations
# ---------------------------------------------------------------------------

_TABLE_REGISTRY: dict[str, dict] = {
    "sensor_readings": {
        "model": SensorReadingModel,
        "ts_col": "timestamp",
        "exportable": True,
        "purgeable": True,
    },
    "archive_records": {
        "model": ArchiveRecordModel,
        "ts_col": "record_time",
        "exportable": True,
        "purgeable": True,
    },
    "nowcast_history": {
        "model": NowcastHistory,
        "ts_col": "created_at",
        "exportable": True,
        "purgeable": True,
    },
    "nowcast_verification": {
        "model": NowcastVerification,
        "ts_col": "verified_at",
        "exportable": False,
        "purgeable": True,
    },
    "nowcast_knowledge": {
        "model": NowcastKnowledge,
        "ts_col": "created_at",
        "exportable": True,
        "purgeable": True,
    },
    "spray_schedules": {
        "model": SpraySchedule,
        "ts_col": "created_at",
        "exportable": True,
        "purgeable": True,
    },
    "spray_outcomes": {
        "model": SprayOutcome,
        "ts_col": "logged_at",
        "exportable": True,
        "purgeable": True,
    },
    # Protected tables — stats only
    "spray_products": {
        "model": SprayProduct,
        "ts_col": "created_at",
        "exportable": False,
        "purgeable": False,
    },
    "station_config": {
        "model": StationConfigModel,
        "ts_col": "updated_at",
        "exportable": False,
        "purgeable": False,
    },
}


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class PurgeRequest(BaseModel):
    confirm: str | None = None
    before: str | None = None  # ISO date string "2025-01-01"


class CompactRequest(BaseModel):
    before: str  # ISO date string — compact readings older than this
    confirm: str


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Row counts and date ranges for all tables, plus database file size."""
    tables = []
    for table_name, info in _TABLE_REGISTRY.items():
        model = info["model"]
        ts_col_name = info["ts_col"]
        ts_col = getattr(model, ts_col_name, None)

        row_count = db.query(func.count()).select_from(model).scalar() or 0

        oldest = None
        newest = None
        if ts_col is not None:
            oldest_val = db.query(func.min(ts_col)).scalar()
            newest_val = db.query(func.max(ts_col)).scalar()
            if oldest_val:
                oldest = oldest_val.isoformat() if isinstance(oldest_val, datetime) else str(oldest_val)
            if newest_val:
                newest = newest_val.isoformat() if isinstance(newest_val, datetime) else str(newest_val)

        tables.append({
            "table": table_name,
            "row_count": row_count,
            "oldest": oldest,
            "newest": newest,
        })

    db_size = 0
    try:
        db_size = os.path.getsize(settings.db_path)
    except OSError:
        pass

    return {"tables": tables, "db_size_bytes": db_size}


# ---------------------------------------------------------------------------
# Export — JSON
# ---------------------------------------------------------------------------

def _model_row_to_dict(row) -> dict:
    """Convert a SQLAlchemy model instance to a JSON-serialisable dict."""
    d = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        d[col.name] = val
    return d


def _stream_json(db: Session, model, ts_col, start: str | None, end: str | None):
    """Generator that yields a JSON array in chunks."""
    query = db.query(model)
    if ts_col is not None:
        if start:
            query = query.filter(ts_col >= start)
        if end:
            query = query.filter(ts_col <= end)
        query = query.order_by(ts_col)

    chunk_size = 1000
    offset = 0
    first = True
    yield "["
    while True:
        rows = query.offset(offset).limit(chunk_size).all()
        if not rows:
            break
        for row in rows:
            if not first:
                yield ","
            yield json.dumps(_model_row_to_dict(row))
            first = False
        offset += chunk_size
    yield "]"


@router.get("/export/json/{table}")
def export_json(
    table: str,
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Stream a JSON export of a single table."""
    info = _TABLE_REGISTRY.get(table)
    if not info or not info["exportable"]:
        raise HTTPException(400, f"Table '{table}' is not exportable")

    model = info["model"]
    ts_col = getattr(model, info["ts_col"], None)
    today = date.today().isoformat()
    filename = f"kanfei_{table}_{today}.json"

    return StreamingResponse(
        _stream_json(db, model, ts_col, start, end),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Export — Full SQLite backup
# ---------------------------------------------------------------------------

@router.get("/export/backup")
def export_backup():
    """Download a consistent SQLite database backup."""
    today = date.today().isoformat()
    filename = f"kanfei_backup_{today}.db"

    # Create backup in a temp file using sqlite3.backup()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    try:
        src = sqlite3.connect(settings.db_path)
        dst = sqlite3.connect(tmp.name)
        src.backup(dst)
        src.close()
        dst.close()
    except Exception as exc:
        os.unlink(tmp.name)
        raise HTTPException(500, f"Backup failed: {exc}")

    return FileResponse(
        tmp.name,
        media_type="application/x-sqlite3",
        filename=filename,
        background=None,  # keep file until response completes
    )


# ---------------------------------------------------------------------------
# Compact (sensor readings only)
# ---------------------------------------------------------------------------

def _circular_mean_deg(angles: list[float]) -> int:
    """Circular mean of angles in degrees (handles 359/1 wraparound)."""
    if not angles:
        return 0
    sin_sum = sum(math.sin(math.radians(a)) for a in angles)
    cos_sum = sum(math.cos(math.radians(a)) for a in angles)
    mean = math.degrees(math.atan2(sin_sum, cos_sum))
    return round(mean) % 360


@router.post("/compact")
def compact_readings(body: CompactRequest, db: Session = Depends(get_db)):
    """Compact raw sensor readings into 5-minute averages."""
    if body.confirm != "COMPACT":
        raise HTTPException(400, "Confirmation required: set confirm to 'COMPACT'")

    try:
        cutoff = datetime.fromisoformat(body.before)
    except ValueError:
        raise HTTPException(400, "Invalid date format — use ISO 8601 (e.g. 2025-01-01)")

    # Count rows to be compacted
    original_count = (
        db.query(func.count())
        .select_from(SensorReadingModel)
        .filter(SensorReadingModel.timestamp < cutoff)
        .scalar()
    ) or 0

    if original_count == 0:
        return {"original_rows": 0, "compacted_rows": 0, "deleted": 0}

    # Fetch all rows before cutoff, ordered by time
    rows = (
        db.query(SensorReadingModel)
        .filter(SensorReadingModel.timestamp < cutoff)
        .order_by(SensorReadingModel.timestamp)
        .all()
    )

    # Group into 5-minute buckets
    buckets: dict[str, list] = {}
    for row in rows:
        # Bucket key: floor timestamp to 5-minute boundary
        ts = row.timestamp
        bucket_min = (ts.minute // 5) * 5
        bucket_key = ts.replace(minute=bucket_min, second=0, microsecond=0).isoformat()
        buckets.setdefault(bucket_key, []).append(row)

    # Numeric columns to average
    avg_cols = [
        "inside_temp", "outside_temp", "inside_humidity", "outside_humidity",
        "wind_speed", "barometer", "solar_radiation", "uv_index",
        "heat_index", "dew_point", "wind_chill", "feels_like", "theta_e",
    ]
    # Columns to take MAX (cumulative counters / peak values)
    max_cols = ["rain_total", "rain_yearly", "rain_rate"]

    compacted_rows = []
    for bucket_key, bucket_rows in buckets.items():
        bucket_ts = datetime.fromisoformat(bucket_key)

        new_row = SensorReadingModel(
            timestamp=bucket_ts,
            station_type=bucket_rows[0].station_type,
        )

        # Average columns (round to int)
        for col in avg_cols:
            vals = [getattr(r, col) for r in bucket_rows if getattr(r, col) is not None]
            setattr(new_row, col, round(sum(vals) / len(vals)) if vals else None)

        # Wind direction — circular mean
        wind_dirs = [r.wind_direction for r in bucket_rows if r.wind_direction is not None]
        new_row.wind_direction = _circular_mean_deg(wind_dirs) if wind_dirs else None

        # Max columns
        for col in max_cols:
            vals = [getattr(r, col) for r in bucket_rows if getattr(r, col) is not None]
            setattr(new_row, col, max(vals) if vals else None)

        # Pressure trend — last non-null value in bucket
        trends = [r.pressure_trend for r in bucket_rows if r.pressure_trend is not None]
        new_row.pressure_trend = trends[-1] if trends else None

        compacted_rows.append(new_row)

    # Delete originals and insert compacted rows
    (
        db.query(SensorReadingModel)
        .filter(SensorReadingModel.timestamp < cutoff)
        .delete(synchronize_session=False)
    )
    db.add_all(compacted_rows)
    db.commit()

    return {
        "original_rows": original_count,
        "compacted_rows": len(compacted_rows),
        "deleted": original_count - len(compacted_rows),
    }


# ---------------------------------------------------------------------------
# Purge — single table
# ---------------------------------------------------------------------------

@router.delete("/purge/{table}")
def purge_table(table: str, body: PurgeRequest, db: Session = Depends(get_db)):
    """Purge records from a table — date-range or full."""
    info = _TABLE_REGISTRY.get(table)
    if not info:
        raise HTTPException(404, f"Unknown table: {table}")
    if not info["purgeable"]:
        raise HTTPException(400, f"Table '{table}' is protected and cannot be purged")

    model = info["model"]
    ts_col_name = info["ts_col"]
    ts_col = getattr(model, ts_col_name, None)

    if body.before:
        # Date-range purge — no special confirmation needed
        try:
            cutoff = datetime.fromisoformat(body.before)
        except ValueError:
            raise HTTPException(400, "Invalid date format — use ISO 8601 (e.g. 2025-01-01)")

        if ts_col is None:
            raise HTTPException(400, f"Table '{table}' has no timestamp column for date-range purge")

        deleted = (
            db.query(model)
            .filter(ts_col < cutoff)
            .delete(synchronize_session=False)
        )
    else:
        # Full purge — requires "PURGE" confirmation
        if body.confirm != "PURGE":
            raise HTTPException(400, "Confirmation required: set confirm to 'PURGE'")
        deleted = db.query(model).delete(synchronize_session=False)

    db.commit()
    remaining = db.query(func.count()).select_from(model).scalar() or 0
    return {"deleted": deleted, "remaining": remaining}


# ---------------------------------------------------------------------------
# Purge — all data tables
# ---------------------------------------------------------------------------

@router.delete("/purge-all")
def purge_all(body: PurgeRequest, db: Session = Depends(get_db)):
    """Purge ALL data tables. Configuration and products are preserved."""
    if body.confirm != "DELETE DATABASE":
        raise HTTPException(400, 'Confirmation required: set confirm to "DELETE DATABASE"')

    results = {}
    for table_name, info in _TABLE_REGISTRY.items():
        if not info["purgeable"]:
            continue
        model = info["model"]
        deleted = db.query(model).delete(synchronize_session=False)
        results[table_name] = deleted

    db.commit()
    return results
