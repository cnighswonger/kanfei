"""VantageDriver — StationDriver implementation for Davis Vantage stations.

Supports Vantage Pro1, Pro2, and Vue over serial (RS-232 / USB virtual COM).
Implements the Vantage serial protocol: console wakeup, LOOP/LOOP2 polling,
EEPROM config, clock sync, and DMPAFT archive retrieval.

All blocking serial I/O is protected by _io_lock and can be aborted via
_stop_requested.  Async wrappers use run_in_executor for the event loop.

Reference: Davis Vantage Serial Communication Reference v2.6.1,
           weewx vantage.py driver.
"""

import asyncio
import logging
import struct
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..base import (
    StationDriver,
    SensorSnapshot,
    HardwareInfo,
    CAP_ARCHIVE_SYNC,
    CAP_CALIBRATION_RW,
    CAP_CLOCK_SYNC,
    CAP_RAIN_RESET,
    CAP_HILOWS,
)
from ..serial_port import SerialPort
from ..crc import crc_validate, crc_calculate
from .constants import (
    VantageModel,
    VANTAGE_NAMES,
    VANTAGE_DEFAULT_BAUD,
    WAKEUP,
    WAKEUP_RESPONSE,
    WAKEUP_TIMEOUT,
    WAKEUP_MAX_RETRIES,
    LOOP_PACKET_SIZE,
    LOOP2_PACKET_SIZE,
    RAIN_CLICK_INCHES,
    ARCHIVE_PAGE_SIZE,
    MAX_RETRIES,
    ACK,
    NAK,
    ESC,
)
from .commands import (
    cmd_loop,
    cmd_lps,
    cmd_ver,
    cmd_nver,
    cmd_rxcheck,
    cmd_dmpaft,
    cmd_gettime,
    cmd_settime,
    cmd_eebrd,
    cmd_eebwr,
    build_dmpaft_timestamp,
    build_settime_payload,
)
from .eeprom import (
    STATION_TYPE,
    SETUP_BITS,
    ARCHIVE_INTERVAL,
    LATITUDE,
    LONGITUDE,
    ELEVATION,
    extract_rain_collector_type,
)
from .loop_packet import parse_loop, parse_loop2, loop_to_snapshot
from .archive import (
    parse_archive_record,
    parse_archive_page,
    VantageArchiveRecord,
)

logger = logging.getLogger(__name__)


@dataclass
class VantageHardwareConfig:
    """Hardware configuration cached at connect time."""
    station_type: VantageModel = VantageModel.VANTAGE_PRO
    firmware_date: str = ""
    firmware_version: Optional[str] = None  # None for VP1
    archive_interval: int = 30              # minutes
    rain_collector_type: int = 0            # 0=0.01″, 1=0.2mm, 2=0.1mm
    rain_click_inches: float = 0.01
    latitude: Optional[float] = None        # degrees
    longitude: Optional[float] = None       # degrees
    elevation: Optional[int] = None         # feet
    has_loop2: bool = False                 # VP2/Vue with firmware >= 1.90


class VantageDriver(StationDriver):
    """Driver for Davis Vantage Pro1, Pro2, and Vue stations.

    Implements StationDriver using the Vantage serial protocol.
    """

    def __init__(
        self,
        port: str,
        baud_rate: int = VANTAGE_DEFAULT_BAUD,
        timeout: float = 5.0,
    ):
        self.serial = SerialPort(port, baud_rate, timeout)
        self.hw_config = VantageHardwareConfig()
        self._connected = False
        self._stop_requested = False
        self._io_lock = threading.RLock()

    # ---- StationDriver interface ----

    @property
    def connected(self) -> bool:
        return self._connected and self.serial.is_open

    @property
    def station_name(self) -> str:
        name = VANTAGE_NAMES.get(self.hw_config.station_type, "Vantage")
        if self.hw_config.firmware_version:
            return f"{name} (fw {self.hw_config.firmware_version})"
        return name

    @property
    def capabilities(self) -> set[str]:
        caps = {CAP_ARCHIVE_SYNC, CAP_CLOCK_SYNC, CAP_RAIN_RESET}
        if self.hw_config.has_loop2:
            caps.add(CAP_CALIBRATION_RW)
            caps.add(CAP_HILOWS)
        return caps

    def request_stop(self) -> None:
        self._stop_requested = True

    async def connect(self) -> None:
        """Open serial, wake up console, detect hardware, read config."""
        self._stop_requested = False
        self._open()
        await self._run_in_executor(self._wakeup)
        await self._run_in_executor(self._detect_hardware)
        await self._run_in_executor(self._read_initial_config)

    async def disconnect(self) -> None:
        self._close()

    async def detect_hardware(self) -> HardwareInfo:
        await self._run_in_executor(self._detect_hardware)
        return HardwareInfo(
            name=self.station_name,
            model_code=self.hw_config.station_type.value,
            capabilities=self.capabilities,
        )

    async def poll(self) -> Optional[SensorSnapshot]:
        return await self._run_in_executor(self._poll_sync)

    # ---- Connection lifecycle ----

    def _open(self) -> None:
        self.serial.open()
        self._connected = True

    def _close(self) -> None:
        self.serial.close()
        self._connected = False

    # ---- Wakeup ----

    def _wakeup(self) -> None:
        """Wake the console: send LF, expect LF CR.

        Retries up to WAKEUP_MAX_RETRIES times with delay between.
        """
        with self._io_lock:
            for attempt in range(WAKEUP_MAX_RETRIES):
                if self._stop_requested:
                    raise ConnectionError("Wakeup aborted (stop requested)")
                self.serial.flush()
                self.serial.send(WAKEUP)
                response = self.serial.receive(2)
                if response == WAKEUP_RESPONSE:
                    logger.debug("Wakeup OK (attempt %d)", attempt + 1)
                    return
                logger.debug(
                    "Wakeup attempt %d: got %r (%d bytes)",
                    attempt + 1, response.hex() if response else "empty", len(response),
                )
                time.sleep(WAKEUP_TIMEOUT)
            raise ConnectionError(
                f"Failed to wake Vantage console after {WAKEUP_MAX_RETRIES} attempts"
            )

    # ---- Hardware detection ----

    def _detect_hardware(self) -> None:
        """Detect station type, firmware, and capabilities."""
        with self._io_lock:
            # 1. Firmware date (VER)
            self._wakeup()
            self.serial.flush()
            self.serial.send(cmd_ver())
            response = self._read_ok_response()
            self.hw_config.firmware_date = response.strip()
            logger.info("Firmware date: %s", self.hw_config.firmware_date)

            # 2. Firmware version (NVER — VP2/Vue only)
            self._wakeup()
            self.serial.flush()
            self.serial.send(cmd_nver())
            try:
                response = self._read_ok_response()
                ver = response.strip()
                if ver:
                    self.hw_config.firmware_version = ver
                    self.hw_config.has_loop2 = True
                    logger.info("Firmware version: %s (LOOP2 supported)", ver)
                else:
                    raise ConnectionError("Empty NVER response")
            except ConnectionError:
                self.hw_config.firmware_version = None
                self.hw_config.has_loop2 = False
                logger.info("NVER not supported — VP1 (no LOOP2)")
                # Drain any leftover bytes
                self.serial.flush()

            # 3. Station type from EEPROM
            type_data = self._eeprom_read(STATION_TYPE.address, STATION_TYPE.n_bytes)
            if type_data and len(type_data) >= 1:
                try:
                    self.hw_config.station_type = VantageModel(type_data[0])
                    logger.info(
                        "Station type: %s (code %d)",
                        VANTAGE_NAMES.get(self.hw_config.station_type, "Unknown"),
                        type_data[0],
                    )
                except ValueError:
                    logger.warning("Unknown station type byte: 0x%02X", type_data[0])

    # ---- Initial config from EEPROM ----

    def _read_initial_config(self) -> None:
        """Read operational config needed for correct unit conversions."""
        with self._io_lock:
            # Rain collector type → click-to-inches factor
            setup = self._eeprom_read(SETUP_BITS.address, SETUP_BITS.n_bytes)
            if setup and len(setup) >= 1:
                rc_type = extract_rain_collector_type(setup[0])
                self.hw_config.rain_collector_type = rc_type
                self.hw_config.rain_click_inches = RAIN_CLICK_INCHES.get(rc_type, 0.01)
                logger.info(
                    "Rain collector type: %d (%.5f in/click)",
                    rc_type, self.hw_config.rain_click_inches,
                )

            # Archive interval
            interval = self._eeprom_read(ARCHIVE_INTERVAL.address, ARCHIVE_INTERVAL.n_bytes)
            if interval and len(interval) >= 1:
                self.hw_config.archive_interval = interval[0]
                logger.info("Archive interval: %d min", interval[0])

            # Location (informational)
            lat_data = self._eeprom_read(LATITUDE.address, LATITUDE.n_bytes)
            if lat_data and len(lat_data) == 2:
                self.hw_config.latitude = struct.unpack_from("<h", lat_data)[0] / 10.0

            lon_data = self._eeprom_read(LONGITUDE.address, LONGITUDE.n_bytes)
            if lon_data and len(lon_data) == 2:
                self.hw_config.longitude = struct.unpack_from("<h", lon_data)[0] / 10.0

            elev_data = self._eeprom_read(ELEVATION.address, ELEVATION.n_bytes)
            if elev_data and len(elev_data) == 2:
                self.hw_config.elevation = struct.unpack_from("<h", elev_data)[0]

            if self.hw_config.latitude is not None:
                logger.info(
                    "Station location: %.1f°, %.1f°, %s ft",
                    self.hw_config.latitude,
                    self.hw_config.longitude or 0,
                    self.hw_config.elevation or "?",
                )

    # ---- Polling ----

    def _poll_sync(self) -> Optional[SensorSnapshot]:
        """Execute one poll cycle with retries."""
        with self._io_lock:
            for attempt in range(MAX_RETRIES):
                if self._stop_requested:
                    return None
                try:
                    self._wakeup()
                    if self.hw_config.has_loop2:
                        return self._poll_lps()
                    else:
                        return self._poll_loop_only()
                except Exception as exc:
                    if self._stop_requested:
                        return None
                    logger.warning("Poll attempt %d/%d failed: %s", attempt + 1, MAX_RETRIES, exc)
                    self.serial.flush()

            logger.error("Poll failed after %d attempts", MAX_RETRIES)
            return None

    def _poll_lps(self) -> Optional[SensorSnapshot]:
        """LPS 3 1 → one LOOP + one LOOP2 packet (VP2/Vue)."""
        self.serial.flush()
        self.serial.send(cmd_lps(3, 1))

        ack = self.serial.receive_byte()
        if ack != ACK:
            raise ConnectionError(f"LPS not ACKed (got 0x{ack:02X})" if ack is not None else "LPS timeout")

        # Read LOOP packet
        loop_raw = self.serial.receive(LOOP_PACKET_SIZE)
        if len(loop_raw) < LOOP_PACKET_SIZE:
            raise ConnectionError(f"LOOP short read: {len(loop_raw)}/{LOOP_PACKET_SIZE}")

        loop_data = parse_loop(loop_raw)
        if loop_data is None:
            raise ConnectionError("LOOP parse failed")

        # Read LOOP2 packet
        loop2_raw = self.serial.receive(LOOP2_PACKET_SIZE)
        loop2_data = None
        if len(loop2_raw) >= LOOP2_PACKET_SIZE:
            loop2_data = parse_loop2(loop2_raw)
            if loop2_data is None:
                logger.warning("LOOP2 parse failed (using LOOP only)")

        return loop_to_snapshot(
            loop_data, loop2_data, self.hw_config.rain_click_inches,
        )

    def _poll_loop_only(self) -> Optional[SensorSnapshot]:
        """LOOP 1 → single LOOP packet (VP1 fallback)."""
        self.serial.flush()
        self.serial.send(cmd_loop(1))

        ack = self.serial.receive_byte()
        if ack != ACK:
            raise ConnectionError(f"LOOP not ACKed (got 0x{ack:02X})" if ack is not None else "LOOP timeout")

        loop_raw = self.serial.receive(LOOP_PACKET_SIZE)
        if len(loop_raw) < LOOP_PACKET_SIZE:
            raise ConnectionError(f"LOOP short read: {len(loop_raw)}/{LOOP_PACKET_SIZE}")

        loop_data = parse_loop(loop_raw)
        if loop_data is None:
            raise ConnectionError("LOOP parse failed")

        return loop_to_snapshot(loop_data, None, self.hw_config.rain_click_inches)

    # ---- EEPROM ----

    def _eeprom_read(self, address: int, n_bytes: int) -> Optional[bytes]:
        """Read n_bytes from EEPROM. Returns data bytes or None."""
        self._wakeup()
        self.serial.flush()
        self.serial.send(cmd_eebrd(address, n_bytes))

        ack = self.serial.receive_byte()
        if ack != ACK:
            logger.warning("EEBRD 0x%04X: no ACK", address)
            return None

        response = self.serial.receive(n_bytes + 2)
        if len(response) < n_bytes + 2:
            logger.warning("EEBRD 0x%04X: short read (%d bytes)", address, len(response))
            return response[:n_bytes] if len(response) >= n_bytes else None

        if not crc_validate(response):
            logger.warning("EEBRD 0x%04X: CRC failed", address)
            return None

        return response[:n_bytes]

    def _eeprom_write(self, address: int, data: bytes) -> bool:
        """Write data to EEPROM. Returns True on success."""
        self._wakeup()
        self.serial.flush()
        self.serial.send(cmd_eebwr(address, len(data)))

        ack = self.serial.receive_byte()
        if ack != ACK:
            return False

        crc = crc_calculate(data)
        self.serial.send(data + struct.pack(">H", crc))

        ack = self.serial.receive_byte()
        return ack == ACK

    # ---- Clock ----

    def read_station_time(self) -> Optional[dict]:
        """Read station clock via GETTIME.

        Returns dict with year, month, day, hour, minute, second.
        """
        with self._io_lock:
            self._wakeup()
            self.serial.flush()
            self.serial.send(cmd_gettime())

            ack = self.serial.receive_byte()
            if ack != ACK:
                logger.warning("GETTIME: no ACK")
                return None

            # 8 bytes: sec, min, hr, day, month, year-1900, CRC(2)
            response = self.serial.receive(8)
            if len(response) < 8:
                logger.warning("GETTIME: short read (%d bytes)", len(response))
                return None

            if not crc_validate(response):
                logger.warning("GETTIME: CRC failed")
                return None

            sec, min_, hr, day, month, yr_off = response[0:6]
            return {
                "second": sec,
                "minute": min_,
                "hour": hr,
                "day": day,
                "month": month,
                "year": 1900 + yr_off,
            }

    def write_station_time(self, dt: datetime) -> bool:
        """Set station clock via SETTIME."""
        with self._io_lock:
            self._wakeup()
            self.serial.flush()
            self.serial.send(cmd_settime())

            ack = self.serial.receive_byte()
            if ack != ACK:
                logger.warning("SETTIME: no ACK")
                return False

            payload = build_settime_payload(
                dt.year, dt.month, dt.day,
                dt.hour, dt.minute, dt.second,
            )
            self.serial.send(payload)

            ack = self.serial.receive_byte()
            ok = ack == ACK
            if ok:
                logger.info("Station clock set to %s", dt.strftime("%Y-%m-%d %H:%M:%S"))
            else:
                logger.warning("SETTIME: data payload not ACKed")
            return ok

    # ---- Archive (DMPAFT) ----

    def dmpaft(self, after: datetime) -> list[VantageArchiveRecord]:
        """Download archive records after the given timestamp."""
        with self._io_lock:
            self._wakeup()
            self.serial.flush()
            self.serial.send(cmd_dmpaft())

            ack = self.serial.receive_byte()
            if ack != ACK:
                raise ConnectionError("DMPAFT: no ACK")

            # Send timestamp payload
            ts_payload = build_dmpaft_timestamp(
                after.year, after.month, after.day,
                after.hour, after.minute,
            )
            self.serial.send(ts_payload)

            ack = self.serial.receive_byte()
            if ack != ACK:
                raise ConnectionError("DMPAFT: timestamp not ACKed")

            # Read header: page_count (u16 LE) + first_record_offset (u16 LE)
            header = self.serial.receive(4)
            if len(header) < 4:
                raise ConnectionError("DMPAFT: header short read")

            page_count = struct.unpack_from("<H", header, 0)[0]
            first_offset = struct.unpack_from("<H", header, 2)[0]
            logger.info("DMPAFT: %d pages, first record offset %d", page_count, first_offset)

            if page_count == 0:
                return []

            records: list[VantageArchiveRecord] = []
            for page_num in range(page_count):
                if self._stop_requested:
                    self.serial.send(bytes([ESC]))
                    logger.info("DMPAFT: aborted by stop request at page %d", page_num)
                    break

                page_data = self.serial.receive(ARCHIVE_PAGE_SIZE)
                if len(page_data) < ARCHIVE_PAGE_SIZE:
                    logger.warning("DMPAFT page %d: short read (%d bytes)", page_num, len(page_data))
                    self.serial.send(bytes([NAK]))
                    continue

                if not crc_validate(page_data[:ARCHIVE_PAGE_SIZE]):
                    logger.warning("DMPAFT page %d: CRC failed, sending NAK", page_num)
                    self.serial.send(bytes([NAK]))
                    continue

                # ACK this page
                self.serial.send(bytes([ACK]))

                # Parse records
                page_records = parse_archive_page(page_data)
                for offset, record_bytes in page_records:
                    if page_num == 0 and offset < first_offset:
                        continue  # skip records before the requested time

                    record = parse_archive_record(
                        record_bytes, self.hw_config.rain_click_inches,
                    )
                    if record is not None:
                        records.append(record)

            logger.info("DMPAFT: retrieved %d records", len(records))
            return records

    # ---- RXCHECK diagnostics ----

    def rxcheck(self) -> Optional[dict]:
        """Read receiver diagnostics via RXCHECK."""
        with self._io_lock:
            self._wakeup()
            self.serial.flush()
            self.serial.send(cmd_rxcheck())

            response = self._read_ok_response()
            parts = response.strip().split()
            if len(parts) >= 5:
                return {
                    "packets_received": int(parts[0]),
                    "missed": int(parts[1]),
                    "resync": int(parts[2]),
                    "max_consecutive": int(parts[3]),
                    "crc_errors": int(parts[4]),
                }
            logger.warning("RXCHECK: unexpected response: %r", response)
            return None

    # ---- Text response reader ----

    def _read_ok_response(self, max_bytes: int = 256) -> str:
        """Read an OK-prefixed text response terminated by LF CR.

        Vantage text responses follow the pattern:
          LF CR "OK" LF CR <payload> LF CR
        This method reads until a LF CR after the OK prefix, then
        reads the actual payload terminated by LF CR.
        """
        buf = b""
        for _ in range(max_bytes):
            byte = self.serial.receive(1)
            if not byte:
                break
            buf += byte
            # Check for response completion — look for LF CR after content
            if len(buf) >= 4 and buf.endswith(b"\n\r"):
                # Have we seen the "OK" and then payload after it?
                text = buf.decode("ascii", errors="replace")
                # Remove leading whitespace/control chars
                stripped = text.lstrip("\n\r \t")
                if stripped.startswith("OK"):
                    payload = stripped[2:].strip("\n\r \t")
                    if payload:
                        return payload
                    # OK with no payload yet — keep reading for the next LF CR
                    continue
                elif stripped:
                    # Got a response without OK prefix (e.g. NAK or error)
                    return stripped

        # If we got here, return whatever we have
        text = buf.decode("ascii", errors="replace").strip("\n\r \t")
        if text.startswith("OK"):
            text = text[2:].strip("\n\r \t")
        if not text:
            raise ConnectionError("No response received")
        return text

    # ---- Async helpers ----

    async def _run_in_executor(self, func, *args):
        """Run a blocking function in the default thread pool executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args)

    async def async_read_station_time(self) -> Optional[dict]:
        return await self._run_in_executor(self.read_station_time)

    async def async_write_station_time(self, dt: datetime) -> bool:
        return await self._run_in_executor(self.write_station_time, dt)

    async def async_dmpaft(self, after: datetime) -> list[VantageArchiveRecord]:
        return await self._run_in_executor(self.dmpaft, after)

    async def async_rxcheck(self) -> Optional[dict]:
        return await self._run_in_executor(self.rxcheck)
