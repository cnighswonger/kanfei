"""Firmware version + date in _h_status.

The Vantage driver already caches firmware_version and firmware_date on
its hw_config at connect (VER + NVER during _detect_hardware).  The
status handler just needs to surface those cached values so the
frontend can show them, and treat a legacy driver's absence of hw_config
as `None` rather than crashing.
"""

import pytest


def _daemon(driver):
    from logger_main import LoggerDaemon
    daemon = LoggerDaemon.__new__(LoggerDaemon)
    daemon.driver = driver
    daemon.poller = None
    return daemon


def _vantage_with_firmware(version=None, date=None):
    from app.protocol.vantage.driver import VantageDriver

    drv = VantageDriver("/dev/null", 19200)
    drv._connected = False  # doesn't matter for _h_status
    drv.hw_config.firmware_version = version
    drv.hw_config.firmware_date = date if date is not None else ""
    return drv


@pytest.mark.asyncio
async def test_firmware_version_populated_from_hw_config():
    drv = _vantage_with_firmware(version="1.90", date="Aug 15 2013")
    result = await _daemon(drv)._h_status({})
    assert result["firmware_version"] == "1.90"
    assert result["firmware_date"] == "Aug 15 2013"


@pytest.mark.asyncio
async def test_vp1_reports_only_date_no_version():
    # VP1: VER works, NVER does not.  hw_config.firmware_version is None,
    # firmware_date holds the VER string.
    drv = _vantage_with_firmware(version=None, date="Nov 22 2005")
    result = await _daemon(drv)._h_status({})
    assert result["firmware_version"] is None
    assert result["firmware_date"] == "Nov 22 2005"


@pytest.mark.asyncio
async def test_empty_date_becomes_null():
    # firmware_date starts as "" per the dataclass default and only gets
    # populated once _detect_hardware runs.  A blank string reads as
    # "unset", not "blank date"; report it as None so the UI hides the
    # firmware row rather than showing a value the operator can't
    # interpret.
    drv = _vantage_with_firmware(version=None, date="")
    result = await _daemon(drv)._h_status({})
    assert result["firmware_version"] is None
    assert result["firmware_date"] is None


@pytest.mark.asyncio
async def test_legacy_driver_reports_null_firmware():
    # LinkDriver has no hw_config with firmware fields.  Must not crash
    # and must surface both values as None so the frontend hides the row.
    from app.protocol.link_driver import LinkDriver

    drv = LinkDriver("/dev/null", 2400)
    drv._connected = False
    result = await _daemon(drv)._h_status({})
    assert result["firmware_version"] is None
    assert result["firmware_date"] is None


@pytest.mark.asyncio
async def test_no_driver_reports_null_firmware():
    daemon = _daemon(None)
    result = await daemon._h_status({})
    assert result["firmware_version"] is None
    assert result["firmware_date"] is None
