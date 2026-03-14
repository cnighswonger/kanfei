"""Tests for LOOP packet parsing."""

import struct
from app.protocol.crc import crc_calculate
from app.protocol.constants import StationModel, SOH
from app.protocol.loop_packet import parse_loop_packet


def _make_basic_packet(
    inside_temp: int = 720,
    outside_temp: int = 451,
    wind_speed: int = 12,
    wind_direction: int = 225,
    barometer: int = 30120,
    inside_humidity: int = 45,
    outside_humidity: int = 78,
    rain_total: int = 150,
) -> bytes:
    """Build a valid Monitor/Wizard/Perception LOOP packet with correct CRC."""
    data = b""
    data += struct.pack("<h", inside_temp)       # 2 bytes
    data += struct.pack("<h", outside_temp)       # 2 bytes
    data += bytes([wind_speed])                   # 1 byte
    data += struct.pack("<H", wind_direction)     # 2 bytes
    data += struct.pack("<H", barometer)          # 2 bytes
    data += bytes([inside_humidity])              # 1 byte
    data += bytes([outside_humidity])             # 1 byte
    data += struct.pack("<H", rain_total)         # 2 bytes
    data += struct.pack("<H", 0)                  # 2 bytes unused
    assert len(data) == 15

    # Calculate CRC over data bytes
    crc = crc_calculate(data)
    crc_bytes = struct.pack(">H", crc)  # big-endian CRC

    return bytes([SOH]) + data + crc_bytes


class TestBasicLoopParsing:
    def test_parse_valid_packet(self):
        raw = _make_basic_packet()
        reading = parse_loop_packet(raw, StationModel.MONITOR)
        assert reading is not None
        assert reading.inside_temp == 720
        assert reading.outside_temp == 451
        assert reading.wind_speed == 12
        assert reading.wind_direction == 225
        assert reading.barometer == 30120
        assert reading.inside_humidity == 45
        assert reading.outside_humidity == 78
        assert reading.rain_total == 150

    def test_parse_works_for_all_basic_stations(self):
        raw = _make_basic_packet()
        for model in [
            StationModel.MONITOR,
            StationModel.WIZARD_III,
            StationModel.WIZARD_II,
            StationModel.PERCEPTION,
        ]:
            reading = parse_loop_packet(raw, model)
            assert reading is not None
            assert reading.inside_temp == 720

    def test_negative_temperature(self):
        raw = _make_basic_packet(outside_temp=-100)  # -10.0 F
        reading = parse_loop_packet(raw, StationModel.MONITOR)
        assert reading is not None
        assert reading.outside_temp == -100

    def test_invalid_temp_returns_none(self):
        raw = _make_basic_packet(inside_temp=0x7FFF)
        reading = parse_loop_packet(raw, StationModel.MONITOR)
        assert reading is not None
        assert reading.inside_temp is None

    def test_not_connected_temp_returns_none(self):
        # 0x8000 as signed i16 is -32768
        raw = _make_basic_packet(outside_temp=-32768)
        reading = parse_loop_packet(raw, StationModel.MONITOR)
        assert reading is not None
        assert reading.outside_temp is None

    def test_invalid_humidity_returns_none(self):
        raw = _make_basic_packet(inside_humidity=128)
        reading = parse_loop_packet(raw, StationModel.MONITOR)
        assert reading is not None
        assert reading.inside_humidity is None

    def test_packet_too_short(self):
        reading = parse_loop_packet(b"\x01\x00\x00", StationModel.MONITOR)
        assert reading is None

    def test_wrong_header(self):
        raw = _make_basic_packet()
        raw = bytes([0x02]) + raw[1:]  # Replace SOH with wrong byte
        reading = parse_loop_packet(raw, StationModel.MONITOR)
        assert reading is None

    def test_corrupted_crc(self):
        raw = bytearray(_make_basic_packet())
        raw[-1] ^= 0xFF  # Corrupt last CRC byte
        reading = parse_loop_packet(bytes(raw), StationModel.MONITOR)
        assert reading is None

    def test_solar_and_uv_none_for_basic(self):
        raw = _make_basic_packet()
        reading = parse_loop_packet(raw, StationModel.MONITOR)
        assert reading is not None
        assert reading.solar_radiation is None
        assert reading.uv_index is None

    def test_zero_wind_speed(self):
        raw = _make_basic_packet(wind_speed=0, wind_direction=0)
        reading = parse_loop_packet(raw, StationModel.MONITOR)
        assert reading is not None
        assert reading.wind_speed == 0
        assert reading.wind_direction == 0
