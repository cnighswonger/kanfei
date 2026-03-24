"""Tests for Davis serial protocol command builders."""

import struct

from app.protocol.commands import (
    build_loop_command,
    build_wrd_command,
    build_wwr_command,
    build_rrd_command,
    build_srd_command,
    build_dmp_command,
    build_sap_command,
    build_ssp_command,
    build_stop_command,
    build_start_command,
    build_arc_command,
    build_crc0_command,
    build_crc1_command,
)
from app.protocol.constants import CR


class TestBuildLoopCommand:

    def test_single_packet(self):
        cmd = build_loop_command(1)
        assert cmd.startswith(b"LOOP")
        assert cmd.endswith(bytes([CR]))
        # Count = 65536 - 1 = 65535 = 0xFFFF little-endian
        count = struct.unpack("<H", cmd[4:6])[0]
        assert count == 0xFFFF

    def test_ten_packets(self):
        cmd = build_loop_command(10)
        count = struct.unpack("<H", cmd[4:6])[0]
        assert count == 65536 - 10

    def test_ends_with_cr(self):
        assert build_loop_command()[-1] == CR


class TestBuildWrdCommand:

    def test_bank_0(self):
        cmd = build_wrd_command(n_nibbles=4, bank=0, address=0x50)
        assert cmd.startswith(b"WRD")
        # Bank 0 code = 0x02, n=4 shifted left 4 = 0x40, combined = 0x42
        assert cmd[3] == 0x42
        assert cmd[4] == 0x50
        assert cmd[-1] == CR

    def test_bank_1(self):
        cmd = build_wrd_command(n_nibbles=2, bank=1, address=0x10)
        # Bank 1 code = 0x04, n=2 shifted left 4 = 0x20, combined = 0x24
        assert cmd[3] == 0x24
        assert cmd[4] == 0x10


class TestBuildWwrCommand:

    def test_bank_0_with_data(self):
        cmd = build_wwr_command(n_nibbles=2, bank=0, address=0x30, data=b"\xAB")
        assert cmd.startswith(b"WWR")
        # Bank 0 code = 0x01, n=2 shifted left 4 = 0x20, combined = 0x21
        assert cmd[3] == 0x21
        assert cmd[4] == 0x30
        assert cmd[5] == 0xAB
        assert cmd[-1] == CR


class TestBuildRrdCommand:

    def test_read_link_memory(self):
        cmd = build_rrd_command(bank=1, address=0x20, n_nibbles=4)
        assert cmd.startswith(b"RRD")
        assert cmd[3] == 1  # bank
        assert cmd[4] == 0x20  # address
        assert cmd[5] == 3  # n-1
        assert cmd[-1] == CR


class TestBuildSrdCommand:

    def test_archive_read(self):
        cmd = build_srd_command(address=0x100, n_bytes=256)
        assert cmd.startswith(b"SRD")
        addr = struct.unpack("<H", cmd[3:5])[0]
        count = struct.unpack("<H", cmd[5:7])[0]
        assert addr == 0x100
        assert count == 255  # n_bytes - 1
        assert cmd[-1] == CR


class TestSimpleCommands:

    def test_dmp(self):
        cmd = build_dmp_command()
        assert cmd == b"DMP" + bytes([CR])

    def test_stop(self):
        cmd = build_stop_command()
        assert cmd == b"STOP" + bytes([CR])

    def test_start(self):
        cmd = build_start_command()
        assert cmd == b"START" + bytes([CR])

    def test_arc(self):
        cmd = build_arc_command()
        assert cmd == b"ARC" + bytes([CR])

    def test_crc1(self):
        cmd = build_crc1_command()
        assert cmd == b"CRC1" + bytes([CR])


class TestBuildSapCommand:

    def test_archive_period(self):
        cmd = build_sap_command(15)
        assert cmd.startswith(b"SAP")
        assert cmd[3] == 15
        assert cmd[-1] == CR


class TestBuildSspCommand:

    def test_sample_period(self):
        cmd = build_ssp_command(30)
        assert cmd.startswith(b"SSP")
        # 256 - 30 = 226
        assert cmd[3] == 226
        assert cmd[-1] == CR


class TestBuildCrc0Command:

    def test_has_magic_prefix(self):
        cmd = build_crc0_command()
        # Must start with magic bytes 0x2C 0xF7
        assert cmd[0] == 0x2C
        assert cmd[1] == 0xF7
        assert b"CRC0" in cmd
        assert cmd[-1] == CR
