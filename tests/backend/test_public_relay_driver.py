"""Public-relay driver — the no-I/O driver that powers the public droplet.

The driver holds a single in-memory snapshot buffer that ``poll()``
returns.  Phase 1 (issue #336) ships the stub; Phase 2 wires the ingest
endpoints that call ``push_snapshot``.  These tests pin the stub's shape
so the ingest wiring in Phase 2 has a stable target.
"""

import asyncio

import pytest

from app.protocol.base import SensorSnapshot
from app.protocol.public_relay.driver import STATION_NAME, PublicRelayDriver


class TestBuffering:
    def test_poll_returns_none_before_first_push(self):
        drv = PublicRelayDriver()
        assert asyncio.run(drv.poll()) is None

    def test_push_snapshot_then_poll_returns_it(self):
        drv = PublicRelayDriver()
        snap = SensorSnapshot(outside_temp=22.5, outside_humidity=55)
        drv.push_snapshot(snap)
        got = asyncio.run(drv.poll())
        assert got is snap

    def test_repeated_push_overwrites_buffer(self):
        drv = PublicRelayDriver()
        drv.push_snapshot(SensorSnapshot(outside_temp=10.0))
        drv.push_snapshot(SensorSnapshot(outside_temp=20.0))
        got = asyncio.run(drv.poll())
        assert got.outside_temp == 20.0


class TestLifecycle:
    def test_connect_is_a_no_op_and_sets_connected(self):
        drv = PublicRelayDriver()
        assert drv.connected is False
        asyncio.run(drv.connect())
        assert drv.connected is True

    def test_disconnect_clears_connected(self):
        async def _cycle(d):
            await d.connect()
            await d.disconnect()

        drv = PublicRelayDriver()
        asyncio.run(_cycle(drv))
        assert drv.connected is False

    def test_capabilities_are_empty(self):
        """A public droplet holds no hardware — every capability-gated
        write endpoint must be a 501/403, never accidentally succeed."""
        assert PublicRelayDriver().capabilities == set()

    def test_station_name_default(self):
        assert PublicRelayDriver().station_name == STATION_NAME

    def test_station_name_carries_upstream_identity(self):
        drv = PublicRelayDriver()
        drv.push_config({"station_name": "Vantage Vue (fw 2.12)"})
        assert STATION_NAME in drv.station_name
        assert "Vantage Vue" in drv.station_name


class TestLoggerFactoryBranch:
    def test_create_driver_returns_public_relay_instance(self):
        """The logger daemon's ``_create_driver`` factory must recognise
        ``public_relay`` and return a ``PublicRelayDriver`` — otherwise
        selecting the driver in the setup wizard would raise
        ``Unknown driver type``."""
        import sys
        from pathlib import Path
        # logger_main.py lives at backend/logger_main.py (not under app/)
        backend_dir = Path(__file__).resolve().parents[2] / "backend"
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        from logger_main import _create_driver

        drv = _create_driver("public_relay", config={})
        assert isinstance(drv, PublicRelayDriver)
