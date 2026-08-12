"""OPMODE — undocumented Davis radio-state query.

Verified on the wire audit (see `reference/vantage_fw433_wire_audit.md`
§N3) to return an identical multi-line KEY: value block on Vue fw 2.12
and fw 4.33.

Observed on our bench (fw 4.33) in normal ops:

    TST: 0
    TX:  0
    RX:  0
    HOP: 0
    BAND: 0
    CHAN: 0
    DOM: 1
    XTLCAL: 14
    TEMP: 746
    TEMP CAL: -1

The parser normalises the wire's ``TEMP CAL`` to ``TEMP_CAL`` for dict-
key friendliness; every other key is used as-is.  Malformed
individual fields are dropped from the returned dict rather than
crashing the whole read.
"""

import pytest

from app.protocol.vantage.commands import cmd_opmode
from app.protocol.vantage.driver import VantageDriver


# Full bench-observed OPMODE response (fw 4.33) plus the quiet-read
# delay the console signals between text-block responses.  The stub's
# `receive_byte` returns None once the payload is exhausted, which
# `_read_text_block` interprets as the quiet-read that terminates the
# block.
BENCH_OPMODE_RESPONSE = (
    b"\n\rTST: 0\n\r"
    b"TX:  0\n\r"
    b"RX:  0\n\r"
    b"HOP: 0\n\r"
    b"BAND: 0\n\r"
    b"CHAN: 0\n\r"
    b"DOM: 1\n\r"
    b"XTLCAL: 14\n\r"
    b"TEMP: 746\n\r"
    b"TEMP CAL: -1\n\r\n\r"
)


class FakeSerial:
    """Serial stub that replays a scripted OPMODE response."""

    is_open = True
    timeout = 5.0

    def __init__(self, payload: bytes = BENCH_OPMODE_RESPONSE):
        self.sent: list[bytes] = []
        self._pending = bytearray(payload)

    def flush(self):
        pass

    def set_timeout(self, timeout):
        self.timeout = timeout

    def send(self, data: bytes):
        self.sent.append(data)

    def receive(self, n: int) -> bytes:
        take = self._pending[:n]
        del self._pending[:n]
        return bytes(take)

    def receive_byte(self):
        data = self.receive(1)
        return data[0] if data else None


@pytest.fixture
def driver():
    drv = VantageDriver("/dev/null", 19200)
    drv.serial = FakeSerial()
    drv._wakeup = lambda: None  # skip wakeup handshake in tests
    return drv


class TestCommandFormat:
    def test_cmd_opmode_wire_format(self):
        assert cmd_opmode() == b"OPMODE\n"


class TestBenchObservedResponse:
    """Parse the exact response we saw on the audit."""

    def test_all_ten_fields_present(self, driver):
        state = driver.read_radio_state()
        assert state is not None
        assert set(state.keys()) == {
            "TST", "TX", "RX", "HOP", "BAND", "CHAN",
            "DOM", "XTLCAL", "TEMP", "TEMP_CAL",
        }

    def test_values_match_wire_capture(self, driver):
        state = driver.read_radio_state()
        assert state["TST"] == 0
        assert state["TX"] == 0
        assert state["RX"] == 0
        assert state["HOP"] == 0
        assert state["BAND"] == 0
        assert state["CHAN"] == 0
        assert state["DOM"] == 1
        assert state["XTLCAL"] == 14
        assert state["TEMP"] == 746
        assert state["TEMP_CAL"] == -1

    def test_temp_cal_key_normalised(self, driver):
        """The wire says ``TEMP CAL:`` with a literal space.  The
        parser must fold that to ``TEMP_CAL`` because a dict key with
        an embedded space is a footgun downstream (JSON round-trips
        fine, Python attribute-access does not, and callers cannot
        write ``state.TEMP CAL``)."""
        state = driver.read_radio_state()
        assert "TEMP_CAL" in state
        assert "TEMP CAL" not in state


class TestRobustness:
    """The parser must degrade gracefully on the sort of malformed
    responses an unsupported firmware might produce."""

    def _drv(self, payload: bytes) -> VantageDriver:
        drv = VantageDriver("/dev/null", 19200)
        drv.serial = FakeSerial(payload)
        drv._wakeup = lambda: None
        return drv

    def test_empty_response_returns_none(self):
        drv = self._drv(b"")
        assert drv.read_radio_state() is None

    def test_no_parseable_fields_returns_none(self):
        # All-noise response — no colons, so nothing matches the
        # KEY: value shape.
        drv = self._drv(b"\n\r????????\n\r\n\r")
        assert drv.read_radio_state() is None

    def test_single_malformed_field_dropped_others_kept(self):
        # Two good fields plus one where the value isn't an integer.
        # The bad one must be dropped from the returned dict; the
        # good ones must still be present.
        drv = self._drv(
            b"\n\rTST: 0\n\r"
            b"XTLCAL: not_a_number\n\r"
            b"DOM: 1\n\r\n\r"
        )
        state = drv.read_radio_state()
        assert state is not None
        assert state == {"TST": 0, "DOM": 1}
        assert "XTLCAL" not in state

    def test_missing_colon_line_skipped(self):
        # A line without a colon (e.g., a header or comment) should
        # be ignored without crashing.
        drv = self._drv(
            b"\n\r=== Radio Settings ===\n\r"
            b"TST: 0\n\r"
            b"DOM: 1\n\r\n\r"
        )
        state = drv.read_radio_state()
        assert state == {"TST": 0, "DOM": 1}

    def test_wire_prefix_LF_CR_tolerated(self):
        # Different firmware versions may or may not lead with the
        # LF CR pair.  The parser reads until quiet and splits on
        # newlines, so a leading terminator is a benign no-op.
        drv = self._drv(
            b"\n\r"
            b"TST: 0\n\r"
            b"DOM: 1\n\r\n\r"
        )
        state = drv.read_radio_state()
        assert state == {"TST": 0, "DOM": 1}
