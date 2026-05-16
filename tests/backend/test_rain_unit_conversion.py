"""Tests for the rain accumulator register → mm conversion.

The legacy LinkDriver previously did `register / 10.0` to produce mm,
which happened to be correct only when rain_cal=254.  The fix uses the
documented Davis relationship `inches = register / rain_cal` (where
rain_cal = clicks per inch), giving `mm = register * 25.4 / rain_cal`.
"""

import pytest

from app.protocol.link_driver import _rain_register_to_mm


class TestRainRegisterToMm:

    def test_davis_default_rain_cal_one_inch(self):
        # rain_cal=100 is Davis's default for the standard 0.01" tipping
        # bucket.  1.00 inch of real rain = 100 register value = 25.4 mm.
        assert _rain_register_to_mm(100, 100) == pytest.approx(25.4)

    def test_davis_default_rain_cal_half_inch(self):
        assert _rain_register_to_mm(50, 100) == pytest.approx(12.7)

    def test_workaround_rain_cal_254_matches_old_buggy_output(self):
        # The "rain_cal=254" workaround value is the only setting where
        # the previous /10 formula coincidentally produced correct mm.
        # The new formula must agree with the old buggy formula at this
        # specific value (preserves correctness for users who took the
        # workaround before the fix landed).
        for register in (100, 254, 1000, 0):
            assert _rain_register_to_mm(register, 254) == pytest.approx(register / 10.0)

    def test_correction_factor_against_default(self):
        # At default rain_cal=100, the new formula yields 2.54× the old
        # formula's output.  This is the magnitude of the under-report
        # the pre-fix code was producing.
        register = 100  # one inch of rain
        old_output = register / 10.0  # what the buggy code reported
        new_output = _rain_register_to_mm(register, 100)
        assert new_output == pytest.approx(old_output * 2.54)

    def test_metric_bucket_rain_cal_127(self):
        # 0.2 mm tipping bucket: 1 inch = 25.4 mm = 127 clicks at 0.2 mm/click.
        # For 1 inch of real rain, register would read 127.
        assert _rain_register_to_mm(127, 127) == pytest.approx(25.4)

    def test_none_register_returns_none(self):
        assert _rain_register_to_mm(None, 100) is None

    def test_zero_register_returns_zero(self):
        # No rain is a valid reading, not a sentinel.
        assert _rain_register_to_mm(0, 100) == 0.0

    def test_zero_rain_cal_falls_back_to_default(self):
        # A bad calibration read returning 0 should not divide-by-zero
        # the entire poll path.  Fall back to Davis default 100.
        assert _rain_register_to_mm(100, 0) == pytest.approx(25.4)

    def test_negative_rain_cal_falls_back_to_default(self):
        assert _rain_register_to_mm(100, -5) == pytest.approx(25.4)
