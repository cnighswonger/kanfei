"""Backup and restore service for Kanfei station data.

Creates .tar.gz archives containing the SQLite database, background images,
and a manifest file. Includes rotation for automatic scheduled backups.
"""

import asyncio
import json
import logging
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MANIFEST_NAME = "backup_manifest.json"
VERSION = "0.1.0"


def _wal_checkpoint(db_path: str) -> None:
    """Force WAL checkpoint to ensure consistent DB snapshot."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def _count_rows(db_path: str) -> dict[str, int]:
    """Get row counts for key tables (best-effort, skip missing tables)."""
    counts: dict[str, int] = {}
    tables = [
        "sensor_readings", "archive_records", "station_config",
        "spray_products", "spray_schedules", "spray_outcomes",
    ]
    conn = sqlite3.connect(db_path)
    try:
        for table in tables:
            try:
                cur = conn.execute(f"SELECT COUNT(*) FROM [{table}]")
                counts[table] = cur.fetchone()[0]
            except sqlite3.OperationalError:
                pass  # table doesn't exist
    finally:
        conn.close()
    return counts


def create_backup(db_path: str, output_path: str) -> dict:
    """Create a backup archive containing DB + backgrounds + manifest.

    Args:
        db_path: Path to the SQLite database file.
        output_path: Path for the output .tar.gz file.

    Returns:
        Manifest dict with backup metadata.
    """
    db = Path(db_path)
    if not db.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Checkpoint WAL for consistent snapshot
    _wal_checkpoint(db_path)

    backgrounds_dir = db.parent / "backgrounds"
    timestamp = datetime.now(timezone.utc).isoformat()

    manifest = {
        "kanfei_version": VERSION,
        "timestamp": timestamp,
        "db_file": db.name,
        "db_size_bytes": db.stat().st_size,
        "row_counts": _count_rows(db_path),
        "backgrounds_included": backgrounds_dir.is_dir(),
        "original_db_path": str(db),
    }

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Copy database
        shutil.copy2(db, tmp_path / db.name)

        # Copy backgrounds if they exist
        if backgrounds_dir.is_dir():
            shutil.copytree(backgrounds_dir, tmp_path / "backgrounds")
            manifest["backgrounds_count"] = len(list(backgrounds_dir.iterdir()))
        else:
            manifest["backgrounds_count"] = 0

        # Write manifest
        (tmp_path / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2) + "\n"
        )

        # Create tar.gz
        with tarfile.open(str(output), "w:gz") as tar:
            for item in tmp_path.iterdir():
                tar.add(str(item), arcname=item.name)

    manifest["archive_path"] = str(output)
    manifest["archive_size_bytes"] = output.stat().st_size
    logger.info(
        "Backup created: %s (%d bytes)",
        output, output.stat().st_size,
    )
    return manifest


def restore_backup(archive_path: str, target_dir: str) -> dict:
    """Restore from a backup archive.

    Creates a .pre-restore copy of the current DB as a safety net.

    Args:
        archive_path: Path to the .tar.gz backup archive.
        target_dir: Directory to restore into (where the DB lives).

    Returns:
        Manifest dict from the archive.
    """
    archive = Path(archive_path)
    if not archive.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    # Extract to temp dir first, validate manifest
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        with tarfile.open(str(archive), "r:gz") as tar:
            # Security: reject paths that escape the extraction dir
            for member in tar.getmembers():
                if member.name.startswith("/") or ".." in member.name:
                    raise ValueError(f"Unsafe path in archive: {member.name}")
            tar.extractall(tmp_path)

        manifest_path = tmp_path / MANIFEST_NAME
        if not manifest_path.exists():
            raise ValueError("Invalid backup: no manifest found")

        manifest = json.loads(manifest_path.read_text())
        db_name = manifest.get("db_file", "kanfei.db")

        extracted_db = tmp_path / db_name
        if not extracted_db.exists():
            raise ValueError(f"Invalid backup: database {db_name} not found in archive")

        # Safety: backup current DB before overwriting
        current_db = target / db_name
        if current_db.exists():
            pre_restore = target / f"{db_name}.pre-restore"
            shutil.copy2(current_db, pre_restore)
            logger.info("Pre-restore backup: %s", pre_restore)

        # Also checkpoint current DB WAL before replacing
        if current_db.exists():
            try:
                _wal_checkpoint(str(current_db))
            except Exception:
                pass  # best effort

        # Restore database
        shutil.copy2(extracted_db, current_db)

        # Restore backgrounds
        extracted_bg = tmp_path / "backgrounds"
        target_bg = target / "backgrounds"
        if extracted_bg.is_dir():
            if target_bg.exists():
                shutil.rmtree(target_bg)
            shutil.copytree(extracted_bg, target_bg)

    logger.info("Restored from backup: %s", archive)
    return manifest


def list_backups(backup_dir: str) -> list[dict]:
    """List existing backup archives in a directory.

    Returns:
        List of dicts with name, size_bytes, modified timestamp.
    """
    d = Path(backup_dir)
    if not d.is_dir():
        return []

    backups = []
    for f in sorted(d.glob("kanfei-backup-*.tar.gz"), reverse=True):
        backups.append({
            "name": f.name,
            "size_bytes": f.stat().st_size,
            "modified": datetime.fromtimestamp(
                f.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
        })
    return backups


def rotate_backups(backup_dir: str, keep: int = 7) -> int:
    """Delete oldest backups beyond the retention count.

    Returns:
        Number of backups deleted.
    """
    d = Path(backup_dir)
    if not d.is_dir():
        return 0

    archives = sorted(d.glob("kanfei-backup-*.tar.gz"))
    to_delete = archives[:-keep] if len(archives) > keep else []

    for f in to_delete:
        f.unlink()
        logger.info("Rotated old backup: %s", f.name)

    return len(to_delete)


def get_backup_dir(db_path: str, configured_dir: str = "") -> str:
    """Resolve the backup directory.

    Uses configured_dir if set, otherwise defaults to {db_parent}/backups/.
    """
    if configured_dir:
        return configured_dir
    return str(Path(db_path).parent / "backups")


def generate_backup_filename() -> str:
    """Generate a timestamped backup filename."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    return f"kanfei-backup-{ts}.tar.gz"


def _seconds_until_time(target_hhmm: str, tz_name: str = "") -> float:
    """Calculate seconds until the next occurrence of HH:MM.

    Uses station timezone if configured, otherwise local system time.
    If the target time has already passed today, returns seconds until
    tomorrow's occurrence.
    """
    try:
        hour, minute = int(target_hhmm[:2]), int(target_hhmm[3:5])
    except (ValueError, IndexError):
        return 0.0

    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo(tz_name))
        except (ImportError, KeyError):
            now = datetime.now().astimezone()
    else:
        now = datetime.now().astimezone()

    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)

    return (target - now).total_seconds()


def _read_backup_config(db_path: str) -> dict:
    """Read current backup config from station_config (best-effort)."""
    defaults = {
        "backup_enabled": False,
        "backup_interval_hours": 24,
        "backup_retention_count": 7,
        "backup_directory": "",
        "backup_schedule_time": "",
        "station_timezone": "",
    }
    try:
        conn = sqlite3.connect(db_path)
        for key in defaults:
            cur = conn.execute(
                "SELECT value FROM station_config WHERE key = ?", (key,)
            )
            row = cur.fetchone()
            if row is not None:
                val = row[0]
                if val.lower() in ("true", "false"):
                    defaults[key] = val.lower() == "true"
                else:
                    try:
                        defaults[key] = int(val)
                    except ValueError:
                        defaults[key] = val
        conn.close()
    except Exception:
        pass
    return defaults


async def backup_scheduler(
    db_path: str,
    backup_dir: str,
    interval_hours: int = 24,
    retention_count: int = 7,
    schedule_time: str = "",
    timezone_name: str = "",
) -> None:
    """Background task — creates backups on a schedule with rotation.

    Re-reads config from DB each cycle so changes in the Settings UI
    take effect without restarting. If schedule_time is set (HH:MM),
    runs at that time of day. Otherwise, runs on a fixed interval.

    Runs until cancelled. Intended to be started as an asyncio task
    in the web app lifespan.
    """
    logger.info("Backup scheduler started (dir=%s)", backup_dir)

    while True:
        # Re-read config each cycle so Settings changes take effect
        cfg = _read_backup_config(db_path)
        if not cfg["backup_enabled"]:
            # Disabled — check again in 60s
            await asyncio.sleep(60)
            continue

        cur_schedule = str(cfg.get("backup_schedule_time", ""))
        cur_interval = int(cfg.get("backup_interval_hours", 24))
        cur_retention = int(cfg.get("backup_retention_count", 7))
        cur_tz = str(cfg.get("station_timezone", ""))
        cur_dir = get_backup_dir(db_path, str(cfg.get("backup_directory", "")))

        if cur_schedule:
            wait = _seconds_until_time(cur_schedule, cur_tz)
            logger.debug("Backup scheduled at %s in %.0f seconds", cur_schedule, wait)
            await asyncio.sleep(wait)
        else:
            await asyncio.sleep(cur_interval * 3600)

        # Re-check enabled after sleep (user may have disabled during wait)
        cfg = _read_backup_config(db_path)
        if not cfg["backup_enabled"]:
            continue

        cur_retention = int(cfg.get("backup_retention_count", 7))
        cur_dir = get_backup_dir(db_path, str(cfg.get("backup_directory", "")))

        try:
            filename = generate_backup_filename()
            output = str(Path(cur_dir) / filename)
            manifest = create_backup(db_path, output)
            deleted = rotate_backups(cur_dir, keep=cur_retention)
            logger.info(
                "Scheduled backup complete: %s (%d bytes, %d rotated)",
                filename, manifest.get("archive_size_bytes", 0), deleted,
            )
            _update_backup_status(db_path, success=True, timestamp=manifest["timestamp"])
        except Exception as exc:
            logger.error("Scheduled backup failed: %s", exc)
            _update_backup_status(db_path, success=False, error=str(exc))


def _update_backup_status(db_path: str, success: bool, timestamp: str = "", error: str = "") -> None:
    """Write backup status to station_config (best-effort)."""
    try:
        conn = sqlite3.connect(db_path)
        now = datetime.now(timezone.utc).isoformat()
        if success:
            conn.execute(
                "INSERT OR REPLACE INTO station_config (key, value, updated_at) VALUES (?, ?, ?)",
                ("backup_last_success", timestamp, now),
            )
            conn.execute(
                "INSERT OR REPLACE INTO station_config (key, value, updated_at) VALUES (?, ?, ?)",
                ("backup_last_error", "", now),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO station_config (key, value, updated_at) VALUES (?, ?, ?)",
                ("backup_last_error", error, now),
            )
        conn.commit()
        conn.close()
    except Exception:
        pass  # best effort — don't crash the scheduler
