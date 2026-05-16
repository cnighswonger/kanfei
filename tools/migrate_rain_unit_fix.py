#!/usr/bin/env python3
"""Correct historical rain values stored before the rain-cal unit-conversion fix.

Background
----------
Prior to the fix, ``LinkDriver.poll`` converted the link's RAIN_DAILY and
RAIN_YEARLY registers to millimeters via ``register / 10.0``.  The link's
register magnitude scales with ``rain_cal`` (clicks per inch), so this
formula was only correct when ``rain_cal == 254`` (because 254 / 10 =
25.4 ≈ mm-per-inch).  Every other ``rain_cal`` setting — including the
Davis default of 100 — produced rain values that were too low by a factor
of ``254 / rain_cal`` (≈2.54× too low at the default).

This script multiplies the stored ``rain_total`` and ``rain_yearly``
columns of ``sensor_readings`` by the correction factor that matches your
station's current ``rain_cal`` setting.  ``rain_rate`` is intentionally
NOT touched — its conversion lives on a different code path and is
tracked as a separate follow-up.

Reliability caveats
-------------------
1. The correction factor depends on what ``rain_cal`` was active when the
   data was written.  This script uses your *current* ``rain_cal`` value
   from the daemon's canonical row (or, failing that, the live link).
   If you changed ``rain_cal`` partway through your history, the
   correction will be wrong for the older portion of the data — the
   script can't know.
2. If your current ``rain_cal`` is ``254`` (the workaround value), your
   stored data is already correct and the script will skip the migration
   while still recording the marker.
3. If your current ``rain_cal`` is some other unusual value (not 100 and
   not 254), the script will warn and require you to pass
   ``--force-rain-cal N`` to confirm you understand the implications.

Usage
-----
    python tools/migrate_rain_unit_fix.py --dry-run
    python tools/migrate_rain_unit_fix.py
    python tools/migrate_rain_unit_fix.py --db /path/to/kanfei.db --dry-run

Creates a ``.pre-rain-fix-migration`` backup before writing.  Idempotent:
a marker row in ``station_config`` (key ``db_rain_cal_unit_fix``) prevents
re-running.
"""

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Optional, Tuple

MIGRATION_MARKER = "db_rain_cal_unit_fix"
CANONICAL_KEY = "weatherlink_canonical"

# rain_cal at which the buggy /10 formula happens to be correct.  Data
# stored under this setting is fine as-is.
ALREADY_CORRECT_RAIN_CAL = 254
# Davis default — the most common case where data is 2.54× too low.
DAVIS_DEFAULT_RAIN_CAL = 100


def _resolve_rain_cal(
    conn: sqlite3.Connection, override: Optional[int],
) -> Tuple[Optional[int], str]:
    """Determine the rain_cal value to use for the correction factor.

    Returns (value, source) where source is one of "override", "canonical",
    "default", or "unknown".
    """
    if override is not None:
        return override, "override"
    try:
        cur = conn.execute(
            "SELECT value FROM station_config WHERE key = ?", (CANONICAL_KEY,),
        )
        row = cur.fetchone()
        if row and row[0]:
            try:
                canonical = json.loads(row[0])
                rain_cal = canonical.get("calibration", {}).get("rain_cal")
                if rain_cal is not None:
                    return int(rain_cal), "canonical"
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
    except sqlite3.OperationalError:
        pass
    return None, "unknown"


def _already_migrated(conn: sqlite3.Connection) -> bool:
    """Check whether the marker row exists in any form.

    We record the run *outcome* in the marker value (``applied``,
    ``skipped-already-correct``, ``applied-empty``, ...) rather than a
    literal ``true``, so the idempotency check must be "row present" not
    "row equals true" — otherwise re-runs would silently double-apply
    the correction factor.
    """
    try:
        cur = conn.execute(
            "SELECT value FROM station_config WHERE key = ?", (MIGRATION_MARKER,),
        )
        row = cur.fetchone()
        return row is not None and row[0] not in (None, "")
    except sqlite3.OperationalError:
        return False


def _set_marker(conn: sqlite3.Connection, status: str) -> None:
    """Record the migration outcome (`applied`, `skipped`, etc.) so we
    don't keep nagging on subsequent runs."""
    conn.execute(
        "INSERT OR REPLACE INTO station_config (key, value, updated_at) "
        "VALUES (?, ?, datetime('now'))",
        (MIGRATION_MARKER, status),
    )


def migrate(db_path: str, dry_run: bool, override_rain_cal: Optional[int]) -> int:
    db = Path(db_path)
    if not db.exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    try:
        if _already_migrated(conn):
            cur = conn.execute(
                "SELECT value FROM station_config WHERE key = ?",
                (MIGRATION_MARKER,),
            )
            outcome = cur.fetchone()[0]
            print(f"Migration marker present (status={outcome!r}). Nothing to do.")
            return 0

        rain_cal, source = _resolve_rain_cal(conn, override_rain_cal)
        print(f"Database:    {db_path}")
        print(f"rain_cal:    {rain_cal} (source: {source})")

        if rain_cal is None:
            print(
                "\nERROR: Cannot determine rain_cal.  Run the daemon at least "
                "once so the canonical row gets populated, or pass "
                "--force-rain-cal N explicitly.",
                file=sys.stderr,
            )
            return 1

        if rain_cal == ALREADY_CORRECT_RAIN_CAL:
            print(
                f"\nrain_cal == {ALREADY_CORRECT_RAIN_CAL} — historical data "
                "was stored correctly by the pre-fix code (the buggy /10 "
                "formula happens to match correct mm at this calibration).  "
                "No correction needed.",
            )
            if not dry_run:
                _set_marker(conn, "skipped-already-correct")
                conn.commit()
            return 0

        factor = ALREADY_CORRECT_RAIN_CAL / rain_cal
        print(f"Correction:  multiply rain_total + rain_yearly by {factor:.4f}")

        if rain_cal not in (DAVIS_DEFAULT_RAIN_CAL, ALREADY_CORRECT_RAIN_CAL):
            if override_rain_cal is None:
                print(
                    f"\nERROR: rain_cal={rain_cal} is unusual (not 100 default "
                    f"and not 254 workaround).  The correction factor "
                    f"{factor:.4f} will be applied to ALL historical rows in "
                    f"sensor_readings.  If your rain_cal has been steady at "
                    f"this value for the entire history, re-run with "
                    f"--force-rain-cal {rain_cal} to confirm.  If rain_cal "
                    "has changed during your history, the migration will "
                    "produce incorrect results for the portion stored under "
                    "the other value(s); the script cannot help in that case.",
                    file=sys.stderr,
                )
                return 1
            print(
                f"(Unusual rain_cal accepted via --force-rain-cal; proceeding.)",
            )

        # Count affected rows
        cur = conn.execute(
            "SELECT COUNT(*) FROM sensor_readings WHERE "
            "rain_total IS NOT NULL OR rain_yearly IS NOT NULL"
        )
        affected = cur.fetchone()[0]
        print(f"Rows to fix: {affected} in sensor_readings")

        if affected == 0:
            print("\nNo rain rows to update.  Setting marker and exiting.")
            if not dry_run:
                _set_marker(conn, "applied-empty")
                conn.commit()
            return 0

        if dry_run:
            print("\nDRY RUN — no changes will be made.")
            return 0

        # Backup before writing
        backup_path = f"{db_path}.pre-rain-fix-migration"
        print(f"\nCreating backup: {backup_path}")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        shutil.copy2(db_path, backup_path)
        conn = sqlite3.connect(db_path)

        # Apply correction.  sensor_readings.rain_total and rain_yearly are
        # stored as tenths of mm (integer); multiplying by the correction
        # factor and ROUND-ing preserves the same precision/scale.
        for col in ("rain_total", "rain_yearly"):
            conn.execute(
                f"UPDATE sensor_readings SET {col} = "
                f"CAST(ROUND({col} * ?) AS INTEGER) "
                f"WHERE {col} IS NOT NULL",
                (factor,),
            )
            print(f"  {col}: scaled by {factor:.4f}")

        _set_marker(conn, "applied")
        conn.commit()
        print(f"\nMigration complete.  Backup at: {backup_path}")
        print("Restart the web app and logger daemon to refresh any caches.")
        return 0
    finally:
        conn.close()


def _resolve_default_db() -> Optional[str]:
    # Try the app config first (resolves to whatever KANFEI_DB_PATH or
    # default location the daemon uses).
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    try:
        from app.config import settings  # type: ignore
        return settings.db_path
    except Exception:
        pass
    # Fallback to common filenames at repo root.
    for candidate in ("kanfei.db", "weather.db"):
        p = Path(__file__).resolve().parent.parent / candidate
        if p.exists():
            return str(p)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Correct historical rain values stored before the rain-cal "
            "unit-conversion fix.  See module docstring for details."
        ),
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="Path to kanfei.db (default: resolved from app config)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be migrated without making changes",
    )
    parser.add_argument(
        "--force-rain-cal", type=int, default=None,
        help=(
            "Override the rain_cal value used for the correction factor.  "
            "Required when current rain_cal is not 100 or 254."
        ),
    )
    args = parser.parse_args()

    db_path = args.db or _resolve_default_db()
    if not db_path:
        print(
            "ERROR: Cannot find database.  Use --db to specify path.",
            file=sys.stderr,
        )
        return 1

    return migrate(db_path, dry_run=args.dry_run, override_rain_cal=args.force_rain_cal)


if __name__ == "__main__":
    sys.exit(main())
