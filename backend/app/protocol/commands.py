"""Command builders for the Davis WeatherLink serial protocol.

All commands are uppercase ASCII terminated with CR (0x0D).
Reference: techref.txt section VI (lines 422-844).
"""

import struct

from .crc import crc_calculate
from .constants import CR


def _cmd(text: str, *binary_args: int) -> bytes:
    """Build a command: ASCII text + binary args + CR."""
    result = text.encode("ascii")
    for arg in binary_args:
        result += bytes([arg])
    result += bytes([CR])
    return result


def _with_rev_e_crc(cmd: bytes) -> bytes:
    """Prepend Rev E CRC to a command (CRC includes the CR terminator)."""
    crc = crc_calculate(cmd)
    return struct.pack(">H", crc) + cmd


def build_loop_command(n_packets: int = 1) -> bytes:
    """Build LOOP command to request n sensor image packets.

    Format: LOOP [16-bit count] CR
    The count is sent as 65536 - n (little-endian).
    Example: 1 packet -> LOOP 0xFF 0xFF CR
    """
    count = (65536 - n_packets) & 0xFFFF
    return b"LOOP" + struct.pack("<H", count) + bytes([CR])


def build_wrd_command(n_nibbles: int, bank: int, address: int) -> bytes:
    """Build WRD command to read station processor memory.

    Format: WRD [n|bank] [address] CR
    Bank encoding: bank 0 -> add 2, bank 1 -> add 4
    n_nibbles in upper nibble (shifted by 4), bank code in lower.

    Per techref.txt lines 652-654:
    - Bank 0: (n_nibbles << 4) | 0x02
    - Bank 1: (n_nibbles << 4) | 0x04
    """
    bank_code = 0x02 if bank == 0 else 0x04
    cmd_byte = ((n_nibbles & 0x0F) << 4) | bank_code
    return _cmd("WRD", cmd_byte, address & 0xFF)


def build_wwr_command(n_nibbles: int, bank: int, address: int, data: bytes) -> bytes:
    """Build WWR command to write station processor memory.

    Format: WWR [n|bank] [address] [data...] CR
    Bank encoding: bank 0 -> add 1, bank 1 -> add 3
    """
    bank_code = 0x01 if bank == 0 else 0x03
    cmd_byte = ((n_nibbles & 0x0F) << 4) | bank_code
    return b"WWR" + bytes([cmd_byte, address & 0xFF]) + data + bytes([CR])


def build_rrd_command(bank: int, address: int, n_nibbles: int) -> bytes:
    """Build RRD command to read link processor memory.

    Format: RRD [bank] [address] [n-1] CR
    """
    return _cmd("RRD", bank & 0xFF, address & 0xFF, (n_nibbles - 1) & 0xFF)


def build_rwr_command(bank: int, n_nibbles: int, address: int, data: bytes) -> bytes:
    """Build RWR command to write link processor memory.

    Format: RWR [bank|n-1] [address] [2-byte data] CR
    """
    cmd_byte = (bank & 0x0F) | (((n_nibbles - 1) & 0x0F) << 4)
    return b"RWR" + bytes([cmd_byte, address & 0xFF]) + data + bytes([CR])


def build_srd_command(address: int, n_bytes: int) -> bytes:
    """Build SRD command to read archive/SRAM memory.

    Format: SRD [2-byte address] [2-byte count-1] CR
    """
    return b"SRD" + struct.pack("<H", address) + struct.pack("<H", n_bytes - 1) + bytes([CR])


def build_dmp_command() -> bytes:
    """Build DMP command for archive memory dump (XMODEM CRC)."""
    return _cmd("DMP")


def build_sap_command(minutes: int) -> bytes:
    """Build SAP command to set archive period in minutes (1-120)."""
    return _cmd("SAP", minutes & 0xFF)


def build_ssp_command(seconds: int) -> bytes:
    """Build SSP command to set sample period.

    Format: SSP [256-n] CR where n is seconds (1-255).
    """
    return _cmd("SSP", (256 - seconds) & 0xFF)


def build_stop_command() -> bytes:
    """Build STOP command to pause station polling."""
    return _cmd("STOP")


def build_start_command() -> bytes:
    """Build START command to resume station polling."""
    return _cmd("START")


def build_arc_command() -> bytes:
    """Build ARC command to force archive write."""
    return _cmd("ARC")


def build_img_command() -> bytes:
    """Build IMG command to force sensor image sample."""
    return _cmd("IMG")


def build_dbt_command() -> bytes:
    """Build DBT command to disable archive timer."""
    return _cmd("DBT")


def build_ebt_command() -> bytes:
    """Build EBT command to enable archive timer."""
    return _cmd("EBT")


def build_crc0_command() -> bytes:
    """Build CRC0 command to disable CRC checking (Rev E only).

    Must be preceded by CRC bytes 0x2C 0xF7.
    """
    return bytes([0x2C, 0xF7]) + _cmd("CRC0")


def build_crc1_command() -> bytes:
    """Build CRC1 command to enable CRC checking (Rev E only)."""
    return _cmd("CRC1")
