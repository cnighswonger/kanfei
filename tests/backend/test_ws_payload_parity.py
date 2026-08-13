"""WebSocket broadcast payload must include every field ``/api/current``
publishes for tile-safe consumption.

Regression: after #329-#333 landed, the WS broadcast in
``poller._snapshot_to_dict`` was hand-built and missed the new fields
(``uv_warning``, ``solar_energy_daily``, ``et_daily`` / ``et_monthly``
/ ``et_yearly``).  The frontend does a full ``setCurrentConditions(data)``
replace on every WS message, so any missing field null-shifted the tile
between REST polls — sections flickered off after each WS push and
back on at the next 5-minute REST refresh.

This test file pins the invariant: for a snapshot with all sensors
populated, the WS payload must expose the same keys the REST current
endpoint does for anything a dashboard tile needs to render without
blinking.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.poller import Poller


def _fake_snapshot() -> SimpleNamespace:
    """A snapshot with every optional field populated so we can assert
    every derived key ends up in the payload — a snapshot with sparse
    fields is covered by the individual /api/current tests."""
    return SimpleNamespace(
        inside_temp=22.0, outside_temp=24.0,
        inside_humidity=45, outside_humidity=62,
        wind_speed=3.6, wind_gust=5.2, wind_direction=225,
        barometer=1016.6,
        rain_daily=0.0, rain_yearly=25.4, rain_rate=0.0,
        solar_radiation=512,
        uv_index=5.2,
        thsw_index=25.0,
        et_daily=4.1,        # mm
        et_monthly=42.7,     # mm
        et_yearly=630.68,    # mm
        extra={},
    )


def _make_poller() -> Poller:
    """Minimal Poller instance — just enough surface for
    ``_snapshot_to_dict`` to run.  We don't need the driver, config,
    or async loop for this test."""
    p = Poller.__new__(Poller)
    p.driver = SimpleNamespace(station_name="Vantage Vue (fw 2.12)")
    p.rain_yesterday = 0.12
    return p


class TestWsPayloadIncludesRestFields:
    """Every field ``/api/current`` publishes for the Solar & UV tile
    must also appear on the WS broadcast so a WS push doesn't wipe them
    from ``setCurrentConditions``.
    """

    def test_uv_warning_present(self):
        p = _make_poller()
        payload = p._snapshot_to_dict(
            _fake_snapshot(),
            hi=None, dp=None, wc=None, fl=None, theta=None, trend=None,
            solar_energy_daily={"value": 20.37, "unit": "MJ/m²"},
        )
        assert "uv_warning" in payload
        # 5.2 → Moderate per WHO bands
        assert payload["uv_warning"] == "Moderate"

    def test_solar_energy_daily_present(self):
        p = _make_poller()
        expected = {"value": 20.37, "unit": "MJ/m²"}
        payload = p._snapshot_to_dict(
            _fake_snapshot(),
            hi=None, dp=None, wc=None, fl=None, theta=None, trend=None,
            solar_energy_daily=expected,
        )
        assert payload["solar_energy_daily"] == expected

    def test_solar_energy_daily_null_when_no_samples(self):
        p = _make_poller()
        payload = p._snapshot_to_dict(
            _fake_snapshot(),
            hi=None, dp=None, wc=None, fl=None, theta=None, trend=None,
            solar_energy_daily=None,
        )
        assert payload["solar_energy_daily"] is None

    def test_et_daily_monthly_yearly_all_present(self):
        p = _make_poller()
        payload = p._snapshot_to_dict(
            _fake_snapshot(),
            hi=None, dp=None, wc=None, fl=None, theta=None, trend=None,
            solar_energy_daily=None,
        )
        # ET fields should be {value, unit} dicts, not raw mm floats.
        assert payload["et_daily"] is not None
        assert payload["et_monthly"] is not None
        assert payload["et_yearly"] is not None
        assert "value" in payload["et_daily"]
        assert "unit" in payload["et_daily"]

    def test_et_none_when_snapshot_lacks_et(self):
        """A station that doesn't report ET (non-Vantage, or Vantage
        before the first successful LOOP1) → ET fields null, no crash."""
        snap = _fake_snapshot()
        snap.et_daily = None
        snap.et_monthly = None
        snap.et_yearly = None
        p = _make_poller()
        payload = p._snapshot_to_dict(
            snap,
            hi=None, dp=None, wc=None, fl=None, theta=None, trend=None,
            solar_energy_daily=None,
        )
        assert payload["et_daily"] is None
        assert payload["et_monthly"] is None
        assert payload["et_yearly"] is None

    def test_uv_warning_null_when_no_uv_sensor(self):
        snap = _fake_snapshot()
        snap.uv_index = None
        p = _make_poller()
        payload = p._snapshot_to_dict(
            snap,
            hi=None, dp=None, wc=None, fl=None, theta=None, trend=None,
            solar_energy_daily=None,
        )
        assert payload["uv_warning"] is None


class TestPayloadKeysMatchRestSurface:
    """Higher-level guard: the WS payload's top-level keys should be a
    superset of what the Solar & UV tile reads from `/api/current`.

    If someone adds a new tile field to the REST response and forgets
    the WS broadcast (this class of bug), this test will surface it —
    without having to run the full API TestClient."""

    REQUIRED_KEYS = {
        # Existing fields (regression guard for the whole set)
        "timestamp", "station_type", "temperature", "humidity", "wind",
        "barometer", "rain", "derived",
        "solar_radiation", "uv_index",
        # Post-#329 additions that were missing from the WS payload
        "uv_warning", "solar_energy_daily",
        "et_daily", "et_monthly", "et_yearly",
        "daily_extremes",
    }

    def test_payload_contains_every_required_key(self):
        p = _make_poller()
        payload = p._snapshot_to_dict(
            _fake_snapshot(),
            hi=None, dp=None, wc=None, fl=None, theta=None, trend=None,
            solar_energy_daily={"value": 20.37, "unit": "MJ/m²"},
        )
        missing = self.REQUIRED_KEYS - set(payload.keys())
        assert not missing, (
            f"WS payload missing keys the frontend expects: {sorted(missing)}. "
            f"When adding a new tile field to /api/current, remember to "
            f"add it here too (`_snapshot_to_dict` in poller.py) — the "
            f"frontend does a full setCurrentConditions() replace on every "
            f"WS message, so a missing field wipes the tile."
        )
