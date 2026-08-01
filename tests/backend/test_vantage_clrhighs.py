"""Tests for CLRHIGHS / CLRLOWS on Vantage stations (Ref #221).

Two things are being pinned down here.

First, the period argument. The manual (§IX.13) says 0/1/2 for
daily/monthly/yearly, but the docstring in this repo previously claimed
-1 meant yearly. Nothing called it, so nothing broke — but an unguarded
call would have put an undefined value on the wire. The validation tests
below exist so that claim cannot quietly come back.

Second, the blast radius. Per §II.4 there is no way to clear a single
sensor's extremum: CLRHIGHS 0 drops every daily high the console holds.
That is a protocol limit, not an implementation gap, so the tests assert
the command is built exactly as documented rather than pretending a
narrower version exists.
"""

import pytest

from app.protocol.vantage.commands import (
    CLR_PERIODS,
    CLR_PERIOD_DAILY,
    CLR_PERIOD_MONTHLY,
    CLR_PERIOD_NAMES,
    CLR_PERIOD_YEARLY,
    cmd_clrhighs,
    cmd_clrlows,
)
from app.protocol.vantage.driver import VantageDriver


class TestPeriodConstants:
    """Values come straight from the manual's own wording:
    'Clears all of the daily (0), monthly (1), or yearly (2) ...'"""

    @pytest.mark.parametrize("const,expected", [
        (CLR_PERIOD_DAILY, 0),
        (CLR_PERIOD_MONTHLY, 1),
        (CLR_PERIOD_YEARLY, 2),
    ])
    def test_period_numbers_match_the_manual(self, const, expected):
        assert const == expected

    def test_minus_one_is_not_a_period(self):
        """The old docstring claimed -1 was yearly. It never was."""
        assert -1 not in CLR_PERIODS

    def test_period_set_is_exactly_zero_one_two(self):
        assert CLR_PERIODS == frozenset({0, 1, 2})

    def test_every_period_has_a_display_name(self):
        assert set(CLR_PERIOD_NAMES) == set(CLR_PERIODS)


class TestCommandFormat:
    @pytest.mark.parametrize("period,expected", [
        (0, b"CLRHIGHS 0\n"),
        (1, b"CLRHIGHS 1\n"),
        (2, b"CLRHIGHS 2\n"),
    ])
    def test_clrhighs_wire_format(self, period, expected):
        assert cmd_clrhighs(period) == expected

    @pytest.mark.parametrize("period,expected", [
        (0, b"CLRLOWS 0\n"),
        (1, b"CLRLOWS 1\n"),
        (2, b"CLRLOWS 2\n"),
    ])
    def test_clrlows_wire_format(self, period, expected):
        assert cmd_clrlows(period) == expected

    def test_default_period_is_daily(self):
        assert cmd_clrhighs() == b"CLRHIGHS 0\n"
        assert cmd_clrlows() == b"CLRLOWS 0\n"


class TestValidation:
    """Illegal periods must be rejected before any byte reaches the port —
    the console's behaviour for out-of-range values is undocumented."""

    @pytest.mark.parametrize("bad", [-1, 3, 4, 99, -2])
    def test_clear_highs_rejects_illegal_period(self, bad):
        drv = VantageDriver("/dev/null", 19200)
        with pytest.raises(ValueError, match="CLRHIGHS period"):
            drv.clear_highs(bad)

    @pytest.mark.parametrize("bad", [-1, 3, 4, 99, -2])
    def test_clear_lows_rejects_illegal_period(self, bad):
        drv = VantageDriver("/dev/null", 19200)
        with pytest.raises(ValueError, match="CLRLOWS period"):
            drv.clear_lows(bad)

    def test_rejection_names_the_legal_set(self):
        """The error should tell the caller what IS allowed, not just that
        they were wrong."""
        drv = VantageDriver("/dev/null", 19200)
        with pytest.raises(ValueError, match=r"\[0, 1, 2\]"):
            drv.clear_highs(-1)


class TestDriverInterface:
    def test_driver_exposes_sync_and_async_variants(self):
        for name in ("clear_highs", "clear_lows",
                     "async_clear_highs", "async_clear_lows"):
            assert hasattr(VantageDriver, name), f"missing {name}"

    def test_clear_methods_default_to_daily(self):
        """A bare clear_highs() must not surprise the caller by wiping the
        year."""
        import inspect
        for meth in (VantageDriver.clear_highs, VantageDriver.clear_lows,
                     VantageDriver.async_clear_highs,
                     VantageDriver.async_clear_lows):
            sig = inspect.signature(meth)
            assert sig.parameters["period"].default == CLR_PERIOD_DAILY
