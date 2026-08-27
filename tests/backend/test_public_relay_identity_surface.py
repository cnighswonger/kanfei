"""PublicRelayDriver exposes the pushed identity via ``hw_config`` and
the last snapshot's timestamp via ``async_read_station_time``, so the
daemon's ``_h_status`` / ``_h_read_station_time`` handlers surface
Firmware, Product SKU and Console clock on the droplet's Console tile
without a public-relay branch in those handlers.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from app.protocol.base import SensorSnapshot
from app.protocol.public_relay.driver import PublicRelayDriver


def test_hw_config_reads_from_upstream_info() -> None:
    drv = PublicRelayDriver()
    drv.push_config({
        "firmware_version": "4.33",
        "firmware_date": "Apr 16 2018",
        "product_sku": "6351",
    })
    hw = drv.hw_config
    assert hw.firmware_version == "4.33"
    assert hw.firmware_date == "Apr 16 2018"
    assert hw.product_sku == "6351"


def test_hw_config_none_before_first_push() -> None:
    drv = PublicRelayDriver()
    hw = drv.hw_config
    assert hw.firmware_version is None
    assert hw.firmware_date is None
    assert hw.product_sku is None


def test_async_read_station_time_returns_push_arrival_components() -> None:
    drv = PublicRelayDriver()
    drv.push_snapshot(SensorSnapshot())
    ts = datetime(2026, 8, 27, 17, 42, 3)
    drv._last_push_at = ts.timestamp()
    result = asyncio.run(drv.async_read_station_time())
    assert result == {
        "year": 2026,
        "month": 8,
        "day": 27,
        "hour": 17,
        "minute": 42,
        "second": 3,
    }


def test_async_read_station_time_none_before_first_push() -> None:
    drv = PublicRelayDriver()
    result = asyncio.run(drv.async_read_station_time())
    assert result is None
