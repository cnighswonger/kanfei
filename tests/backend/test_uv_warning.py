"""UV Index → WHO warning band classification.

The bands are inclusive-low. Boundary values (3, 6, 8, 11) must land on
the higher band. Fractional inputs are common because Vantage reports
UVI as tenths — 2.9 is Low, 3.0 is Moderate.

Reference: WHO / WMO Global Solar UV Index, 2002 edition.
"""

import pytest

from app.services.uv_warning import classify_uv


class TestBandBoundaries:
    """Boundary values fall on the higher band (inclusive-low)."""

    def test_zero_is_low(self):
        assert classify_uv(0) == "Low"

    def test_2_999_still_low(self):
        assert classify_uv(2.999) == "Low"

    def test_3_is_moderate(self):
        assert classify_uv(3) == "Moderate"
        assert classify_uv(3.0) == "Moderate"

    def test_5_999_still_moderate(self):
        assert classify_uv(5.999) == "Moderate"

    def test_6_is_high(self):
        assert classify_uv(6) == "High"

    def test_7_999_still_high(self):
        assert classify_uv(7.999) == "High"

    def test_8_is_very_high(self):
        assert classify_uv(8) == "Very High"

    def test_10_999_still_very_high(self):
        assert classify_uv(10.999) == "Very High"

    def test_11_is_extreme(self):
        assert classify_uv(11) == "Extreme"


class TestExtreme:
    """The Extreme band has no upper cap; a UVI of 20 (rare, but recorded
    at high altitude / low latitude) still classifies."""

    def test_20_is_extreme(self):
        assert classify_uv(20) == "Extreme"


class TestNoneAndNegative:
    """None input and sentinel-negative values both return None so
    render code can distinguish 'no sensor' from a real reading."""

    def test_none_returns_none(self):
        assert classify_uv(None) is None

    def test_negative_returns_none(self):
        # Some drivers emit -1 for 'sensor not connected' before falling
        # back to None; treat that as no reading rather than a Low band.
        assert classify_uv(-1) is None
