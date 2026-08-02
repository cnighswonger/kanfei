"""Tests for BARDATA parsing on Vantage stations (Ref #221).

The reference response below is a byte-for-byte capture from a Vantage Vue
(fw 2.12), not the manual's example. That distinction matters here: the
capture contains two things the manual's sample does not, and both would
break a parser written from the documentation alone.

  * Keys contain spaces — "DEW POINT", "VIRTUAL TEMP" — so a line must be
    split on its LAST space. Splitting on the first yields key="DEW" and
    a value of "POINT 80".
  * OFFSET came back NEGATIVE (-44). Every value in the manual's example
    is positive, so an unsigned parse looks correct right up until it
    meets a console like this one.
"""

import pytest

from app.protocol.vantage.bardata import (
    BarometerCalibration,
    parse_bardata,
)
from app.protocol.vantage.commands import cmd_bardata

# Captured from the bench Vue, 2026-08-01. LF CR line endings, as sent.
REAL_RESPONSE = (
    "\n\rOK\n\rBAR 29916\n\rELEVATION 265\n\rDEW POINT 80\n\r"
    "VIRTUAL TEMP 74\n\rC 69\n\rR 1007\n\rBARCAL 50\n\rGAIN 0\n\r"
    "OFFSET -44\n\r"
)


def test_command_format():
    assert cmd_bardata() == b"BARDATA\n"


class TestRealResponse:
    """Every assertion here is against values a real console produced."""

    @pytest.fixture
    def cal(self):
        return parse_bardata(REAL_RESPONSE)

    def test_parses(self, cal):
        assert cal is not None
        assert isinstance(cal, BarometerCalibration)

    def test_barometer_scaled_from_thousandths(self, cal):
        assert cal.barometer_inhg == pytest.approx(29.916)

    def test_elevation_is_plain_feet(self, cal):
        assert cal.elevation_ft == 265

    def test_multi_word_keys_parse(self, cal):
        """The failure mode of splitting on the first space."""
        assert cal.dew_point_f == 80
        assert cal.virtual_temp_f == 74

    def test_correction_ratio_scaled(self, cal):
        assert cal.correction_ratio == pytest.approx(1.007)

    def test_barcal_scaled_from_thousandths(self, cal):
        assert cal.barcal_inhg == pytest.approx(0.050)

    def test_humidity_correction(self, cal):
        assert cal.humidity_correction == 69

    def test_negative_offset(self, cal):
        """The manual's example never shows a negative. This console does."""
        assert cal.offset == -44

    def test_gain_zero_is_preserved_not_dropped(self, cal):
        """0 is a real reported value, not a missing field."""
        assert cal.gain == 0

    def test_raw_keeps_every_key_as_reported(self, cal):
        assert cal.raw["BAR"] == 29916
        assert cal.raw["OFFSET"] == -44
        assert cal.raw["DEW POINT"] == 80
        assert len(cal.raw) == 9

    def test_ok_line_is_not_a_field(self, cal):
        assert "OK" not in cal.raw


class TestScaling:
    """Only BAR, R and BARCAL are thousandths; the rest are plain."""

    def test_only_documented_fields_are_scaled(self):
        cal = parse_bardata(
            "OK\n\rBAR 30000\n\rELEVATION 1000\n\rR 1000\n\rBARCAL 1000\n\r"
            "DEW POINT 1000\n\rC 1000\n\r"
        )
        assert cal.barometer_inhg == pytest.approx(30.0)
        assert cal.correction_ratio == pytest.approx(1.0)
        assert cal.barcal_inhg == pytest.approx(1.0)
        # not scaled
        assert cal.elevation_ft == 1000
        assert cal.dew_point_f == 1000
        assert cal.humidity_correction == 1000

    def test_negative_barcal_scales_with_sign(self):
        cal = parse_bardata("OK\n\rBARCAL -125\n\r")
        assert cal.barcal_inhg == pytest.approx(-0.125)


class TestLineEndings:
    """The console sends LF CR. Do not depend on that order."""

    @pytest.mark.parametrize("sep", ["\n\r", "\r\n", "\n", "\r"])
    def test_all_line_ending_styles(self, sep):
        resp = sep.join(["", "OK", "BAR 29916", "ELEVATION 265", ""])
        cal = parse_bardata(resp)
        assert cal is not None
        assert cal.barometer_inhg == pytest.approx(29.916)
        assert cal.elevation_ft == 265


class TestDegradedResponses:
    def test_empty_response_is_none(self):
        assert parse_bardata("") is None

    def test_response_with_no_fields_is_none(self):
        assert parse_bardata("\n\rOK\n\r") is None

    def test_partial_response_keeps_what_arrived(self):
        """A console omitting fields should not cost us the rest."""
        cal = parse_bardata("OK\n\rBAR 29916\n\rELEVATION 265\n\r")
        assert cal is not None
        assert cal.barometer_inhg == pytest.approx(29.916)
        assert cal.elevation_ft == 265
        assert cal.offset is None
        assert cal.gain is None

    def test_garbage_lines_skipped_not_fatal(self):
        cal = parse_bardata(
            "OK\n\rBAR 29916\n\r<<garbage>>\n\rELEVATION 265\n\r"
        )
        assert cal is not None
        assert cal.barometer_inhg == pytest.approx(29.916)
        assert cal.elevation_ft == 265

    def test_non_integer_value_skipped(self):
        cal = parse_bardata("OK\n\rBAR ABC\n\rELEVATION 265\n\r")
        assert cal is not None
        assert cal.barometer_inhg is None
        assert cal.elevation_ft == 265


class TestDriverInterface:
    def test_driver_exposes_sync_and_async(self):
        from app.protocol.vantage.driver import VantageDriver
        assert hasattr(VantageDriver, "bardata")
        assert hasattr(VantageDriver, "async_bardata")

    def test_multiline_reader_exists(self):
        """BARDATA needs a reader that does not stop at the first payload
        line, unlike _read_ok_response()."""
        from app.protocol.vantage.driver import VantageDriver
        assert hasattr(VantageDriver, "_read_text_block")
