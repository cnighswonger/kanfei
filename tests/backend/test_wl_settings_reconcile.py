"""Tests for the WeatherLink-settings reconciliation logic.

Covers the three branches of LoggerDaemon._reconcile_wl_settings (seed, no-op,
drift-correct), the SAP-failure tolerance path, and the canonical-config
persistence side-effect of _h_write_config.  Together these implement issue
#147 — the local DB (`station_config.weatherlink_canonical`) is source of
truth for archive_period / sample_period / calibration, and the link is
brought into compliance on every connect and every UI Save.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.database import Base, SessionLocal, engine
from app.models.station_config import StationConfigModel
from app.protocol.link_driver import CalibrationOffsets
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


def _mock_link(arc_period=1, sample_period=248, cal=None):
    """Build a Mock LinkDriver shaped enough for _reconcile_wl_settings
    and _h_write_config — including the post-write read-back paths.

    Default behavior: every set/write succeeds with ACK, and the matching
    read-back returns the *requested* value (modeling a healthy link that
    actually persists what it ACKs).  Tests that want to simulate the
    "ACK-but-no-persist" pathology override the read-back AsyncMock to
    return a different value.
    """
    link = MagicMock()
    state_cal = cal or CalibrationOffsets(
        inside_temp=0, outside_temp=0, barometer=0, outside_hum=0, rain_cal=100,
    )
    link.calibration = state_cal

    async def _set_arc(value):
        link.async_read_archive_period.return_value = value
        return True

    async def _set_samp(value):
        link.async_read_sample_period.return_value = value
        return True

    async def _write_cal(offsets):
        # Mirror real LinkDriver behavior: a successful write updates
        # link.calibration in place, and a follow-up read returns it.
        link.calibration = offsets
        link.async_read_calibration.return_value = offsets
        return True

    link.async_set_archive_period = AsyncMock(side_effect=_set_arc)
    link.async_set_sample_period = AsyncMock(side_effect=_set_samp)
    link.async_write_calibration = AsyncMock(side_effect=_write_cal)
    link.async_read_archive_period = AsyncMock(return_value=arc_period)
    link.async_read_sample_period = AsyncMock(return_value=sample_period)
    link.async_read_calibration = AsyncMock(return_value=state_cal)
    return link


def _daemon(arc=1, sample=248):
    d = LoggerDaemon()
    d._archive_period = arc
    d._sample_period = sample
    return d


class TestCanonicalConfigPersistence:

    def test_load_returns_none_when_row_missing(self):
        assert LoggerDaemon._load_canonical_wl_config() is None

    def test_save_then_load_roundtrips(self):
        values = {
            "archive_period": 5,
            "sample_period": 60,
            "calibration": {
                "inside_temp": 1, "outside_temp": -2, "barometer": 0,
                "outside_humidity": 0, "rain_cal": 100,
            },
        }
        LoggerDaemon._save_canonical_wl_config(values)
        assert LoggerDaemon._load_canonical_wl_config() == values

    def test_save_upserts(self):
        LoggerDaemon._save_canonical_wl_config({"archive_period": 1})
        LoggerDaemon._save_canonical_wl_config({"archive_period": 5})
        loaded = LoggerDaemon._load_canonical_wl_config()
        assert loaded == {"archive_period": 5}
        # Still exactly one row, not a duplicate.
        db = SessionLocal()
        try:
            assert db.query(StationConfigModel).filter_by(
                key=LoggerDaemon._CANONICAL_KEY,
            ).count() == 1
        finally:
            db.close()

    def test_load_returns_none_on_unparseable_value(self):
        # Manually plant an invalid JSON blob — older row format, corruption,
        # whatever.  Reconcile must treat it as missing rather than crashing.
        db = SessionLocal()
        try:
            db.add(StationConfigModel(
                key=LoggerDaemon._CANONICAL_KEY, value="not-json-at-all",
            ))
            db.commit()
        finally:
            db.close()
        assert LoggerDaemon._load_canonical_wl_config() is None


class TestReconcile:

    @pytest.mark.asyncio
    async def test_seed_when_no_canonical_row(self):
        d = _daemon(arc=1, sample=248)
        link = _mock_link()

        await d._reconcile_wl_settings(link)

        # No SAP/SSP/WWR-cal calls — nothing to reconcile.
        link.async_set_archive_period.assert_not_called()
        link.async_set_sample_period.assert_not_called()
        link.async_write_calibration.assert_not_called()
        # Canonical row now exists, seeded from the link state the daemon cached.
        canonical = LoggerDaemon._load_canonical_wl_config()
        assert canonical == {
            "archive_period": 1,
            "sample_period": 248,
            "calibration": {
                "inside_temp": 0, "outside_temp": 0, "barometer": 0,
                "outside_humidity": 0, "rain_cal": 100,
            },
        }

    @pytest.mark.asyncio
    async def test_noop_when_canonical_matches_link(self):
        LoggerDaemon._save_canonical_wl_config({
            "archive_period": 1, "sample_period": 248,
            "calibration": {
                "inside_temp": 0, "outside_temp": 0, "barometer": 0,
                "outside_humidity": 0, "rain_cal": 100,
            },
        })
        d = _daemon(arc=1, sample=248)
        link = _mock_link()

        await d._reconcile_wl_settings(link)

        link.async_set_archive_period.assert_not_called()
        link.async_set_sample_period.assert_not_called()
        link.async_write_calibration.assert_not_called()
        assert d._archive_period == 1
        assert d._sample_period == 248

    @pytest.mark.asyncio
    async def test_drift_corrects_archive_period(self):
        LoggerDaemon._save_canonical_wl_config({
            "archive_period": 1, "sample_period": 248,
        })
        # Link drifted to 51-minute archive (the real-world #147 symptom).
        d = _daemon(arc=51, sample=248)
        link = _mock_link()

        await d._reconcile_wl_settings(link)

        link.async_set_archive_period.assert_awaited_once_with(1)
        link.async_set_sample_period.assert_not_called()
        # Daemon cache is now the canonical value, not the link's old value.
        assert d._archive_period == 1

    @pytest.mark.asyncio
    async def test_drift_corrects_sample_period(self):
        LoggerDaemon._save_canonical_wl_config({
            "archive_period": 1, "sample_period": 60,
        })
        d = _daemon(arc=1, sample=248)
        link = _mock_link()

        await d._reconcile_wl_settings(link)

        link.async_set_sample_period.assert_awaited_once_with(60)
        assert d._sample_period == 60

    @pytest.mark.asyncio
    async def test_drift_corrects_calibration(self):
        # Canonical has inside_temp = 5; link is reporting 0.
        LoggerDaemon._save_canonical_wl_config({
            "archive_period": 1, "sample_period": 248,
            "calibration": {
                "inside_temp": 5, "outside_temp": 0, "barometer": 0,
                "outside_humidity": 0, "rain_cal": 100,
            },
        })
        d = _daemon(arc=1, sample=248)
        link = _mock_link()  # calibration defaults to zeroes

        await d._reconcile_wl_settings(link)

        link.async_write_calibration.assert_awaited_once()
        sent: CalibrationOffsets = link.async_write_calibration.call_args[0][0]
        assert sent.inside_temp == 5

    @pytest.mark.asyncio
    async def test_sap_failure_keeps_link_value_in_cache(self):
        LoggerDaemon._save_canonical_wl_config({
            "archive_period": 1, "sample_period": 248,
        })
        d = _daemon(arc=51, sample=248)
        link = _mock_link()
        link.async_set_archive_period = AsyncMock(return_value=False)

        await d._reconcile_wl_settings(link)

        link.async_set_archive_period.assert_awaited_once_with(1)
        # The link rejected the SAP; daemon's cached view stays at the link's
        # actual value (51), not the canonical we failed to write.  Better to
        # be honest about what the link is running than to lie based on intent.
        assert d._archive_period == 51


class TestWriteConfigPersistsCanonical:
    """The IPC write_config handler must keep the canonical row in sync with
    successful link writes, so a later reconcile uses the new value."""

    @pytest.mark.asyncio
    async def test_writes_to_canonical_on_success(self):
        d = _daemon(arc=1, sample=248)
        link = _mock_link()
        link.connected = True
        d.driver = link

        # Patch _link so the handler picks up our mock as a LinkDriver.
        # _link is a @property; patch it via the class.
        class _ForceLinkDaemon(LoggerDaemon):
            @property
            def _link(self):
                return link

        d.__class__ = _ForceLinkDaemon

        msg = {
            "archive_period": 5,
            "sample_period": 30,
            "calibration": {
                "inside_temp": 2, "outside_temp": -1, "barometer": 0,
                "outside_humidity": 0, "rain_cal": 100,
            },
        }
        result = await d._h_write_config(msg)

        assert result["results"]["archive_period"] == "ok"
        assert result["results"]["sample_period"] == "ok"
        assert result["results"]["calibration"] == "ok"
        canonical = LoggerDaemon._load_canonical_wl_config()
        assert canonical["archive_period"] == 5
        assert canonical["sample_period"] == 30
        assert canonical["calibration"]["inside_temp"] == 2

    @pytest.mark.asyncio
    async def test_does_not_persist_failed_writes_to_canonical(self):
        # Pre-seed canonical at 1; the failed write should NOT overwrite it.
        LoggerDaemon._save_canonical_wl_config({"archive_period": 1})
        d = _daemon(arc=1, sample=248)
        link = _mock_link()
        link.connected = True
        link.async_set_archive_period = AsyncMock(return_value=False)
        d.driver = link

        class _ForceLinkDaemon(LoggerDaemon):
            @property
            def _link(self):
                return link

        d.__class__ = _ForceLinkDaemon

        result = await d._h_write_config({"archive_period": 5})

        assert result["results"]["archive_period"] == "failed"
        canonical = LoggerDaemon._load_canonical_wl_config()
        # Still 1 — the failed write didn't poison the source of truth.
        assert canonical == {"archive_period": 1}

    @pytest.mark.asyncio
    async def test_mixed_results_preserves_independent_canonical_fields(self):
        """archive_period write succeeds, calibration write fails.  The
        canonical row must reflect the NEW archive_period and the PREVIOUS
        calibration — partial successes don't poison the unchanged side, and
        partial failures don't roll back the changed side.  Codex round-1
        review on PR #148 specifically called out the lack of this case.
        """
        # Pre-seed canonical with a baseline calibration we want preserved.
        prior_cal = {
            "inside_temp": 7, "outside_temp": 3, "barometer": 0,
            "outside_humidity": 0, "rain_cal": 100,
        }
        LoggerDaemon._save_canonical_wl_config({
            "archive_period": 1,
            "sample_period": 248,
            "calibration": prior_cal,
        })
        d = _daemon(arc=1, sample=248)
        link = _mock_link()
        link.connected = True
        # Calibration write rejects at ACK.
        link.async_write_calibration = AsyncMock(return_value=False)
        d.driver = link

        class _ForceLinkDaemon(LoggerDaemon):
            @property
            def _link(self):
                return link

        d.__class__ = _ForceLinkDaemon

        result = await d._h_write_config({
            "archive_period": 5,
            "calibration": {
                "inside_temp": 99, "outside_temp": 99, "barometer": 99,
                "outside_humidity": 99, "rain_cal": 99,
            },
        })

        assert result["results"]["archive_period"] == "ok"
        assert result["results"]["calibration"] == "failed"
        canonical = LoggerDaemon._load_canonical_wl_config()
        # New archive_period landed.
        assert canonical["archive_period"] == 5
        # Sample period untouched (not in the request).
        assert canonical["sample_period"] == 248
        # Previous calibration preserved — failed write didn't replace it.
        assert canonical["calibration"] == prior_cal


class TestReadBackVerification:
    """Codex round-1 review on PR #148 flagged that SAP/SSP/WWR-cal "success"
    was ACK-only — a link that ACKs without persisting the change would let
    self-cache and canonical drift away from the link's actual state.  The
    fix routes every successful write through a read-back; cache + canonical
    only land the read-back value, and a mismatch downgrades the result to
    "failed".  These tests pin the read-back-mismatch behavior."""

    @pytest.mark.asyncio
    async def test_reconcile_does_not_update_cache_when_readback_mismatches(self):
        LoggerDaemon._save_canonical_wl_config({
            "archive_period": 1, "sample_period": 248,
        })
        d = _daemon(arc=51, sample=248)
        link = _mock_link()
        # SAP ACKs but the readback still returns the old value (the pathology
        # the read-back verification is designed to catch).
        link.async_set_archive_period = AsyncMock(return_value=True)
        link.async_read_archive_period = AsyncMock(return_value=51)

        await d._reconcile_wl_settings(link)

        # Daemon cache reflects the readback (link's actual state), not the
        # canonical value we attempted to write.
        assert d._archive_period == 51

    @pytest.mark.asyncio
    async def test_h_write_config_marks_failed_on_readback_mismatch(self):
        d = _daemon(arc=1, sample=248)
        link = _mock_link()
        link.connected = True
        # SAP ACKs but readback returns a different value.
        link.async_set_archive_period = AsyncMock(return_value=True)
        link.async_read_archive_period = AsyncMock(return_value=1)  # stuck at old
        d.driver = link

        class _ForceLinkDaemon(LoggerDaemon):
            @property
            def _link(self):
                return link

        d.__class__ = _ForceLinkDaemon

        result = await d._h_write_config({"archive_period": 5})

        # Result is "failed" — the ACK was a lie.
        assert result["results"]["archive_period"] == "failed"
        # Canonical row is NOT updated to 5; it stays unset (we didn't pre-seed).
        canonical = LoggerDaemon._load_canonical_wl_config()
        assert canonical is None
        # Daemon cache reflects the readback (link's actual state).
        assert d._archive_period == 1
