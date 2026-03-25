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
from app.models.database import init_database, SessionLocal, engine
from app.models.station_config import StationConfigModel
from app.protocol.base import StationDriver
from app.protocol.link_driver import LinkDriver, CalibrationOffsets
from app.protocol.serial_port import list_serial_ports
from app.protocol.constants import STATION_NAMES
from app.services.poller import Poller
from app.services.archive_sync import async_sync_archive
from app.ipc.server import IPCServer
from app.ipc import protocol as ipc
from app.services.wunderground import WundergroundUploader
from app.services.cwop import CwopUploader

logger = logging.getLogger("davis.logger")


# --------------- Driver Factory ---------------

def _create_driver(driver_type: str, config: dict) -> StationDriver:
    """Create a StationDriver instance based on config.

    Args:
        driver_type: One of: legacy, vantage, weatherlink_ip,
            weatherlink_live, ecowitt, tempest, ambient.
        config: Effective station config dict.
    """
    port = str(config.get("serial_port", settings.serial_port))
    baud = int(config.get("baud_rate", settings.baud_rate))

    if driver_type == "legacy":
        return LinkDriver(port=port, baud_rate=baud, timeout=settings.serial_timeout)

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
        station_type_code = 0
        if link is not None:
            self._archive_period = await link.async_read_archive_period()
            self._sample_period = await link.async_read_sample_period()
            logger.info("Archive period: %s min, Sample period: %s sec",
                         self._archive_period, self._sample_period)

            # Sync station clock to system time
            now = datetime.now()
            if await link.async_write_station_time(now):
                logger.info("Station clock synced to %s", now.strftime("%H:%M:%S"))
            else:
                logger.warning("Failed to sync station clock")

            # Archive sync in background (shares _io_lock with poller)
            asyncio.create_task(self._bg_archive_sync())

            station_type_code = link.station_model.value if link.station_model else 0

        self.poller = Poller(
            self.driver,
            poll_interval=settings.poll_interval_sec,
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
        logger.info("Poller started (%ds interval)", settings.poll_interval_sec)

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
        while self._running:
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

            if not self._running:
                break

            await self._do_midnight_rain_reset()

    async def _do_midnight_rain_reset(self) -> None:
        """Save today's daily rain as yesterday, then clear the station counter."""
        link = self._link
        if not link or not link.connected:
            logger.warning("Midnight rain reset skipped — station not connected")
            return

        # Read current daily rain (direct memory read for accuracy)
        try:
            daily_clicks = await link.async_read_rain_daily()
            daily_inches = round(daily_clicks * 0.01, 2) if daily_clicks else 0.0
        except Exception:
            daily_inches = 0.0

        # Persist as rain_yesterday in config
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

        # Update poller's cached value
        if self.poller:
            self.poller.rain_yesterday = daily_inches

        # Clear station hardware + reset poller rain cache
        try:
            ok = await link.async_clear_rain_daily()
            if ok:
                await self._refresh_after_rain_clear()
                logger.info(
                    "Midnight rain reset: yesterday=%.2f in, daily cleared",
                    daily_inches,
                )
            else:
                logger.warning("Midnight rain reset: hardware clear failed")
        except Exception as exc:
            logger.warning("Midnight rain reset failed: %s", exc)

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
        link = self._link
        if not link or not link.connected:
            raise RuntimeError("Not connected (or driver does not support clock read)")
        result = await link.async_read_station_time()
        if result is None:
            logger.warning("read_station_time returned None")
        return result

    async def _h_sync_station_time(self, _msg: dict) -> dict[str, Any]:
        link = self._link
        if not link or not link.connected:
            raise RuntimeError("Not connected (or driver does not support clock sync)")
        now = datetime.now()
        ok = await link.async_write_station_time(now)
        return {"success": ok, "synced_to": now.strftime("%H:%M:%S %m/%d/%Y")}

    async def _h_read_config(self, _msg: dict) -> dict[str, Any]:
        link = self._link
        if not link or not link.connected:
            raise RuntimeError("Not connected (or driver does not support config read)")
        cal = link.calibration
        return {
            "archive_period": self._archive_period,
            "sample_period": self._sample_period,
            "calibration": {
                "inside_temp": cal.inside_temp,
                "outside_temp": cal.outside_temp,
                "barometer": cal.barometer,
                "outside_humidity": cal.outside_hum,
                "rain_cal": cal.rain_cal,
            },
        }

    async def _h_write_config(self, msg: dict) -> dict[str, Any]:
        link = self._link
        if not link or not link.connected:
            raise RuntimeError("Not connected (or driver does not support config write)")
        results: dict[str, str] = {}

        if msg.get("archive_period") is not None:
            ok = await link.async_set_archive_period(msg["archive_period"])
            results["archive_period"] = "ok" if ok else "failed"
            if ok:
                self._archive_period = msg["archive_period"]

        if msg.get("sample_period") is not None:
            ok = await link.async_set_sample_period(msg["sample_period"])
            results["sample_period"] = "ok" if ok else "failed"
            if ok:
                self._sample_period = msg["sample_period"]

        if msg.get("calibration") is not None:
            cal = msg["calibration"]
            offsets = CalibrationOffsets(
                inside_temp=cal["inside_temp"],
                outside_temp=cal["outside_temp"],
                barometer=cal["barometer"],
                outside_hum=cal["outside_humidity"],
                rain_cal=cal["rain_cal"],
            )
            ok = await link.async_write_calibration(offsets)
            results["calibration"] = "ok" if ok else "failed"

        return {"results": results}

    async def _h_clear_rain_daily(self, _msg: dict) -> dict[str, Any]:
        link = self._link
        if not link or not link.connected:
            raise RuntimeError("Not connected (or driver does not support rain clear)")
        ok = await link.async_clear_rain_daily()
        if ok:
            await self._refresh_after_rain_clear()
        return {"success": ok}

    async def _h_clear_rain_yearly(self, _msg: dict) -> dict[str, Any]:
        link = self._link
        if not link or not link.connected:
            raise RuntimeError("Not connected (or driver does not support rain clear)")
        ok = await link.async_clear_rain_yearly()
        if ok:
            await self._refresh_after_rain_clear()
        return {"success": ok}

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
        return {"success": ok}


# --------------- Entry point ---------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    daemon = LoggerDaemon()
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
