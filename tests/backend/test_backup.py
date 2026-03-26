"""Tests for backup and restore service."""

import json
import sqlite3
import tarfile
import time
from pathlib import Path

import pytest

from app.services.backup import (
    create_backup,
    restore_backup,
    list_backups,
    rotate_backups,
    get_backup_dir,
    generate_backup_filename,
    MANIFEST_NAME,
)


@pytest.fixture
def fake_db(tmp_path):
    """Create a minimal SQLite DB with station_config table."""
    db_path = tmp_path / "kanfei.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE station_config (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)"
    )
    conn.execute(
        "INSERT INTO station_config VALUES ('serial_port', '/dev/ttyUSB0', '2026-01-01')"
    )
    conn.execute(
        "CREATE TABLE sensor_readings (id INTEGER PRIMARY KEY, temp REAL)"
    )
    for i in range(10):
        conn.execute("INSERT INTO sensor_readings (temp) VALUES (?)", (70.0 + i,))
    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture
def fake_db_with_backgrounds(fake_db, tmp_path):
    """Fake DB with a backgrounds directory."""
    bg_dir = tmp_path / "backgrounds"
    bg_dir.mkdir()
    (bg_dir / "clear-day.jpg").write_bytes(b"\xff\xd8fake-jpeg")
    (bg_dir / "rain.png").write_bytes(b"\x89PNGfake-png")
    return fake_db


class TestCreateBackup:

    def test_creates_tar_gz(self, fake_db, tmp_path):
        output = str(tmp_path / "backup.tar.gz")
        manifest = create_backup(fake_db, output)

        assert Path(output).exists()
        assert manifest["kanfei_version"] == "0.1.0"
        assert manifest["db_file"] == "kanfei.db"
        assert manifest["row_counts"]["station_config"] == 1
        assert manifest["row_counts"]["sensor_readings"] == 10

    def test_archive_contains_db_and_manifest(self, fake_db, tmp_path):
        output = str(tmp_path / "backup.tar.gz")
        create_backup(fake_db, output)

        with tarfile.open(output, "r:gz") as tar:
            names = tar.getnames()
        assert "kanfei.db" in names
        assert MANIFEST_NAME in names

    def test_includes_backgrounds(self, fake_db_with_backgrounds, tmp_path):
        output = str(tmp_path / "backup.tar.gz")
        manifest = create_backup(fake_db_with_backgrounds, output)

        assert manifest["backgrounds_included"] is True
        assert manifest["backgrounds_count"] == 2

        with tarfile.open(output, "r:gz") as tar:
            names = tar.getnames()
        assert "backgrounds/clear-day.jpg" in names
        assert "backgrounds/rain.png" in names

    def test_no_backgrounds_dir(self, fake_db, tmp_path):
        output = str(tmp_path / "backup.tar.gz")
        manifest = create_backup(fake_db, output)

        assert manifest["backgrounds_included"] is False
        assert manifest["backgrounds_count"] == 0

    def test_missing_db_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            create_backup("/nonexistent/kanfei.db", str(tmp_path / "out.tar.gz"))


class TestRestoreBackup:

    def test_restores_db(self, fake_db, tmp_path):
        # Create backup
        archive = str(tmp_path / "backup.tar.gz")
        create_backup(fake_db, archive)

        # Restore to new location
        restore_dir = tmp_path / "restored"
        restore_dir.mkdir()
        manifest = restore_backup(archive, str(restore_dir))

        restored_db = restore_dir / "kanfei.db"
        assert restored_db.exists()
        assert manifest["db_file"] == "kanfei.db"

        # Verify data is intact
        conn = sqlite3.connect(str(restored_db))
        count = conn.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]
        conn.close()
        assert count == 10

    def test_creates_pre_restore_backup(self, fake_db, tmp_path):
        archive = str(tmp_path / "backup.tar.gz")
        create_backup(fake_db, archive)

        # Restore over existing DB
        manifest = restore_backup(archive, str(tmp_path))

        pre_restore = tmp_path / "kanfei.db.pre-restore"
        assert pre_restore.exists()

    def test_restores_backgrounds(self, fake_db_with_backgrounds, tmp_path):
        archive = str(tmp_path / "backup.tar.gz")
        create_backup(fake_db_with_backgrounds, archive)

        restore_dir = tmp_path / "restored"
        restore_dir.mkdir()
        restore_backup(archive, str(restore_dir))

        assert (restore_dir / "backgrounds" / "clear-day.jpg").exists()
        assert (restore_dir / "backgrounds" / "rain.png").exists()

    def test_invalid_archive_raises(self, tmp_path):
        bad_file = tmp_path / "bad.tar.gz"
        bad_file.write_bytes(b"not a tar file")
        with pytest.raises(Exception):
            restore_backup(str(bad_file), str(tmp_path / "out"))

    def test_missing_manifest_raises(self, tmp_path):
        # Create a tar.gz without a manifest
        archive = tmp_path / "no-manifest.tar.gz"
        with tarfile.open(str(archive), "w:gz") as tar:
            dummy = tmp_path / "dummy.txt"
            dummy.write_text("hello")
            tar.add(str(dummy), arcname="dummy.txt")

        with pytest.raises(ValueError, match="no manifest"):
            restore_backup(str(archive), str(tmp_path / "out"))

    def test_rejects_path_traversal(self, tmp_path):
        # Create a malicious tar.gz with path traversal
        archive = tmp_path / "evil.tar.gz"
        with tarfile.open(str(archive), "w:gz") as tar:
            info = tarfile.TarInfo(name="../../../etc/passwd")
            info.size = 5
            import io
            tar.addfile(info, io.BytesIO(b"evil\n"))

        with pytest.raises(ValueError, match="Unsafe path"):
            restore_backup(str(archive), str(tmp_path / "out"))


class TestListBackups:

    def test_empty_dir(self, tmp_path):
        assert list_backups(str(tmp_path)) == []

    def test_nonexistent_dir(self):
        assert list_backups("/nonexistent/path") == []

    def test_lists_matching_files(self, tmp_path):
        (tmp_path / "kanfei-backup-2026-03-24-120000.tar.gz").write_bytes(b"a")
        (tmp_path / "kanfei-backup-2026-03-23-120000.tar.gz").write_bytes(b"bb")
        (tmp_path / "other-file.txt").write_bytes(b"ignore")

        backups = list_backups(str(tmp_path))
        assert len(backups) == 2
        # Newest first
        assert backups[0]["name"] == "kanfei-backup-2026-03-24-120000.tar.gz"
        assert backups[1]["name"] == "kanfei-backup-2026-03-23-120000.tar.gz"

    def test_includes_size(self, tmp_path):
        (tmp_path / "kanfei-backup-2026-03-24-120000.tar.gz").write_bytes(b"x" * 100)
        backups = list_backups(str(tmp_path))
        assert backups[0]["size_bytes"] == 100


class TestRotateBackups:

    def test_keeps_n_newest(self, tmp_path):
        for i in range(5):
            (tmp_path / f"kanfei-backup-2026-03-{20+i:02d}-120000.tar.gz").write_bytes(b"x")

        deleted = rotate_backups(str(tmp_path), keep=3)
        assert deleted == 2
        remaining = list(tmp_path.glob("kanfei-backup-*.tar.gz"))
        assert len(remaining) == 3

    def test_no_delete_when_under_limit(self, tmp_path):
        (tmp_path / "kanfei-backup-2026-03-24-120000.tar.gz").write_bytes(b"x")
        deleted = rotate_backups(str(tmp_path), keep=5)
        assert deleted == 0

    def test_nonexistent_dir(self):
        assert rotate_backups("/nonexistent") == 0


class TestGetBackupDir:

    def test_default(self):
        result = get_backup_dir("/var/lib/kanfei/kanfei.db")
        assert result == "/var/lib/kanfei/backups"

    def test_configured(self):
        result = get_backup_dir("/var/lib/kanfei/kanfei.db", "/mnt/backup")
        assert result == "/mnt/backup"

    def test_empty_string_uses_default(self):
        result = get_backup_dir("/home/user/kanfei.db", "")
        assert result == "/home/user/backups"


class TestGenerateBackupFilename:

    def test_format(self):
        name = generate_backup_filename()
        assert name.startswith("kanfei-backup-")
        assert name.endswith(".tar.gz")
        # Should contain a date-like pattern
        assert "202" in name


class TestSecondsUntilTime:

    def test_future_time_today(self):
        from app.services.backup import _seconds_until_time
        from datetime import datetime
        # Use a time 1 hour from now — should be ~3600 seconds
        now = datetime.now().astimezone()
        future = now.replace(second=0, microsecond=0)
        # Add 1 hour, handle midnight wrap
        future_hour = (future.hour + 1) % 24
        target = f"{future_hour:02d}:{future.minute:02d}"
        result = _seconds_until_time(target)
        # Should be roughly 3600 seconds (±60 for timing)
        assert 3500 <= result <= 3700

    def test_past_time_wraps_to_tomorrow(self):
        from app.services.backup import _seconds_until_time
        from datetime import datetime
        # Use a time 1 hour ago — should wrap to tomorrow (~23h from now)
        now = datetime.now().astimezone()
        past_hour = (now.hour - 1) % 24
        target = f"{past_hour:02d}:{now.minute:02d}"
        result = _seconds_until_time(target)
        # Should be roughly 23 hours
        assert 82000 <= result <= 86500

    def test_invalid_format_returns_zero(self):
        from app.services.backup import _seconds_until_time
        assert _seconds_until_time("") == 0.0
        assert _seconds_until_time("bad") == 0.0

    def test_midnight(self):
        from app.services.backup import _seconds_until_time
        result = _seconds_until_time("00:00")
        # Should be between 0 and 86400 seconds
        assert 0 < result <= 86400
