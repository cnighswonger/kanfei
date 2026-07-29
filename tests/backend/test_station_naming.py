"""Regression tests for station_type -> display name resolution (#215).

A Vantage Vue reported "Weather Wizard III" from /api/current because the
persisted code was resolved against the legacy StationModel enum alone.
"""

import pytest

from app.services.station_naming import resolve_station_name, UNKNOWN


class TestVantageNaming:
    def test_vue_is_not_reported_as_a_legacy_station(self):
        """The #215 regression: code 17 must never be 'Weather Wizard III'."""
        name = resolve_station_name(17, None, "vantage")
        assert name == "Vantage Vue"
        assert "Wizard" not in name

    def test_vantage_pro(self):
        assert resolve_station_name(16, None, "vantage") == "Vantage Pro2"

    def test_vantage_detection_failure_is_explicit(self):
        assert resolve_station_name(-1, None, "vantage") == "Vantage (unknown model)"


class TestLegacyNaming:
    def test_monitor_ii_unaffected(self):
        """Legacy stations kept working throughout; guard against regression."""
        assert resolve_station_name(2, None, "legacy") == "Weather Monitor II"

    def test_zero_is_still_a_real_legacy_station(self):
        """0 is a legitimate legacy model, which is why the bug was invisible."""
        assert resolve_station_name(0, None, "legacy") == "Weather Wizard III"

    def test_sentinel_is_not_a_legacy_station(self):
        assert resolve_station_name(-1, None, "legacy") == UNKNOWN


class TestUnknownAndSentinels:
    @pytest.mark.parametrize("driver", ["ecowitt", "tempest", "weatherlink_ip", None])
    def test_sentinel_never_claims_to_be_vantage(self, driver):
        """-1 collides with VantageModel.UNKNOWN; a non-Vantage driver must
        not be labelled 'Vantage (unknown model)'."""
        assert resolve_station_name(-1, None, driver) == UNKNOWN

    def test_null_station_type(self):
        assert resolve_station_name(None, None, "legacy") == UNKNOWN

    def test_unmappable_code(self):
        assert resolve_station_name(99, None, "vantage") == UNKNOWN

    def test_falls_back_across_both_enums_when_driver_unknown(self):
        """Older rows predate station_driver_type; both enums are tried."""
        assert resolve_station_name(17, None, None) == "Vantage Vue"
        assert resolve_station_name(2, None, None) == "Weather Monitor II"


class TestDriverModelCode:
    def test_vantage_driver_reports_its_detected_code(self):
        from logger_main import _driver_model_code, STATION_TYPE_UNKNOWN
        from app.protocol.vantage.driver import VantageDriver
        from app.protocol.vantage.constants import VantageModel

        drv = VantageDriver("/dev/null", 19200)
        drv.hw_config.station_type = VantageModel.VANTAGE_VUE
        assert _driver_model_code(drv) == 17

    def test_driver_without_hw_config_yields_sentinel(self):
        """Was 0 (= Weather Wizard III) before #215."""
        from logger_main import _driver_model_code, STATION_TYPE_UNKNOWN

        class Bare:
            pass

        assert _driver_model_code(Bare()) == STATION_TYPE_UNKNOWN
        assert STATION_TYPE_UNKNOWN != 0
