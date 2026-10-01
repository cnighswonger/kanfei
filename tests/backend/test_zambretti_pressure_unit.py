"""Regression tests for the Zambretti + pressure-trend unit bug.

``sensor_readings.barometer`` is stored in **tenths of hPa** (schema
canonical — see ``utils.units.si_pressure_to_display_inhg`` and
``archive_sync.py``).  Two consumers were reading the raw column as if
it were already thousandths of inHg and feeding it directly to their
algorithms:

- ``api/forecast.py`` → ``zambretti_forecast``: a high-pressure reading
  (e.g. 10220 tenths-hPa = 1022.0 hPa = 30.18 inHg) got clamped to
  ``PRESSURE_LOW`` and the z-number pinned to the worst entry.  On
  "steady" trend that was "Stormy, much rain" — the user-visible
  symptom observed 2026-10-01.
- ``poller._get_pressure_trend`` → ``analyze_pressure_trend``: the
  threshold constants are in thousandths of inHg (0.020 inHg over
  3h = 20 thousandths); tenths-hPa deltas under-report trends.

Both callers now convert via ``hpa_tenths_to_inhg_thousandths``.
These tests drive the actual callers (``get_forecast`` endpoint,
``Poller._get_pressure_trend`` method) with tenths-hPa rows so that a
future edit removing either conversion fails the suite rather than
silently reverting the bug.
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.api.forecast import get_forecast
from app.models.database import Base, SessionLocal, engine
from app.models.sensor_reading import SensorReadingModel
from app.protocol.constants import StationModel
from app.services.forecast_local import (
    STEADY_FORECASTS,
    zambretti_forecast,
)
from app.services.pressure_trend import TREND_THRESHOLD, analyze_pressure_trend
from app.services.poller import Poller
from app.utils.units import hpa_tenths_to_inhg_thousandths


# ---------------------------------------------------------------------------
# Caller-level regressions — these are the ones that fail if either
# conversion is removed from production code.
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_readings():
    """Isolate each test with a clean sensor_readings table.

    ``create_all`` creates every ORM-registered table, not just
    sensor_readings — ``get_forecast`` touches ``station_config`` via
    its NWS config lookup even when NWS is disabled, so an isolated
    sensor_readings table alone would raise ``no such table`` the
    moment the endpoint is exercised."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    db = SessionLocal()
    try:
        db.query(SensorReadingModel).delete()
        db.commit()
    finally:
        db.close()


def _add_reading(db, *, when, baro_tenths_hpa):
    db.add(SensorReadingModel(
        timestamp=when,
        station_type=int(StationModel.MONITOR.value),
        barometer=baro_tenths_hpa,
    ))


class TestGetForecastCallerRegression:
    """``get_forecast`` reads rows directly from ``sensor_readings`` and
    hands them to ``zambretti_forecast``.  Driving it with tenths-hPa
    DB values is the only way to catch a dropped conversion in the
    endpoint itself."""

    def test_high_pressure_db_row_does_not_pin_to_stormy(self, fresh_readings):
        """A single row at 1022.0 hPa (10220 tenths-hPa) is fair-
        weather territory; the Zambretti forecast must not land on
        the worst entry of the steady table the way the pre-fix
        caller did."""
        db = SessionLocal()
        try:
            _add_reading(
                db, when=datetime.now(timezone.utc), baro_tenths_hpa=10220,
            )
            db.commit()
            result = asyncio.run(get_forecast(db))
        finally:
            db.close()

        local = result["local"]
        assert local is not None
        assert local["trend"] == "steady"
        # The specific text and z-number live downstream; the regression
        # we're pinning is just "not the worst entry."
        assert local["text"] != STEADY_FORECASTS[-1]
        assert "Stormy" not in local["text"]

    def test_low_pressure_db_row_lands_in_stormy_half(self, fresh_readings):
        """Symmetric to the above — 980.0 hPa (9800) must still land
        in the upper half of the steady table.  Confirms the fix
        hasn't inverted the mapping."""
        db = SessionLocal()
        try:
            _add_reading(
                db, when=datetime.now(timezone.utc), baro_tenths_hpa=9800,
            )
            db.commit()
            result = asyncio.run(get_forecast(db))
        finally:
            db.close()

        local = result["local"]
        assert local is not None
        # Not asserting a specific entry — just the half of the table.
        # The entry's content changes if the table ever grows; this
        # stays stable.
        assert any(
            local["text"] == STEADY_FORECASTS[i]
            for i in range(len(STEADY_FORECASTS) // 2, len(STEADY_FORECASTS))
        ), f"got '{local['text']}'; expected the stormy half of the table"


class TestPollerPressureTrendCallerRegression:
    """``Poller._get_pressure_trend`` reads rows directly from
    ``sensor_readings`` and hands them to ``analyze_pressure_trend``.
    Driving it with tenths-hPa DB rows is the only way to catch a
    dropped conversion in the poller method itself."""

    def test_real_rise_classifies_as_rising(self, fresh_readings):
        """1020.0 → 1022.0 hPa over ~2.5h is a clearly-rising pressure
        change.  Pre-fix the raw diff would land at 20 tenths-hPa,
        which fails the strict ``>`` threshold and reads as 'steady'.

        We stay inside the 3h window with a safety margin — a sample
        taken AT exactly ``now - 3h`` is on the knife-edge of the
        ``timestamp >= cutoff_3h`` filter and the few ms between the
        INSERT and the SELECT can push it out."""
        now = datetime.now(timezone.utc)
        db = SessionLocal()
        try:
            _add_reading(
                db,
                when=now - timedelta(hours=2, minutes=30),
                baro_tenths_hpa=10200,
            )
            _add_reading(db, when=now, baro_tenths_hpa=10220)
            db.commit()
        finally:
            db.close()

        # ``_get_pressure_trend`` touches no self state, so skipping
        # ``__init__`` (which would require a real driver) is sound.
        poller = Poller.__new__(Poller)
        trend = asyncio.run(poller._get_pressure_trend())
        assert trend == "rising", (
            f"expected 'rising' after converting the 2 hPa / ~2.5h "
            f"rise to thousandths-inHg; got '{trend}'"
        )

    def test_real_fall_classifies_as_falling(self, fresh_readings):
        """Symmetric fall case."""
        now = datetime.now(timezone.utc)
        db = SessionLocal()
        try:
            _add_reading(
                db,
                when=now - timedelta(hours=2, minutes=30),
                baro_tenths_hpa=10200,
            )
            _add_reading(db, when=now, baro_tenths_hpa=10180)
            db.commit()
        finally:
            db.close()

        poller = Poller.__new__(Poller)
        trend = asyncio.run(poller._get_pressure_trend())
        assert trend == "falling", f"expected 'falling'; got '{trend}'"


# ---------------------------------------------------------------------------
# Algorithm-level documentation tests — these catch unit drift in the
# algorithm modules themselves, independent of the caller fixes.
# ---------------------------------------------------------------------------


class TestZambrettiAlgorithmUnit:
    """Documents the inputs ``zambretti_forecast`` expects."""

    def test_high_pressure_lands_in_fine_bucket(self):
        """30.18 inHg at steady trend is fair weather."""
        result = zambretti_forecast(
            pressure_thousandths=hpa_tenths_to_inhg_thousandths(10220),
            pressure_change_3h=0,
            wind_dir_deg=None,
            month=10,
        )
        assert result.trend == "steady"
        assert "Stormy" not in result.forecast_text
        assert result.z_number <= len(STEADY_FORECASTS) // 2 - 1

    def test_low_pressure_lands_in_stormy_bucket(self):
        """28.94 inHg at steady trend is nor'easter territory."""
        result = zambretti_forecast(
            pressure_thousandths=hpa_tenths_to_inhg_thousandths(9800),
            pressure_change_3h=0,
            wind_dir_deg=None,
            month=10,
        )
        assert result.trend == "steady"
        assert result.z_number >= len(STEADY_FORECASTS) // 2


class TestPressureTrendAlgorithmUnit:
    """Pins the strict ``>``/``<`` behavior of the trend classifier at
    its exact threshold values.  Lives at the algorithm level so the
    contract is documented at the point of definition — a future
    threshold change would also need to update these."""

    def _result(self, change_thousandths: int):
        now = time.time()
        return analyze_pressure_trend([
            (now - 10800, 30000),
            (now, 30000 + change_thousandths),
        ])

    def test_rise_at_threshold_is_steady(self):
        """``+TREND_THRESHOLD`` exactly equals the cut — the strict
        ``>`` keeps it in the steady bucket."""
        assert self._result(TREND_THRESHOLD).trend == "steady"

    def test_rise_one_over_threshold_is_rising(self):
        """``+TREND_THRESHOLD+1`` crosses; classifier flips to rising."""
        assert self._result(TREND_THRESHOLD + 1).trend == "rising"

    def test_fall_at_threshold_is_steady(self):
        """Symmetric to the rising case at the negative threshold."""
        assert self._result(-TREND_THRESHOLD).trend == "steady"

    def test_fall_one_under_threshold_is_falling(self):
        assert self._result(-TREND_THRESHOLD - 1).trend == "falling"
