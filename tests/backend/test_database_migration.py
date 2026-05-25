"""Tests for one-shot DB migrations in ``init_database``.

Today's focus: the ``cwop_mute_*`` → ``channel_mute_*`` rename
introduced in issue #162.  Each operator who saved a mute under the
beta16 keys must find that mute still in effect after the daemon
restarts on beta17 — under the new key name.
"""

from sqlalchemy import text

from app.models.database import (
    Base,
    SessionLocal,
    engine,
    init_database,
)
from app.models.station_config import StationConfigModel


def _wipe_station_config() -> None:
    Base.metadata.drop_all(bind=engine, tables=[StationConfigModel.__table__])
    Base.metadata.create_all(bind=engine, tables=[StationConfigModel.__table__])


def _all_rows() -> dict[str, str]:
    db = SessionLocal()
    try:
        return {r.key: r.value for r in db.query(StationConfigModel).all()}
    finally:
        db.close()


class TestChannelMuteRenameMigration:

    def test_migrates_beta16_keys_to_beta17(self):
        _wipe_station_config()
        db = SessionLocal()
        try:
            db.add(StationConfigModel(
                key="cwop_mute_outdoor_temperature", value="true",
            ))
            db.add(StationConfigModel(
                key="cwop_mute_wind_speed", value="false",
            ))
            db.commit()
        finally:
            db.close()

        init_database()

        rows = _all_rows()
        assert "cwop_mute_outdoor_temperature" not in rows
        assert "cwop_mute_wind_speed" not in rows
        assert rows.get("channel_mute_outdoor_temperature") == "true"
        assert rows.get("channel_mute_wind_speed") == "false"

    def test_idempotent_on_second_run(self):
        _wipe_station_config()
        db = SessionLocal()
        try:
            db.add(StationConfigModel(
                key="cwop_mute_outdoor_temperature", value="true",
            ))
            db.commit()
        finally:
            db.close()

        init_database()
        snapshot_after_first = _all_rows()

        init_database()
        snapshot_after_second = _all_rows()

        assert snapshot_after_first == snapshot_after_second

    def test_existing_new_key_is_not_overwritten(self):
        # If an operator (or a previous partial-migration) already wrote the
        # new key, the migration must not clobber the existing value with
        # the legacy one.
        _wipe_station_config()
        db = SessionLocal()
        try:
            db.add(StationConfigModel(
                key="cwop_mute_outdoor_temperature", value="true",
            ))
            db.add(StationConfigModel(
                key="channel_mute_outdoor_temperature", value="false",
            ))
            db.commit()
        finally:
            db.close()

        init_database()

        rows = _all_rows()
        assert "cwop_mute_outdoor_temperature" not in rows
        # Existing new-key value preserved.
        assert rows.get("channel_mute_outdoor_temperature") == "false"

    def test_no_migration_needed_no_change(self):
        _wipe_station_config()
        db = SessionLocal()
        try:
            db.add(StationConfigModel(
                key="channel_mute_outdoor_temperature", value="true",
            ))
            db.commit()
        finally:
            db.close()

        init_database()

        rows = _all_rows()
        assert rows == {"channel_mute_outdoor_temperature": "true"}
