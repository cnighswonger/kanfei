"""CCITT CRC-1021 implementation for Davis WeatherLink protocol.

The CRC table is generated programmatically from the CCITT polynomial 0x1021
rather than copied from the reference ccitt.h (which may contain errors).
"""

POLYNOMIAL = 0x1021


def _generate_crc_table() -> list[int]:
    """Generate the 256-entry CRC lookup table from the CCITT polynomial."""
    table = []
    for i in range(256):
        crc = i << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ POLYNOMIAL
            else:
                crc = crc << 1
            crc &= 0xFFFF
        table.append(crc)
    return table


CRC_TABLE = _generate_crc_table()


def crc_accum(crc: int, data: int) -> int:
    """Accumulate one byte into the running CRC.

    Formula: crc = crc_table[(crc >> 8) ^ data] ^ (crc << 8)
    Per serial.c line 219.
    """
    return (CRC_TABLE[((crc >> 8) ^ data) & 0xFF] ^ (crc << 8)) & 0xFFFF


def crc_calculate(data: bytes) -> int:
    """Calculate CRC over a sequence of bytes. Initial value is 0."""
    crc = 0
    for byte in data:
        crc = crc_accum(crc, byte)
    return crc


def crc_validate(data_with_crc: bytes) -> bool:
    """Validate data + 2-byte CRC. Returns True if CRC is correct.

    After processing all data bytes followed by the 2 CRC bytes,
    the accumulator should equal 0 if no transmission errors.
    """
    return crc_calculate(data_with_crc) == 0
