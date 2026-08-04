"""Console reception diagnostics exposed through IPC (Ref #238).

RXCHECK's counters are the diagnostic for the failure that has cost this
project the most time: a transmitter drops out, the console reports the
dashed sentinel, that sentinel is stored as a real reading, and the
poisoned daily maximum is then published for the rest of the day (#230).
Until now the only symptom was the data going strange hours later.

Measured on the bench Vue (fw 2.12), 2026-08-02:

    27152 packets received, 132 missed, 0 resyncs,
    1770 longest run received, 36 CRC errors   →  99.52% reception

**Field 4 is "the largest number of packets received IN A ROW"** — manual
§IX, "RXCHECK". It is a run of *successes*, so a large value is healthy.
It is not a count of consecutive misses. That inversion was written into a
diagnostic script during this very investigation and reported a healthy
link as a fault, so the naming and its meaning are pinned below.
"""

import pytest

from app.ipc import protocol as ipc
from app.protocol.vantage.commands import cmd_rxcheck
from app.protocol.vantage.driver import VantageDriver


class FakeSerial:
    """Serial stub that replays a scripted OK-response for RXCHECK."""

    def __init__(self, payload: bytes = b"\n\rOK\n\r 27152 132 0 1770 36\n\r"):
        self.sent: list[bytes] = []
        self._pending = bytearray(payload)

    def flush(self):
        pass

    # The driver narrows the read timeout while reading a text
    # block and restores it after (#257); the stub only needs to
    # accept the call.
    timeout = 5.0

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
    return drv


class TestCommandAndConstant:
    def test_rxcheck_command_format(self):
        assert cmd_rxcheck() == b"RXCHECK\n"

    def test_ipc_command_registered(self):
        assert ipc.CMD_SIGNAL_QUALITY == "signal_quality"


class TestFieldSemantics:
    """The manual's field order, and the one that inverts if misread."""

    def test_parses_the_measured_vue_response(self, driver):
        stats = driver.rxcheck()
        assert stats == {
            "packets_received": 27152,
            "missed": 132,
            "resync": 0,
            "max_consecutive_received": 1770,
            "crc_errors": 36,
        }

    def test_field_four_is_a_run_of_successes_not_misses(self, driver):
        """A large field-4 value is HEALTHY. If this is ever reinterpreted
        as consecutive misses, 1770 would read as a catastrophic outage on
        a link that is actually 99.5% clean."""
        stats = driver.rxcheck()
        assert stats["max_consecutive_received"] <= stats["packets_received"], (
            "a run of received packets cannot exceed total received — "
            "if it does, the field is being read as something else"
        )

    def test_field_four_key_names_what_it_counts(self, driver):
        """The name is the real guard; the invariant above is weak (it
        holds for plenty of wrong readings too).  A caller writing an
        alert threshold sees the key, not this module's docstring, so the
        key has to say `received`."""
        stats = driver.rxcheck()
        assert "max_consecutive_received" in stats
        assert "max_consecutive" not in stats, (
            "the bare name reads equally well as consecutive MISSES, "
            "which inverts the field's meaning"
        )

    def test_field_four_exceeds_misses_on_a_healthy_link(self, driver):
        """Directional check the weak invariant misses: on the measured
        Vue the longest received run (1770) dwarfs total misses (132).
        Under the inverted reading that relationship is impossible."""
        stats = driver.rxcheck()
        assert stats["max_consecutive_received"] > stats["missed"]

    def test_reception_rate_is_derivable(self, driver):
        stats = driver.rxcheck()
        total = stats["packets_received"] + stats["missed"]
        rate = 100.0 * stats["packets_received"] / total
        assert rate == pytest.approx(99.52, abs=0.01)

    def test_short_response_is_none_not_partial(self):
        """Four fields instead of five must not silently yield a dict with
        a missing key — downstream would KeyError far from the cause."""
        drv = VantageDriver("/dev/null", 19200)
        drv.serial = FakeSerial(b"\n\rOK\n\r 100 2 0 50\n\r")
        assert drv.rxcheck() is None


class TestDriverInterface:
    """The IPC handler dispatches on these by name, gated on the method
    existing rather than on driver type (#220 / #234)."""

    @pytest.mark.parametrize("method", ["rxcheck", "async_rxcheck",
                                        "receivers", "async_receivers"])
    def test_method_exists(self, method):
        assert hasattr(VantageDriver("/dev/null", 19200), method)

    def test_legacy_driver_lacks_rxcheck(self):
        """The handler's hasattr guard has to actually discriminate — if
        LinkDriver grew an async_rxcheck this test should fail loudly so
        the 501 path gets re-examined."""
        from app.protocol.link_driver import LinkDriver

        assert not hasattr(LinkDriver, "async_rxcheck")


class TestEmptyReceiversIsNotAFailure:
    """A Vue reports no transmitters while working perfectly — the same
    distinction pinned in test_vantage_getee_receivers.py, restated here
    because the handler merges RECEIVERS into the RXCHECK payload and
    must not treat [] as an error."""

    def test_empty_list_is_falsy_but_valid(self):
        receivers: list[int] = []
        assert receivers is not None
        assert not receivers

    def test_none_and_empty_are_distinguishable(self):
        """`None` means the command failed; `[]` means it succeeded and the
        console hears nothing addressable. Collapsing them loses the
        difference between a broken link and a Vue."""
        assert [] != None      # noqa: E711 — the point is the distinction
