"""Ecowitt TCP binary protocol transport layer.

Handles packet construction, checksum calculation, and TCP send/receive
for the Ecowitt LAN API (port 45000).  Each command opens a fresh TCP
connection — Ecowitt gateways are designed for this pattern.
"""

import asyncio
import logging
import struct

from .constants import DEFAULT_PORT, DEFAULT_TIMEOUT, HEADER, LONG_SIZE_COMMANDS

logger = logging.getLogger(__name__)


class EcowittProtocolError(ConnectionError):
    """Raised when a response fails checksum or format validation."""


def calc_checksum(data: bytes) -> int:
    """Checksum = sum of bytes mod 256."""
    return sum(data) & 0xFF


def build_request(cmd: int, payload: bytes = b"") -> bytes:
    """Build a request packet.

    Format: [0xFF][0xFF][cmd][size][payload...][checksum]
    size = 1(cmd) + 1(size) + len(payload) + 1(checksum) = 3 + len(payload)
    """
    size = 3 + len(payload)
    body = bytes([cmd, size]) + payload
    return HEADER + body + bytes([calc_checksum(body)])


async def send_command(
    host: str,
    port: int = DEFAULT_PORT,
    cmd: int = 0,
    payload: bytes = b"",
    timeout: float = DEFAULT_TIMEOUT,
) -> bytes:
    """Send a command and return the response payload.

    Opens a TCP connection, sends the request, reads the full response,
    validates the checksum, closes the connection, and returns the payload
    bytes (everything between the size field and the checksum).

    Raises:
        ConnectionError: TCP connection failed.
        TimeoutError: No response within *timeout* seconds.
        EcowittProtocolError: Checksum mismatch or malformed response.
    """
    request = build_request(cmd, payload)

    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port),
        timeout=timeout,
    )
    try:
        writer.write(request)
        await writer.drain()

        # Read header (2 bytes)
        header = await asyncio.wait_for(reader.readexactly(2), timeout=timeout)
        if header != HEADER:
            raise EcowittProtocolError(
                f"Bad header: expected FF FF, got {header.hex()}"
            )

        # Read command echo (1 byte)
        resp_cmd = (await asyncio.wait_for(reader.readexactly(1), timeout=timeout))[0]

        # Size field: 2 bytes for certain commands, 1 byte for the rest
        if resp_cmd in LONG_SIZE_COMMANDS:
            size_bytes = await asyncio.wait_for(reader.readexactly(2), timeout=timeout)
            size = struct.unpack(">H", size_bytes)[0]
            # size includes: cmd(1) + size_hi(1) + size_lo(1) + payload + checksum(1)
            remaining = size - 3  # payload + checksum
        else:
            size_byte = (await asyncio.wait_for(
                reader.readexactly(1), timeout=timeout
            ))[0]
            size = size_byte
            # size includes: cmd(1) + size(1) + payload + checksum(1)
            remaining = size - 2  # payload + checksum

        if remaining < 1:
            raise EcowittProtocolError(f"Size too small: {size}")

        # Read payload + checksum
        tail = await asyncio.wait_for(
            reader.readexactly(remaining), timeout=timeout
        )
        resp_payload = tail[:-1]
        resp_checksum = tail[-1]

        # Validate checksum over cmd + size bytes + payload
        if resp_cmd in LONG_SIZE_COMMANDS:
            check_data = bytes([resp_cmd]) + size_bytes + resp_payload
        else:
            check_data = bytes([resp_cmd, size_byte]) + resp_payload

        if calc_checksum(check_data) != resp_checksum:
            raise EcowittProtocolError(
                f"Checksum mismatch: expected {calc_checksum(check_data):02x}, "
                f"got {resp_checksum:02x}"
            )

        return resp_payload
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
