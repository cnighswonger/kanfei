"""Tests for the legacy-link-bank typo fix (issue #174).

Locks in three things:

1. The MemAddr entries for SamplePer/ArcPeriod live in link memory Bank 1,
   matching the Davis techref.  A regression to bank=0 would put these
   reads back into station memory at addresses that hold sensor data, so
   the invariant test catches it cheaply.
2. read_archive_period and read_sample_period reject values outside their
   Davis-legal ranges and return None instead of poisoning downstream
   state.  set_archive_period raises rather than writing a non-honored
   value to the SAP register.
3. The one-shot canonical-reset migration drops a bogus archive_period
   from the persisted canonical, records its outcome, and is idempotent.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.models.archive_record import ArchiveRecordModel
from app.models.database import Base, SessionLocal, engine
from app.models.station_config import StationConfigModel
from app.protocol.constants import DAVIS_LEGAL_ARCHIVE_PERIODS, StationModel
from app.protocol.link_driver import CalibrationOffsets, LinkDriver
from app.protocol.memory_map import GroWeatherLinkBank1, LinkBank1
from logger_main import LoggerDaemon


@pytest.fixture(autouse=True)
def _setup_db():
    tables = [StationConfigModel.__table__, ArchiveRecordModel.__table__]
    Base.metadata.drop_all(bind=engine, tables=tables)
    Base.metadata.create_all(bind=engine, tables=tables)
    yield
    db = SessionLocal()
    db.query(StationConfigModel).delete()
    db.query(ArchiveRecordModel).delete()
    db.commit()
    db.close()


class TestMemoryMapBanks:
    """Pin Bank 1 for SamplePer/ArcPeriod on every legacy station family.

    The previous bank=0 typo silently read garbage from station memory
    (e.g. Tp2Lo on a Monitor) instead of the actual link-memory ArcPeriod
    register.  These three asserts are dirt-cheap and would have caught
    issue #174 at any point in the project's history.
    """

    def test_link_bank1_sample_period_is_bank_1(self):
        assert LinkBank1.SAMPLE_PERIOD.bank == 1

    def test_link_bank1_archive_period_is_bank_1(self):
        assert LinkBank1.ARCHIVE_PERIOD.bank == 1

    def test_groweather_link_bank1_archive_period_is_bank_1(self):
        assert GroWeatherLinkBank1.ARCHIVE_PERIOD.bank == 1


class TestReadArchivePeriodValidation:
    """read_archive_period rejects values the Davis firmware can't honor."""

    def _driver(self) -> LinkDriver:
        d = LinkDriver.__new__(LinkDriver)
        d.serial = MagicMock()
        d.station_model = StationModel.MONITOR
        d.calibration = CalibrationOffsets()
        d.is_rev_e = False
        d._connected = True
        d._stop_requested = False
        return d

    @pytest.mark.parametrize("legal", sorted(DAVIS_LEGAL_ARCHIVE_PERIODS))
    def test_accepts_davis_legal_values(self, legal):
        d = self._driver()
        d.read_link_memory = MagicMock(return_value=bytes([legal]))
        assert d.read_archive_period() == legal

    @pytest.mark.parametrize("garbage", [0, 2, 3, 7, 68, 102, 221, 255])
    def test_rejects_non_legal_values(self, garbage):
        d = self._driver()
        d.read_link_memory = MagicMock(return_value=bytes([garbage]))
        assert d.read_archive_period() is None

    def test_returns_none_on_empty_read(self):
        d = self._driver()
        d.read_link_memory = MagicMock(return_value=None)
        assert d.read_archive_period() is None


class TestReadSamplePeriodValidation:
    """read_sample_period decodes the (256-raw) byte and rejects out-of-range."""

    def _driver(self) -> LinkDriver:
        d = LinkDriver.__new__(LinkDriver)
        d.serial = MagicMock()
        d.station_model = StationModel.MONITOR
        d.calibration = CalibrationOffsets()
        d.is_rev_e = False
        d._connected = True
        d._stop_requested = False
        return d

    @pytest.mark.parametrize("raw,decoded", [
        (8, 248),    # the value Chris's Monitor reports
        (255, 1),    # minimum
        (1, 255),    # maximum (decoded = 256-1 = 255)
        (0, 256),    # raw=0 sentinel decodes to 256, rejected as out-of-range
    ])
    def test_decoding_and_range_check(self, raw, decoded):
        d = self._driver()
        d.read_link_memory = MagicMock(return_value=bytes([raw]))
        result = d.read_sample_period()
        if 1 <= decoded <= 255:
            assert result == decoded
        else:
            assert result is None


class TestSetArchivePeriodValidation:
    """set_archive_period rejects non-Davis-legal values pre-write."""

    def _driver(self) -> LinkDriver:
        d = LinkDriver.__new__(LinkDriver)
        d.serial = MagicMock()
        d.serial.flush = MagicMock()
        d.station_model = StationModel.MONITOR
        d._io_lock = MagicMock()
        d._io_lock.__enter__ = MagicMock()
        d._io_lock.__exit__ = MagicMock()
        return d

    @pytest.mark.parametrize("bad", [0, 2, 3, 7, 68, 102, 121, 255])
    def test_rejects_non_legal(self, bad):
        d = self._driver()
        with pytest.raises(ValueError):
            d.set_archive_period(bad)
        d.serial.send.assert_not_called()

    @pytest.mark.parametrize("good", sorted(DAVIS_LEGAL_ARCHIVE_PERIODS))
    def test_accepts_legal(self, good):
        d = self._driver()
        d.serial.wait_for_ack = MagicMock(return_value=True)
        assert d.set_archive_period(good) is True
        d.serial.send.assert_called_once()


class TestLegacyLinkPeriodMigration:
    """The canonical-reset migration drops bogus archive_period, idempotent."""

    _KEY = LoggerDaemon._CANONICAL_KEY
    _MARKER = LoggerDaemon._LEGACY_LINK_PERIOD_MIGRATION_KEY

    def _seed_canonical(self, archive_period_value):
        db = SessionLocal()
        try:
            payload = {
                "archive_period": archive_period_value,
                "sample_period": 248,
                "calibration": {
                    "inside_temp": 0, "outside_temp": 0,
                    "barometer": 456, "outside_humidity": 0, "rain_cal": 100,
                },
            }
            db.add(StationConfigModel(key=self._KEY, value=json.dumps(payload)))
            db.commit()
        finally:
            db.close()

    def _read_canonical(self):
        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key=self._KEY).first()
            return json.loads(row.value) if row and row.value else None
        finally:
            db.close()

    def _read_marker(self):
        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key=self._MARKER).first()
            return row.value if row else None
        finally:
            db.close()

    def _seed_archive_records(self, intervals: list[int]) -> None:
        db = SessionLocal()
        try:
            for i, interval in enumerate(intervals):
                db.add(ArchiveRecordModel(
                    archive_address=0x1000 + i,
                    record_time=datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc),
                    station_type=2,
                    archive_interval=interval,
                ))
            db.commit()
        finally:
            db.close()

    def _read_interval_distribution(self) -> dict:
        db = SessionLocal()
        try:
            rows = db.query(ArchiveRecordModel.archive_interval).all()
            counts: dict[int, int] = {}
            for (v,) in rows:
                counts[v] = counts.get(v, 0) + 1
            return counts
        finally:
            db.close()

    def test_replaces_bogus_archive_period_with_fresh_read(self):
        """Bogus canonical AP + Davis-legal fresh read => replace in canonical.

        Codex review on PR #175 flagged that dropping the field is not
        enough: _reconcile_wl_settings only re-seeds when the *whole*
        canonical row is None, so dropping just one field leaves it
        permanently missing.  The migration must replace in place.
        """
        self._seed_canonical(68)
        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon._archive_period = 1  # the freshly-read (post-fix) value
        daemon._migrate_legacy_link_period_v1()

        canonical = self._read_canonical()
        assert canonical["archive_period"] == 1  # replaced, not dropped
        # sample_period and calibration untouched
        assert canonical["sample_period"] == 248
        assert canonical["calibration"]["barometer"] == 456
        assert self._read_marker() == "replaced:68->1;records-clean"

    def test_defers_when_fresh_read_also_failed(self):
        """Bogus canonical AP + fresh read returned None => defer.

        Setting the marker here would lock in a permanently-broken
        canonical (post-fix migrations would skip and the field would
        stay bogus).  Leave both canonical and marker untouched so the
        next restart can retry.
        """
        self._seed_canonical(68)
        self._seed_archive_records([255, 255, 102])  # bogus rows present too
        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon._archive_period = None  # fresh read still failing
        daemon._migrate_legacy_link_period_v1()

        canonical = self._read_canonical()
        assert canonical["archive_period"] == 68  # untouched
        assert self._read_marker() is None  # marker NOT set
        # archive_records also untouched — defer applies to the whole migration
        assert self._read_interval_distribution() == {255: 2, 102: 1}

    def test_preserves_legal_archive_period(self):
        self._seed_canonical(1)
        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon._archive_period = 1
        daemon._migrate_legacy_link_period_v1()

        canonical = self._read_canonical()
        assert canonical["archive_period"] == 1
        assert self._read_marker() == "valid;records-clean"

    def test_no_canonical_records_marker(self):
        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon._archive_period = 1
        daemon._migrate_legacy_link_period_v1()
        assert self._read_marker() == "no-canonical;records-clean"

    def test_idempotent_second_run_noop(self):
        self._seed_canonical(68)
        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon._archive_period = 1

        daemon._migrate_legacy_link_period_v1()
        assert self._read_marker() == "replaced:68->1;records-clean"

        # Re-poison canonical to verify the second migration call DOES NOT
        # re-fire and touch it.
        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key=self._KEY).first()
            canonical = json.loads(row.value)
            canonical["archive_period"] = 999  # garbage
            row.value = json.dumps(canonical)
            db.commit()
        finally:
            db.close()

        daemon._migrate_legacy_link_period_v1()  # should no-op
        canonical = self._read_canonical()
        assert canonical["archive_period"] == 999  # untouched
        assert self._read_marker() == "replaced:68->1;records-clean"  # unchanged

    def test_repairs_archive_records_alongside_canonical(self):
        """Bogus canonical + bogus archive_records => repair both in one pass.

        This is the beta19 self-healing path: an upgrader with both a
        bogus canonical AP and a tableful of archive_interval=255 (or
        other garbage) gets the canonical replaced AND every bogus
        archive row rewritten in a single connect, with no manual tool.
        """
        self._seed_canonical(68)
        self._seed_archive_records([255, 255, 255, 102, 221, 1])  # 5 bogus + 1 clean

        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon._archive_period = 1
        daemon._migrate_legacy_link_period_v1()

        dist = self._read_interval_distribution()
        assert dist == {1: 6}  # all five bogus rows rewritten to 1
        assert self._read_marker() == "replaced:68->1;records-repaired:5->1"

    def test_repairs_archive_records_when_canonical_already_legal(self):
        """Legal canonical + bogus archive_records => repair rows using canonical's value.

        Covers the user who manually fixed canonical via the Settings UI
        before upgrading but left archive_records bogus.  Target value is
        canonical's existing legal AP, not fresh_ap, so the repair
        matches what the reconciler will push to the station.
        """
        self._seed_canonical(5)  # legal AP that differs from fresh_ap below
        self._seed_archive_records([255, 102])
        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon._archive_period = 1  # would-be fresh read, but canonical wins

        daemon._migrate_legacy_link_period_v1()

        dist = self._read_interval_distribution()
        assert dist == {5: 2}  # rewritten to canonical's value, not fresh_ap
        assert self._read_marker() == "valid;records-repaired:2->5"

    def test_no_repair_when_no_bogus_records_exist(self):
        """Legal canonical + only legal records => marker says records-clean."""
        self._seed_canonical(1)
        self._seed_archive_records([1, 1, 5, 10, 30])  # all Davis-legal
        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon._archive_period = 1
        daemon._migrate_legacy_link_period_v1()

        # All rows untouched
        dist = self._read_interval_distribution()
        assert dist == {1: 2, 5: 1, 10: 1, 30: 1}
        assert self._read_marker() == "valid;records-clean"

    def test_no_repair_when_target_ap_unknown(self):
        """No canonical + no fresh_ap => can't choose a target, leave records.

        Edge: a brand-new install where the daemon hasn't read the link
        yet (fresh_ap=None) AND there's no canonical row yet.  We have
        no value to rewrite bogus archive_intervals to, so leave them.
        With both fresh_ap None and no canonical there's nothing to
        defer for either — set marker as a clean no-op.
        """
        self._seed_archive_records([255, 102])
        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon._archive_period = None
        daemon._migrate_legacy_link_period_v1()

        dist = self._read_interval_distribution()
        assert dist == {255: 1, 102: 1}  # untouched
        assert self._read_marker() == "no-canonical;records-clean"
