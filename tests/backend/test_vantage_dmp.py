"""Tests for DMP — full archive download (Ref #221).

DMP and DMPAFT share the paged transfer in §X.6, so the page/retry/CRC
loop is now factored into _read_archive_pages() and both call it. That
shared code carries two details that were expensive to get right the
first time, and the tests below pin them so a future edit cannot quietly
undo either:

  * A NAK asks the station to resend the SAME page. The loop counter must
    not advance on failure, or the stream desynchronises from the station.
  * An ESC is required to abort cleanly. Walking away mid-transfer leaves
    the station still sending.

The difference between the two commands is the header: DMPAFT negotiates
a page count, DMP just starts streaming, so DMP supplies the fixed
archive size instead.
"""

import struct

import pytest

from app.protocol.crc import crc_calculate
from app.protocol.vantage.commands import cmd_dmp
from app.protocol.vantage.constants import (
    ACK,
    ARCHIVE_PAGE_SIZE,
    ARCHIVE_RECORDS_PER_PAGE,
    ARCHIVE_TOTAL_PAGES,
    ARCHIVE_TOTAL_RECORDS,
    ESC,
    NAK,
)
from app.protocol.vantage.driver import VantageDriver


def test_command_format():
    assert cmd_dmp() == b"DMP\n"


class TestArchiveSizeConstants:
    def test_total_records_matches_the_manual(self):
        """§I quotes 'up to 2560 archive records'."""
        assert ARCHIVE_TOTAL_RECORDS == 2560

    def test_pages_derived_from_records_per_page(self):
        assert ARCHIVE_TOTAL_PAGES == 512
        assert ARCHIVE_TOTAL_PAGES * ARCHIVE_RECORDS_PER_PAGE == 2560


def _make_page(seq: int, record_time: int = 0) -> bytes:
    """A structurally valid 267-byte archive page with a good CRC."""
    page = bytearray(ARCHIVE_PAGE_SIZE)
    page[0] = seq
    for i in range(ARCHIVE_RECORDS_PER_PAGE):
        base = 1 + i * 52
        # date stamp 0 marks an unwritten slot, which the parser skips —
        # fine here, since these tests are about transfer mechanics.
        struct.pack_into("<H", page, base, record_time)
    crc = crc_calculate(bytes(page[:ARCHIVE_PAGE_SIZE - 2]))
    struct.pack_into(">H", page, ARCHIVE_PAGE_SIZE - 2, crc)
    return bytes(page)


class _ScriptedSerial:
    """Replays pages and records every control byte the driver sends."""

    is_open = True

    def __init__(self, pages: list[bytes], ack_first: bool = True):
        self._queue = list(pages)
        self._buf = b""
        self._ack_first = ack_first
        self.control: list[int] = []
        self.corrupt_next = 0

    def flush(self):
        pass

    def send(self, data: bytes):
        if len(data) == 1 and data[0] in (ACK, NAK, ESC):
            self.control.append(data[0])

    def receive_byte(self):
        return ACK if self._ack_first else NAK

    def receive(self, n: int) -> bytes:
        while len(self._buf) < n and self._queue:
            page = self._queue.pop(0)
            if self.corrupt_next > 0:
                page = page[:-2] + b"\xDE\xAD"   # break the CRC
                self.corrupt_next -= 1
            self._buf += page
        out, self._buf = self._buf[:n], self._buf[n:]
        return out


def _driver(pages, ack_first=True, total_pages=None):
    drv = VantageDriver("/dev/null", 19200)
    drv.serial = _ScriptedSerial(pages, ack_first)
    drv._wakeup = lambda: None
    if total_pages is not None:
        import app.protocol.vantage.driver as mod
        drv._test_pages = total_pages
    return drv


class TestDmpTransfer:
    def test_no_ack_raises(self):
        drv = _driver([_make_page(0)], ack_first=False)
        with pytest.raises(ConnectionError, match="DMP: no ACK"):
            drv.dmp()

    def test_each_good_page_is_acked(self, monkeypatch):
        """ACK advances the station; without it the transfer stalls."""
        monkeypatch.setattr(
            "app.protocol.vantage.driver.ARCHIVE_TOTAL_PAGES", 3)
        drv = _driver([_make_page(i) for i in range(3)])
        drv.dmp()
        assert drv.serial.control.count(ACK) == 3
        assert NAK not in drv.serial.control

    def test_corrupt_page_is_naked_then_retried(self, monkeypatch):
        """A NAK must ask for the SAME page again, not skip ahead."""
        monkeypatch.setattr(
            "app.protocol.vantage.driver.ARCHIVE_TOTAL_PAGES", 1)
        page = _make_page(0)
        drv = _driver([page, page])          # corrupt copy, then good one
        drv.serial.corrupt_next = 1
        drv.dmp()
        assert NAK in drv.serial.control, "corrupt page should be NAKed"
        assert ACK in drv.serial.control, "retry should then be ACKed"
        # NAK must come before the ACK — proving it retried rather than
        # accepted the bad page and moved on.
        assert (drv.serial.control.index(NAK)
                < drv.serial.control.index(ACK))

    def test_unreadable_page_aborts_with_esc(self, monkeypatch):
        """Out of retries: send ESC rather than abandoning the station
        mid-stream."""
        monkeypatch.setattr(
            "app.protocol.vantage.driver.ARCHIVE_TOTAL_PAGES", 1)
        page = _make_page(0)
        drv = _driver([page] * 5)
        drv.serial.corrupt_next = 5          # every attempt fails
        with pytest.raises(ConnectionError, match="unreadable after"):
            drv.dmp()
        assert ESC in drv.serial.control

    def test_stop_request_aborts_with_esc(self, monkeypatch):
        monkeypatch.setattr(
            "app.protocol.vantage.driver.ARCHIVE_TOTAL_PAGES", 3)
        drv = _driver([_make_page(i) for i in range(3)])
        drv.request_stop()
        drv.dmp()
        assert ESC in drv.serial.control

    def test_returns_a_list(self, monkeypatch):
        monkeypatch.setattr(
            "app.protocol.vantage.driver.ARCHIVE_TOTAL_PAGES", 2)
        drv = _driver([_make_page(i) for i in range(2)])
        assert isinstance(drv.dmp(), list)


class TestSharedWithDmpaft:
    def test_both_use_the_same_page_reader(self):
        """One copy of the retry/CRC/abort logic, not two that drift."""
        import inspect
        src = inspect.getsource(VantageDriver.dmp)
        assert "_read_archive_pages" in src
        src_after = inspect.getsource(VantageDriver.dmpaft)
        assert "_read_archive_pages" in src_after

    def test_dmp_passes_no_time_filter(self):
        """DMP keeps everything; DMPAFT filters on the cutoff."""
        import inspect
        src = inspect.getsource(VantageDriver.dmp)
        assert "after=None" in src


class TestDriverInterface:
    @pytest.mark.parametrize("name", ["dmp", "async_dmp", "_read_archive_pages"])
    def test_exposed(self, name):
        assert hasattr(VantageDriver, name), f"missing {name}"
