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

from .daily_extremes import (
    get_daily_extremes,
    get_month_extremes,
    get_year_extremes,
    get_weekly_delta,
)
from .solar_energy import compute_daily_solar_energy_j_per_m2, joules_to_display_unit
from .uv_warning import classify_uv

from ..config import settings
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
from ..models.sensor_meta import SENSOR_BOUNDS
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
        # ``_last_poll`` is set the instant a poll returns a snapshot
        # (before DB writes and broadcast).  ``_last_poll_completed_at``
        # advances only after ``_process_reading`` returns — i.e. after
        # DB write, broadcast, and any downstream uploaders complete.
        # A watchdog can only trust the second one as a liveness signal
        # (issue #473 / umbrella #472).
        self._last_poll_completed_at: Optional[datetime] = None
        # Advances after the full broadcast callback returns — which
        # inside the daemon includes the IPC subscriber broadcast AND
        # WU / CWOP / public-relay uploaders that hang off it.  An
        # uploader hang holds this back too, which is intentional: if
        # the callback-fan-out step is stuck, "we sent the WS update"
        # is not really true either.
        self._last_broadcast_at: Optional[datetime] = None
        # Wall-clock instant the poller's run loop entered.  Lets
        # ``poll_stall_seconds`` fall back to "seconds since the
        # poller started" until the first cycle completes, so a
        # startup-time wedge — driver connected, poller created,
        # first poll hangs before ``_process_reading`` returns —
        # is not indistinguishable from a healthy first-second window
        # (Codex R1 on #473).
        self._poll_started_at: Optional[datetime] = None
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
        # Tracks the last connection_status value we broadcast. None
        # until the first cycle, so the first tick always emits (which
        # gives every browser that opened during a startup gap a
        # correct update as soon as poll #1 runs).
        self._last_broadcast_connected: Optional[bool] = None
        self._alert_checker = AlertChecker()

    @property
    def stats(self) -> dict:
        now = datetime.now(timezone.utc)
        completed = self._last_poll_completed_at
        broadcast = self._last_broadcast_at
        started = self._poll_started_at
        # Age since the last completed cycle when we have one; else the
        # age since the poller started running (so a hung first poll
        # trips the same /api/health threshold as a subsequent stall).
        # None only while the poller has not entered its run loop yet
        # — a very short window that /api/health treats as ok since a
        # stall we can't yet measure isn't a stall we can page on.
        if completed is not None:
            stall = (now - completed).total_seconds()
        elif started is not None:
            stall = (now - started).total_seconds()
        else:
            stall = None
        return {
            "last_poll": self._last_poll.isoformat() if self._last_poll else None,
            "last_poll_completed_at": completed.isoformat() if completed else None,
            "last_broadcast_at": broadcast.isoformat() if broadcast else None,
            "poll_stall_seconds": stall,
            "crc_errors": self._crc_errors,
            "timeouts": self._timeouts,
            "uptime_seconds": int(time.time() - self._start_time),
        }

    async def _maybe_broadcast_connection_change(self) -> None:
        """Emit a connection_status WS message when driver.connected flips.

        Fixes #492: without this the frontend only ever sees the one
        message ws/handler.py sends at WS open. If the handshake landed
        during a startup or watchdog window, the browser was stuck on
        the wrong value until a page reload. Emitting on-change here
        covers both directions (offline→online after recovery, online→
        offline after a stall), for every connected browser.
        """
        if self._broadcast_callback is None:
            return
        current = bool(self.driver.connected)
        if current == self._last_broadcast_connected:
            return
        await self._broadcast_callback({
            "type": "connection_status",
            "connected": current,
        })
        self._last_broadcast_connected = current

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
        self._poll_started_at = datetime.now(timezone.utc)
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
                    # Advance the liveness clock ONLY after
                    # ``_process_reading`` returns — DB write, broadcast,
                    # and uploaders all completed.  A watchdog checking
                    # this timestamp can tell the poller is truly making
                    # progress, not just that a single serial read went
                    # through and something downstream is wedged.
                    self._last_poll_completed_at = datetime.now(timezone.utc)
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

            await self._maybe_broadcast_connection_change()

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

        # SensorSnapshot is now SI (°C, hPa, m/s, mm).
        # Scale to tenths for calculation functions and DB storage.
        temp_tenths_c = (
            round(snapshot.outside_temp * 10)
            if snapshot.outside_temp is not None else None
        )
        hum = snapshot.outside_humidity
        baro_tenths_hpa = (
            round(snapshot.barometer * 10)
            if snapshot.barometer is not None else None
        )
        wind_tenths_ms = (
            round(snapshot.wind_speed * 10)
            if snapshot.wind_speed is not None else None
        )
        wind_gust_tenths_ms = (
            round(snapshot.wind_gust * 10)
            if snapshot.wind_gust is not None else None
        )

        # Compute derived values
        hi = None
        dp = None
        wc = None
        fl = None
        theta = None

        if temp_tenths_c is not None and hum is not None:
            hi = heat_index(temp_tenths_c, hum)
            dp = dew_point(temp_tenths_c, hum)

            if baro_tenths_hpa is not None:
                theta = equivalent_potential_temperature(temp_tenths_c, hum, baro_tenths_hpa)

        if temp_tenths_c is not None and wind_tenths_ms is not None:
            wc = wind_chill(temp_tenths_c, wind_tenths_ms)

        if temp_tenths_c is not None and hum is not None and wind_tenths_ms is not None:
            fl = feels_like(temp_tenths_c, hum, wind_tenths_ms)

        # Pressure trend from recent history
        trend = await self._get_pressure_trend()

        # Store to database — SensorSnapshot is SI, DB wants tenths (×10).
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
                wind_speed=(
                    round(snapshot.wind_speed * 10)
                    if snapshot.wind_speed is not None else None
                ),
                wind_gust=wind_gust_tenths_ms,
                wind_direction=snapshot.wind_direction,
                barometer=(
                    round(snapshot.barometer * 10)
                    if snapshot.barometer is not None else None
                ),
                rain_total=(
                    round(snapshot.rain_daily * 10)
                    if snapshot.rain_daily is not None else None
                ),
                rain_rate=(
                    round(snapshot.rain_rate * 10)
                    if snapshot.rain_rate is not None else None
                ),
                rain_yearly=(
                    round(snapshot.rain_yearly * 10)
                    if snapshot.rain_yearly is not None else None
                ),
                solar_radiation=snapshot.solar_radiation,
                uv_index=(
                    round(snapshot.uv_index * 10)
                    if snapshot.uv_index is not None else None
                ),
                # ET: snapshot carries mm; DB stores tenths mm (same shape
                # as rain_total).  See SENSOR_BOUNDS in sensor_meta.py.
                et_daily=(
                    round(snapshot.et_daily * 10)
                    if snapshot.et_daily is not None else None
                ),
                et_monthly=(
                    round(snapshot.et_monthly * 10)
                    if snapshot.et_monthly is not None else None
                ),
                et_yearly=(
                    round(snapshot.et_yearly * 10)
                    if snapshot.et_yearly is not None else None
                ),
                heat_index=hi,
                dew_point=dp,
                wind_chill=wc,
                feels_like=fl,
                theta_e=theta,
                # Station-computed, not calculated here — stored in tenths
                # °C like the other temperature columns.
                thsw_index=(
                    round(snapshot.thsw_index * 10)
                    if snapshot.thsw_index is not None else None
                ),
                pressure_trend=trend,
                extra_json=self._build_extra_json(snapshot),
            )
            db.add(model)
            db.commit()

            # Query daily / monthly / yearly extremes AND the weekly
            # rain / ET rollups while the session is open.  All four
            # ride the WS broadcast so the frontend does not blink
            # them to null between poll cycles (see the comment below
            # about setCurrentConditions() overwriting the whole
            # object).
            extremes = self._get_daily_extremes(db)
            monthly_extremes = get_month_extremes(db)
            yearly_extremes = get_year_extremes(db)
            from ..models.sensor_reading import SensorReadingModel as _S
            rain_weekly = get_weekly_delta(db, _S.rain_yearly, "rain_yearly")
            et_weekly = get_weekly_delta(db, _S.et_yearly, "et_yearly")
            # Solar-energy accumulator needs the same DB session and the
            # operator's unit preference.  Match what /api/current computes
            # so the WS broadcast doesn't blink the field to null on every
            # push (the frontend does a full setCurrentConditions(data)
            # replace on each WS message — any field missing from the WS
            # payload but present in /api/current disappears from the tile
            # for a poll cycle, then reappears at the next REST refresh).
            # Yearly rain: console value + reset detection + optional
            # archive fallback.  Uses the DB session already open here
            # rather than opening its own, matching how solar-energy /
            # extremes are stitched into the broadcast.  See
            # services/rain_year.compute_yearly_rain for the modes.
            from ..services.rain_year import compute_yearly_rain
            from ..models.sensor_meta import convert, SENSOR_UNITS
            source_row = db.query(StationConfigModel).filter_by(
                key="rain_yearly_source",
            ).first()
            source_mode = (source_row.value if source_row and source_row.value else "auto")
            yearly_result = compute_yearly_rain(
                db,
                round(snapshot.rain_yearly * 10) if snapshot.rain_yearly is not None else None,
                source_mode,
                season_month=None,
            )
            if yearly_result.get("value") is None:
                yearly_rain: Optional[dict] = None
            else:
                yearly_rain = {
                    "value": convert("rain_yearly", yearly_result["value"]),
                    "unit": SENSOR_UNITS.get("rain_yearly", "in"),
                    "source": yearly_result.get("source", "console"),
                }
                if "detected_reset_at" in yearly_result:
                    yearly_rain["detected_reset_at"] = yearly_result["detected_reset_at"]

            solar_j = compute_daily_solar_energy_j_per_m2(db)
            unit_row = db.query(StationConfigModel).filter_by(
                key="solar_energy_unit",
            ).first()
            solar_energy_unit = (
                unit_row.value if unit_row and unit_row.value
                else settings.units_solar_energy
            )
            solar_energy_daily_value = joules_to_display_unit(
                solar_j, solar_energy_unit,
            )
            solar_energy_daily = (
                {"value": solar_energy_daily_value, "unit": solar_energy_unit}
                if solar_energy_daily_value is not None else None
            )
        finally:
            db.close()

        # Broadcast to subscribers (IPC clients / WebSocket relay)
        if self._broadcast_callback:
            data_dict = self._snapshot_to_dict(
                snapshot, hi, dp, wc, fl, theta, trend, extremes,
                solar_energy_daily=solar_energy_daily,
                monthly_extremes=monthly_extremes,
                yearly_extremes=yearly_extremes,
                rain_weekly=rain_weekly,
                et_weekly=et_weekly,
                yearly_rain=yearly_rain,
            )
            # ``snapshot`` (the raw SensorSnapshot dataclass) rides
            # along so downstream consumers that need the flat SI
            # shape don't have to reverse-engineer it from the nested
            # ``data`` dict.  The public-relay sender in
            # ``kanfei-logger`` uses this to build the ingest payload
            # that mirrors ``SensorSnapshot`` 1:1 (issue #336 Phase 3);
            # ``data_dict`` is REST-current-shaped and lossy after
            # unit conversion.
            await self._broadcast_callback({
                "type": "sensor_update",
                "data": data_dict,
                "snapshot": snapshot,
            })
            self._last_broadcast_at = datetime.now(timezone.utc)

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
        """Delegate to shared implementation."""
        return get_daily_extremes(db)

    @staticmethod
    def _build_extra_json(snapshot) -> Optional[str]:
        """Return the driver's ``extra`` dict serialised as JSON, or None.

        ET graduated from ``extra_json`` to dedicated ``sensor_readings``
        columns (``et_daily``, ``et_monthly``, ``et_yearly``) in the
        migration alongside this commit — the poller now writes them as
        top-level fields on the DB row (see ``SensorReadingModel`` and
        the ``et_daily=`` assignment in this file's storage block).
        ``extra_json`` no longer carries ET, so this helper collapses to
        a pass-through of ``snapshot.extra``.

        Kept as a helper (rather than inlined) so future extras with
        similar "standardised on the snapshot, blob on the row" shape
        have an obvious place to land.
        """
        extras = dict(snapshot.extra) if snapshot.extra else {}
        return json.dumps(extras) if extras else None

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
        solar_energy_daily: Optional[dict] = None,
        monthly_extremes: Optional[dict] = None,
        yearly_extremes: Optional[dict] = None,
        rain_weekly: Optional[dict] = None,
        et_weekly: Optional[dict] = None,
        yearly_rain: Optional[dict] = None,
    ) -> dict:
        """Convert a SensorSnapshot (SI) to a JSON-serializable dict for WebSocket.

        Format matches the REST /api/current response so the frontend
        can use the same CurrentConditions type for both sources.

        This is the ONLY place SI → display conversion happens for live data.
        Derived values (hi, dp, wc, fl, theta) are in tenths °C / tenths K.
        """
        from ..utils.units import (
            si_temp_to_display_f,
            si_pressure_to_display_inhg,
            si_wind_to_display_mph,
            si_rain_to_display_in,
        )

        def _temp_f(c: Optional[float]) -> Optional[float]:
            """°C float → °F display float."""
            return round(c * 9 / 5 + 32, 1) if c is not None else None

        def _derived_f(tenths_c: Optional[int]) -> Optional[float]:
            """Derived value tenths °C → °F display float."""
            return si_temp_to_display_f(tenths_c) if tenths_c is not None else None

        def _baro(hpa: Optional[float]) -> Optional[float]:
            """hPa float → inHg display float."""
            return round(hpa / 33.8639, 2) if hpa is not None else None

        def _wind(ms: Optional[float]) -> Optional[int]:
            """m/s float → mph display int."""
            return round(ms * 2.23694) if ms is not None else None

        def _gust(ms: Optional[float]) -> Optional[int]:
            """m/s float → mph display int, dropping out-of-range values.

            The gust now goes straight out to CWOP/WU, so it gets the same
            SENSOR_BOUNDS check the stored columns get.  Bounds are in
            tenths m/s (storage units), matching how the value is written
            to the DB — a driver-level sentinel must not survive the hop
            to a published packet, which is how 255 mph reached findu
            (#230).
            """
            if ms is None:
                return None
            bounds = SENSOR_BOUNDS.get("wind_gust")
            if bounds is not None and not (bounds[0] <= round(ms * 10) <= bounds[1]):
                return None
            return _wind(ms)

        def _rain(mm: Optional[float]) -> Optional[float]:
            """mm float → inches display float."""
            return round(mm / 25.4, 2) if mm is not None else None

        def _et_display(mm: Optional[float]) -> Optional[dict]:
            """ET mm float → {value, unit} in operator's rain unit.
            Matches the /api/current shape from api/current.py so the
            frontend can consume WS and REST payloads the same way."""
            if mm is None:
                return None
            if settings.units_rain == "mm":
                return {"value": round(mm, 2), "unit": "mm"}
            return {"value": round(mm / 25.4, 3), "unit": "in"}

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "station_type": self.driver.station_name,
            "temperature": {
                "inside": {"value": _temp_f(snapshot.inside_temp), "unit": "F"},
                "outside": {"value": _temp_f(snapshot.outside_temp), "unit": "F"},
            },
            "humidity": {
                "inside": {"value": min(snapshot.inside_humidity, 100) if snapshot.inside_humidity is not None else None, "unit": "%"},
                "outside": {"value": min(snapshot.outside_humidity, 100) if snapshot.outside_humidity is not None else None, "unit": "%"},
            },
            "wind": {
                "speed": {"value": _wind(snapshot.wind_speed), "unit": "mph"},
                "direction": {"value": snapshot.wind_direction, "unit": "°"},
                "cardinal": self._cardinal(snapshot.wind_direction),
                # Must mirror the /api/current shape — cwop.py and
                # wunderground.py read whichever payload reaches them and
                # cannot tell the two apart.
                "gust": {"value": _gust(snapshot.wind_gust), "unit": "mph"},
            },
            "barometer": {
                "value": _baro(snapshot.barometer),
                "unit": "inHg",
                "trend": trend,
            },
            "rain": {
                "daily": (
                    {"value": _rain(snapshot.rain_daily), "unit": "in"}
                    if snapshot.rain_daily is not None else None
                ),
                # Yearly may be either the console's counter or an
                # archive-derived recomputation (see services/rain_year).
                # ``yearly_rain`` is precomputed by _poll_once so this
                # broadcast shape matches /api/current — a missing key
                # here blinks the field to null in the WS-updated tile.
                "yearly": yearly_rain,
                "rate": (
                    {"value": _rain(snapshot.rain_rate), "unit": "in/hr"}
                    if snapshot.rain_rate is not None else None
                ),
                "yesterday": {"value": round(self.rain_yesterday, 2), "unit": "in"},
                "weekly": rain_weekly,
            },
            "derived": {
                "heat_index": {"value": _derived_f(hi), "unit": "F"},
                "dew_point": {"value": _derived_f(dp), "unit": "F"},
                "wind_chill": {"value": _derived_f(wc), "unit": "F"},
                "feels_like": {"value": _derived_f(fl), "unit": "F"},
                "theta_e": {"value": theta / 10.0 if theta is not None else None, "unit": "K"},
                "thsw_index": {
                    "value": _derived_f(round(snapshot.thsw_index * 10))
                    if snapshot.thsw_index is not None else None,
                    "unit": "F",
                },
            },
            "solar_radiation": (
                {"value": snapshot.solar_radiation, "unit": "W/m²"}
                if snapshot.solar_radiation is not None else None
            ),
            "uv_index": (
                {"value": snapshot.uv_index, "unit": ""}
                if snapshot.uv_index is not None else None
            ),
            # WHO UV band — derived from uv_index server-side so consumers
            # don't reimplement the boundaries (matches /api/current shape).
            "uv_warning": classify_uv(snapshot.uv_index),
            # Trapezoid-integrated cumulative solar energy since local
            # midnight, in the operator's preferred unit.  Computed
            # upstream in the poll flow while the DB session was open;
            # passed in so we don't re-open a session per broadcast.
            "solar_energy_daily": solar_energy_daily,
            # ET: snapshot carries mm; display in the operator's rain unit
            # (same convention as /api/current).
            "et_daily": _et_display(snapshot.et_daily),
            "et_monthly": _et_display(snapshot.et_monthly),
            "et_yearly": _et_display(snapshot.et_yearly),
            "et_weekly": et_weekly,
            "daily_extremes": extremes,
            "monthly_extremes": monthly_extremes,
            "yearly_extremes": yearly_extremes,
        }
