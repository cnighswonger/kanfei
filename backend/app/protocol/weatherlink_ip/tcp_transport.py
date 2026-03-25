"""TCP socket transport that duck-types SerialPort for WeatherLink IP (6555).

The WeatherLink IP is a transparent TCP-to-serial bridge on port 22222.
It forwards the same Davis protocol commands over TCP instead of a serial
port.  This class provides the same interface as SerialPort so that
LinkDriver can use it without modification.
"""

import logging
import socket
import time
from typing import Optional

from ..constants import ACK

logger = logging.getLogger(__name__)

# TCP-specific constants
DEFAULT_PORT = 22222
SEND_DELAY = 0.5          # seconds pause after each socket write
CONNECT_TIMEOUT = 5.0     # seconds for initial TCP connect
WAKEUP_MAX_TRIES = 3
CONNECT_MAX_TRIES = 3
CONNECT_RETRY_DELAY = 2.0


class TcpTransport:
    """TCP socket transport for the Davis WeatherLink IP (6555).

    Provides the same public API as :class:`SerialPort` (open, close, flush,
    send, receive, receive_byte, wait_for_ack, is_open) so that
    :class:`LinkDriver` can use it as a drop-in replacement.
    """

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = 4.0,
    ):
        self.host = host
        self.port = port            # reused by LinkDriver (serial.port)
        self.baud_rate: int = 0     # dummy — LinkDriver reads serial.baud_rate
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None

    @property
    def is_open(self) -> bool:
        return self._sock is not None

    def open(self) -> None:
        """Connect TCP socket with retry for connection-refused.

        The 6555 refuses connections while uploading to Davis cloud.
        We retry up to 3 times with a 2-second backoff.
        """
        for attempt in range(CONNECT_MAX_TRIES):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(CONNECT_TIMEOUT)
                sock.connect((self.host, self.port))
                sock.settimeout(self.timeout)
                self._sock = sock
                logger.info(
                    "TCP connected to %s:%d", self.host, self.port,
                )
                self._wakeup()
                return
            except ConnectionRefusedError:
                if attempt < CONNECT_MAX_TRIES - 1:
                    logger.warning(
                        "Connection refused by %s:%d (attempt %d/%d, "
                        "device may be uploading) — retrying in %.0fs",
                        self.host, self.port,
                        attempt + 1, CONNECT_MAX_TRIES,
                        CONNECT_RETRY_DELAY,
                    )
                    time.sleep(CONNECT_RETRY_DELAY)
                else:
                    raise
            except Exception:
                # Clean up partial socket on other errors
                try:
                    sock.close()
                except Exception:
                    pass
                raise

    def _wakeup(self) -> None:
        """Send wakeup sequence to the station via TCP.

        Same as the Vantage serial wakeup: extra newlines to cancel any
        pending LOOP, flush, then send ``\\n`` and expect ``\\n\\r`` back.
        """
        if self._sock is None:
            raise RuntimeError("TCP socket not connected")

        # Extra newlines to cancel any pending LOOP command
        self._sock.sendall(b"\n\n\n")
        time.sleep(SEND_DELAY)
        self.flush()

        # Standard Vantage wakeup: send \n, expect \n\r
        for attempt in range(WAKEUP_MAX_TRIES):
            self._sock.sendall(b"\n")
            time.sleep(SEND_DELAY)
            try:
                data = self._sock.recv(16)
                if b"\n\r" in data:
                    logger.debug("Wakeup OK (attempt %d)", attempt + 1)
                    return
            except socket.timeout:
                continue
            logger.debug("Wakeup attempt %d: got %r", attempt + 1, data)

        raise ConnectionError(
            f"WeatherLink IP wakeup failed after {WAKEUP_MAX_TRIES} attempts"
        )

    def close(self) -> None:
        """Close the TCP socket."""
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
            logger.info("TCP connection to %s:%d closed", self.host, self.port)

    def flush(self) -> None:
        """Drain any pending data from the socket."""
        if self._sock is None:
            return
        self._sock.setblocking(False)
        try:
            while True:
                data = self._sock.recv(4096)
                if not data:
                    break
        except (BlockingIOError, socket.error):
            pass
        finally:
            self._sock.settimeout(self.timeout)

    def send(self, data: bytes) -> None:
        """Send raw bytes over the TCP socket.

        A 0.5-second delay follows each write — the 6555 needs time to
        forward the bytes to the station and relay the response back.
        """
        if self._sock is None:
            raise RuntimeError("TCP socket not connected")
        self._sock.sendall(data)
        time.sleep(SEND_DELAY)
        logger.debug("TX: %s", data.hex())

    def receive(self, n: int) -> bytes:
        """Read exactly *n* bytes from the socket.

        Returns the bytes read.  May return fewer than *n* if timeout occurs.
        """
        if self._sock is None:
            raise RuntimeError("TCP socket not connected")
        buf = b""
        while len(buf) < n:
            try:
                chunk = self._sock.recv(n - len(buf))
                if not chunk:
                    break  # connection closed
                buf += chunk
            except socket.timeout:
                break
        logger.debug("RX: %s", buf.hex())
        return buf

    def receive_byte(self) -> Optional[int]:
        """Read a single byte.  Returns ``None`` on timeout."""
        data = self.receive(1)
        if len(data) == 0:
            return None
        return data[0]

    def wait_for_ack(self) -> bool:
        """Wait for an ACK (0x06) response.

        Returns ``True`` if ACK received, ``False`` on timeout or wrong byte.
        """
        response = self.receive_byte()
        if response is None:
            logger.warning("Timeout waiting for ACK (TCP)")
            return False
        if response == ACK:
            return True
        logger.warning("Expected ACK (0x06), got 0x%02X (TCP)", response)
        return False
