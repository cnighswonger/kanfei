"""Tests for PUTRAIN and PUTET (Ref #221).

These two commands sit adjacent in the manual, read almost identically,
and take DIFFERENT UNITS:

    PUTRAIN <yearly rain in RAIN CLICKS>
    PUTET   <yearly ET in HUNDREDTHS OF AN INCH>

Worse, a rain click is not a fixed size — 0.01", 0.2 mm or 0.1 mm
depending on the collector fitted (EEPROM setup bits, 0x2B). So the same
integer means different rainfall totals on different stations, and a
caller who assumes a shared unit or a fixed click size silently sets a
yearly total that is wrong by a factor of two or more.

Both driver wrappers therefore take millimetres — the unit this codebase
uses for rain everywhere else — and convert. The tests below pin the
conversions against the manual's own worked example and against each
collector type.
"""

import pytest

from app.protocol.vantage.commands import cmd_putet, cmd_putrain
from app.protocol.vantage.constants import RAIN_CLICK_INCHES
from app.protocol.vantage.driver import VantageDriver


class _RecordingDriver(VantageDriver):
    """Captures what would go on the wire."""

    def __init__(self, click_inches: float = 0.01):
        super().__init__("/dev/null", 19200)
        self.sent: list[bytes] = []
        self.status_ok = True
        self.hw_config.rain_click_inches = click_inches
        self._wakeup = lambda: None

        class _S:
            is_open = True

            def flush(_s):
                pass

            def send(_s, data):
                self.sent.append(data)

            def receive(_s, n):
                return b""

            def receive_byte(_s):
                return None

        self.serial = _S()

    def _read_status_reply(self, timeout_reads=24):
        return self.status_ok


class TestCommandFormat:
    def test_putrain_wire_format(self):
        assert cmd_putrain(2483) == b"PUTRAIN 2483\n"

    def test_putet_wire_format(self):
        assert cmd_putet(2483) == b"PUTET 2483\n"

    def test_manual_worked_example(self):
        """The manual sets 24.83 inches on a 0.01" collector as
        'PUTRAIN 2483'."""
        assert cmd_putrain(2483) == b"PUTRAIN 2483\n"

    def test_zero_is_expressible(self):
        """Setting a yearly total to zero is a legitimate operation —
        it must not be confused with 'no value'."""
        assert cmd_putrain(0) == b"PUTRAIN 0\n"
        assert cmd_putet(0) == b"PUTET 0\n"


class TestRainClickConversion:
    """The load-bearing part: mm -> clicks depends on the collector."""

    def test_imperial_collector(self):
        """0.01" per click. 24.83 in = 630.68 mm -> 2483 clicks, matching
        the manual's example."""
        drv = _RecordingDriver(click_inches=0.01)
        assert drv.set_yearly_rain(630.68) is True
        assert drv.sent[-1] == b"PUTRAIN 2483\n"

    def test_metric_02mm_collector(self):
        """0.2 mm per click: 100 mm -> 500 clicks."""
        drv = _RecordingDriver(click_inches=RAIN_CLICK_INCHES[1])
        drv.set_yearly_rain(100.0)
        assert drv.sent[-1] == b"PUTRAIN 500\n"

    def test_metric_01mm_collector(self):
        """0.1 mm per click: 100 mm -> 1000 clicks."""
        drv = _RecordingDriver(click_inches=RAIN_CLICK_INCHES[2])
        drv.set_yearly_rain(100.0)
        assert drv.sent[-1] == b"PUTRAIN 1000\n"

    def test_same_mm_gives_different_clicks_per_collector(self):
        """This is exactly the bug the wrapper exists to prevent: an
        unconverted click count would be wrong by 2x between these two."""
        metric_02 = _RecordingDriver(click_inches=RAIN_CLICK_INCHES[1])
        metric_01 = _RecordingDriver(click_inches=RAIN_CLICK_INCHES[2])
        metric_02.set_yearly_rain(100.0)
        metric_01.set_yearly_rain(100.0)
        assert metric_02.sent[-1] != metric_01.sent[-1]

    def test_refuses_when_collector_unknown(self):
        """Better to fail than to guess and store a wrong yearly total."""
        drv = _RecordingDriver()
        drv.hw_config.rain_click_inches = 0
        assert drv.set_yearly_rain(100.0) is False
        assert drv.sent == []

    def test_zero_clears_the_total(self):
        drv = _RecordingDriver(click_inches=0.01)
        assert drv.set_yearly_rain(0.0) is True
        assert drv.sent[-1] == b"PUTRAIN 0\n"

    def test_negative_rejected(self):
        drv = _RecordingDriver()
        with pytest.raises(ValueError, match="cannot be negative"):
            drv.set_yearly_rain(-1.0)
        assert drv.sent == []


class TestEtConversion:
    """ET is hundredths of an inch, fixed — no collector dependency."""

    def test_hundredths_of_an_inch(self):
        """24.83 in = 630.68 mm -> 2483 hundredths."""
        drv = _RecordingDriver()
        assert drv.set_yearly_et(630.68) is True
        assert drv.sent[-1] == b"PUTET 2483\n"

    def test_one_inch(self):
        drv = _RecordingDriver()
        drv.set_yearly_et(25.4)
        assert drv.sent[-1] == b"PUTET 100\n"

    def test_et_ignores_collector_size(self):
        """PUTRAIN's unit depends on the collector; PUTET's does not.
        Same mm through both collectors must give the same ET command."""
        a = _RecordingDriver(click_inches=RAIN_CLICK_INCHES[1])
        b = _RecordingDriver(click_inches=RAIN_CLICK_INCHES[2])
        a.set_yearly_et(100.0)
        b.set_yearly_et(100.0)
        assert a.sent[-1] == b.sent[-1]

    def test_negative_rejected(self):
        drv = _RecordingDriver()
        with pytest.raises(ValueError, match="cannot be negative"):
            drv.set_yearly_et(-1.0)
        assert drv.sent == []


class TestUnitsAreNotShared:
    """The adjacency trap: same mm must NOT produce the same integer."""

    def test_rain_and_et_differ_for_the_same_millimetres(self):
        drv = _RecordingDriver(click_inches=RAIN_CLICK_INCHES[1])  # 0.2mm
        drv.set_yearly_rain(100.0)
        rain_cmd = drv.sent[-1]
        drv.set_yearly_et(100.0)
        et_cmd = drv.sent[-1]
        rain_n = int(rain_cmd.split()[1])
        et_n = int(et_cmd.split()[1])
        assert rain_n != et_n, (
            "PUTRAIN and PUTET take different units; identical numbers "
            "for the same millimetres means a conversion was skipped"
        )


class TestFailureReporting:
    def test_rain_reports_console_refusal(self):
        drv = _RecordingDriver()
        drv.status_ok = False
        assert drv.set_yearly_rain(100.0) is False

    def test_et_reports_console_refusal(self):
        drv = _RecordingDriver()
        drv.status_ok = False
        assert drv.set_yearly_et(100.0) is False


class TestDriverInterface:
    @pytest.mark.parametrize("name", [
        "set_yearly_rain", "set_yearly_et",
        "async_set_yearly_rain", "async_set_yearly_et",
    ])
    def test_exposed(self, name):
        assert hasattr(VantageDriver, name), f"missing {name}"
