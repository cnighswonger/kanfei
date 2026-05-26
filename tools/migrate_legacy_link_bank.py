#!/usr/bin/env python3
"""Repair canonical/archive data poisoned by the legacy-link-bank typo.

Background
----------
Prior to the fix for issue #174, ``backend/app/protocol/memory_map.py``
declared ``LinkBank1.SAMPLE_PERIOD``, ``LinkBank1.ARCHIVE_PERIOD``, and
``GroWeatherLinkBank1.ARCHIVE_PERIOD`` with ``bank=0`` — but the Davis
techref clearly puts them in link memory Bank 1 for every legacy station
(Monitor / Wizard / Perception / GroWeather / Energy / Health).  The
wrong-bank read returned whatever stale byte happened to live at station
memory 0x13C, so ``read_archive_period`` returned a different garbage
value on every call.

Symptoms on installs that ran the buggy build:

1. ``station_config.weatherlink_canonical.archive_period`` holds a value
   the Davis firmware does not honor (anything outside
   ``{1, 5, 10, 15, 30, 60, 120}``).  The reconciler re-pushes it to the
   SAP register on every restart.
2. ``archive_records.archive_interval`` rows hold garbage values
   (commonly 255, but also 68, 102, 221, 0 — whichever byte was at
   station memory 0x13C at the moment of each batch's period read).
3. The history chart's bin-width math uses ``archive_interval`` to
   align archive rows to their period window, producing visually wrong
   resolution-stepped charts.

What this script does
---------------------
- Drops the bogus ``archive_period`` from ``weatherlink_canonical`` so
  the post-fix reconciler will re-seed from a now-correct register
  read.  (The daemon also does this via a one-shot migration on next
  start; running this tool first is safe and idempotent.)
- Optionally repairs ``archive_records.archive_interval``: every row
  whose interval is not in the Davis-legal set is rewritten to the
  value passed via ``--archive-period N``.  If you don't pass
  ``--archive-period``, the tool prints what it would change and exits
  without touching archive_records (the canonical fix still applies
  unless ``--dry-run``).

Usage
-----
    # Inspect — no writes
    python tools/migrate_legacy_link_bank.py --dry-run

    # Fix canonical only; leave archive_records alone
    python tools/migrate_legacy_link_bank.py

    # Fix canonical AND rewrite bogus archive_records to interval=1
    python tools/migrate_legacy_link_bank.py --archive-period 1

    # Same against a non-default DB path
    python tools/migrate_legacy_link_bank.py --db /var/lib/kanfei/kanfei.db --archive-period 1

Creates a ``.pre-legacy-link-bank-fix`` backup before writing.
Idempotent: a marker row in ``station_config``
(key ``legacy_link_bank_fix_v1``) prevents re-running.
"""

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Optional

MIGRATION_MARKER = "legacy_link_bank_fix_v1"
CANONICAL_KEY = "weatherlink_canonical"
DAVIS_LEGAL_ARCHIVE_PERIODS = frozenset({1, 5, 10, 15, 30, 60, 120})


def _already_migrated(conn: sqlite3.Connection) -> bool:
    try:
        cur = conn.execute(
            "SELECT value FROM station_config WHERE key = ?", (MIGRATION_MARKER,),
        )
        row = cur.fetchone()
        return row is not None and row[0] not in (None, "")
    except sqlite3.OperationalError:
        return False


def _set_marker(conn: sqlite3.Connection, status: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO station_config (key, value, updated_at) "
        "VALUES (?, ?, datetime('now'))",
        (MIGRATION_MARKER, status),
    )


def _load_canonical(conn: sqlite3.Connection) -> Optional[dict]:
    try:
        cur = conn.execute(
            "SELECT value FROM station_config WHERE key = ?", (CANONICAL_KEY,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, ValueError):
            return None
    except sqlite3.OperationalError:
        return None


def _bogus_archive_interval_stats(conn: sqlite3.Connection) -> dict[int, int]:
    """Return {interval: count} for rows whose archive_interval is bogus."""
    placeholders = ",".join("?" for _ in DAVIS_LEGAL_ARCHIVE_PERIODS)
    cur = conn.execute(
        f"SELECT archive_interval, COUNT(*) FROM archive_records "
        f"WHERE archive_interval IS NOT NULL "
        f"AND archive_interval NOT IN ({placeholders}) "
        f"GROUP BY archive_interval ORDER BY 2 DESC",
        tuple(DAVIS_LEGAL_ARCHIVE_PERIODS),
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def migrate(db_path: str, dry_run: bool, archive_period: Optional[int]) -> int:
    db = Path(db_path)
    if not db.exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        return 1

    if archive_period is not None and archive_period not in DAVIS_LEGAL_ARCHIVE_PERIODS:
        print(
            f"ERROR: --archive-period must be one of "
            f"{sorted(DAVIS_LEGAL_ARCHIVE_PERIODS)} (got {archive_period})",
            file=sys.stderr,
        )
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

        canonical = _load_canonical(conn)
        canonical_ap = (canonical or {}).get("archive_period")
        canonical_bogus = (
            canonical_ap is not None
            and canonical_ap not in DAVIS_LEGAL_ARCHIVE_PERIODS
        )

        bogus_intervals = _bogus_archive_interval_stats(conn)
        bogus_row_total = sum(bogus_intervals.values())

        print(f"Database:                  {db_path}")
        print(f"Canonical archive_period:  {canonical_ap!r}"
              f"{'  (BOGUS)' if canonical_bogus else ''}")
        if bogus_intervals:
            print(f"archive_records with bogus archive_interval: {bogus_row_total}")
            for v, n in bogus_intervals.items():
                print(f"  interval={v}  count={n}")
        else:
            print("archive_records: no bogus archive_interval rows")

        if not canonical_bogus and not bogus_intervals:
            print("\nNothing to repair.  Recording marker so we don't re-check.")
            if not dry_run:
                _set_marker(conn, "clean")
                conn.commit()
            return 0

        if dry_run:
            print("\nDRY RUN — no changes will be made.")
            if bogus_intervals and archive_period is None:
                print(
                    "Note: pass --archive-period N to also repair archive_records "
                    "rows during a non-dry-run.",
                )
            return 0

        # Backup before writing
        backup_path = f"{db_path}.pre-legacy-link-bank-fix"
        print(f"\nCreating backup: {backup_path}")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        shutil.copy2(db_path, backup_path)
        conn = sqlite3.connect(db_path)

        actions: list[str] = []

        # 1. Drop bogus archive_period from canonical
        if canonical_bogus and canonical is not None:
            del canonical["archive_period"]
            conn.execute(
                "UPDATE station_config SET value = ?, updated_at = datetime('now') "
                "WHERE key = ?",
                (json.dumps(canonical), CANONICAL_KEY),
            )
            actions.append(f"canonical-dropped:{canonical_ap}")
            print(f"Dropped canonical.archive_period (was {canonical_ap})")

        # 2. Rewrite bogus archive_records.archive_interval if user supplied target
        if bogus_intervals:
            if archive_period is None:
                print(
                    "Skipping archive_records repair — pass --archive-period N "
                    "to set those rows to a Davis-legal value.",
                )
                actions.append(f"archive-records-left:{bogus_row_total}")
            else:
                placeholders = ",".join("?" for _ in DAVIS_LEGAL_ARCHIVE_PERIODS)
                cur = conn.execute(
                    f"UPDATE archive_records SET archive_interval = ? "
                    f"WHERE archive_interval IS NOT NULL "
                    f"AND archive_interval NOT IN ({placeholders})",
                    (archive_period, *DAVIS_LEGAL_ARCHIVE_PERIODS),
                )
                print(
                    f"Repaired {cur.rowcount} archive_records rows "
                    f"(archive_interval -> {archive_period})"
                )
                actions.append(f"archive-records-repaired:{cur.rowcount}->{archive_period}")

        _set_marker(conn, ";".join(actions) if actions else "clean")
        conn.commit()
        print(f"\nMigration complete.  Backup at: {backup_path}")
        print("Restart the web app and logger daemon to refresh any caches.")
        return 0
    finally:
        conn.close()


def _resolve_default_db() -> Optional[str]:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    try:
        from app.config import settings  # type: ignore
        return settings.db_path
    except Exception:
        pass
    for candidate in ("kanfei.db", "weather.db"):
        p = Path(__file__).resolve().parent.parent / candidate
        if p.exists():
            return str(p)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Repair canonical and archive_records poisoned by the legacy-"
            "link-bank typo.  See module docstring and issue #174."
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
        "--archive-period", type=int, default=None,
        help=(
            "Davis-legal archive period in minutes (1, 5, 10, 15, 30, 60, 120).  "
            "Required to repair bogus archive_records rows; without it, the "
            "tool fixes only the canonical row."
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

    return migrate(db_path, dry_run=args.dry_run, archive_period=args.archive_period)


if __name__ == "__main__":
    sys.exit(main())
