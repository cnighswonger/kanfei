"""Tests for CRC-CCITT implementation."""

from app.protocol.crc import CRC_TABLE, crc_accum, crc_calculate, crc_validate


# Reference table from ccitt.h for cross-checking
REFERENCE_TABLE_FIRST_16 = [
    0x0, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7,
    0x8108, 0x9129, 0xA14A, 0xB16B, 0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
]

REFERENCE_TABLE_LAST_16 = [
    0xEF1F, 0xFF3E, 0xCF5D, 0xDF7C, 0xAF9B, 0xBFBA, 0x8FD9, 0x9FF8,
    0x6E17, 0x7E36, 0x4E55, 0x5E74, 0x2E93, 0x3EB2, 0x0ED1, 0x1EF0,
]


class TestCRCTable:
    def test_table_length(self):
        assert len(CRC_TABLE) == 256

    def test_first_entry_is_zero(self):
        assert CRC_TABLE[0] == 0

    def test_all_entries_are_16_bit(self):
        for entry in CRC_TABLE:
            assert 0 <= entry <= 0xFFFF

    def test_cross_check_first_16_against_reference(self):
        """Cross-check our generated table against the reference ccitt.h."""
        for i, expected in enumerate(REFERENCE_TABLE_FIRST_16):
            assert CRC_TABLE[i] == expected, (
                f"Table mismatch at index {i}: generated 0x{CRC_TABLE[i]:04X}, "
                f"reference 0x{expected:04X}"
            )

    def test_cross_check_last_16_against_reference(self):
        for i, expected in enumerate(REFERENCE_TABLE_LAST_16):
            idx = 240 + i
            assert CRC_TABLE[idx] == expected, (
                f"Table mismatch at index {idx}: generated 0x{CRC_TABLE[idx]:04X}, "
                f"reference 0x{expected:04X}"
            )


class TestCRCCalculation:
    def test_empty_data(self):
        assert crc_calculate(b"") == 0

    def test_single_byte(self):
        result = crc_calculate(b"\x01")
        assert result == CRC_TABLE[1]

    def test_known_string(self):
        """CRC-CCITT (init=0x0000) of "123456789" should be 0x31C3."""
        result = crc_calculate(b"123456789")
        assert result == 0x31C3

    def test_accumulate_matches_calculate(self):
        data = b"\x01\x02\x03\x04"
        crc = 0
        for byte in data:
            crc = crc_accum(crc, byte)
        assert crc == crc_calculate(data)


class TestCRCValidation:
    def test_valid_data_with_crc(self):
        """Data + its CRC appended should validate to True."""
        data = b"Hello, Davis!"
        crc = crc_calculate(data)
        # CRC is sent big-endian (high byte first) per protocol
        data_with_crc = data + bytes([crc >> 8, crc & 0xFF])
        assert crc_validate(data_with_crc) is True

    def test_corrupted_data_fails(self):
        data = b"Hello, Davis!"
        crc = crc_calculate(data)
        data_with_crc = data + bytes([crc >> 8, crc & 0xFF])
        # Corrupt one byte
        corrupted = bytearray(data_with_crc)
        corrupted[3] ^= 0x01
        assert crc_validate(bytes(corrupted)) is False

    def test_wrong_crc_fails(self):
        data = b"\x01\x02\x03"
        data_with_crc = data + b"\x00\x00"
        assert crc_validate(data_with_crc) is False
