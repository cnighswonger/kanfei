"""Regression tests for the WeatherLink settings panel on non-legacy
drivers (#219).

Both config handlers gated on `isinstance(driver, LinkDriver)`, so the
whole settings panel was dead on Vantage stations — and the failure came
back as HTTP 200 with an error body, so the UI could not tell success
from failure.
"""

import pytest

from app.protocol.base import (
    CAP_ARCHIVE_PERIOD_RW,
    CAP_SAMPLE_PERIOD_RW,
    CAP_CALIBRATION_RW,
)
from app.protocol.link_driver import LinkDriver
from app.protocol.vantage.driver import VantageDriver


class TestCapabilityDeclarations:
    def test_legacy_declares_both_periods(self):
        caps = LinkDriver("/dev/null").capabilities
        assert CAP_ARCHIVE_PERIOD_RW in caps
        assert CAP_SAMPLE_PERIOD_RW in caps

    def test_vantage_declares_archive_period(self):
        """SETPER — added in #217."""
        assert CAP_ARCHIVE_PERIOD_RW in VantageDriver("/dev/null", 19200).capabilities

    def test_vantage_does_not_claim_sample_period(self):
        """'Sample period' is a WeatherLink concept with no Vantage
        equivalent — claiming it would be the #209 mistake again."""
        assert CAP_SAMPLE_PERIOD_RW not in VantageDriver("/dev/null", 19200).capabilities

    def test_legacy_capabilities_unchanged(self):
        """The legacy station is the one in production; guard it."""
        caps = LinkDriver("/dev/null").capabilities
        for expected in ("archive_sync", "calibration_rw", "clock_sync",
                         "rain_reset", "hilows"):
            assert expected in caps


class TestVantageArchivePeriod:
    def test_read_archive_period_exists(self):
        """Was missing entirely; the panel had nothing to display."""
        drv = VantageDriver("/dev/null", 19200)
        assert hasattr(drv, "read_archive_period")
        assert hasattr(drv, "async_read_archive_period")

    @pytest.mark.parametrize("bad", [0, 2, 7, 45, 121, 255])
    def test_set_archive_period_rejects_illegal_values(self, bad):
        """Davis honours only {1,5,10,15,30,60,120} — see #174."""
        drv = VantageDriver("/dev/null", 19200)
        with pytest.raises(ValueError):
            drv.set_archive_period(bad)

    @pytest.mark.parametrize("good", [1, 5, 10, 15, 30, 60, 120])
    def test_legal_values_pass_validation(self, good):
        """Reaches the port (and fails there), rather than being rejected."""
        drv = VantageDriver("/dev/null", 19200)
        try:
            drv.set_archive_period(good)
        except ValueError as exc:
            pytest.fail(f"legal period {good} rejected: {exc}")
        except Exception:
            pass          # port I/O failure is expected on /dev/null


class TestCapabilityInference:
    """_driver_caps falls back to method presence so a driver that predates
    the CAP_*_RW flags is not treated as supporting nothing."""

    def test_driver_without_declared_flags_is_still_usable(self):
        import logger_main

        class Bare:
            connected = True
            capabilities = set()
            station_name = "Bare"

            async def async_set_archive_period(self, m): return True
            async def async_read_archive_period(self): return 5

        d = logger_main.LoggerDaemon()
        d.driver = Bare()
        caps = d._driver_caps()
        assert CAP_ARCHIVE_PERIOD_RW in caps, "method-based fallback failed"
        assert CAP_SAMPLE_PERIOD_RW not in caps
        assert CAP_CALIBRATION_RW not in caps

    def test_disconnected_driver_reports_nothing(self):
        import logger_main

        class Off:
            connected = False
            capabilities = {CAP_ARCHIVE_PERIOD_RW}

        d = logger_main.LoggerDaemon()
        d.driver = Off()
        assert d._driver_caps() == set()
