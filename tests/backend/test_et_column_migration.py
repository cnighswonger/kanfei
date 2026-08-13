"""ET graduated from ``extra_json`` to dedicated ``sensor_readings``
columns in the beta30 migration (follow-on to #329).

This test file pins:

  1. The three new ORM fields are present and readable.
  2. ``sensor_meta`` registers them and converts tenths-mm to inches.
  3. The migration's backfill copies extra_json values (float mm) into
     the new columns (int tenths-mm) — matching the round-trip shape
     the poller uses going forward.
  4. Poller output shape: ET no longer appears in extra_json.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import json
import pytest
from sqlalchemy import text

from app.models.database import Base, SessionLocal, engine, init_database
from app.models.sensor_meta import SENSOR_COLUMNS, SENSOR_UNITS, convert
from app.models.sensor_reading import SensorReadingModel
from app.services.poller import Poller


class TestOrmColumnsPresent:
    def test_et_daily_field_exists(self):
        assert hasattr(SensorReadingModel, "et_daily")

    def test_et_monthly_field_exists(self):
        assert hasattr(SensorReadingModel, "et_monthly")

    def test_et_yearly_field_exists(self):
        assert hasattr(SensorReadingModel, "et_yearly")

    def test_et_columns_registered_in_sensor_meta(self):
        assert "et_daily" in SENSOR_COLUMNS
        assert "et_monthly" in SENSOR_COLUMNS
        assert "et_yearly" in SENSOR_COLUMNS

    def test_et_units_are_inches(self):
        # Display unit is inches (converted from tenths-mm at read time)
        assert SENSOR_UNITS["et_daily"] == "in"
        assert SENSOR_UNITS["et_monthly"] == "in"
        assert SENSOR_UNITS["et_yearly"] == "in"


class TestTenthsMmToInchesConversion:
    """DB stores tenths of a millimetre; API returns inches.  This is the
    same conversion path rain_total uses."""

    def test_zero(self):
        assert convert("et_daily", 0) == 0.0

    def test_one_inch_via_tenths_mm(self):
        # 25.4 mm = 254 tenths mm = 1.00 inch
        assert convert("et_daily", 254) == pytest.approx(1.00, abs=0.01)

    def test_ten_inches(self):
        # 254 mm = 2540 tenths mm = 10.00 inches
        assert convert("et_yearly", 2540) == pytest.approx(10.00, abs=0.01)


class TestBackfillFromExtraJson:
    """Init-time migration backfills columns from the pre-migration
    ``extra_json`` payload so charts have full history on day-one after
    the upgrade."""

    def setup_method(self):
        Base.metadata.drop_all(bind=engine, tables=[SensorReadingModel.__table__])
        Base.metadata.create_all(bind=engine, tables=[SensorReadingModel.__table__])

    def teardown_method(self):
        db = SessionLocal()
        try:
            db.query(SensorReadingModel).delete()
            db.commit()
        finally:
            db.close()

    def _seed_extras_row(self, extras: dict) -> None:
        db = SessionLocal()
        try:
            db.add(SensorReadingModel(
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                station_type=16,
                extra_json=json.dumps(extras),
            ))
            db.commit()
        finally:
            db.close()

    def _run_backfill_sql(self) -> None:
        """The exact SQL the init-time migration runs, called directly so
        the test doesn't have to invoke the full ``init_database()``.

        Kept in sync with ``backend/app/models/database.py`` — if the
        migration query there changes, this must change too.  The
        `test_backfill_matches_poller_rounding` case pins the shape.
        """
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

    def test_all_three_backfilled(self):
        self._seed_extras_row({
            "et_daily_mm": 3.5,        # → 35 tenths mm (round(3.5*10) = 35)
            "et_monthly_mm": 42.7,     # → 427 tenths mm
            "et_yearly_mm": 630.68,    # → 6307 tenths mm (round(6306.8) = 6307)
        })
        self._run_backfill_sql()

        db = SessionLocal()
        try:
            row = db.query(SensorReadingModel).first()
            assert row.et_daily == 35
            assert row.et_monthly == 427
            assert row.et_yearly == 6307
        finally:
            db.close()

    def test_partial_extras_backfilled(self):
        """A row with only et_daily_mm gets et_daily populated; the other
        two columns stay NULL."""
        self._seed_extras_row({"et_daily_mm": 3.5})
        self._run_backfill_sql()

        db = SessionLocal()
        try:
            row = db.query(SensorReadingModel).first()
            assert row.et_daily == 35
            assert row.et_monthly is None
            assert row.et_yearly is None
        finally:
            db.close()

    def test_row_without_extras_untouched(self):
        db = SessionLocal()
        try:
            db.add(SensorReadingModel(
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                station_type=16,
            ))
            db.commit()
        finally:
            db.close()
        self._run_backfill_sql()

        db = SessionLocal()
        try:
            row = db.query(SensorReadingModel).first()
            assert row.et_daily is None
            assert row.et_monthly is None
            assert row.et_yearly is None
        finally:
            db.close()

    def test_backfill_idempotent(self):
        """Running the backfill twice must not double-count.  This is what
        the ``WHERE et_daily IS NULL`` guard enforces."""
        self._seed_extras_row({"et_daily_mm": 3.5})
        self._run_backfill_sql()
        self._run_backfill_sql()

        db = SessionLocal()
        try:
            row = db.query(SensorReadingModel).first()
            assert row.et_daily == 35
        finally:
            db.close()

    def test_backfill_matches_poller_rounding(self):
        """Backfill uses ``round()`` (not ``CAST AS INTEGER`` truncate) so
        it matches the poller's live write path (`round(mm * 10)`).  A
        value that would truncate down under CAST semantics rounds up
        here, keeping backfilled rows and freshly-polled rows at the
        same tenths-mm quantization.

        3.549 mm * 10 = 35.49 → round → 35.  A different mismatch shows:
        3.55 mm * 10 = 35.5 → round-half-to-even (banker's) → 36 in
        Python; SQLite's ``round(35.5)`` returns 36 as well.  So a value
        chosen to expose truncate-vs-round: 630.68 mm * 10 = 6306.8 →
        round → 6307.  CAST would give 6306.
        """
        self._seed_extras_row({"et_yearly_mm": 630.68})
        self._run_backfill_sql()

        db = SessionLocal()
        try:
            row = db.query(SensorReadingModel).first()
            assert row.et_yearly == 6307, (
                "backfill must round to match the poller's round(mm*10); "
                f"got {row.et_yearly}, expected 6307 (would be 6306 under CAST truncate)"
            )
        finally:
            db.close()

    def test_backfill_survives_malformed_json_row(self):
        """A historical row with malformed extra_json must not abort the
        migration.  The runtime readers already handle bad JSON as
        survivable (via try/except); the migration matches that via
        `json_valid(extra_json)`.

        Without the guard, `json_extract` on invalid JSON would raise
        `sqlite3.OperationalError: malformed JSON` and startup would
        block, taking the whole daemon down after upgrade.
        """
        # A row with genuinely invalid JSON alongside a valid ET row.
        db = SessionLocal()
        try:
            db.add(SensorReadingModel(
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                station_type=16,
                extra_json="{{not json",  # invalid
            ))
            db.add(SensorReadingModel(
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                station_type=16,
                extra_json=json.dumps({"et_daily_mm": 3.5}),  # valid
            ))
            db.commit()
        finally:
            db.close()

        # Must NOT raise.  The malformed row is skipped; the valid row
        # gets backfilled.
        self._run_backfill_sql()

        db = SessionLocal()
        try:
            rows = db.query(SensorReadingModel).order_by(SensorReadingModel.id).all()
            # First row: malformed extras, no column update
            assert rows[0].et_daily is None
            # Second row: valid extras, backfilled
            assert rows[1].et_daily == 35
        finally:
            db.close()


class TestPollerNoLongerWritesEtToExtras:
    """The poller writes ET to top-level columns, not to extra_json."""

    def test_extra_json_helper_returns_none_for_bare_snapshot(self):
        snap = SimpleNamespace(
            extra={},
            et_daily=3.5,
            et_monthly=42.7,
            et_yearly=630.68,
        )
        # ET fields present on the snapshot but no vendor extras: the
        # helper collapses to None (ET goes to columns, not extras).
        assert Poller._build_extra_json(snap) is None

    def test_extra_json_helper_passes_through_vendor_extras(self):
        snap = SimpleNamespace(
            extra={"bar_trend": 60, "forecast_rule": 3},
            et_daily=3.5,
            et_monthly=42.7,
            et_yearly=630.68,
        )
        # Vendor extras present: pass through, and ET must NOT appear.
        result = Poller._build_extra_json(snap)
        assert result is not None
        parsed = json.loads(result)
        assert parsed == {"bar_trend": 60, "forecast_rule": 3}
        assert "et_daily_mm" not in parsed
        assert "et_monthly_mm" not in parsed
        assert "et_yearly_mm" not in parsed

    def test_extra_json_helper_none_when_no_extras_no_et(self):
        snap = SimpleNamespace(extra={}, et_daily=None, et_monthly=None, et_yearly=None)
        assert Poller._build_extra_json(snap) is None
