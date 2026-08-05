#!/usr/bin/env python3
"""Weather station data logger daemon.

Owns the station connection, polls sensors via the StationDriver interface,
writes to the database, and exposes an IPC server so the web application
can query status and send hardware commands.

Start:  python logger_main.py
Stop:   Ctrl-C or SIGTERM
"""

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

# Ensure the backend package is importable when running from the backend/ dir
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import settings
from app.logging_setup import configure_logging
from app.models.database import init_database, SessionLocal, engine
from app.models.station_config import StationConfigModel
from app.protocol.base import (
    StationDriver,
    CAP_ARCHIVE_PERIOD_RW,
    CAP_SAMPLE_PERIOD_RW,
    CAP_CALIBRATION_RW,
    CAP_BAROMETER_CAL,
)
from app.protocol.link_driver import LinkDriver, CalibrationOffsets, _rain_register_to_mm
from app.protocol.serial_port import list_serial_ports
from app.protocol.constants import STATION_NAMES, DAVIS_LEGAL_ARCHIVE_PERIODS
from app.services.poller import Poller
from app.services.archive_sync import async_sync_archive
from app.ipc.server import IPCServer
from app.ipc import protocol as ipc
from app.services.wunderground import WundergroundUploader
from app.services.cwop import CwopUploader

logger = logging.getLogger("davis.logger")


# --------------- Driver Factory ---------------

# Persisted in sensor_readings.station_type for drivers that have no numeric
# model code of their own (IP/cloud drivers, or a driver whose detection
# failed).  Deliberately outside both StationModel (0-15) and VantageModel
# (16-17) so it can never be mistaken for a real station.
STATION_TYPE_UNKNOWN = -1


def _driver_model_code(driver: StationDriver) -> int:
    """Numeric model code to persist alongside each reading.

    Serial drivers expose a station type they detected from the hardware;
    everything else has no meaningful code.  Return STATION_TYPE_UNKNOWN
    rather than 0 in that case — 0 is Weather Wizard III, so defaulting to
    it makes an unknown station claim to be a specific real one (#215).
    """
    hw = getattr(driver, "hw_config", None)
    model = getattr(hw, "station_type", None) if hw is not None else None
    value = getattr(model, "value", None)
    if isinstance(value, int):
        return value
    return STATION_TYPE_UNKNOWN


def _create_driver(driver_type: str, config: dict) -> StationDriver:
    """Create a StationDriver instance based on config.

    Args:
        driver_type: One of: legacy, vantage, weatherlink_ip,
            weatherlink_live, ecowitt, tempest, ambient.
        config: Effective station config dict.
    """
    port = str(config.get("serial_port", settings.serial_port))
    baud = int(config.get("baud_rate", settings.baud_rate))
    timeout = float(config.get("serial_timeout", settings.serial_timeout))

    if driver_type == "legacy":
        return LinkDriver(port=port, baud_rate=baud, timeout=timeout)

    elif driver_type == "vantage":
        from app.protocol.vantage.driver import VantageDriver
        return VantageDriver(port=port, baud_rate=baud)

    elif driver_type == "weatherlink_ip":
        from app.protocol.weatherlink_ip.driver import WeatherLinkIPDriver
        ip = str(config.get("weatherlink_ip", ""))
        wl_port = int(config.get("weatherlink_port", 22222))
        if not ip:
            raise ValueError("weatherlink_ip is required for WeatherLink IP driver")
        return WeatherLinkIPDriver(ip=ip, port=wl_port)

    elif driver_type == "weatherlink_live":
        from app.protocol.weatherlink_live.driver import WeatherLinkLiveDriver
        ip = str(config.get("weatherlink_ip", ""))
        if not ip:
            raise ValueError("weatherlink_ip is required for WeatherLink Live driver")
        return WeatherLinkLiveDriver(ip=ip)

    elif driver_type == "ecowitt":
        from app.protocol.ecowitt.driver import EcowittDriver
        ip = str(config.get("ecowitt_ip", ""))
        if not ip:
            raise ValueError("ecowitt_ip is required for Ecowitt driver")
        return EcowittDriver(ip=ip)

    elif driver_type == "tempest":
        from app.protocol.tempest.driver import TempestDriver
        hub_sn = str(config.get("tempest_hub_sn", ""))
        elevation_ft = float(config.get("elevation", 0))
        tz = str(config.get("station_timezone", ""))
        return TempestDriver(hub_sn=hub_sn, elevation_ft=elevation_ft, timezone_name=tz)

    elif driver_type == "ambient":
        from app.protocol.ambient.driver import AmbientDriver
        listen_port = int(config.get("ambient_listen_port", 8080))
        return AmbientDriver(port=listen_port)

    raise ValueError(f"Unknown driver type: {driver_type!r}")


# --------------- Logger Daemon ---------------


class LoggerDaemon:
    """Main logger daemon — station owner, poller, IPC server."""

    def __init__(self) -> None:
        self.driver: Optional[StationDriver] = None
        self.poller: Optional[Poller] = None
        self.poller_task: Optional[asyncio.Task] = None
        self._midnight_task: Optional[asyncio.Task] = None
        self.ipc_server: Optional[IPCServer] = None
        self.state_file = Path(settings.db_path).parent / ".logger_state.json"
        # Cached hardware config (read at connect, updated on write)
        self._archive_period: Optional[int] = None
        self._sample_period: Optional[int] = None
        self.wu_uploader = WundergroundUploader()
        self.cwop_uploader = CwopUploader()

    # ---- helpers for LinkDriver-specific operations ----

    @property
    def _link(self) -> Optional[LinkDriver]:
        """Return the driver as LinkDriver if it is one, else None."""
        return self.driver if isinstance(self.driver, LinkDriver) else None

    # ---- public entry point ----

    async def run(self) -> None:
        """Initialise and run until SIGTERM / SIGINT."""
        init_database()

        self.ipc_server = IPCServer(settings.ipc_port)
        self._register_handlers()
        await self.ipc_server.start()

        if self._is_setup_complete():
            port, baud = self._get_serial_config()
            try:
                await self._connect(port, baud)
            except Exception as exc:
                logger.error("Auto-connect failed: %s", exc)
        else:
            logger.info("Setup not complete — waiting for connect command via IPC")

        # Wait for shutdown signal
        stop_event = asyncio.Event()
        loop = asyncio.get_event_loop()
        if sys.platform != "win32":
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, stop_event.set)
        else:
            # Windows: signal handlers work differently
            signal.signal(signal.SIGINT, lambda *_: stop_event.set())
            signal.signal(signal.SIGTERM, lambda *_: stop_event.set())

        logger.info("Logger daemon ready (IPC port %d)", settings.ipc_port)
        await stop_event.wait()
        await self.shutdown()

    async def shutdown(self) -> None:
        logger.info("Shutting down logger daemon...")
        await self._teardown_driver()
        if self.ipc_server:
            await self.ipc_server.stop()
        logger.info("Logger daemon stopped")
        # Exit directly — asyncio.run() cleanup hangs on executor threads
        logging.shutdown()
        os._exit(0)

    # ---- connection lifecycle ----

    async def _connect(self, port: str, baud: int) -> None:
        """Create driver, connect, sync hardware, start poller."""
        config = self._get_effective_config()
        driver_type = str(config.get("station_driver_type", "legacy"))
        logger.info("Connecting (driver: %s)...", driver_type)

        self.driver = _create_driver(driver_type, config)
        await self.driver.connect()
        logger.info("Station: %s", self.driver.station_name)

        # LinkDriver-specific post-connect: cache hardware config, clock sync, archive sync
        link = self._link
        # Default to the driver's own model code where it has one.  This used
        # to be a bare `= 0`, only overwritten inside the `link is not None`
        # branch below — i.e. only for legacy stations.  Vantage stations
        # therefore persisted station_type=0, which is a *valid* legacy enum
        # member (Weather Wizard III), so /api/current reported a
        # confidently wrong model rather than an unknown one (#215).
        station_type_code = _driver_model_code(self.driver)
        if link is not None:
            self._archive_period = await link.async_read_archive_period()
            self._sample_period = await link.async_read_sample_period()
            logger.info("Archive period: %s min, Sample period: %s sec",
                         self._archive_period, self._sample_period)

            # Reconcile the link's actual registers against the canonical row
            # in station_config (issue #147).  Must run before clock sync /
            # archive sync so they operate on the canonical archive_period.
            try:
                await self._reconcile_wl_settings(link)
            except Exception as exc:
                logger.warning(
                    "WeatherLink settings reconciliation failed: %s "
                    "(continuing with link's reported values)",
                    exc,
                )

            # Sync station clock to system time
            now = datetime.now()
            if await link.async_write_station_time(now):
                logger.info("Station clock synced to %s", now.strftime("%H:%M:%S"))
            else:
                logger.warning("Failed to sync station clock")

            # Archive sync in background (shares _io_lock with poller)
            asyncio.create_task(self._bg_archive_sync())

            station_type_code = link.station_model.value if link.station_model else 0

        poll_interval = int(config.get("poll_interval", settings.poll_interval_sec))
        self.poller = Poller(
            self.driver,
            poll_interval=poll_interval,
            station_type_code=station_type_code,
        )
        self.wu_uploader.reload_config()
        self.cwop_uploader.reload_config()

        async def _broadcast_and_upload(msg: dict) -> None:
            await self.ipc_server.broadcast_to_subscribers(msg)
            if msg.get("type") == "sensor_update":
                await self.wu_uploader.maybe_upload(msg["data"])
                await self.cwop_uploader.maybe_upload(msg["data"])

        self.poller.set_broadcast_callback(_broadcast_and_upload)

        # Restore rain state from a previous run
        self._restore_rain_state()

        self.poller_task = asyncio.create_task(self.poller.run())
        logger.info("Poller started (%ds interval)", poll_interval)

        self._midnight_task = asyncio.create_task(self._midnight_rain_reset_loop())

    async def _teardown_driver(self) -> None:
        if self._midnight_task:
            self._midnight_task.cancel()
            self._midnight_task = None
        if self.poller:
            self._save_rain_state()
            self.poller.stop()
        if self.poller_task:
            self.poller_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self.poller_task), timeout=6.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
        if self.driver:
            try:
                await self.driver.disconnect()
            except Exception:
                pass
        self.driver = None
        self.poller = None
        self.poller_task = None

    async def _bg_archive_sync(self) -> None:
        link = self._link
        if link is None:
            return
        try:
            n = await async_sync_archive(link)
            logger.info("Archive sync: %d new records", n)
        except Exception as exc:
            logger.warning("Archive sync failed: %s", exc)

    # ---- rain state persistence ----

    def _save_rain_state(self) -> None:
        if self.poller is None:
            return
        state = {
            "last_rain_daily": self.poller._last_rain_daily,
            "last_rain_tip_time": (
                self.poller._last_rain_tip_time.isoformat()
                if self.poller._last_rain_tip_time else None
            ),
            "rain_rate_in_per_hr": self.poller._rain_rate_in_per_hr,
        }
        try:
            self.state_file.write_text(json.dumps(state))
            logger.info("Rain state saved to %s", self.state_file)
        except Exception as exc:
            logger.warning("Failed to save rain state: %s", exc)

    def _restore_rain_state(self) -> None:
        if self.poller is None:
            return
        # Load rain_yesterday from persistent config
        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
            if row:
                self.poller.rain_yesterday = float(row.value)
        except Exception:
            pass
        finally:
            db.close()

        if not self.state_file.exists():
            return
        try:
            state = json.loads(self.state_file.read_text())
            # Support both old format (last_rain_total int) and new (last_rain_daily float)
            if "last_rain_daily" in state:
                self.poller._last_rain_daily = state["last_rain_daily"]
            elif "last_rain_total" in state and state["last_rain_total"] is not None:
                # Migrate from old click-based format to inches
                self.poller._last_rain_daily = state["last_rain_total"] * 0.01
            tip = state.get("last_rain_tip_time")
            if tip:
                self.poller._last_rain_tip_time = datetime.fromisoformat(tip)
            self.poller._rain_rate_in_per_hr = state.get("rain_rate_in_per_hr", 0.0)
            logger.info("Restored rain state from %s", self.state_file)
        except Exception as exc:
            logger.warning("Failed to restore rain state: %s", exc)

    # ---- config helpers ----

    # Key in station_config holding the user's canonical WeatherLink settings.
    # The link processor's actual registers are reconciled against this row at
    # every connect (see _reconcile_wl_settings).  When this row is missing
    # (first run after the feature lands), the daemon seeds it from whatever
    # the link is currently reporting — the user's existing setup becomes the
    # baseline without any explicit action.
    _CANONICAL_KEY = "weatherlink_canonical"

    @staticmethod
    def _load_canonical_wl_config() -> Optional[dict]:
        """Return the canonical WeatherLink settings dict, or None if unset."""
        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(
                key=LoggerDaemon._CANONICAL_KEY,
            ).first()
            if row is None or not row.value:
                return None
            try:
                return json.loads(row.value)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "Canonical WL config row is unparseable, treating as missing: %s",
                    exc,
                )
                return None
        finally:
            db.close()

    @staticmethod
    def _save_canonical_wl_config(values: dict) -> None:
        """Upsert the canonical WeatherLink settings row."""
        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(
                key=LoggerDaemon._CANONICAL_KEY,
            ).first()
            payload = json.dumps(values)
            if row is None:
                db.add(StationConfigModel(
                    key=LoggerDaemon._CANONICAL_KEY,
                    value=payload,
                ))
            else:
                row.value = payload
            db.commit()
        finally:
            db.close()

    # Marker recording that the legacy-link-period bank-typo migration has
    # run.  See _migrate_legacy_link_period_v1 below and issue #174.
    #
    # Versioned: v1 (PR #175) only repaired the canonical row.  v2 (PR #176)
    # also repairs archive_records.archive_interval rows poisoned by the
    # same bug.  An install carrying the v1 marker must still run the v2
    # migration to get the records repair, so the key string is bumped to
    # force a re-run; the v1 marker row, if present, is harmless.
    _LEGACY_LINK_PERIOD_MIGRATION_KEY = "legacy_link_period_migration_v2"

    def _migrate_legacy_link_period_v1(self) -> None:
        """One-time migration: repair canonical.archive_period AND the
        archive_records.archive_interval rows poisoned by the bank typo.

        Issue #174 fixed a memory_map.py bank typo that made
        read_archive_period return a different garbage byte on every
        call for every legacy Davis station (Monitor/Wizard/Perception/
        GroWeather/Energy/Health).  Garbage seeded the canonical on
        first connect, then got pushed back to the station register on
        every restart via set_archive_period (which used to accept any
        1..120 value).  Each archive_sync batch was tagged with whatever
        garbage byte read_archive_period returned at the start of the
        run, so historical archive_records hold ``archive_interval``
        values like 255, 68, 102, 221 — values that no Davis station
        actually emits.

        Two repairs in one shot:

        1. Canonical row: if ``archive_period`` is outside the Davis-
           legal set, replace it with the freshly-read
           ``self._archive_period`` (correct post-fix).  If the fresh
           read also returned None, defer (no marker, retry next
           restart) so canonical is never left permanently incomplete —
           the reconcile path only re-seeds when the *whole* canonical
           row is missing, not individual fields.
        2. archive_records rows: any row whose ``archive_interval`` is
           not in the Davis-legal set is rewritten to the target value
           (whichever of fresh-read / already-legal-canonical we pulled
           in step 1).  No-op when no bogus rows exist.

        sample_period and calibration are intentionally left alone in
        both steps.
        """
        # Need self._archive_period to be populated by _connect() before
        # this runs; defer otherwise.
        fresh_ap = getattr(self, "_archive_period", None)

        db = SessionLocal()
        try:
            marker = db.query(StationConfigModel).filter_by(
                key=self._LEGACY_LINK_PERIOD_MIGRATION_KEY,
            ).first()
            if marker is not None and marker.value:
                return  # already migrated

            # --- Step 1: canonical row ---
            row = db.query(StationConfigModel).filter_by(
                key=self._CANONICAL_KEY,
            ).first()
            canonical_outcome: str = "no-canonical"
            # The repair target for archive_records.archive_interval —
            # whichever value the daemon will end up reconciling against
            # the station.  Starts at fresh_ap and is overridden below if
            # canonical already holds a legal value.
            target_ap: Optional[int] = fresh_ap
            if row is not None and row.value:
                try:
                    canonical = json.loads(row.value)
                except (json.JSONDecodeError, ValueError):
                    canonical = None
                if canonical is not None:
                    ap = canonical.get("archive_period")
                    if ap is not None and ap not in DAVIS_LEGAL_ARCHIVE_PERIODS:
                        if fresh_ap is None:
                            # Post-fix read still failing — leave canonical
                            # as-is and retry on the next restart.  Do NOT
                            # set the marker.
                            logger.warning(
                                "legacy-link-period migration: canonical "
                                "archive_period=%s is bogus but the fresh "
                                "register read also failed; deferring "
                                "migration until next restart (issue #174)",
                                ap,
                            )
                            return
                        canonical["archive_period"] = fresh_ap
                        row.value = json.dumps(canonical)
                        logger.info(
                            "legacy-link-period migration: replaced bogus "
                            "canonical archive_period=%s with %s "
                            "(issue #174)",
                            ap, fresh_ap,
                        )
                        canonical_outcome = f"replaced:{ap}->{fresh_ap}"
                    else:
                        canonical_outcome = "valid"
                        if ap in DAVIS_LEGAL_ARCHIVE_PERIODS:
                            # Prefer the already-legal canonical value
                            # over fresh_ap when both exist — that's
                            # what the reconciler will push to the
                            # station register, so historical rows
                            # should match.
                            target_ap = ap

            # --- Step 2: archive_records rows ---
            records_outcome = "records-clean"
            if target_ap is not None:
                # Late import to keep the existing import surface small;
                # the model lives in app.models and isn't needed
                # elsewhere in this file.
                from app.models.archive_record import ArchiveRecordModel
                bogus_filter = (
                    ArchiveRecordModel.archive_interval.isnot(None),
                    ArchiveRecordModel.archive_interval.notin_(
                        DAVIS_LEGAL_ARCHIVE_PERIODS
                    ),
                )
                bogus_count = db.query(ArchiveRecordModel).filter(*bogus_filter).count()
                if bogus_count > 0:
                    updated = db.query(ArchiveRecordModel).filter(*bogus_filter).update(
                        {ArchiveRecordModel.archive_interval: target_ap},
                        synchronize_session=False,
                    )
                    logger.info(
                        "legacy-link-period migration: repaired %d "
                        "archive_records rows (archive_interval -> %s) "
                        "(issue #174)",
                        updated, target_ap,
                    )
                    records_outcome = f"records-repaired:{updated}->{target_ap}"

            outcome = f"{canonical_outcome};{records_outcome}"
            if marker is None:
                db.add(StationConfigModel(
                    key=self._LEGACY_LINK_PERIOD_MIGRATION_KEY,
                    value=outcome,
                ))
            else:
                marker.value = outcome
            db.commit()
        finally:
            db.close()

    # Marker recording that the bar_cal-sign migration has run.  See
    # _migrate_bar_cal_sign_v1 below and issue #154.
    _BAR_CAL_SIGN_MIGRATION_KEY = "bar_cal_sign_migration_v1"

    def _migrate_bar_cal_sign_v1(self) -> None:
        """One-time migration: flip the sign of the canonical row's
        barometer calibration entry.

        Issue #154 changed kanfei's in-memory barometer cal sign from
        "subtract from raw" (Davis BAR_CAL register convention) to
        "add to raw" (user-facing convention).  Existing users who
        calibrated via the UI before that fix have their canonical
        station_config row storing the *old* sign — typically the
        negated value they had to enter as a workaround for the sign-
        inversion bug.

        If we just shipped the link_driver.py negate-on-I/O change
        without migrating the canonical row, the first post-fix
        reconcile would see canonical (old sign) ≠ link cal (new sign)
        and force-write the canonical's negated value back through the
        new negate-on-write path, putting the register at the opposite
        of where the user wanted it.  That would silently break every
        working barometer calibration.

        This runs at the top of _reconcile_wl_settings before any
        compare/write, idempotent via a station_config marker.
        """
        db = SessionLocal()
        try:
            marker = db.query(StationConfigModel).filter_by(
                key=self._BAR_CAL_SIGN_MIGRATION_KEY,
            ).first()
            if marker is not None and marker.value:
                return  # already migrated

            row = db.query(StationConfigModel).filter_by(
                key=self._CANONICAL_KEY,
            ).first()
            if row is not None and row.value:
                try:
                    canonical = json.loads(row.value)
                except (json.JSONDecodeError, ValueError):
                    canonical = None
                if canonical is not None:
                    cal = canonical.get("calibration") or {}
                    if "barometer" in cal and cal["barometer"] != 0:
                        old = int(cal["barometer"])
                        cal["barometer"] = -old
                        canonical["calibration"] = cal
                        row.value = json.dumps(canonical)
                        logger.info(
                            "bar_cal sign migration: canonical barometer "
                            "%d -> %d (issue #154)",
                            old, -old,
                        )

            # Record outcome regardless — once we've passed this check,
            # future restarts skip it.  The value field records whether
            # we flipped anything for audit.
            outcome = "flipped" if (
                row is not None and row.value
            ) else "no-canonical"
            if marker is None:
                db.add(StationConfigModel(
                    key=self._BAR_CAL_SIGN_MIGRATION_KEY,
                    value=outcome,
                ))
            else:
                marker.value = outcome
            db.commit()
        finally:
            db.close()

    async def _reconcile_wl_settings(self, link: LinkDriver) -> None:
        """Force the link's settings to match the canonical row in station_config.

        Drift between the user's intent (recorded in station_config when they
        Save via the UI) and the link's actual registers is the bug shape from
        issue #147.  Without active reconciliation, the link can sit on a
        different value indefinitely — e.g. the link's ArcPeriod register
        showing 51 minutes while the user's saved canonical value is 1.

        First run: no canonical row exists.  Seed it from the link's current
        values so the user's existing setup becomes the baseline.

        Subsequent runs: compare each field.  Mismatches get pushed to the
        link via SAP/SSP/WWR-cal.  A failed write is logged but is not fatal;
        the daemon's cached values fall back to the link's actual state.
        """
        # One-time migration of the canonical row's archive_period field
        # to drop legacy bank-typo garbage.  See _migrate_legacy_link_period_v1
        # docstring and issue #174.
        self._migrate_legacy_link_period_v1()

        # One-time migration of the canonical row's barometer cal sign.
        # See _migrate_bar_cal_sign_v1 docstring and issue #154.  This
        # MUST run before _load_canonical_wl_config below so the post-
        # migration value is what gets compared against the link cal.
        self._migrate_bar_cal_sign_v1()

        canonical = self._load_canonical_wl_config()
        link_cal = link.calibration
        link_state = {
            "archive_period": self._archive_period,
            "sample_period": self._sample_period,
            "calibration": {
                "inside_temp": link_cal.inside_temp,
                "outside_temp": link_cal.outside_temp,
                "barometer": link_cal.barometer,
                "outside_humidity": link_cal.outside_hum,
                "rain_cal": link_cal.rain_cal,
            },
        }

        if canonical is None:
            self._save_canonical_wl_config(link_state)
            logger.info(
                "Seeded canonical WeatherLink settings from link "
                "(archive_period=%s, sample_period=%s)",
                link_state["archive_period"], link_state["sample_period"],
            )
            return

        # Archive period — write, then read-back to verify the register
        # actually took the new value.  Codex review on PR #148 flagged that
        # SAP ACK alone doesn't guarantee persistence: the link may ACK and
        # then keep the old value, in which case trusting the ACK would put
        # cache != register and silently re-introduce drift.  Trust the
        # readback as the post-write truth.
        target_arc = canonical.get("archive_period")
        if (target_arc is not None
                and self._archive_period is not None
                and target_arc != self._archive_period):
            logger.info(
                "Reconciling archive_period: link reports %s, canonical is %s",
                self._archive_period, target_arc,
            )
            if await link.async_set_archive_period(target_arc):
                actual = await link.async_read_archive_period()
                if actual == target_arc:
                    self._archive_period = actual
                else:
                    logger.warning(
                        "SAP ACKed but link still reports %s after write (wanted %s)",
                        actual, target_arc,
                    )
                    if actual is not None:
                        self._archive_period = actual
            else:
                logger.warning(
                    "SAP failed during reconciliation; leaving link at %s",
                    self._archive_period,
                )

        # Sample period — same read-back discipline.
        target_samp = canonical.get("sample_period")
        if (target_samp is not None
                and self._sample_period is not None
                and target_samp != self._sample_period):
            logger.info(
                "Reconciling sample_period: link reports %s, canonical is %s",
                self._sample_period, target_samp,
            )
            if await link.async_set_sample_period(target_samp):
                actual = await link.async_read_sample_period()
                if actual == target_samp:
                    self._sample_period = actual
                else:
                    logger.warning(
                        "SSP ACKed but link still reports %s after write (wanted %s)",
                        actual, target_samp,
                    )
                    if actual is not None:
                        self._sample_period = actual
            else:
                logger.warning(
                    "SSP failed during reconciliation; leaving link at %s",
                    self._sample_period,
                )

        # Calibration — write_calibration covers all five fields atomically,
        # so a mismatch on any single field triggers a full re-write.  Read
        # back the calibration registers after a successful write to confirm
        # the link actually persisted the values; on mismatch, the readback
        # becomes link.calibration (read_calibration mutates it in place) so
        # the daemon sees the link's real state, not the requested state.
        target_cal = canonical.get("calibration") or {}
        live_cal = link_state["calibration"]
        if target_cal and target_cal != live_cal:
            logger.info(
                "Reconciling calibration: link=%s, canonical=%s",
                live_cal, target_cal,
            )
            offsets = CalibrationOffsets(
                inside_temp=int(target_cal.get("inside_temp", live_cal["inside_temp"])),
                outside_temp=int(target_cal.get("outside_temp", live_cal["outside_temp"])),
                barometer=int(target_cal.get("barometer", live_cal["barometer"])),
                outside_hum=int(target_cal.get("outside_humidity", live_cal["outside_humidity"])),
                rain_cal=int(target_cal.get("rain_cal", live_cal["rain_cal"])),
            )
            if await link.async_write_calibration(offsets):
                fresh = await link.async_read_calibration()
                if fresh != offsets:
                    logger.warning(
                        "WWR-cal ACKed but readback differs: wanted=%s, got=%s",
                        offsets, fresh,
                    )
            else:
                logger.warning(
                    "WWR-cal failed during reconciliation; leaving link calibration unchanged",
                )

    @staticmethod
    def _is_setup_complete() -> bool:
        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="setup_complete").first()
            return row is not None and row.value == "true"
        finally:
            db.close()

    @staticmethod
    def _get_serial_config() -> tuple[str, int]:
        db = SessionLocal()
        try:
            from app.api.config import get_effective_config
            cfg = get_effective_config(db)
            return str(cfg.get("serial_port", settings.serial_port)), int(cfg.get("baud_rate", settings.baud_rate))
        finally:
            db.close()

    @staticmethod
    def _get_effective_config() -> dict:
        """Get the full effective config (DB values merged with defaults)."""
        db = SessionLocal()
        try:
            from app.api.config import get_effective_config
            return get_effective_config(db)
        finally:
            db.close()

    @staticmethod
    def _get_driver_type() -> str:
        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="station_driver_type").first()
            return row.value if row else "legacy"
        finally:
            db.close()

    # ---- midnight rain reset ----

    def _get_station_timezone(self):
        """Return the station's timezone as a ZoneInfo, falling back to system local."""
        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="station_timezone").first()
            if row and row.value:
                return ZoneInfo(row.value)
        except Exception:
            pass
        finally:
            db.close()
        # Fall back to system local timezone
        return datetime.now().astimezone().tzinfo

    async def _midnight_rain_reset_loop(self) -> None:
        """At station-local midnight, save daily rain as yesterday and clear."""
        while True:
            tz = self._get_station_timezone()
            now = datetime.now(tz)
            next_midnight = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0,
            )
            wait_seconds = (next_midnight - now).total_seconds()
            logger.info(
                "Midnight rain reset scheduled in %.0f seconds (%s)",
                wait_seconds, next_midnight.strftime("%Y-%m-%d %H:%M %Z"),
            )

            try:
                await asyncio.sleep(wait_seconds)
            except asyncio.CancelledError:
                break

            await self._do_midnight_rain_reset()

    async def _do_midnight_rain_reset(self) -> None:
        """Save today's daily rain as yesterday, then clear the station counter.

        Order matters: clear hardware BEFORE persisting yesterday.  If the
        clear fails, leave both the in-config ``rain_yesterday`` row and the
        poller's cached value untouched — otherwise the next midnight reads
        an un-cleared station counter (today's total + tomorrow's rainfall)
        and rolls that pile into ``rain_yesterday``, double-counting today's
        rain.  Driver-agnostic rollover (Tempest et al.) is tracked in #171;
        for now this method is a no-op on any non-``LinkDriver`` driver.
        """
        driver = self.driver
        link = self._link
        if link is None:
            # Non-Davis driver: midnight rollover for these drivers is tracked
            # in #171.  Log at debug so we don't spam WARN every night on
            # healthy Tempest / Ambient / etc. installs.
            if driver is not None:
                logger.debug(
                    "Midnight rain reset: skipping for non-LinkDriver driver %s",
                    type(driver).__name__,
                )
            return
        if not link.connected:
            logger.warning("Midnight rain reset skipped — station not connected")
            return

        # Read current daily rain (direct memory read for accuracy).
        # Convert via the same helper used by the poller (#149) so non-default
        # rain_cal stations record the correct yesterday value: inches =
        # clicks / rain_cal, derived from the mm form returned by the helper.
        try:
            daily_clicks = await link.async_read_rain_daily()
            mm = _rain_register_to_mm(daily_clicks, link.calibration.rain_cal)
            daily_inches = round(mm / 25.4, 2) if mm else 0.0
        except Exception as exc:
            logger.warning("Midnight rain reset: read failed (%s) — skipping", exc)
            return

        # Clear station hardware FIRST.  Only persist yesterday after the
        # hardware clear succeeds; otherwise tomorrow's midnight will read
        # an un-cleared counter and double-count.
        try:
            ok = await link.async_clear_rain_daily()
        except Exception as exc:
            logger.warning("Midnight rain reset: hardware clear raised (%s) — yesterday NOT updated", exc)
            return
        if not ok:
            logger.warning("Midnight rain reset: hardware clear failed — yesterday NOT updated")
            return

        # Hardware clear succeeded — safe to commit yesterday now.
        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
            if row:
                row.value = str(daily_inches)
            else:
                db.add(StationConfigModel(
                    key="rain_yesterday",
                    value=str(daily_inches),
                    updated_at=datetime.now(timezone.utc),
                ))
            db.commit()
        except Exception as exc:
            logger.warning("Failed to save rain_yesterday: %s", exc)
        finally:
            db.close()

        if self.poller:
            self.poller.rain_yesterday = daily_inches

        await self._refresh_after_rain_clear()
        logger.info(
            "Midnight rain reset: yesterday=%.2f in, daily cleared", daily_inches,
        )

    # ---- IPC handler registration ----

    def _register_handlers(self) -> None:
        h = self.ipc_server.register_handler
        h(ipc.CMD_STATUS, self._h_status)
        h(ipc.CMD_PROBE, self._h_probe)
        h(ipc.CMD_AUTO_DETECT, self._h_auto_detect)
        h(ipc.CMD_CONNECT, self._h_connect)
        h(ipc.CMD_RECONNECT, self._h_reconnect)
        h(ipc.CMD_READ_STATION_TIME, self._h_read_station_time)
        h(ipc.CMD_SYNC_STATION_TIME, self._h_sync_station_time)
        h(ipc.CMD_READ_CONFIG, self._h_read_config)
        h(ipc.CMD_WRITE_CONFIG, self._h_write_config)
        h(ipc.CMD_CLEAR_RAIN_DAILY, self._h_clear_rain_daily)
        h(ipc.CMD_CLEAR_RAIN_YEARLY, self._h_clear_rain_yearly)
        h(ipc.CMD_FORCE_ARCHIVE, self._h_force_archive)
        h(ipc.CMD_BAROMETER_CAL, self._h_barometer_cal)
        h(ipc.CMD_SET_BAROMETER, self._h_set_barometer)
        h(ipc.CMD_SIGNAL_QUALITY, self._h_signal_quality)
        h(ipc.CMD_READ_VANTAGE_CAL, self._h_read_vantage_cal)
        h(ipc.CMD_WRITE_VANTAGE_CAL, self._h_write_vantage_cal)
        h(ipc.CMD_CLEAR_VANTAGE_CAL, self._h_clear_vantage_cal)

    # ---- IPC handlers ----

    async def _h_status(self, _msg: dict) -> dict[str, Any]:
        connected = self.driver.connected if self.driver else False
        stats = self.poller.stats if self.poller else {}
        link = self._link
        return {
            "connected": connected,
            "type_code": link.station_model.value if link and link.station_model else -1,
            "type_name": self.driver.station_name if self.driver else "Not connected",
            "link_revision": ("E" if link.is_rev_e else "D") if link else "unknown",
            "poll_interval": self.poller.poll_interval if self.poller else 0,
            **stats,
        }

    async def _h_probe(self, msg: dict) -> dict[str, Any]:
        port, baud = msg["port"], msg["baud"]

        # If we're already connected to this port, return current info
        link = self._link
        if (link and link.connected
                and link.serial and link.serial.port == port):
            return {
                "success": True,
                "station_type": link.station_name,
                "station_code": link.station_model.value if link.station_model else None,
                "driver_type": "legacy",
            }

        tmp = LinkDriver(port=port, baud_rate=baud, timeout=3.0)
        tmp.open()
        try:
            station = await tmp.async_detect_station_type()
            return {
                "success": True,
                "station_type": STATION_NAMES.get(station, "Unknown"),
                "station_code": station.value,
                "driver_type": "legacy",
            }
        finally:
            tmp.close()

    async def _h_auto_detect(self, _msg: dict) -> dict[str, Any]:
        # Already connected? Return immediately
        link = self._link
        if link and link.connected and link.station_model:
            return {
                "found": True,
                "port": link.serial.port,
                "baud_rate": link.serial.baud_rate,
                "station_type": link.station_name,
                "station_code": link.station_model.value,
                "driver_type": "legacy",
                "attempts": [],
            }

        ports = list_serial_ports()
        attempts: list[dict] = []
        for port in ports:
            for baud in (2400, 1200):
                try:
                    tmp = LinkDriver(port=port, baud_rate=baud, timeout=3.0)
                    tmp.open()
                    try:
                        station = await tmp.async_detect_station_type()
                        attempts.append({"port": port, "baud": baud, "result": "found"})
                        return {
                            "found": True,
                            "port": port,
                            "baud_rate": baud,
                            "station_type": STATION_NAMES.get(station, "Unknown"),
                            "station_code": station.value,
                            "driver_type": "legacy",
                            "attempts": attempts,
                        }
                    finally:
                        tmp.close()
                except Exception as exc:
                    attempts.append({"port": port, "baud": baud, "error": str(exc)})

        return {"found": False, "attempts": attempts}

    async def _h_connect(self, msg: dict) -> dict[str, Any]:
        await self._teardown_driver()
        await self._connect(msg["port"], msg["baud"])
        return {
            "success": True,
            "station_type": self.driver.station_name if self.driver else "Unknown",
        }

    async def _h_reconnect(self, _msg: dict) -> dict[str, Any]:
        port, baud = self._get_serial_config()
        await self._teardown_driver()
        await self._connect(port, baud)
        return {
            "success": True,
            "station_type": self.driver.station_name if self.driver else "Unknown",
        }

    async def _h_read_station_time(self, _msg: dict) -> Any:
        # Same fix as the config handlers (#219): this used to require a
        # LinkDriver, so the dashboard's station-clock tile was empty on
        # Vantage stations even though VantageDriver implements the clock
        # methods.  Ask the driver, not its type.
        drv = self.driver
        if drv is None or not drv.connected:
            raise RuntimeError("Not connected")
        if not hasattr(drv, "async_read_station_time"):
            raise RuntimeError(
                f"{drv.station_name} does not support reading the station clock"
            )
        result = await drv.async_read_station_time()
        if result is None:
            logger.warning("read_station_time returned None")
        return result

    def _require_barometer_cal(self) -> StationDriver:
        """Return the driver if it can calibrate its barometer via BAR=.

        Gated on CAP_BAROMETER_CAL rather than driver type.  That
        distinction is load-bearing here in a way it is not for most
        capabilities: legacy stations DO calibrate their barometer, but
        by a direct BAR_CAL register write with subtract semantics.  A
        type check that let one through would not merely fail — it would
        write an offset with the wrong sign and double the error.
        """
        drv = self.driver
        if drv is None or not drv.connected:
            raise RuntimeError("Not connected")
        if CAP_BAROMETER_CAL not in drv.capabilities:
            raise RuntimeError(
                f"{drv.station_name} does not support barometer calibration"
            )
        return drv

    async def _h_barometer_cal(self, _msg: dict) -> dict[str, Any]:
        """Current barometer calibration state, via BARDATA."""
        drv = self._require_barometer_cal()
        cal = await drv.async_bardata()
        if cal is None:
            raise RuntimeError("Station did not return barometer calibration")
        return {
            "barometer_inhg": cal.barometer_inhg,
            "elevation_ft": cal.elevation_ft,
            "barcal_inhg": cal.barcal_inhg,
            # Factory sensor constants.  Surfaced for the audit log the
            # procedure asks for, NOT for the user to act on — `offset`
            # in particular is not the field BAR= sets, and confusing the
            # two is the terminology trap in the procedure doc.
            "gain": cal.gain,
            "offset": cal.offset,
        }

    async def _h_set_barometer(self, msg: dict) -> dict[str, Any]:
        """Set barometer calibration and elevation via BAR=.

        Reads BARDATA before and after so the caller gets an auditable
        before/after pair from one IPC round trip — the procedure
        requires logging both, and doing it here means the caller cannot
        forget the before-snapshot or take it minutes earlier.

        The whole BARDATA/BAR=/BARDATA sequence runs under one serial
        lock via ``async_calibrate_barometer``.  It used to be three
        separate calls, which let a poll interleave and pushed the round
        trip past the API timeout — the request returned 504 while the
        write had actually succeeded (#257).

        BAR= itself is NOT atomic across its two arguments: a console
        that refuses the pressure value still applies the elevation.
        That is why the failure path reports the after-snapshot rather
        than asserting the station is unchanged.
        """
        drv = self._require_barometer_cal()

        bar = msg.get("bar_thousandths_inhg")
        elevation = msg.get("elevation_ft")
        if bar is None or elevation is None:
            raise RuntimeError(
                "bar_thousandths_inhg and elevation_ft are both required"
            )

        try:
            before, ok, after = await drv.async_calibrate_barometer(
                int(bar), int(elevation)
            )
        except ValueError as exc:
            # Out-of-range values are rejected by the driver before they
            # reach the wire; surface the reason rather than a bare False.
            raise RuntimeError(str(exc)) from exc

        def _snap(cal) -> Optional[dict]:
            if cal is None:
                return None
            return {
                "barometer_inhg": cal.barometer_inhg,
                "elevation_ft": cal.elevation_ft,
                "barcal_inhg": cal.barcal_inhg,
            }

        if not ok:
            # A console NAK must not return normally.  The IPC server
            # wraps any non-raising return as ok:true (server.py:127), so
            # a rejected write would have surfaced as HTTP 200 carrying
            # success:false — a write that did not take looking exactly
            # like one that did.  Raising puts it on the error path,
            # where the API maps it to 503.
            #
            # A rejected BAR= is NOT a no-op: measured on a Vue (fw 3.0),
            # the console refuses the command and applies the elevation
            # argument anyway (BAR=0 400 -> elev 400; BAR=99999 275 ->
            # NAK, elev 275).  So the after-snapshot is the only truthful
            # statement available about the resulting state, and the
            # message must not claim the station was left untouched.
            snap = _snap(after)
            state = (
                f"station now reads: {snap}" if snap is not None
                else "could not re-read the station to confirm its state"
            )
            raise RuntimeError(
                "Station rejected the calibration (BAR= not acknowledged). "
                f"The pressure offset was NOT applied, but elevation may "
                f"have been — {state}"
            )

        return {"success": ok, "before": _snap(before), "after": _snap(after)}

    # ---- Vantage temperature/humidity calibration ----

    # Maps the wire field name to its EEPROM address.  Deliberately a
    # closed set: write_calibration() refuses anything outside the
    # calibration block, but an explicit allowlist means a typo in a
    # request is a clear error rather than an address computed from user
    # input.
    _VANTAGE_CAL_FIELDS = {
        "inside_temp": "CAL_INSIDE_TEMP",
        "outside_temp": "CAL_OUTSIDE_TEMP",
        "inside_humidity": "CAL_INSIDE_HUM",
        "outside_humidity": "CAL_OUTSIDE_HUM",
    }

    def _require_vantage_cal(self) -> StationDriver:
        drv = self.driver
        if drv is None or not drv.connected:
            raise RuntimeError("Not connected")
        if CAP_CALIBRATION_RW not in drv.capabilities:
            raise RuntimeError(
                f"{drv.station_name} does not support calibration offsets"
            )
        # NOT a hasattr check: LinkDriver also has async_read_calibration,
        # but it returns a five-field CalibrationOffsets dataclass in the
        # legacy shape, not the Vantage per-sensor dict.  The two are
        # indistinguishable by attribute presence, which is precisely the
        # trap that made a legacy station look supported here.  Gate on
        # the concrete capability the Vantage driver declares instead.
        if not hasattr(drv, "CALIBRATION_FIELDS"):
            raise RuntimeError(
                f"{drv.station_name} does not support per-sensor "
                "calibration offsets"
            )
        return drv

    async def _h_read_vantage_cal(self, _msg: dict) -> dict[str, Any]:
        """Current temperature/humidity offsets, in the console's units."""
        drv = self._require_vantage_cal()
        offsets = await drv.async_read_calibration()
        if offsets is None:
            raise RuntimeError("Station did not return calibration offsets")
        return {
            "offsets": offsets,
            # Units are not obvious and getting them wrong is a tenfold
            # error: temperature is TENTHS of a degree F.
            "temp_units": "tenths_f",
            "humidity_units": "percent",
        }

    async def _h_write_vantage_cal(self, msg: dict) -> dict[str, Any]:
        """Set one calibration offset, then read every field back.

        One field per call, matching the driver.  The manual's block form
        writes 43 bytes from 0x32, which runs past the calibration block
        and over the graph defaults and alarm thresholds.
        """
        from app.protocol.vantage import eeprom as vantage_eeprom

        drv = self._require_vantage_cal()

        field = msg.get("field")
        offset = msg.get("offset")
        if field is None or offset is None:
            raise RuntimeError("field and offset are both required")
        if field not in self._VANTAGE_CAL_FIELDS:
            # "must be" is what api/station.py::_cal_error routes to 400.
            # An earlier wording here said "unknown calibration field",
            # which matched no rule and surfaced a client error as a 503
            # server fault — the same bug as the offset range message one
            # branch below, which I fixed while leaving this one (Codex,
            # #267 R1).
            raise RuntimeError(
                f"calibration field must be one of "
                + ", ".join(sorted(self._VANTAGE_CAL_FIELDS))
                + f"; got {field!r}"
            )

        addr = getattr(vantage_eeprom, self._VANTAGE_CAL_FIELDS[field])
        before = await drv.async_read_calibration()
        try:
            ok = await drv.async_write_calibration(addr, int(offset))
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        after = await drv.async_read_calibration()

        if not ok:
            # Same rule as the barometer write (#252): a failed write must
            # not return normally, and must not claim nothing changed.
            raise RuntimeError(
                "Station did not accept the calibration; "
                f"offsets now read: {after}"
            )

        return {"success": ok, "before": before, "after": after}

    async def _h_clear_vantage_cal(self, _msg: dict) -> dict[str, Any]:
        """CLRCAL — zero every temperature and humidity offset.

        Note this does NOT touch barometer calibration, which lives
        behind BAR= and has its own panel.  Naming it "clear calibration"
        in the UI without that qualifier would imply more than it does.
        """
        drv = self._require_vantage_cal()
        before = await drv.async_read_calibration()
        ok = await drv.async_clear_calibration()
        after = await drv.async_read_calibration()

        if not ok:
            raise RuntimeError(
                f"Station did not accept CLRCAL; offsets now read: {after}"
            )
        return {"success": ok, "before": before, "after": after}

    async def _h_signal_quality(self, _msg: dict) -> dict[str, Any]:
        """Console reception diagnostics — RXCHECK plus the heard-Tx list.

        This is the diagnostic for the failure that has cost the most time
        on this project: a transmitter dropping out, its dashed sentinel
        being stored as a real reading, and the poisoned daily maximum
        then being published for the rest of the day (#230).  Until now
        the only symptom was the data going strange hours later; these
        counters name the cause while it is happening.

        Gated on the value being reachable rather than on driver type,
        per #220 / #234 — any driver growing an ``async_rxcheck`` gets
        this for free.
        """
        drv = self.driver
        if drv is None or not drv.connected:
            raise RuntimeError("Not connected")
        if not hasattr(drv, "async_rxcheck"):
            raise RuntimeError(
                f"{drv.station_name} does not support reception diagnostics"
            )

        stats = await drv.async_rxcheck()
        if stats is None:
            raise RuntimeError("Station did not return reception diagnostics")

        # RECEIVERS is a separate command and a Vue legitimately answers
        # with an empty list, so a failure here must not sink the whole
        # response — the RXCHECK counters are the load-bearing part.
        receivers: Optional[list[int]] = None
        if hasattr(drv, "async_receivers"):
            try:
                receivers = await drv.async_receivers()
            except Exception as exc:
                logger.warning("RECEIVERS failed (reporting RXCHECK only): %s", exc)

        return {**stats, "receivers": receivers}

    async def _h_sync_station_time(self, _msg: dict) -> dict[str, Any]:
        drv = self.driver
        if drv is None or not drv.connected:
            raise RuntimeError("Not connected")
        if not hasattr(drv, "async_write_station_time"):
            raise RuntimeError(
                f"{drv.station_name} does not support setting the station clock"
            )
        now = datetime.now()
        ok = await drv.async_write_station_time(now)
        return {"success": ok, "synced_to": now.strftime("%H:%M:%S %m/%d/%Y")}

    # Config operations, and the driver methods that implement them.  Used
    # to infer support when a driver has not declared the capability flag.
    _CONFIG_OPS: dict[str, tuple[str, tuple[str, ...]]] = {
        CAP_ARCHIVE_PERIOD_RW: (
            "archive_period",
            ("async_set_archive_period", "async_read_archive_period"),
        ),
        CAP_SAMPLE_PERIOD_RW: (
            "sample_period",
            ("async_set_sample_period", "async_read_sample_period"),
        ),
        CAP_CALIBRATION_RW: (
            "calibration",
            ("async_write_calibration", "async_read_calibration"),
        ),
    }

    def _driver_caps(self) -> set[str]:
        """Config capabilities of the connected driver.

        Prefers the driver's declared `capabilities`, but falls back to
        checking for the implementing methods.  A driver that predates the
        CAP_*_RW constants (or a test double) still works rather than
        having every setting rejected as unsupported.
        """
        drv = self.driver
        if drv is None or not drv.connected:
            return set()

        try:
            declared = set(drv.capabilities)
        except Exception:          # pragma: no cover — defensive
            declared = set()

        caps: set[str] = set()
        for cap, (_field, methods) in self._CONFIG_OPS.items():
            if cap in declared or all(hasattr(drv, m) for m in methods):
                caps.add(cap)
        # Preserve any other declared flags (archive_sync, hilows, ...).
        return caps | {c for c in declared if isinstance(c, str)}

    async def _h_read_config(self, _msg: dict) -> dict[str, Any]:
        """Report the settings this station supports.

        Previously gated on isinstance(driver, LinkDriver), which made the
        whole settings panel dead on Vantage stations (#219).  Now driven by
        declared capabilities, and the response says which fields the
        station actually supports so the UI can hide the rest instead of
        offering controls that do nothing.
        """
        drv = self.driver
        if drv is None or not drv.connected:
            raise RuntimeError("Not connected")

        caps = self._driver_caps()
        link = self._link

        archive_period = None
        if CAP_ARCHIVE_PERIOD_RW in caps:
            archive_period = self._archive_period
            if archive_period is None and hasattr(drv, "async_read_archive_period"):
                archive_period = await drv.async_read_archive_period()

        sample_period = self._sample_period if CAP_SAMPLE_PERIOD_RW in caps else None

        calibration = None
        if CAP_CALIBRATION_RW in caps and link is not None:
            # The calibration block is still LinkDriver-shaped (five legacy
            # fields).  Vantage calibration uses different addresses and a
            # different write procedure (#214), so it is reported as
            # unsupported here rather than mapped onto a shape that does not
            # fit — see "supported" below.
            cal = link.calibration
            calibration = {
                "inside_temp": cal.inside_temp,
                "outside_temp": cal.outside_temp,
                "barometer": cal.barometer,
                "outside_humidity": cal.outside_hum,
                "rain_cal": cal.rain_cal,
            }

        return {
            "archive_period": archive_period,
            "sample_period": sample_period,
            "calibration": calibration,
            "supported": {
                "archive_period": CAP_ARCHIVE_PERIOD_RW in caps,
                "sample_period": CAP_SAMPLE_PERIOD_RW in caps,
                "calibration": calibration is not None,
                # Reported from the capability rather than from a value
                # being non-None like `calibration` above: barometer
                # calibration has no readable block in this response to
                # sniff, and asking the console would cost a serial round
                # trip to answer a question the daemon already holds.
                "barometer_cal": CAP_BAROMETER_CAL in caps,
                # Per-sensor offsets via CALED/CALFIX.  Distinct from
                # "calibration" above, which is the legacy five-field
                # block and is false on a Vantage, and from
                # "barometer_cal", which is BAR= — a different
                # mechanism again.  Three separate things.
                "sensor_calibration": (
                    CAP_CALIBRATION_RW in caps
                    and hasattr(self.driver, "CALIBRATION_FIELDS")
                ),
            },
        }

    async def _h_write_config(self, msg: dict) -> dict[str, Any]:
        drv = self.driver
        if drv is None or not drv.connected:
            raise RuntimeError("Not connected")

        caps = self._driver_caps()
        link = self._link
        results: dict[str, str] = {}

        # Reject up front anything this station cannot do, with a distinct
        # result value.  "unsupported" is not "failed": one means the
        # station has no such setting, the other means the write was tried
        # and did not take.  Collapsing them is how #219 looked like a
        # generic malfunction rather than a missing feature.
        for field, cap in (
            ("archive_period", CAP_ARCHIVE_PERIOD_RW),
            ("sample_period", CAP_SAMPLE_PERIOD_RW),
            ("calibration", CAP_CALIBRATION_RW),
        ):
            if msg.get(field) is not None and cap not in caps:
                results[field] = "unsupported"
                logger.info(
                    "write_config: %s not supported by %s",
                    field, drv.station_name,
                )

        # Calibration additionally needs the legacy register layout; the
        # Vantage path has different addresses and a CALED/CALFIX write
        # sequence (#214) that this handler does not yet speak.
        if msg.get("calibration") is not None and link is None:
            results["calibration"] = "unsupported"
        # Pull current canonical state up front; we'll merge successful writes
        # back in below and persist a single updated row at the end so the
        # daemon's source-of-truth stays in sync with the link (issue #147).
        canonical = self._load_canonical_wl_config() or {}
        canonical.setdefault("calibration", {})
        canonical_changed = False

        # Each branch follows the same shape: write, then read back, and
        # only declare success (and update self-cache + canonical) when the
        # readback matches the requested value.  Codex review on PR #148:
        # an ACK alone doesn't guarantee the register actually took the
        # change, so trusting ACK lets cache and canonical drift away from
        # the link's true state silently.  A mismatch is "failed" — the
        # canonical row stays at the previous value, and the daemon's
        # cached state is set to whatever the link is actually reporting.
        if msg.get("archive_period") is not None and "archive_period" not in results:
            want = msg["archive_period"]
            # Route to whichever driver is connected — LinkDriver (SAP) and
            # VantageDriver (SETPER) both expose this pair.  Verifying by
            # read-back rather than trusting the ACK is what caught SETPER
            # silently not applying on some consoles.
            try:
                ack = await drv.async_set_archive_period(want)
            except ValueError as exc:
                # Driver rejected an illegal period before touching the
                # hardware (Davis honours only {1,5,10,15,30,60,120}).
                logger.warning("archive_period rejected: %s", exc)
                results["archive_period"] = "invalid"
                ack = False
            if ack:
                actual = await drv.async_read_archive_period()
                if actual == want:
                    self._archive_period = actual
                    canonical["archive_period"] = actual
                    canonical_changed = True
                    results["archive_period"] = "ok"
                else:
                    logger.warning(
                        "archive period ACKed but station still reports %s (wanted %s)",
                        actual, want,
                    )
                    if actual is not None:
                        self._archive_period = actual
                    results["archive_period"] = "failed"
            elif results.get("archive_period") != "invalid":
                results["archive_period"] = "failed"

        if msg.get("sample_period") is not None and "sample_period" not in results:
            want = msg["sample_period"]
            ack = await link.async_set_sample_period(want)
            if ack:
                actual = await link.async_read_sample_period()
                if actual == want:
                    self._sample_period = actual
                    canonical["sample_period"] = actual
                    canonical_changed = True
                    results["sample_period"] = "ok"
                else:
                    logger.warning(
                        "SSP ACKed but link still reports %s (wanted %s)",
                        actual, want,
                    )
                    if actual is not None:
                        self._sample_period = actual
                    results["sample_period"] = "failed"
            else:
                results["sample_period"] = "failed"

        if msg.get("calibration") is not None and "calibration" not in results:
            cal = msg["calibration"]
            offsets = CalibrationOffsets(
                inside_temp=cal["inside_temp"],
                outside_temp=cal["outside_temp"],
                barometer=cal["barometer"],
                outside_hum=cal["outside_humidity"],
                rain_cal=cal["rain_cal"],
            )
            ack = await link.async_write_calibration(offsets)
            if ack:
                fresh = await link.async_read_calibration()
                if fresh == offsets:
                    canonical["calibration"] = {
                        "inside_temp": cal["inside_temp"],
                        "outside_temp": cal["outside_temp"],
                        "barometer": cal["barometer"],
                        "outside_humidity": cal["outside_humidity"],
                        "rain_cal": cal["rain_cal"],
                    }
                    canonical_changed = True
                    results["calibration"] = "ok"
                else:
                    logger.warning(
                        "WWR-cal ACKed but readback differs: wanted=%s, got=%s",
                        offsets, fresh,
                    )
                    results["calibration"] = "failed"
            else:
                results["calibration"] = "failed"

        if canonical_changed:
            self._save_canonical_wl_config(canonical)

        return {"results": results}

    async def _clear_rain(self, which: str) -> dict[str, Any]:
        """Clear a rain accumulator on whichever driver is connected.

        Was LinkDriver-gated, so the rain-clear buttons did nothing on
        Vantage stations even though the protocol supports it — CLRVAR 13
        (daily) and CLRVAR 17 (yearly), manual section IX.6.  I originally
        recorded this as "unsupported by the protocol" in #219 on the
        strength of a hasattr() check, which only ever answered "did we
        implement it".  See #221.
        """
        method = f"async_clear_rain_{which}"
        drv = self.driver
        if drv is None or not drv.connected:
            raise RuntimeError("Not connected")
        if not hasattr(drv, method):
            raise RuntimeError(
                f"{drv.station_name} does not support clearing {which} rain"
            )
        ok = await getattr(drv, method)()
        if ok:
            await self._refresh_after_rain_clear()
        return {"success": ok}

    async def _h_clear_rain_daily(self, _msg: dict) -> dict[str, Any]:
        return await self._clear_rain("daily")

    async def _h_clear_rain_yearly(self, _msg: dict) -> dict[str, Any]:
        return await self._clear_rain("yearly")

    async def _refresh_after_rain_clear(self) -> None:
        """Reset poller rain cache and force an immediate poll so the
        zeroed value propagates to the DB and WebSocket clients."""
        if self.poller:
            self.poller._last_rain_daily = None
            self.poller._last_rain_tip_time = None
            self.poller._rain_rate_in_per_hr = 0.0
            try:
                snapshot = await self.driver.poll()
                if snapshot is not None:
                    await self.poller._process_reading(snapshot)
            except Exception as e:
                logger.warning("Post-clear refresh poll failed: %s", e)

    async def _h_force_archive(self, _msg: dict) -> dict[str, Any]:
        link = self._link
        if not link or not link.connected:
            raise RuntimeError("Not connected (or driver does not support archive force)")
        ok = await link.async_force_archive()
        records_synced = 0
        if ok:
            try:
                records_synced = await async_sync_archive(link)
            except Exception as exc:
                logger.warning("Post-force archive sync failed: %s", exc)
        return {"success": ok, "records_synced": records_synced}


# --------------- Entry point ---------------

def main() -> None:
    # Shared setup — quietens httpx/httpcore (which log full request URLs,
    # credentials included) and installs the redaction filter.  This daemon
    # previously called basicConfig() directly and leaked Weather Underground
    # credentials into the systemd journal on every upload (#206).
    configure_logging(level=logging.INFO)
    daemon = LoggerDaemon()
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
