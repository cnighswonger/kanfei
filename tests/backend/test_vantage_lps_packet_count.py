"""LPS packet-count semantics on Vantage stations.

``LPS <bitmask> <count>`` takes the TOTAL number of packets across all
selected types, not the number of rounds.  The driver asked for
``LPS 3 1`` — bitmask 3 selects LOOP *and* LOOP2, count 1 means one
packet altogether — so the console sent the LOOP and stopped.  The
LOOP2 read that followed always timed out.

That alone would have been visible, but the short read was discarded
without a log line, so every LOOP2-derived field silently stayed None
for the life of the install.  Measured on the production box before the
fix: 714,779 rows, not one carrying a LOOP2 key (wind_2min_avg_ms,
wind_10min_avg_ms, wind_gust_10min_ms, thsw_index, rain_15min_mm,
rain_hour_mm), and wind_gust populated on 854 rows out of all of them.

Verified on the bench Vue (fw 2.12) before writing these tests:

    LPS 3 1: packet1=99B hdr=b'LOO'  packet2=0B  hdr=b''
    LPS 3 2: packet1=99B hdr=b'LOO'  packet2=99B hdr=b'LOO'

The manual's own example (§IX, "LPS") says ``LPS 3 4`` requests "2 LOOP
and 2 LOOP2 packets" — 4 is the total, confirming the reading above.
"""

import pytest

from app.protocol.vantage.commands import cmd_lps
from app.protocol.vantage.constants import (
    ACK,
    LOOP2_PACKET_SIZE,
    LOOP_PACKET_SIZE,
)
from app.protocol.vantage.driver import VantageDriver


def _loop_packet() -> bytes:
    """A CRC-valid LOOP packet with enough set for parse_loop() to accept."""
    from app.protocol.crc import crc_calculate

    raw = bytearray(LOOP_PACKET_SIZE)
    raw[0:3] = b"LOO"
    raw[3] = 0                      # bar trend
    raw[4] = 0                      # packet type: LOOP
    raw[7:9] = (29920).to_bytes(2, "little")    # barometer, inHg/1000
    raw[9:11] = (720).to_bytes(2, "little")     # inside temp, 0.1°F
    raw[11] = 45                                # inside humidity
    raw[12:14] = (750).to_bytes(2, "little")    # outside temp, 0.1°F
    raw[14] = 5                                 # wind speed, mph
    raw[15] = 4                                 # 10-min avg wind, mph
    raw[16:18] = (180).to_bytes(2, "little")    # wind direction
    raw[33] = 55                                # outside humidity
    raw[95:97] = b"\n\r"
    raw[97:99] = crc_calculate(bytes(raw[:97])).to_bytes(2, "big")
    return bytes(raw)


def _loop2_packet(gust_tenths_mph: int = 210,
                  avg2_tenths_mph: int = 88,
                  avg10_tenths_mph: int = 95) -> bytes:
    """A CRC-valid LOOP2 packet carrying the higher-precision wind fields."""
    from app.protocol.crc import crc_calculate

    raw = bytearray(LOOP2_PACKET_SIZE)
    raw[0:3] = b"LOO"
    raw[4] = 1                      # packet type: LOOP2
    raw[7:9] = (29920).to_bytes(2, "little")
    raw[9:11] = (720).to_bytes(2, "little")
    raw[11] = 45
    raw[12:14] = (750).to_bytes(2, "little")
    raw[14] = 5
    raw[16:18] = (180).to_bytes(2, "little")
    raw[18:20] = avg10_tenths_mph.to_bytes(2, "little")
    raw[20:22] = avg2_tenths_mph.to_bytes(2, "little")
    raw[22:24] = gust_tenths_mph.to_bytes(2, "little")
    raw[24:26] = (200).to_bytes(2, "little")     # gust direction
    raw[33] = 55
    raw[95:97] = b"\n\r"
    raw[97:99] = crc_calculate(bytes(raw[:97])).to_bytes(2, "big")
    return bytes(raw)


class FakeSerial:
    """Serial stub that honours the LPS packet-count contract.

    It replays exactly as many 99-byte packets as the LPS count argument
    asks for, alternating LOOP/LOOP2 when the bitmask selects both — so a
    driver that under-requests gets a short read, just as the console
    gives it one.
    """

    def __init__(self):
        self.sent: list[bytes] = []
        self._pending = bytearray()

    def flush(self):
        pass

    def send(self, data: bytes):
        self.sent.append(data)
        if not data.startswith(b"LPS "):
            return
        _, mask_s, count_s = data.decode().strip().split()
        mask, count = int(mask_s), int(count_s)

        types = []
        if mask & 1:
            types.append(_loop_packet())
        if mask & 2:
            types.append(_loop2_packet())

        self._pending += bytes([ACK])
        for i in range(count):
            self._pending += types[i % len(types)]

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
    drv.hw_config.has_loop2 = True
    drv.hw_config.rain_click_inches = 0.01
    return drv


class TestPacketCountIsTotalNotRounds:
    def test_requests_two_packets_for_one_loop_plus_one_loop2(self, driver):
        """The regression guard: count is the TOTAL across both types."""
        driver._poll_lps()
        assert driver.serial.sent[0] == b"LPS 3 2\n"

    def test_lps_3_1_would_starve_the_loop2_read(self):
        """Prove the old argument really does yield only one packet, so
        this test fails loudly if someone 'simplifies' it back to 1."""
        fake = FakeSerial()
        fake.send(b"LPS 3 1\n")
        assert fake.receive_byte() == ACK
        assert len(fake.receive(LOOP_PACKET_SIZE)) == LOOP_PACKET_SIZE
        assert fake.receive(LOOP2_PACKET_SIZE) == b""

    def test_lps_3_2_yields_both_packets(self):
        fake = FakeSerial()
        fake.send(b"LPS 3 2\n")
        assert fake.receive_byte() == ACK
        assert len(fake.receive(LOOP_PACKET_SIZE)) == LOOP_PACKET_SIZE
        assert len(fake.receive(LOOP2_PACKET_SIZE)) == LOOP2_PACKET_SIZE

    def test_command_builder_formats_the_total(self):
        assert cmd_lps(3, 2) == b"LPS 3 2\n"


class TestLoop2FieldsReachTheSnapshot:
    """The point of the fix — these are the fields the console displays as
    2-min and 10-min wind, and the gust that CWOP/WU publish."""

    def test_gust_is_populated(self, driver):
        snapshot = driver._poll_lps()
        assert snapshot.wind_gust is not None
        assert snapshot.wind_gust > 0

    def test_two_minute_average_reaches_extra(self, driver):
        snapshot = driver._poll_lps()
        assert "wind_2min_avg_ms" in snapshot.extra

    def test_ten_minute_average_reaches_extra(self, driver):
        snapshot = driver._poll_lps()
        assert "wind_10min_avg_ms" in snapshot.extra

    def test_gust_direction_reaches_extra(self, driver):
        snapshot = driver._poll_lps()
        assert snapshot.extra["wind_gust_dir"] == 200

    def test_console_gust_exceeds_instantaneous_wind(self, driver):
        """Why the console value is worth having: a 21.0 mph gust against a
        5 mph instantaneous sample is a peak a 15 s poll would never see.
        Deriving gust from our own samples would under-report it."""
        snapshot = driver._poll_lps()
        assert snapshot.wind_gust > snapshot.wind_speed


class TestShortLoop2IsLoud:
    """A missing LOOP2 is survivable — every field it carries is
    supplementary — but it must never again be silent."""

    def test_short_read_is_logged(self, driver, caplog):
        driver.serial.send = lambda data: driver.serial.sent.append(data)
        driver.serial._pending = bytearray([ACK]) + bytearray(_loop_packet())
        with caplog.at_level("WARNING"):
            driver._poll_lps()
        assert any("LOOP2 short read" in r.message for r in caplog.records)

    def test_short_read_still_returns_a_usable_snapshot(self, driver):
        driver.serial.send = lambda data: driver.serial.sent.append(data)
        driver.serial._pending = bytearray([ACK]) + bytearray(_loop_packet())
        snapshot = driver._poll_lps()
        assert snapshot is not None
        assert snapshot.outside_temp is not None

    def test_short_read_leaves_gust_none_rather_than_guessing(self, driver):
        driver.serial.send = lambda data: driver.serial.sent.append(data)
        driver.serial._pending = bytearray([ACK]) + bytearray(_loop_packet())
        snapshot = driver._poll_lps()
        assert snapshot.wind_gust is None
