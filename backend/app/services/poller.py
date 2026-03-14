"""Async polling loop for weather station sensors.

Periodically polls the station via the StationDriver interface, computes
derived values, stores to database, and broadcasts via a configurable
callback.  Works with any driver that implements StationDriver.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional

from sqlalchemy import func

from ..protocol.base import StationDriver, SensorSnapshot
from ..services.calculations import (
    heat_index,
    dew_point,
    wind_chill,
    feels_like,
    equivalent_potential_temperature,
)
from ..services.pressure_trend import analyze_pressure_trend
from ..services.alerts import AlertChecker
from ..models.database import SessionLocal
from ..models.sensor_reading import SensorReadingModel
from ..models.station_config import StationConfigModel

CARDINAL_DIRECTIONS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]

logger = logging.getLogger(__name__)

# Minimum rain gauge resolution (inches per bucket tip).
# 0.01" is the standard for virtually all tipping-bucket gauges.
_RAIN_TIP_INCHES = 0.01


class Poller:
    """Manages the sensor polling lifecycle."""

    def __init__(
        self,
        driver: StationDriver,
        poll_interval: int = 10,
        station_type_code: int = 0,
    ):
        self.driver = driver
        self.poll_interval = poll_interval
        self._station_type_code = station_type_code
        self._running = False
        self._last_poll: Optional[datetime] = None
        self._last_rain_daily: Optional[float] = None
        self._last_rain_tip_time: Optional[datetime] = None
        self._rain_rate_in_per_hr: float = 0.0
        self.rain_yesterday: float = 0.0
        self._crc_errors = 0
        self._timeouts = 0
        self._start_time = time.time()
        self._broadcast_callback: (
            Callable[[dict[str, Any]], Coroutine[Any, Any, Any]] | None
        ) = None
        self._alert_checker = AlertChecker()

    @property
    def stats(self) -> dict:
        return {
            "last_poll": self._last_poll.isoformat() if self._last_poll else None,
            "crc_errors": self._crc_errors,
            "timeouts": self._timeouts,
            "uptime_seconds": int(time.time() - self._start_time),
        }

    def reload_alert_thresholds(self) -> None:
        """Load alert thresholds from the database."""
        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="alert_thresholds").first()
            if row:
                thresholds = json.loads(row.value)
                self._alert_checker.load_thresholds(thresholds)
            else:
                self._alert_checker.load_thresholds([])
        except Exception as e:
            logger.error("Failed to load alert thresholds: %s", e)
        finally:
            db.close()

    async def run(self) -> None:
        """Main polling loop. Runs until cancelled."""
        self._running = True
        self._start_time = time.time()
        self.reload_alert_thresholds()
        logger.info("Poller starting with %ds interval", self.poll_interval)

        while self._running:
            try:
                logger.debug("Sending poll...")
                snapshot = await self.driver.poll()
                if snapshot is not None:
                    self._last_poll = datetime.now(timezone.utc)
                    logger.info(
                        "Poll OK: outside_temp=%s wind=%s baro=%s",
                        snapshot.outside_temp, snapshot.wind_speed, snapshot.barometer,
                    )
                    await self._process_reading(snapshot)
                else:
                    self._timeouts += 1
                    logger.warning("Poll returned no data (timeout #%d)", self._timeouts)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                logger.error("Polling error: %s", e, exc_info=True)
                self._timeouts += 1

            try:
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break

    def set_broadcast_callback(
        self,
        callback: Callable[[dict[str, Any]], Coroutine[Any, Any, Any]],
    ) -> None:
        """Set the async callback invoked after each reading.

        In the logger daemon this is IPCServer.broadcast_to_subscribers.
        """
        self._broadcast_callback = callback

    def stop(self) -> None:
        self._running = False
        self.driver.request_stop()

    async def _process_reading(self, snapshot: SensorSnapshot) -> None:
        """Compute derived values, store to DB, broadcast to WS clients."""
        # Compute rain_rate from bucket tips for drivers that don't provide it.
        # Uses time-between-tips with decay: rate holds steady until the next
        # expected tip is overdue, then decays toward 0.  After 15 min with no
        # tip, rate drops to 0 (rain stopped).
        if snapshot.rain_rate is None and snapshot.rain_daily is not None:
            now = datetime.now(timezone.utc)

            if self._last_rain_daily is not None:
                rain_delta = snapshot.rain_daily - self._last_rain_daily
                if rain_delta < 0:
                    rain_delta = 0.0  # counter wrapped or reset

                if rain_delta > 0 and self._last_rain_tip_time is not None:
                    # Bucket tipped — rate from time since last tip
                    elapsed_hr = (now - self._last_rain_tip_time).total_seconds() / 3600
                    if elapsed_hr > 0:
                        self._rain_rate_in_per_hr = rain_delta / elapsed_hr
                    self._last_rain_tip_time = now
                elif rain_delta > 0:
                    # First tip(s) detected — estimate rate from the poll
                    # interval since we have no prior tip timestamp.
                    poll_hr = self.poll_interval / 3600
                    if poll_hr > 0:
                        self._rain_rate_in_per_hr = rain_delta / poll_hr
                    self._last_rain_tip_time = now
                elif self._last_rain_tip_time is not None:
                    # No new tips — decay: can't be raining faster than
                    # one tip / time_waiting or a tip would have occurred
                    elapsed_s = (now - self._last_rain_tip_time).total_seconds()
                    if elapsed_s > 900:  # 15 min timeout
                        self._rain_rate_in_per_hr = 0.0
                    else:
                        elapsed_hr = elapsed_s / 3600
                        if elapsed_hr > 0:
                            self._rain_rate_in_per_hr = min(
                                self._rain_rate_in_per_hr,
                                _RAIN_TIP_INCHES / elapsed_hr,
                            )

            snapshot.rain_rate = self._rain_rate_in_per_hr
            self._last_rain_daily = snapshot.rain_daily

        # Convert to native units for the calculation functions (tenths F,
        # thousandths inHg) which have been validated against reference tables.
        temp_tenths = (
            round(snapshot.outside_temp * 10)
            if snapshot.outside_temp is not None else None
        )
        hum = snapshot.outside_humidity
        baro_thou = (
            round(snapshot.barometer * 1000)
            if snapshot.barometer is not None else None
        )
        wind = snapshot.wind_speed

        # Compute derived values
        hi = None
        dp = None
        wc = None
        fl = None
        theta = None

        if temp_tenths is not None and hum is not None:
            hi = heat_index(temp_tenths, hum)
            dp = dew_point(temp_tenths, hum)

            if baro_thou is not None:
                theta = equivalent_potential_temperature(temp_tenths, hum, baro_thou)

        if temp_tenths is not None and wind is not None:
            wc = wind_chill(temp_tenths, wind)

        if temp_tenths is not None and hum is not None and wind is not None:
            fl = feels_like(temp_tenths, hum, wind)

        # Pressure trend from recent history
        trend = await self._get_pressure_trend()

        # Store to database — convert SensorSnapshot floats to DB integer columns
        db = SessionLocal()
        try:
            model = SensorReadingModel(
                timestamp=datetime.now(timezone.utc),
                station_type=self._station_type_code,
                inside_temp=(
                    round(snapshot.inside_temp * 10)
                    if snapshot.inside_temp is not None else None
                ),
                outside_temp=(
                    round(snapshot.outside_temp * 10)
                    if snapshot.outside_temp is not None else None
                ),
                inside_humidity=snapshot.inside_humidity,
                outside_humidity=snapshot.outside_humidity,
                wind_speed=snapshot.wind_speed,
                wind_direction=snapshot.wind_direction,
                barometer=(
                    round(snapshot.barometer * 1000)
                    if snapshot.barometer is not None else None
                ),
                rain_total=(
                    round(snapshot.rain_daily * 100)
                    if snapshot.rain_daily is not None else None
                ),
                rain_rate=(
                    round(snapshot.rain_rate * 10)
                    if snapshot.rain_rate is not None else None
                ),
                rain_yearly=(
                    round(snapshot.rain_yearly * 100)
                    if snapshot.rain_yearly is not None else None
                ),
                solar_radiation=snapshot.solar_radiation,
                uv_index=(
                    round(snapshot.uv_index * 10)
                    if snapshot.uv_index is not None else None
                ),
                heat_index=hi,
                dew_point=dp,
                wind_chill=wc,
                feels_like=fl,
                theta_e=theta,
                pressure_trend=trend,
                extra_json=(
                    json.dumps(snapshot.extra)
                    if snapshot.extra else None
                ),
            )
            db.add(model)
            db.commit()

            # Query daily extremes while session is open
            extremes = self._get_daily_extremes(db)
        finally:
            db.close()

        # Broadcast to subscribers (IPC clients / WebSocket relay)
        if self._broadcast_callback:
            data_dict = self._snapshot_to_dict(snapshot, hi, dp, wc, fl, theta, trend, extremes)
            await self._broadcast_callback({
                "type": "sensor_update",
                "data": data_dict,
            })

            # Reload thresholds each cycle so config changes take effect
            self.reload_alert_thresholds()
            triggered, cleared = self._alert_checker.check(data_dict)
            for alert in triggered:
                await self._broadcast_callback({
                    "type": "alert_triggered",
                    "data": alert,
                })
            for alert in cleared:
                await self._broadcast_callback({
                    "type": "alert_cleared",
                    "data": alert,
                })

    async def _get_pressure_trend(self) -> Optional[str]:
        """Query last 3 hours of barometer readings for trend analysis."""
        db = SessionLocal()
        try:
            cutoff = datetime.now(timezone.utc).timestamp() - 3 * 3600
            results = (
                db.query(
                    SensorReadingModel.timestamp,
                    SensorReadingModel.barometer,
                )
                .filter(SensorReadingModel.barometer.isnot(None))
                .filter(SensorReadingModel.timestamp >= datetime.fromtimestamp(cutoff, tz=timezone.utc))
                .order_by(SensorReadingModel.timestamp)
                .all()
            )

            if len(results) < 2:
                return None

            readings = [(r.timestamp.timestamp(), r.barometer) for r in results]
            result = analyze_pressure_trend(readings)
            return result.trend if result else None
        finally:
            db.close()

    @staticmethod
    def _get_daily_extremes(db) -> Optional[dict]:
        """Query today's high/low extremes from sensor_readings."""
        # Use system-local midnight so the day boundary matches the user's timezone
        now = datetime.now().astimezone()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

        S = SensorReadingModel
        row = (
            db.query(
                func.max(S.outside_temp), func.min(S.outside_temp),
                func.max(S.inside_temp), func.min(S.inside_temp),
                func.max(S.wind_speed),
                func.max(S.barometer), func.min(S.barometer),
                func.max(S.outside_humidity), func.min(S.outside_humidity),
                func.max(S.rain_rate),
            )
            .filter(S.timestamp >= midnight)
            .first()
        )

        if row is None or row[0] is None:
            return None

        def _val(raw, divisor=1, unit=""):
            if raw is None:
                return None
            return {"value": round(raw / divisor, 2) if divisor != 1 else raw, "unit": unit}

        return {
            "outside_temp_hi": _val(row[0], 10, "F"),
            "outside_temp_lo": _val(row[1], 10, "F"),
            "inside_temp_hi": _val(row[2], 10, "F"),
            "inside_temp_lo": _val(row[3], 10, "F"),
            "wind_speed_hi": _val(row[4], 1, "mph"),
            "barometer_hi": _val(row[5], 1000, "inHg"),
            "barometer_lo": _val(row[6], 1000, "inHg"),
            "humidity_hi": _val(row[7], 1, "%"),
            "humidity_lo": _val(row[8], 1, "%"),
            "rain_rate_hi": _val(row[9], 10, "in/hr"),
        }

    @staticmethod
    def _cardinal(degrees: Optional[int]) -> Optional[str]:
        if degrees is None:
            return None
        idx = round(degrees / 22.5) % 16
        return CARDINAL_DIRECTIONS[idx]

    def _snapshot_to_dict(
        self,
        snapshot: SensorSnapshot,
        hi: Optional[int],
        dp: Optional[int],
        wc: Optional[int],
        fl: Optional[int],
        theta: Optional[int],
        trend: Optional[str],
        extremes: Optional[dict] = None,
    ) -> dict:
        """Convert a SensorSnapshot to a JSON-serializable dict for WebSocket.

        Format matches the REST /api/current response so the frontend
        can use the same CurrentConditions type for both sources.

        Derived values (hi, dp, wc, fl, theta) remain in native tenths-F /
        tenths-K for compatibility with the existing API contract.
        """
        def temp_f(tenths: Optional[int]) -> Optional[float]:
            """Convert derived value from tenths-F to float F."""
            return tenths / 10.0 if tenths is not None else None

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "station_type": self.driver.station_name,
            "temperature": {
                "inside": {"value": snapshot.inside_temp, "unit": "F"},
                "outside": {"value": snapshot.outside_temp, "unit": "F"},
            },
            "humidity": {
                "inside": {"value": snapshot.inside_humidity, "unit": "%"},
                "outside": {"value": snapshot.outside_humidity, "unit": "%"},
            },
            "wind": {
                "speed": {"value": snapshot.wind_speed, "unit": "mph"},
                "direction": {"value": snapshot.wind_direction, "unit": "°"},
                "cardinal": self._cardinal(snapshot.wind_direction),
            },
            "barometer": {
                "value": snapshot.barometer,
                "unit": "inHg",
                "trend": trend,
            },
            "rain": {
                "daily": (
                    {"value": round(snapshot.rain_daily, 2), "unit": "in"}
                    if snapshot.rain_daily is not None else None
                ),
                "yearly": (
                    {"value": round(snapshot.rain_yearly, 2), "unit": "in"}
                    if snapshot.rain_yearly is not None else None
                ),
                "rate": (
                    {"value": round(snapshot.rain_rate, 2), "unit": "in/hr"}
                    if snapshot.rain_rate is not None else None
                ),
                "yesterday": {"value": round(self.rain_yesterday, 2), "unit": "in"},
            },
            "derived": {
                "heat_index": {"value": temp_f(hi), "unit": "F"},
                "dew_point": {"value": temp_f(dp), "unit": "F"},
                "wind_chill": {"value": temp_f(wc), "unit": "F"},
                "feels_like": {"value": temp_f(fl), "unit": "F"},
                "theta_e": {"value": theta / 10.0 if theta is not None else None, "unit": "K"},
            },
            "solar_radiation": (
                {"value": snapshot.solar_radiation, "unit": "W/m²"}
                if snapshot.solar_radiation is not None else None
            ),
            "uv_index": (
                {"value": snapshot.uv_index, "unit": ""}
                if snapshot.uv_index is not None else None
            ),
            "daily_extremes": extremes,
        }
