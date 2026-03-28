#!/usr/bin/env python3
"""Build the synthetic test database for Playwright E2E tests.

Creates fixtures/test.db with:
  - station_config: setup_complete=true, units in imperial, location set
  - sensor_readings: 120 rows spanning the last 2 hours, all "today"
    so daily extremes queries work.  Row 120 (latest) is the "anchor"
    reading whose exact display values are asserted in the spec files.

All sensor values are stored in SI units:
  - Temperature: tenths of °C
  - Pressure: tenths of hPa
  - Wind speed: tenths of m/s
  - Rain: tenths of mm
  - Theta-e: tenths of K
  - Humidity: percent (0-100)

Usage:
    python build-test-db.py [fixtures_dir]
"""

import os
import random
import secrets
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# bcrypt for password hashing — matches backend's auth service
import bcrypt

# ---------------------------------------------------------------------------
# Anchor reading — exact raw SI values.
# The expected display values are documented in helpers/values.ts.
# ---------------------------------------------------------------------------

ANCHOR = {
    "station_type": 2,            # Weather Monitor II
    "inside_temp": 211,           # 21.1°C  → 70.0°F
    "outside_temp": 240,          # 24.0°C  → 75.2°F
    "inside_humidity": 45,        # 45%
    "outside_humidity": 62,       # 62%
    "wind_speed": 36,             # 3.6 m/s → 8 mph
    "wind_direction": 225,        # SW
    "barometer": 10166,           # 1016.6 hPa → 30.02 inHg
    "rain_total": 0,              # 0 mm    → 0.00 in
    "rain_rate": 0,               # 0 mm/hr → 0.00 in/hr
    "rain_yearly": 254,           # 25.4 mm → 1.00 in
    "heat_index": 250,            # 25.0°C  → 77.0°F
    "dew_point": 170,             # 17.0°C  → 62.6°F
    "wind_chill": 240,            # 24.0°C  → 75.2°F
    "feels_like": 250,            # 25.0°C  → 77.0°F
    "theta_e": 3300,              # 330.0 K
    "pressure_trend": "rising",
    "solar_radiation": None,
    "uv_index": None,
}

# Row indices (1-based) for daily extremes — keep close to anchor (row 120)
# so they're always within "today" even when tests run near midnight UTC
HIGH_TEMP_ROW = 115  # ~5 min ago
LOW_TEMP_ROW = 110   # ~10 min ago

HIGH_TEMP_RAW = 272  # 27.2°C → 81.0°F → H 81°
LOW_TEMP_RAW = 200   # 20.0°C → 68.0°F → L 68°

TOTAL_ROWS = 120

# Test admin account — matches helpers/values.ts TEST_ADMIN
TEST_ADMIN_USERNAME = "admin"
TEST_ADMIN_PASSWORD = "testpass123"
# Pre-baked session token — injected as a cookie in tests
TEST_SESSION_TOKEN = "e2e_test_session_token_fixed_for_determinism"

# ---------------------------------------------------------------------------
# station_config key-value pairs
# ---------------------------------------------------------------------------

CONFIG = {
    "setup_complete": "true",
    "station_driver_type": "legacy",
    "temp_unit": "F",
    "pressure_unit": "inHg",
    "wind_unit": "mph",
    "rain_unit": "in",
    "latitude": "35.7796",
    "longitude": "-78.6382",
    "elevation": "315",
    "serial_port": "/dev/ttyUSB0",
    "baud_rate": "2400",
    "rain_yesterday": "0.12",
    "backup_enabled": "false",
    "backup_interval_hours": "24",
    "backup_retention_count": "5",
    "nowcast_enabled": "false",
    "spray_enabled": "false",
    "ui_theme": "dark",
    "station_timezone": "America/New_York",
    "poll_interval": "10",
    "db_units_si": "true",
}


def clamp(val, lo, hi):
    return max(lo, min(hi, val))


def build_readings(now: datetime) -> list[dict]:
    """Generate 120 sensor readings ending at `now`, one per minute.

    All timestamps are in the past so history queries find them.
    The daily extremes query filters by `timestamp >= local midnight`.
    To ensure row 20 (daily low) and row 80 (daily high) fall after
    midnight, we keep the span to 2 hours and accept that tests run
    near midnight may miss some rows for extremes.
    """
    rng = random.Random(42)  # deterministic seed for reproducibility
    rows = []

    for i in range(1, TOTAL_ROWS + 1):
        # Row 1 is ~120 min ago, row 120 is now
        minutes_ago = TOTAL_ROWS - i
        ts = now - timedelta(minutes=minutes_ago)

        if i == TOTAL_ROWS:
            # Anchor row — use exact values
            row = dict(ANCHOR, timestamp=ts.strftime("%Y-%m-%d %H:%M:%S.%f"))
            rows.append(row)
            continue

        # Random walk around baseline values
        outside_temp = ANCHOR["outside_temp"] + rng.randint(-15, 15)
        inside_temp = ANCHOR["inside_temp"] + rng.randint(-3, 3)
        outside_humidity = clamp(ANCHOR["outside_humidity"] + rng.randint(-8, 8), 20, 100)
        inside_humidity = clamp(ANCHOR["inside_humidity"] + rng.randint(-3, 3), 30, 60)
        wind_speed = clamp(rng.randint(0, 60), 0, 80)  # 0-6.0 m/s
        wind_direction = rng.choice([0, 45, 90, 135, 180, 225, 270, 315])
        barometer = ANCHOR["barometer"] + rng.randint(-20, 20)
        theta_e = ANCHOR["theta_e"] + rng.randint(-40, 40)

        # Force daily extremes at specific rows
        if i == HIGH_TEMP_ROW:
            outside_temp = HIGH_TEMP_RAW
        elif i == LOW_TEMP_ROW:
            outside_temp = LOW_TEMP_RAW

        # Derived values track outside_temp roughly
        heat_index = outside_temp + rng.randint(5, 15)
        dew_point = outside_temp - rng.randint(50, 80)
        wind_chill = outside_temp - rng.randint(0, 5)
        feels_like = heat_index if outside_temp > 200 else wind_chill  # warm → HI

        row = {
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S.%f"),
            "station_type": 2,
            "inside_temp": inside_temp,
            "outside_temp": outside_temp,
            "inside_humidity": inside_humidity,
            "outside_humidity": outside_humidity,
            "wind_speed": wind_speed,
            "wind_direction": wind_direction,
            "barometer": barometer,
            "rain_total": 0,
            "rain_rate": 0,
            "rain_yearly": ANCHOR["rain_yearly"],
            "heat_index": heat_index,
            "dew_point": dew_point,
            "wind_chill": wind_chill,
            "feels_like": feels_like,
            "theta_e": theta_e,
            "pressure_trend": rng.choice(["rising", "falling", "steady"]),
            "solar_radiation": None,
            "uv_index": None,
        }
        rows.append(row)

    return rows


def create_db(db_path: str) -> None:
    """Create the test database from scratch."""
    if os.path.exists(db_path):
        os.remove(db_path)

    # Clean up any stale backup directory alongside the DB
    backups_dir = os.path.join(os.path.dirname(db_path), "backups")
    if os.path.isdir(backups_dir):
        shutil.rmtree(backups_dir)

    conn = sqlite3.connect(db_path)

    # Create tables matching the ORM models
    conn.executescript("""
        CREATE TABLE sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            station_type INTEGER NOT NULL,
            inside_temp INTEGER,
            outside_temp INTEGER,
            inside_humidity INTEGER,
            outside_humidity INTEGER,
            wind_speed INTEGER,
            wind_direction INTEGER,
            barometer INTEGER,
            rain_total INTEGER,
            rain_rate INTEGER,
            rain_yearly INTEGER,
            solar_radiation INTEGER,
            uv_index INTEGER,
            extra_json TEXT,
            heat_index INTEGER,
            dew_point INTEGER,
            wind_chill INTEGER,
            feels_like INTEGER,
            theta_e INTEGER,
            pressure_trend TEXT
        );
        CREATE INDEX idx_sensor_timestamp ON sensor_readings(timestamp);

        CREATE TABLE station_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE archive_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            downloaded_at DATETIME,
            archive_address INTEGER,
            record_time DATETIME,
            station_type INTEGER,
            inside_temp_avg INTEGER,
            outside_temp_avg INTEGER,
            outside_temp_hi INTEGER,
            outside_temp_lo INTEGER,
            inside_temp_hi INTEGER,
            inside_temp_lo INTEGER,
            outside_humidity_avg INTEGER,
            inside_humidity_avg INTEGER,
            wind_speed_avg INTEGER,
            wind_speed_hi INTEGER,
            wind_direction_avg INTEGER,
            barometer_avg INTEGER,
            barometer_hi INTEGER,
            barometer_lo INTEGER,
            rain_total INTEGER,
            rain_rate_hi INTEGER,
            solar_radiation_avg INTEGER,
            solar_radiation_hi INTEGER,
            uv_index_avg INTEGER,
            uv_index_hi INTEGER,
            et_total INTEGER,
            wind_run INTEGER,
            dew_point_avg INTEGER,
            dew_point_hi INTEGER,
            dew_point_lo INTEGER,
            heat_index_hi INTEGER,
            wind_chill_lo INTEGER
        );
        CREATE UNIQUE INDEX idx_archive_addr_time
            ON archive_records(archive_address, record_time);

        CREATE TABLE IF NOT EXISTS nowcast_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME,
            valid_from DATETIME,
            valid_until DATETIME,
            model_used TEXT,
            summary TEXT,
            details TEXT,
            confidence TEXT,
            sources_used TEXT,
            raw_response TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS nowcast_verification (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nowcast_id INTEGER REFERENCES nowcast_history(id),
            verified_at DATETIME,
            element TEXT,
            predicted TEXT,
            actual TEXT,
            accuracy_score REAL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS nowcast_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME,
            source TEXT,
            category TEXT,
            content TEXT,
            status TEXT DEFAULT 'pending',
            auto_accept_at DATETIME,
            reviewed_at DATETIME,
            recommendation TEXT
        );

        CREATE TABLE IF NOT EXISTS nowcast_radar_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nowcast_id INTEGER REFERENCES nowcast_history(id),
            image_type TEXT,
            product_id TEXT,
            label TEXT,
            png_base64 TEXT
        );

        CREATE TABLE IF NOT EXISTS spray_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'custom',
            is_preset INTEGER DEFAULT 0,
            rain_free_hours REAL DEFAULT 0,
            max_wind_mph REAL DEFAULT 999,
            min_temp_f REAL DEFAULT -999,
            max_temp_f REAL DEFAULT 999,
            min_humidity_pct REAL,
            max_humidity_pct REAL,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS spray_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER REFERENCES spray_products(id),
            planned_date TEXT,
            planned_start TEXT,
            planned_end TEXT,
            status TEXT DEFAULT 'pending',
            evaluation TEXT,
            ai_commentary TEXT,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS spray_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_id INTEGER REFERENCES spray_schedules(id),
            logged_at DATETIME,
            effectiveness INTEGER,
            actual_rain_hours REAL,
            actual_wind_mph REAL,
            actual_temp_f REAL,
            drift_observed INTEGER DEFAULT 0,
            product_efficacy TEXT,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            token TEXT UNIQUE NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME NOT NULL,
            last_active_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            prefix TEXT NOT NULL,
            key_hash TEXT NOT NULL,
            label TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_used_at DATETIME,
            revoked INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS forecasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            source TEXT,
            period_name TEXT,
            forecast_text TEXT,
            temperature REAL,
            precipitation_pct REAL,
            wind_text TEXT,
            expires_at DATETIME
        );
    """)

    # Insert station_config
    conn.executemany(
        "INSERT INTO station_config (key, value) VALUES (?, ?)",
        list(CONFIG.items()),
    )

    # Generate and insert sensor readings
    now = datetime.now(timezone.utc)
    readings = build_readings(now)

    columns = [
        "timestamp", "station_type",
        "inside_temp", "outside_temp", "inside_humidity", "outside_humidity",
        "wind_speed", "wind_direction", "barometer",
        "rain_total", "rain_rate", "rain_yearly",
        "solar_radiation", "uv_index",
        "heat_index", "dew_point", "wind_chill", "feels_like", "theta_e",
        "pressure_trend",
    ]
    placeholders = ", ".join(["?"] * len(columns))
    sql = f"INSERT INTO sensor_readings ({', '.join(columns)}) VALUES ({placeholders})"

    for row in readings:
        values = [row.get(col) for col in columns]
        conn.execute(sql, values)

    # Create test admin user with bcrypt-hashed password
    password_hash = bcrypt.hashpw(
        TEST_ADMIN_PASSWORD.encode(), bcrypt.gensalt()
    ).decode()
    conn.execute(
        "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
        (TEST_ADMIN_USERNAME, password_hash),
    )

    # Pre-create a session so tests can inject the cookie directly
    # without going through the login flow each time
    far_future = (now + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO sessions (user_id, token, expires_at, last_active_at) "
        "VALUES (1, ?, ?, ?)",
        (TEST_SESSION_TOKEN, far_future, now.strftime("%Y-%m-%d %H:%M:%S")),
    )

    conn.commit()

    # Verify
    cursor = conn.execute("SELECT COUNT(*) FROM sensor_readings")
    count = cursor.fetchone()[0]
    cursor = conn.execute("SELECT COUNT(*) FROM station_config")
    config_count = cursor.fetchone()[0]
    cursor = conn.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]

    conn.close()

    print(f"Created {db_path}")
    print(f"  sensor_readings: {count} rows")
    print(f"  station_config:  {config_count} rows")
    print(f"  users:           {user_count} rows")


def main():
    if len(sys.argv) > 1:
        fixtures_dir = sys.argv[1]
    else:
        fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")

    os.makedirs(fixtures_dir, exist_ok=True)
    db_path = os.path.join(fixtures_dir, "test.db")
    create_db(db_path)


if __name__ == "__main__":
    main()
