"""Inside-temperature calibration writes its companion byte.

TEMP_IN_COMP (0x33) is "1's compliment of TEMP_IN_CAL to validate
calibration data" (Vantage serial reference v2.6.1, EEPROM table).

**The firmware does not actually gate on it.** Measured on fw 3.0 (bench
Vue, 2026-08-05, #273): an offset written with a deliberately wrong
complement applied in full, +4.0 °F. What makes a calibration take effect
is CALFIX, not this byte. The vendor doc is wrong here, which puts it
alongside the other cases catalogued in
`reference/vantage_dash_values.md`.

These tests therefore assert a **spec conformance** property, not a
firmware one: we write the pair the reference documents, so the two bytes
never disagree. That is worth pinning — anything that does check the
complement (other firmware, third-party tools, a future Davis change)
would see a consistent pair — but do not read these tests as evidence the
console requires it.
"""

import pytest

from app.protocol.vantage.driver import VantageDriver
from app.protocol.vantage.eeprom import (
    CAL_INSIDE_TEMP,
    CAL_INSIDE_TEMP_COMP,
    CAL_OUTSIDE_TEMP,
)


@pytest.fixture
def driver():
    drv = VantageDriver("/dev/null", 19200)
    drv._connected = True
    drv.writes = []

    def fake_write(addr, data):
        drv.writes.append((addr, bytes(data)))
        return True

    drv._eeprom_write = fake_write
    drv._eeprom_read = lambda addr, n: b"\x00" * n
    # CALED returns a plausible block; CALFIX accepts anything.
    # CALFIX_OFF_OUTSIDE_HUM is 35, so the block must be at least 36 bytes.
    drv._caled = lambda: b"\x00" * 48
    drv._calfix = lambda block: True
    return drv


def _written_to(drv, addr):
    return [data for a, data in drv.writes if a == addr]


class TestInsideTempComplement:
    @pytest.mark.parametrize("offset,expected_comp", [
        (0, 0xFF),
        (10, 0xF5),      # ~10  = -11 -> 0xF5
        (-10, 0x09),     # ~-10 = 9
        (127, 0x80),
        (-128, 0x7F),
    ])
    def test_complement_is_written(self, driver, offset, expected_comp):
        assert driver.write_calibration(CAL_INSIDE_TEMP, offset) is True

        comp = _written_to(driver, CAL_INSIDE_TEMP_COMP.address)
        assert comp, "TEMP_IN_COMP was never written"
        assert comp[-1] == bytes([expected_comp])

    def test_the_offset_itself_is_still_written(self, driver):
        driver.write_calibration(CAL_INSIDE_TEMP, 25)
        assert _written_to(driver, CAL_INSIDE_TEMP.address) == [bytes([25])]

    def test_complement_really_is_the_ones_complement(self, driver):
        """Not the two's complement, which differs by one.  The reference
        specifies 1's, so that is what we write."""
        driver.write_calibration(CAL_INSIDE_TEMP, 10)
        comp = _written_to(driver, CAL_INSIDE_TEMP_COMP.address)[-1][0]
        assert comp == (~10) & 0xFF
        assert comp != ((-10) & 0xFF), "that is the two's complement"

    def test_other_fields_do_not_write_a_complement(self, driver):
        """Only inside temperature has a companion byte; writing 0x33
        while calibrating outside temperature would corrupt the inside
        setting."""
        driver.write_calibration(CAL_OUTSIDE_TEMP, 25)
        assert _written_to(driver, CAL_INSIDE_TEMP_COMP.address) == []

    def test_a_failed_complement_write_fails_the_call(self, driver):
        """A half-written pair is the worst outcome: 0x32 holds the new
        offset while 0x33 still describes the old one, so the two
        disagree and nothing records that."""
        def fail_on_comp(addr, data):
            driver.writes.append((addr, bytes(data)))
            return addr != CAL_INSIDE_TEMP_COMP.address

        driver._eeprom_write = fail_on_comp
        assert driver.write_calibration(CAL_INSIDE_TEMP, 10) is False
