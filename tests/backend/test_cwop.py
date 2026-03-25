"""Tests for CWOP upload service pure logic."""

from app.services.cwop import aprs_passcode, _extract


class TestAprsPasscode:

    def test_cwop_callsign_returns_minus_one(self):
        assert aprs_passcode("CW1234") == "-1"
        assert aprs_passcode("DW5678") == "-1"
        assert aprs_passcode("EW9999") == "-1"

    def test_empty_callsign_returns_minus_one(self):
        assert aprs_passcode("") == "-1"
        assert aprs_passcode("  ") == "-1"

    def test_ham_callsign_exact_hash(self):
        assert aprs_passcode("N0CALL") == "13023"

    def test_case_insensitive(self):
        assert aprs_passcode("n0call") == "13023"

    def test_strips_ssid(self):
        # N0CALL-13 should hash same as N0CALL
        assert aprs_passcode("N0CALL-13") == "13023"

    def test_known_callsign_w3ado(self):
        assert aprs_passcode("W3ADO") == "10901"


class TestExtract:

    def test_simple_path(self):
        data = {"a": {"b": {"c": 42}}}
        assert _extract(data, ("a", "b", "c")) == 42

    def test_missing_key_returns_none(self):
        data = {"a": {"b": 1}}
        assert _extract(data, ("a", "x")) is None

    def test_single_key(self):
        data = {"temp": 72}
        assert _extract(data, ("temp",)) == 72

    def test_none_value_returns_none(self):
        data = {"a": None}
        assert _extract(data, ("a", "b")) is None

    def test_non_dict_intermediate_returns_none(self):
        data = {"a": 42}
        assert _extract(data, ("a", "b")) is None

    def test_empty_path(self):
        data = {"a": 1}
        assert _extract(data, ()) == data
