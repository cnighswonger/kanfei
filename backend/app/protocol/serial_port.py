"""Serial port wrapper for Davis WeatherLink communication.

Provides a thin abstraction over pyserial with timeout handling,
cross-platform port detection, and async-friendly interface.
"""

import asyncio
import logging
from typing import Optional

import serial
import serial.tools.list_ports

from .constants import ACK, DEFAULT_BAUD

logger = logging.getLogger(__name__)


def list_serial_ports() -> list[str]:
    """List available serial ports on the system."""
    return [port.device for port in serial.tools.list_ports.comports()]


class SerialPort:
    """Wrapper around pyserial for WeatherLink communication."""

    def __init__(
        self,
        port: str,
        baud_rate: int = DEFAULT_BAUD,
        timeout: float = 2.0,
    ):
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self._serial: Optional[serial.Serial] = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def open(self) -> None:
        """Open the serial port."""
        if self.is_open:
            return
        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baud_rate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
        )
        logger.info("Opened serial port %s at %d baud", self.port, self.baud_rate)

    def close(self) -> None:
        """Close the serial port."""
        if self._serial is not None:
            self._serial.close()
            self._serial = None
            logger.info("Closed serial port %s", self.port)

    def flush(self) -> None:
        """Flush input and output buffers."""
        if self._serial:
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()

    def send(self, data: bytes) -> None:
        """Send raw bytes over the serial port."""
        if not self._serial:
            raise RuntimeError("Serial port not open")
        self._serial.write(data)
        self._serial.flush()
        logger.debug("TX: %s", data.hex())

    def receive(self, n: int) -> bytes:
        """Read exactly n bytes from the serial port.

        Returns the bytes read. May return fewer than n if timeout occurs.
        """
        if not self._serial:
            raise RuntimeError("Serial port not open")
        data = self._serial.read(n)
        logger.debug("RX: %s", data.hex())
        return data

    def receive_byte(self) -> Optional[int]:
        """Read a single byte. Returns None on timeout."""
        data = self.receive(1)
        if len(data) == 0:
            return None
        return data[0]

    def wait_for_ack(self) -> bool:
        """Wait for an ACK (0x06) response.

        Returns True if ACK received, False on timeout or wrong response.
        """
        response = self.receive_byte()
        if response is None:
            logger.warning("Timeout waiting for ACK")
            return False
        if response == ACK:
            return True
        logger.warning("Expected ACK (0x06), got 0x%02X", response)
        return False

    async def async_send(self, data: bytes) -> None:
        """Async wrapper for send (runs in thread pool)."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.send, data)

    async def async_receive(self, n: int) -> bytes:
        """Async wrapper for receive (runs in thread pool)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.receive, n)

    async def async_wait_for_ack(self) -> bool:
        """Async wrapper for wait_for_ack."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.wait_for_ack)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
