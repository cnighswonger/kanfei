"""Database engine and session factory for SQLAlchemy."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from ..config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # SQLite needs this for multi-thread
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Session:
    """Dependency for FastAPI endpoints."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database() -> None:
    """Create all tables.

    Models must be imported before create_all() so they register with Base.metadata.
    """
    from . import sensor_reading  # noqa: F401
    from . import station_config  # noqa: F401
    from . import archive_record  # noqa: F401
    from . import nowcast  # noqa: F401
    from . import spray  # noqa: F401
    from . import auth  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Enable WAL mode so the logger and web app can access the DB concurrently.
    # busy_timeout tells SQLite to wait up to 5s for a lock instead of failing
    # immediately — prevents "database is locked" errors during concurrent writes.
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA busy_timeout=5000"))
        conn.commit()

    # Migrate: add rain_yearly column if missing
    with engine.connect() as conn:
        try:
            conn.execute(text("SELECT rain_yearly FROM sensor_readings LIMIT 1"))
        except Exception:
            conn.execute(text(
                "ALTER TABLE sensor_readings ADD COLUMN rain_yearly INTEGER"
            ))
            conn.commit()

    # Migrate: add extra_json column if missing
    with engine.connect() as conn:
        try:
            conn.execute(text("SELECT extra_json FROM sensor_readings LIMIT 1"))
        except Exception:
            conn.execute(text(
                "ALTER TABLE sensor_readings ADD COLUMN extra_json TEXT"
            ))
            conn.commit()

    # Migrate: add wind_gust column if missing
    with engine.connect() as conn:
        try:
            conn.execute(text("SELECT wind_gust FROM sensor_readings LIMIT 1"))
        except Exception:
            conn.execute(text(
                "ALTER TABLE sensor_readings ADD COLUMN wind_gust INTEGER"
            ))
            conn.commit()

    # Migrate: add thsw_index column if missing (issue #236)
    #
    # THSW is the one derived value we cannot compute ourselves: it needs
    # solar radiation, so only a station with a solar sensor can report it.
    # A station without one sends the dashed sentinel and the column stays
    # NULL — which is why this is gated on the value arriving rather than
    # on the driver type.
    with engine.connect() as conn:
        try:
            conn.execute(text("SELECT thsw_index FROM sensor_readings LIMIT 1"))
        except Exception:
            conn.execute(text(
                "ALTER TABLE sensor_readings ADD COLUMN thsw_index INTEGER"
            ))
            conn.commit()

    # Migrate: add et_daily / et_monthly / et_yearly columns (beta30 follow-on
    # to #329). ET graduated from `extra_json` to dedicated columns so
    # `/api/history` can chart them the same way it charts rain and
    # temperature.  Store shape matches rain_total: integer tenths of a
    # millimetre.  See SENSOR_BOUNDS in sensor_meta.py.
    #
    # Backfill: for rows written before this migration ran, the historical
    # ET values are already in `extra_json` under keys `et_daily_mm`,
    # `et_monthly_mm`, `et_yearly_mm` (floats, millimetres).  Copy those
    # into the new columns as int tenths-mm so charts have full history
    # from day one after the upgrade.  Idempotent — the backfill only
    # UPDATES rows where the column is still NULL.
    for column in ("et_daily", "et_monthly", "et_yearly"):
        with engine.connect() as conn:
            try:
                conn.execute(text(f"SELECT {column} FROM sensor_readings LIMIT 1"))
            except Exception:
                conn.execute(text(
                    f"ALTER TABLE sensor_readings ADD COLUMN {column} INTEGER"
                ))
                conn.commit()
    # Backfill from extra_json.  Guarded on:
    #
    #   - ``json_valid(extra_json)`` — a single malformed historical row
    #     would otherwise abort startup with
    #     ``OperationalError: malformed JSON`` when ``json_extract``
    #     hit it.  The runtime readers (`/api/current`, `/api/station`,
    #     `/api/astronomy`) already treat malformed extras as survivable;
    #     the migration matches that tolerance.
    #   - Column IS NULL — prevents double-updates on repeated init runs.
    #   - Key is present in the extras — leaves NULL when the row was
    #     written by a non-ET-reporting driver.
    #
    # ``round(...)`` (not ``CAST AS INTEGER``, which truncates) matches
    # the poller's live write path (``round(mm * 10)``) so backfilled
    # rows and freshly-polled rows use the same tenths-mm quantization.
    with engine.connect() as conn:
        for column, extra_key in (
            ("et_daily", "et_daily_mm"),
            ("et_monthly", "et_monthly_mm"),
            ("et_yearly", "et_yearly_mm"),
        ):
            conn.execute(text(
                f"UPDATE sensor_readings "
                f"SET {column} = CAST(round(json_extract(extra_json, '$.{extra_key}') * 10) AS INTEGER) "
                f"WHERE {column} IS NULL "
                f"  AND extra_json IS NOT NULL "
                f"  AND json_valid(extra_json) "
                f"  AND json_extract(extra_json, '$.{extra_key}') IS NOT NULL"
            ))
        conn.commit()

    # Migrate: cwop_mute_* → channel_mute_* (issue #162)
    # Mute keys were CWOP-specific in beta16; from beta17 they gate every
    # outbound upload, so the prefix is generalised.  Copy old → new for
    # any value the operator set, then drop the old rows.  Idempotent.
    # ``updated_at`` is NOT NULL with an ORM-level default; raw SQL needs
    # to provide CURRENT_TIMESTAMP explicitly or INSERT OR IGNORE will
    # silently skip the row.
    with engine.connect() as conn:
        try:
            rows = conn.execute(text(
                "SELECT key, value FROM station_config WHERE key LIKE 'cwop_mute_%'"
            )).fetchall()
            for old_key, value in rows:
                new_key = old_key.replace("cwop_mute_", "channel_mute_", 1)
                conn.execute(text(
                    "INSERT OR IGNORE INTO station_config "
                    "(key, value, updated_at) "
                    "VALUES (:k, :v, CURRENT_TIMESTAMP)"
                ), {"k": new_key, "v": value})
            if rows:
                conn.execute(text(
                    "DELETE FROM station_config WHERE key LIKE 'cwop_mute_%'"
                ))
            conn.commit()
        except Exception:
            pass

    # Migrate: extremes composite indexes + drop the redundant
    # auto-generated timestamp index.
    #
    # ``services.daily_extremes._at`` looks up the timestamp at which a
    # given column reached a given max/min: ``WHERE timestamp >= X AND
    # column == raw``. The bare-timestamp index does not help — the
    # ``column == raw`` filter has no supporting index, so the query
    # falls back to a full table scan. On a 914 k-row demo this cost
    # ~2 s per year/month period-extremes call, five times per call,
    # entirely dominating GET /api/current on weak-CPU hosts.
    #
    # A composite ``(column, timestamp)`` lets SQLite seek by value
    # first and range-scan a small timestamp window inside — orders of
    # magnitude fewer rows touched. Only outside_temp / wind_speed /
    # barometer are indexed since those are the columns ``_at`` is
    # invoked with (see get_period_extremes / get_daily_extremes).
    #
    # Also drops ``ix_sensor_readings_timestamp`` — the auto-generated
    # index from ``index=True`` on the timestamp column. It duplicated
    # ``idx_sensor_timestamp`` (36 MB of redundant b-tree on the demo).
    # The explicit named index in ``__table_args__`` is now the sole
    # timestamp-only index.
    #
    # CREATE / DROP INDEX IF (NOT) EXISTS are idempotent by design;
    # no check-and-alter guard needed. Storage cost per composite:
    # ~55 MiB/year at the observed demo row density (~3,760 rows/day),
    # ~127 MiB/year at a true 10 s poll cadence (8,640 rows/day).
    # See the model-level comment in sensor_reading.py for the
    # derivation.
    with engine.connect() as conn:
        conn.execute(text("DROP INDEX IF EXISTS ix_sensor_readings_timestamp"))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_sensor_outside_temp_ts "
            "ON sensor_readings (outside_temp, timestamp)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_sensor_wind_speed_ts "
            "ON sensor_readings (wind_speed, timestamp)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_sensor_barometer_ts "
            "ON sensor_readings (barometer, timestamp)"
        ))
        conn.commit()
