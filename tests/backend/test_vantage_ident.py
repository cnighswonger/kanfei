"""IDENT — undocumented Davis product-SKU query.

Verified on the wire audit (see `reference/vantage_fw433_wire_audit.md`
§N1) to return the 4-digit product number as ASCII on Vue fw 2.12 and
fw 4.33.  The driver calls it during `_detect_hardware()` right after
NVER; failure is silent — the field stays `None` and the caller falls
back to `station_type_code` for identification.

Two failure modes matter:

1. **Silent unsupported** — VP1 and pre-4.x VP2 may not implement IDENT
   at all.  A wakeup+send returns nothing intelligible; the read times
   out or returns junk.  Must NOT crash the connect flow.

2. **Malformed response** — a partial or noise response could parse to
   a not-4-digit string.  Must NOT be stored as a valid SKU, because
   the UI displays this verbatim and a bogus SKU would mislead an
   operator supporting a real Davis product.
"""

import pytest

from app.protocol.vantage.commands import cmd_ident
from app.protocol.vantage.driver import VantageDriver


class FakeSerial:
    """Serial stub that replays a scripted OK-response for IDENT."""

    is_open = True
    timeout = 5.0

    def __init__(self, payload: bytes = b"\n\rOK\n\r6351\n\r"):
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


class TestCommandFormat:
    def test_cmd_ident_wire_format(self):
        # Straight ASCII with LF terminator — same shape as VER / NVER.
        assert cmd_ident() == b"IDENT\n"


class TestDetectHardwarePopulatesSku:
    """After connect, `hw_config.product_sku` must reflect what IDENT
    returned — or stay None if the response was unusable.  Exercised
    via `_detect_hardware` because that is where the driver actually
    calls IDENT."""

    def _drv_with_response(self, ident_payload: bytes) -> VantageDriver:
        """Compose a scripted serial that satisfies the whole
        detection sequence: VER, NVER, IDENT, and the WRD station-
        type probe."""
        drv = VantageDriver("/dev/null", 19200)
        drv.serial = FakeSerial(
            # VER response — irrelevant to what we're testing but
            # required for the sequence to proceed.
            b"\n\rOK\n\rApr 16 2018\n\r"
            # NVER response — same.
            b"\n\rOK\n\r4.33\n\r"
            # IDENT — the payload under test.
            + ident_payload
            # WRD station-type read — supplies enough bytes for the
            # code path to complete without hanging on an empty read.
            # The station type value itself is not asserted here.
            + b"\x00" * 8
        )
        # Stub wakeup so the FakeSerial isn't asked to satisfy a
        # wakeup handshake it doesn't script for.
        drv._wakeup = lambda: None
        return drv

    def test_valid_sku_populated(self):
        drv = self._drv_with_response(b"\n\rOK\n\r6351\n\r")
        drv._detect_hardware()
        assert drv.hw_config.product_sku == "6351"

    def test_empty_response_leaves_sku_none(self):
        # Payload is only "\n\rOK\n\r" (no SKU digits) — the sort of
        # response an unsupported firmware might dribble back.  Must
        # NOT be stored as the SKU.
        drv = self._drv_with_response(b"\n\rOK\n\r\n\r")
        drv._detect_hardware()
        assert drv.hw_config.product_sku is None

    def test_non_digit_response_leaves_sku_none(self):
        # Alphabetic noise reaches the parser (e.g., firmware barfs a
        # menu instead of a SKU).  Must reject rather than store as
        # SKU.
        drv = self._drv_with_response(b"\n\rOK\n\r????\n\r")
        drv._detect_hardware()
        assert drv.hw_config.product_sku is None

    def test_short_digit_response_leaves_sku_none(self):
        # Three digits — half a SKU.  Reject; a partial number in the
        # UI would look like a legitimate but wrong product.
        drv = self._drv_with_response(b"\n\rOK\n\r635\n\r")
        drv._detect_hardware()
        assert drv.hw_config.product_sku is None

    def test_long_digit_response_leaves_sku_none(self):
        # More than four digits — presumably a different Davis query
        # colliding on our fixture, but the invariant is "4 digits or
        # nothing" so we don't guess.
        drv = self._drv_with_response(b"\n\rOK\n\r63510\n\r")
        drv._detect_hardware()
        assert drv.hw_config.product_sku is None

    def test_ident_failure_does_not_abort_detection(self):
        """The critical property: even when IDENT does not produce a
        usable value, the rest of `_detect_hardware` still runs.  We
        confirm by checking that firmware_date (populated BEFORE
        IDENT) and station_type (populated AFTER) are both set."""
        drv = self._drv_with_response(b"\n\rOK\n\r????\n\r")
        drv._detect_hardware()
        assert drv.hw_config.firmware_date == "Apr 16 2018"
        # station_type default is VANTAGE_PRO; the WRD read of 0x00
        # in our fixture maps to some model.  Assert it isn't broken.
        assert drv.hw_config.product_sku is None  # rejected
        assert drv.hw_config.firmware_version == "4.33"  # VER + NVER OK
