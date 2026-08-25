"""Extremes composite indexes exist after init_database().

Pins the schema-migration guarantee: on both a fresh DB
(``Base.metadata.create_all``) and an upgraded DB (post-init
CREATE INDEX IF NOT EXISTS), the three composite indexes powering
``services.daily_extremes._at`` must be present, and the redundant
auto-generated ``ix_sensor_readings_timestamp`` must be gone.
"""

from sqlalchemy import text

from app.models.database import engine, init_database


COMPOSITE_INDEXES = {
    "idx_sensor_outside_temp_ts",
    "idx_sensor_wind_speed_ts",
    "idx_sensor_barometer_ts",
}


def _index_names() -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index' AND tbl_name = 'sensor_readings'"
        )).fetchall()
    return {r[0] for r in rows}


def test_composite_indexes_present_after_init():
    init_database()
    present = _index_names()
    missing = COMPOSITE_INDEXES - present
    assert not missing, f"expected composite indexes missing: {missing}"


def test_named_timestamp_index_still_present_after_init():
    """The named timestamp index is what the WS live-poll / history
    queries lean on. It must survive the migration that drops the
    duplicate auto-generated one."""
    init_database()
    assert "idx_sensor_timestamp" in _index_names()


def test_redundant_auto_timestamp_index_dropped_after_init():
    """The auto-generated ``ix_sensor_readings_timestamp`` from the old
    ``index=True`` on the timestamp column duplicated the named
    ``idx_sensor_timestamp``. Migration drops it on upgrade; the model
    no longer creates it on fresh DBs."""
    # Simulate an upgrade path: manually plant the old duplicate first.
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_sensor_readings_timestamp "
            "ON sensor_readings (timestamp)"
        ))
        conn.commit()
    init_database()
    assert "ix_sensor_readings_timestamp" not in _index_names()


def test_composite_index_is_used_for_at_lookup():
    """SQLite's query planner should pick the composite for the
    ``_at``-shaped query (equality on the value column, range on
    timestamp). If it doesn't, the whole point of adding the index is
    lost — a full-table scan is still what runs.
    """
    init_database()
    with engine.connect() as conn:
        plan = conn.execute(text(
            "EXPLAIN QUERY PLAN "
            "SELECT MIN(timestamp) FROM sensor_readings "
            "WHERE outside_temp = 850 AND timestamp >= '2026-01-01'"
        )).fetchall()
    plan_text = " | ".join(str(row) for row in plan)
    assert "idx_sensor_outside_temp_ts" in plan_text, (
        f"planner did not pick the composite index; plan={plan_text}"
    )
