#!/usr/bin/env python3
"""Migrate existing Davis-native DB values to SI units.

Converts sensor_readings and archive_records from Davis native units
(tenths °F, thousandths inHg, mph, hundredths inches) to SI units
(tenths °C, tenths hPa, tenths m/s, tenths mm).

Usage:
    python tools/migrate_davis_to_si.py [--db PATH]

Default DB path is resolved from app config (same as the station).
Creates a .pre-migration backup before modifying data.

This script is idempotent-safe: it checks for a migration marker in
station_config and skips if already migrated.
"""

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

# Temperature: tenths °F → tenths °C
# Formula: (f - 320) * 5 / 9, but in integer SQL we need to be careful
# (value * 10 - 3200) * 5 / 9 / 10 has rounding issues
# Better: ROUND((value - 320) * 5.0 / 9.0)
TEMP_EXPR = "ROUND(({{col}} - 320) * 5.0 / 9.0)"

# Pressure: thousandths inHg → tenths hPa
# 1 inHg = 33.8639 hPa
# thousandths inHg / 1000 * 33.8639 * 10 = thousandths * 33.8639 / 100
PRESSURE_EXPR = "ROUND({{col}} * 33.8639 / 100.0)"

# Wind speed: mph → tenths m/s
# 1 mph = 0.44704 m/s → tenths = mph * 4.4704
WIND_EXPR = "ROUND({{col}} * 4.4704)"

# Rain: hundredths inches → tenths mm
# 1/100 inch = 0.254 mm → tenths mm = hundredths * 2.54
RAIN_EXPR = "ROUND({{col}} * 2.54)"

MIGRATION_MARKER = "db_units_si"


def _sql(expr: str, col: str) -> str:
    return expr.replace("{{col}}", col)


def migrate(db_path: str, dry_run: bool = False) -> None:
    """Run the migration."""
    db = Path(db_path)
    if not db.exists():
        print(f"ERROR: Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)

    # Check if already migrated
    try:
        cur = conn.execute(
            "SELECT value FROM station_config WHERE key = ?", (MIGRATION_MARKER,)
        )
        row = cur.fetchone()
        if row and row[0] == "true":
            print("Database already migrated to SI units. Skipping.")
            conn.close()
            return
    except sqlite3.OperationalError:
        pass  # station_config might not exist yet

    # Count rows for progress reporting
    tables_to_check = ["sensor_readings", "archive_records"]
    row_counts = {}
    for table in tables_to_check:
        try:
            cur = conn.execute(f"SELECT COUNT(*) FROM [{table}]")
            row_counts[table] = cur.fetchone()[0]
        except sqlite3.OperationalError:
            row_counts[table] = 0

    print(f"Database: {db_path}")
    print(f"  sensor_readings: {row_counts.get('sensor_readings', 0)} rows")
    print(f"  archive_records: {row_counts.get('archive_records', 0)} rows")

    if dry_run:
        print("\nDRY RUN — no changes will be made.")
        conn.close()
        return

    # Create backup
    backup_path = f"{db_path}.pre-si-migration"
    print(f"\nCreating backup: {backup_path}")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    shutil.copy2(db_path, backup_path)

    # Reconnect and migrate
    conn = sqlite3.connect(db_path)

    # --- sensor_readings ---
    if row_counts.get("sensor_readings", 0) > 0:
        print("\nMigrating sensor_readings...")

        # Temperature fields
        for col in ["inside_temp", "outside_temp", "heat_index", "dew_point",
                     "wind_chill", "feels_like"]:
            sql = f"UPDATE sensor_readings SET {col} = {_sql(TEMP_EXPR, col)} WHERE {col} IS NOT NULL"
            conn.execute(sql)
            print(f"  {col}: converted to tenths °C")

        # Pressure
        sql = f"UPDATE sensor_readings SET barometer = {_sql(PRESSURE_EXPR, 'barometer')} WHERE barometer IS NOT NULL"
        conn.execute(sql)
        print(f"  barometer: converted to tenths hPa")

        # Wind speed
        sql = f"UPDATE sensor_readings SET wind_speed = {_sql(WIND_EXPR, 'wind_speed')} WHERE wind_speed IS NOT NULL"
        conn.execute(sql)
        print(f"  wind_speed: converted to tenths m/s")

        # Rain fields
        for col in ["rain_total", "rain_rate", "rain_yearly"]:
            sql = f"UPDATE sensor_readings SET {col} = {_sql(RAIN_EXPR, col)} WHERE {col} IS NOT NULL"
            conn.execute(sql)
            print(f"  {col}: converted to tenths mm")

        # theta_e stays as tenths K (already SI)
        print(f"  theta_e: already tenths K (no change)")

    # --- archive_records ---
    if row_counts.get("archive_records", 0) > 0:
        print("\nMigrating archive_records...")

        # Check which columns exist in archive_records
        cur = conn.execute("PRAGMA table_info(archive_records)")
        archive_cols = {row[1] for row in cur.fetchall()}

        temp_cols = {"inside_temp_avg", "outside_temp_avg", "outside_temp_hi",
                     "outside_temp_lo", "inside_temp_hi", "inside_temp_lo",
                     "dew_point_avg", "dew_point_hi", "dew_point_lo",
                     "heat_index_hi", "wind_chill_lo"}
        for col in temp_cols & archive_cols:
            conn.execute(
                f"UPDATE archive_records SET {col} = {_sql(TEMP_EXPR, col)} WHERE {col} IS NOT NULL"
            )
            print(f"  {col}: converted to tenths °C")

        pressure_cols = {"barometer_avg", "barometer_hi", "barometer_lo"}
        for col in pressure_cols & archive_cols:
            conn.execute(
                f"UPDATE archive_records SET {col} = {_sql(PRESSURE_EXPR, col)} WHERE {col} IS NOT NULL"
            )
            print(f"  {col}: converted to tenths hPa")

        wind_cols = {"wind_speed_avg", "wind_speed_hi"}
        for col in wind_cols & archive_cols:
            conn.execute(
                f"UPDATE archive_records SET {col} = {_sql(WIND_EXPR, col)} WHERE {col} IS NOT NULL"
            )
            print(f"  {col}: converted to tenths m/s")

        rain_cols = {"rain_total", "rain_rate_hi"}
        for col in rain_cols & archive_cols:
            conn.execute(
                f"UPDATE archive_records SET {col} = {_sql(RAIN_EXPR, col)} WHERE {col} IS NOT NULL"
            )
            print(f"  {col}: converted to tenths mm")

    # Set migration marker
    conn.execute(
        "INSERT OR REPLACE INTO station_config (key, value, updated_at) "
        "VALUES (?, 'true', datetime('now'))",
        (MIGRATION_MARKER,),
    )
    conn.commit()
    conn.close()

    print(f"\nMigration complete. Backup at: {backup_path}")
    print("Restart the web app and logger daemon.")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Kanfei DB from Davis native units to SI",
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="Path to kanfei.db (default: resolved from app config)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be migrated without making changes",
    )
    args = parser.parse_args()

    if args.db:
        db_path = args.db
    else:
        # Resolve from app config
        sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
        try:
            from app.config import settings
            db_path = settings.db_path
        except Exception:
            # Fallback: check common locations
            for candidate in ["kanfei.db", "weather.db"]:
                p = Path(__file__).parent.parent / candidate
                if p.exists():
                    db_path = str(p)
                    break
            else:
                print("ERROR: Cannot find database. Use --db to specify path.")
                sys.exit(1)

    migrate(db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
