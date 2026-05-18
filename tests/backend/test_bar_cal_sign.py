"""Tests for the barometer-calibration sign convention.

Issue #154: the legacy Davis BAR_CAL register stores values with the
"subtract from raw reading" sign per techref.txt:1070
(`Barometer = Barometer - BarCal`).  Pre-fix kanfei exposed that raw
register value directly through the UI, so a user who entered the
intuitive "+456 thousandths inHg → add 0.456 inHg" actually got "−0.456
inHg" applied.  Fix: negate at the kanfei-to-Davis boundary so the
in-memory `cal.barometer`, the UI, and the canonical station_config
row all use user-facing "add to reading" semantics.

These tests pin:
 - read_calibration negates the BAR_CAL register on read into in-memory.
 - write_calibration negates the in-memory value back to the register.
 - apply_calibration ADDS the in-memory cal (positive cal → reading up).
 - A round trip (write then read) returns the same user-facing value.
 - The one-time canonical-row sign migration flips an existing pre-fix
   barometer entry, records its outcome, and is idempotent thereafter.
"""

import json
import struct
from unittest.mock import MagicMock, patch

import pytest

from app.models.database import Base, SessionLocal, engine
from app.models.station_config import StationConfigModel
from app.protocol.link_driver import CalibrationOffsets, LinkDriver
from app.protocol.memory_map import BasicBank1
from app.protocol.station_types import SensorReading
from logger_main import LoggerDaemon


@pytest.fixture(autouse=True)
def _setup_db():
    Base.metadata.drop_all(bind=engine, tables=[StationConfigModel.__table__])
    Base.metadata.create_all(bind=engine, tables=[StationConfigModel.__table__])
    yield
    db = SessionLocal()
    db.query(StationConfigModel).delete()
    db.commit()
    db.close()


def _driver_with_mocked_io() -> LinkDriver:
    """Build a LinkDriver bypassing its serial-port opening.

    We patch read_station_memory and write_station_memory directly on
    the instance so the calibration methods exercise the sign-handling
    code paths without needing a real serial port.
    """
    driver = LinkDriver.__new__(LinkDriver)
    driver.serial = MagicMock()
    driver.serial.flush = MagicMock()
    driver.station_model = None
    driver.calibration = CalibrationOffsets()
    driver.is_rev_e = False
    driver._connected = True
    driver._stop_requested = False
    import threading
    driver._io_lock = threading.RLock()
    return driver


class TestApplyCalibrationSign:
    """`apply_calibration` uses the user-facing 'add to reading' sign for
    barometer — a positive cal.barometer means the reading goes UP, not
    down (the pre-fix bug)."""

    def test_positive_cal_raises_reading(self):
        driver = _driver_with_mocked_io()
        # User-facing semantics: +456 thousandths inHg = add 0.456 inHg.
        # In SI tenths-hPa that's ~ +154 (456 × 33.8639 / 100 = 154.4).
        driver.calibration.barometer = 456

        reading = SensorReading(barometer=10000)  # 1000.0 hPa
        driver.apply_calibration(reading)

        # Should INCREASE.  Exact: 456 × 33.8639 / 100 = 154.4 → round to 154.
        assert reading.barometer == 10154

    def test_negative_cal_lowers_reading(self):
        driver = _driver_with_mocked_io()
        driver.calibration.barometer = -456
        reading = SensorReading(barometer=10000)
        driver.apply_calibration(reading)
        assert reading.barometer == 9846

    def test_zero_cal_no_change(self):
        driver = _driver_with_mocked_io()
        driver.calibration.barometer = 0
        reading = SensorReading(barometer=10000)
        driver.apply_calibration(reading)
        assert reading.barometer == 10000


class TestReadCalibrationNegate:
    """`read_calibration` negates the BAR_CAL register on read so in-memory
    `cal.barometer` carries the user-facing 'add to reading' sign."""

    def test_positive_register_yields_negative_in_memory(self):
        # On-device BAR_CAL = +456 means the firmware subtracts 456 from
        # raw → reading goes DOWN.  Post-fix, in-memory cal.barometer
        # should report -456 (the equivalent user-facing "add" value).
        driver = _driver_with_mocked_io()
        reg = struct.pack("<h", 456)
        with patch.object(driver, "read_station_memory") as rsm:
            # Per-field calls — return zero bytes for everything except bar
            def _stub(bank, addr, nibbles):
                if addr == BasicBank1.BAR_CAL.address:
                    return reg
                return b"\x00\x00"
            rsm.side_effect = _stub
            driver.read_calibration()
        assert driver.calibration.barometer == -456

    def test_negative_register_yields_positive_in_memory(self):
        driver = _driver_with_mocked_io()
        reg = struct.pack("<h", -456)
        with patch.object(driver, "read_station_memory") as rsm:
            def _stub(bank, addr, nibbles):
                if addr == BasicBank1.BAR_CAL.address:
                    return reg
                return b"\x00\x00"
            rsm.side_effect = _stub
            driver.read_calibration()
        assert driver.calibration.barometer == 456


class TestWriteCalibrationNegate:
    """`write_calibration` negates in-memory `barometer` on the way to the
    BAR_CAL register so the user-facing 'add' value lines up with the
    firmware's 'subtract' convention."""

    def test_positive_in_memory_writes_negative_register(self):
        driver = _driver_with_mocked_io()
        captured = {}

        def _capture_write(bank, addr, nibbles, data):
            captured[addr] = data
            return True

        # Stop polling stubs.
        driver.stop_polling = MagicMock(return_value=True)
        driver.start_polling = MagicMock(return_value=True)

        with patch.object(driver, "write_station_memory",
                          side_effect=_capture_write):
            offsets = CalibrationOffsets(barometer=456)
            driver.write_calibration(offsets)

        bar_bytes = captured[BasicBank1.BAR_CAL.address]
        register_value = struct.unpack("<h", bar_bytes)[0]
        assert register_value == -456

    def test_negative_in_memory_writes_positive_register(self):
        driver = _driver_with_mocked_io()
        captured = {}

        def _capture_write(bank, addr, nibbles, data):
            captured[addr] = data
            return True

        driver.stop_polling = MagicMock(return_value=True)
        driver.start_polling = MagicMock(return_value=True)

        with patch.object(driver, "write_station_memory",
                          side_effect=_capture_write):
            offsets = CalibrationOffsets(barometer=-456)
            driver.write_calibration(offsets)

        bar_bytes = captured[BasicBank1.BAR_CAL.address]
        register_value = struct.unpack("<h", bar_bytes)[0]
        assert register_value == 456


class TestReadWriteRoundTrip:
    """End-to-end: writing a user-facing value X then reading it back
    yields the same X.  Catches any asymmetry between the two sign
    boundaries."""

    @pytest.mark.parametrize("user_value", [456, -456, 0, 1234, -1234])
    def test_round_trip_preserves_user_facing_sign(self, user_value):
        driver = _driver_with_mocked_io()
        register_store = {}

        def _capture_write(bank, addr, nibbles, data):
            register_store[(bank, addr)] = data
            return True

        def _read(bank, addr, nibbles):
            return register_store.get((bank, addr), b"\x00\x00")

        driver.stop_polling = MagicMock(return_value=True)
        driver.start_polling = MagicMock(return_value=True)

        with patch.object(driver, "write_station_memory",
                          side_effect=_capture_write):
            driver.write_calibration(CalibrationOffsets(barometer=user_value))

        with patch.object(driver, "read_station_memory", side_effect=_read):
            driver.read_calibration()

        assert driver.calibration.barometer == user_value


class TestBarCalSignMigration:
    """The canonical station_config row's barometer entry must get its
    sign flipped on first run post-fix (issue #154), idempotent via a
    marker.  Otherwise the first reconcile would force-write the old
    (negated) value back through the new negate-on-write path and break
    every working pre-fix calibration."""

    def _seed_canonical(self, cal_barometer):
        db = SessionLocal()
        try:
            db.add(StationConfigModel(
                key=LoggerDaemon._CANONICAL_KEY,
                value=json.dumps({
                    "archive_period": 1,
                    "sample_period": 248,
                    "calibration": {
                        "inside_temp": 0,
                        "outside_temp": 0,
                        "barometer": cal_barometer,
                        "outside_humidity": 0,
                        "rain_cal": 100,
                    },
                }),
            ))
            db.commit()
        finally:
            db.close()

    def _get_marker(self):
        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(
                key=LoggerDaemon._BAR_CAL_SIGN_MIGRATION_KEY,
            ).first()
            return row.value if row else None
        finally:
            db.close()

    def _get_canonical_barometer(self):
        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(
                key=LoggerDaemon._CANONICAL_KEY,
            ).first()
            if row is None:
                return None
            return json.loads(row.value)["calibration"]["barometer"]
        finally:
            db.close()

    def test_flips_existing_negative_cal(self):
        # Pre-fix: user had to enter -456 in UI to get +0.456 inHg effective.
        self._seed_canonical(-456)
        d = LoggerDaemon()
        d._migrate_bar_cal_sign_v1()

        assert self._get_canonical_barometer() == 456
        assert self._get_marker() == "flipped"

    def test_flips_existing_positive_cal(self):
        # Symmetric case: someone who entered +X pre-fix and accepted the
        # bug's downward effect now gets the negated form post-migration.
        self._seed_canonical(200)
        d = LoggerDaemon()
        d._migrate_bar_cal_sign_v1()

        assert self._get_canonical_barometer() == -200
        assert self._get_marker() == "flipped"

    def test_no_op_when_cal_is_zero(self):
        self._seed_canonical(0)
        d = LoggerDaemon()
        d._migrate_bar_cal_sign_v1()

        assert self._get_canonical_barometer() == 0
        # Still records the marker so future runs skip the work.
        assert self._get_marker() == "flipped"

    def test_no_canonical_row_just_sets_marker(self):
        d = LoggerDaemon()
        d._migrate_bar_cal_sign_v1()

        assert self._get_canonical_barometer() is None
        assert self._get_marker() == "no-canonical"

    def test_idempotent_second_run_does_not_flip_again(self):
        self._seed_canonical(-456)
        d = LoggerDaemon()
        d._migrate_bar_cal_sign_v1()
        assert self._get_canonical_barometer() == 456

        # Second call must NOT flip the now-correct value back to -456.
        d._migrate_bar_cal_sign_v1()
        assert self._get_canonical_barometer() == 456
        assert self._get_marker() == "flipped"

    def test_unparseable_canonical_records_marker_without_crashing(self):
        # If something planted a non-JSON value, the migration should
        # leave it alone (no recovery attempt) and still set the marker
        # so the daemon keeps booting.
        db = SessionLocal()
        try:
            db.add(StationConfigModel(
                key=LoggerDaemon._CANONICAL_KEY,
                value="not-json-at-all",
            ))
            db.commit()
        finally:
            db.close()

        d = LoggerDaemon()
        d._migrate_bar_cal_sign_v1()
        assert self._get_marker() is not None
