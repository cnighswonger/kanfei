"""PublicRelayDriver exposes the pushed identity via ``hw_config`` so
the daemon's ``_h_status`` handler surfaces Firmware and Product SKU
on the droplet's Console tile without a public-relay branch.

Console clock is deliberately NOT surfaced — the droplet has no way
to construct the upstream's console-clock timezone from its own
``time.time()``.  See the driver.
"""

from __future__ import annotations

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


def test_async_read_station_time_not_present() -> None:
    """The daemon's ``_h_read_station_time`` gates on
    ``hasattr(drv, 'async_read_station_time')`` — the driver must NOT
    have the attribute, so ``/api/station`` returns ``station_time:
    null`` and the Console tile renders "—".  Any implementation that
    reads from the droplet's ``time.time()`` publishes the droplet's
    timezone as if it were the operator's."""
    drv = PublicRelayDriver()
    assert not hasattr(drv, "async_read_station_time")
