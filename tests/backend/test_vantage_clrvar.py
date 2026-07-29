"""Tests for CLRVAR rain/ET clearing on Vantage stations (#221).

The rain-clear endpoints were LinkDriver-gated, so they did nothing on
Vantage.  I recorded that in #219 as "unsupported by the protocol" on the
strength of a hasattr() check — which answers "did we implement it", not
"can the hardware do it".  The manual documents CLRVAR for exactly this.
"""

import pytest

from app.protocol.vantage.commands import (
    CLRVAR_ET_DAY,
    CLRVAR_ET_MONTH,
    CLRVAR_ET_YEAR,
    CLRVAR_NAMES,
    CLRVAR_RAIN_DAILY,
    CLRVAR_RAIN_MONTH,
    CLRVAR_RAIN_STORM,
    CLRVAR_RAIN_YEAR,
    CLRVAR_VARIABLES,
    cmd_clrvar,
)
from app.protocol.vantage.driver import VantageDriver


class TestClrvarConstants:
    """Numbers come straight from the manual's table (section IX.6)."""

    @pytest.mark.parametrize("const,expected", [
        (CLRVAR_RAIN_DAILY, 13),
        (CLRVAR_RAIN_STORM, 14),
        (CLRVAR_RAIN_MONTH, 16),
        (CLRVAR_RAIN_YEAR, 17),
        (CLRVAR_ET_MONTH, 25),
        (CLRVAR_ET_DAY, 26),
        (CLRVAR_ET_YEAR, 27),
    ])
    def test_variable_numbers_match_the_manual(self, const, expected):
        assert const == expected

    def test_fifteen_is_not_a_valid_variable(self):
        """The documented set is deliberately non-contiguous — 15 is absent,
        and the manual warns results are undefined for anything off-list."""
        assert 15 not in CLRVAR_VARIABLES

    def test_every_variable_has_a_display_name(self):
        assert set(CLRVAR_NAMES) == set(CLRVAR_VARIABLES)

    def test_command_format(self):
        assert cmd_clrvar(13) == b"CLRVAR 13\n"
        assert cmd_clrvar(17) == b"CLRVAR 17\n"


class TestClrvarValidation:
    @pytest.mark.parametrize("bad", [0, 1, 12, 15, 18, 24, 28, 99, -1])
    def test_illegal_variables_rejected_before_hitting_the_port(self, bad):
        """'Results are undefined' — so never send one."""
        drv = VantageDriver("/dev/null", 19200)
        with pytest.raises(ValueError, match="CLRVAR variable"):
            drv.clear_variable(bad)

    @pytest.mark.parametrize("good", sorted(CLRVAR_VARIABLES))
    def test_legal_variables_pass_validation(self, good):
        drv = VantageDriver("/dev/null", 19200)
        try:
            drv.clear_variable(good)
        except ValueError as exc:
            pytest.fail(f"legal variable {good} rejected: {exc}")
        except Exception:
            pass          # port I/O failure on /dev/null is expected


class TestDriverInterface:
    """The IPC handler calls these by name; they must exist and match the
    LinkDriver interface so the handler is driver-agnostic."""

    @pytest.mark.parametrize("method", [
        "clear_rain_daily", "clear_rain_yearly", "clear_variable",
        "async_clear_rain_daily", "async_clear_rain_yearly",
        "async_clear_variable",
    ])
    def test_method_exists(self, method):
        assert hasattr(VantageDriver("/dev/null", 19200), method)

    def test_interface_matches_link_driver(self):
        from app.protocol.link_driver import LinkDriver
        for m in ("async_clear_rain_daily", "async_clear_rain_yearly"):
            assert hasattr(LinkDriver, m) and hasattr(VantageDriver, m), (
                f"{m} must exist on both for the handler to stay generic"
            )
