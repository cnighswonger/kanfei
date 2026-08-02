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
    CAP_ARCHIVE_PERIOD_RW,
    CAP_CLOCK_SYNC,
    CAP_RAIN_RESET,
    CAP_HILOWS,
)
from ..serial_port import SerialPort
from ..crc import crc_validate, crc_calculate
from ..commands import build_wrd_command
from ..constants import DAVIS_LEGAL_ARCHIVE_PERIODS
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
    DMPAFT_HEADER_SIZE,
    STATION_TYPE_WRD_ADDR,
    CALFIX_BLOCK_SIZE,
    CALFIX_OFF_INSIDE_TEMP,
    CALFIX_OFF_OUTSIDE_TEMP,
    CALFIX_OFF_INSIDE_HUM,
    CALFIX_OFF_OUTSIDE_HUM,
    CALFIX_INVALID_TEMP,
    CALFIX_INVALID_HUM,
    CAL_BLOCK_START,
    CAL_BLOCK_END,
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
    cmd_bardata,
    cmd_dmpaft,
    cmd_gettime,
    cmd_settime,
    cmd_eebrd,
    cmd_eebwr,
    cmd_caled,
    cmd_calfix,
    cmd_clrcal,
    cmd_clrlog,
    cmd_clrvar,
    cmd_clrhighs,
    cmd_clrlows,
    cmd_hilows,
    cmd_setper,
    CLRVAR_VARIABLES,
    CLRVAR_NAMES,
    CLRVAR_RAIN_DAILY,
    CLRVAR_RAIN_YEAR,
    CLR_PERIODS,
    CLR_PERIOD_NAMES,
    CLR_PERIOD_DAILY,
    build_dmpaft_timestamp,
    build_settime_payload,
)
from .eeprom import (
    EEAddr,
    SETUP_BITS,
    CAL_INSIDE_TEMP,
    CAL_OUTSIDE_TEMP,
    CAL_INSIDE_HUM,
    CAL_OUTSIDE_HUM,
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
from .hilows import (
    parse_hilows,
    VantageHighsLows,
    HILOWS_TOTAL_SIZE,
)
from .bardata import parse_bardata, BarometerCalibration

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
        # CAP_CALIBRATION_RW is advertised again as of #209: the addresses
        # now come from the Vantage Serial Reference rather than guesswork,
        # and write_calibration() performs the CALED/CALFIX sequence that
        # actually makes an offset take effect.  It was withdrawn in #211
        # because a bare EEBWR silently did nothing.
        caps = {
            CAP_ARCHIVE_SYNC, CAP_CLOCK_SYNC, CAP_RAIN_RESET,
            CAP_CALIBRATION_RW,
            # SETPER — added in #217.  CAP_SAMPLE_PERIOD_RW is deliberately
            # absent: "sample period" is a WeatherLink-logger concept with
            # no equivalent anywhere in the Vantage serial protocol, so it
            # is genuinely unsupported rather than merely unimplemented.
            CAP_ARCHIVE_PERIOD_RW,
        }
        if self.hw_config.has_loop2:
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

            # 3. Station type from processor memory via WRD.
            #
            # This does NOT live in EEPROM.  The previous code read EEBRD
            # 0x12, but 0x12 is the WRD *command byte* (n_nibbles<<4 | bank),
            # not an address -- it was transcribed out of the command
            # `WRD 0x12 0x4D` as though it were an offset.  EEPROM 0x12
            # holds 0x00 on a Vue, so the lookup raised ValueError and the
            # field silently kept its VANTAGE_PRO default: every Vue
            # reported itself as a Pro2.
            self.hw_config.station_type = VantageModel.UNKNOWN
            code = self._read_station_type_code()
            if code is None:
                logger.warning(
                    "Station type: WRD read failed — reporting unknown model"
                )
            else:
                try:
                    self.hw_config.station_type = VantageModel(code)
                    logger.info(
                        "Station type: %s (code %d)",
                        VANTAGE_NAMES.get(self.hw_config.station_type, "Unknown"),
                        code,
                    )
                except ValueError:
                    logger.warning(
                        "Unrecognised station type code %d (0x%02X) — "
                        "reporting unknown model", code, code,
                    )

    def _read_station_type_code(self) -> Optional[int]:
        """Read the station model code from processor memory via WRD.

        Returns the raw code byte, or None if the station did not respond.
        """
        for attempt in range(MAX_RETRIES):
            self._wakeup()
            self.serial.flush()
            self.serial.send(build_wrd_command(1, 0, STATION_TYPE_WRD_ADDR))
            response = self.serial.receive(2)
            if len(response) >= 2 and response[0] == ACK:
                return response[1]
            logger.debug(
                "WRD station type attempt %d/%d: got %r",
                attempt + 1, MAX_RETRIES, response.hex() if response else "empty",
            )
        return None

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
        """Read n_bytes from EEPROM, retrying transient failures.

        Retries matter here: a single dropped response is common on this
        link, and callers that treat None as "field absent" can silently do
        the wrong thing.  write_calibration() is the sharp case — a None
        there would skip un-calibrating a field and make CALFIX send an
        already-calibrated value as if it were raw.
        """
        for attempt in range(MAX_RETRIES):
            result = self._eeprom_read_once(address, n_bytes)
            if result is not None:
                return result
            if attempt + 1 < MAX_RETRIES:
                logger.debug(
                    "EEBRD 0x%04X: retry %d/%d",
                    address, attempt + 1, MAX_RETRIES,
                )
                self.serial.flush()
        logger.warning(
            "EEBRD 0x%04X: failed after %d attempts", address, MAX_RETRIES,
        )
        return None

    def _eeprom_read_once(self, address: int, n_bytes: int) -> Optional[bytes]:
        """Single EEBRD attempt. Returns data bytes or None."""
        self._wakeup()
        self.serial.flush()
        self.serial.send(cmd_eebrd(address, n_bytes))

        ack = self.serial.receive_byte()
        if ack != ACK:
            logger.debug("EEBRD 0x%04X: no ACK", address)
            return None

        response = self.serial.receive(n_bytes + 2)
        if len(response) < n_bytes + 2:
            # Previously this returned response[:n_bytes] on a short read —
            # i.e. CRC-UNVALIDATED bytes, indistinguishable from a good
            # read.  With the retry loop above that would have been worse
            # still: a truncated read would be accepted as success instead
            # of retried.  Fail, and let the caller retry.
            logger.debug(
                "EEBRD 0x%04X: short read (%d of %d bytes)",
                address, len(response), n_bytes + 2,
            )
            return None

        if not crc_validate(response):
            logger.debug("EEBRD 0x%04X: CRC failed", address)
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

    # ---- Calibration ----

    def _caled(self) -> Optional[bytes]:
        """CALED — read the 43-byte block of current CALIBRATED values."""
        self._wakeup()
        self.serial.flush()
        self.serial.send(cmd_caled())

        if self.serial.receive_byte() != ACK:
            logger.warning("CALED: no ACK")
            return None

        payload = self.serial.receive(CALFIX_BLOCK_SIZE + 2)
        if len(payload) < CALFIX_BLOCK_SIZE + 2:
            logger.warning(
                "CALED: short read (%d of %d bytes)",
                len(payload), CALFIX_BLOCK_SIZE + 2,
            )
            return None
        if not crc_validate(payload):
            logger.warning("CALED: CRC failed")
            return None
        return payload[:CALFIX_BLOCK_SIZE]

    def _calfix(self, block: bytes) -> bool:
        """CALFIX — send UN-CALIBRATED values so the display updates."""
        if len(block) != CALFIX_BLOCK_SIZE:
            raise ValueError(
                f"CALFIX block must be {CALFIX_BLOCK_SIZE} bytes, "
                f"got {len(block)}"
            )
        self._wakeup()
        self.serial.flush()
        self.serial.send(cmd_calfix())

        if self.serial.receive_byte() != ACK:
            logger.warning("CALFIX: no ACK")
            return False

        crc = crc_calculate(block)
        self.serial.send(block + struct.pack(">H", crc))
        return self.serial.receive_byte() == ACK

    def write_calibration(self, field: EEAddr, offset: int) -> bool:
        """Set a temperature/humidity calibration offset, and apply it.

        Writing the EEPROM byte alone is not enough.  Per the Vantage
        Serial Reference section XIV.1, a new calibration value "will not
        take effect until the next time the Vantage receives a data packet
        containing that temperature or humidity value" — so this performs
        the documented sequence:

            EEBRD (current offsets) -> CALED (calibrated values)
              -> subtract to get un-calibrated -> EEBWR (new offset)
              -> CALFIX (push un-calibrated values back)

        `field` must be one of the single-byte CAL_* entries in eeprom.py.
        `offset` is in that sensor's native units: tenths °F for
        temperature, whole percent for humidity.

        Deliberately writes ONE field rather than the manual's block form:
        its "EEBWR 32 2B" example writes 43 bytes from 0x32, which runs
        past the calibration block and over the graph defaults and alarm
        thresholds.  See CAL_BLOCK_* in constants.py.
        """
        if field.n_bytes != 1:
            raise ValueError(
                f"write_calibration expects a 1-byte field, "
                f"got {field.n_bytes} at 0x{field.address:02X}"
            )
        if not CAL_BLOCK_START <= field.address <= CAL_BLOCK_END:
            raise ValueError(
                f"0x{field.address:02X} is outside the calibration block "
                f"(0x{CAL_BLOCK_START:02X}..0x{CAL_BLOCK_END:02X})"
            )
        if not -128 <= offset <= 127:
            raise ValueError(f"calibration offset {offset} out of range")

        with self._io_lock:
            # 1. current calibrated sensor values
            calibrated = self._caled()
            if calibrated is None:
                logger.error("write_calibration: CALED failed")
                return False

            # 2. current offsets, so we can back out un-calibrated values
            block = bytearray(calibrated)
            for name, blk_off, size in (
                ("inside temp", CALFIX_OFF_INSIDE_TEMP, 2),
                ("outside temp", CALFIX_OFF_OUTSIDE_TEMP, 2),
                ("inside hum", CALFIX_OFF_INSIDE_HUM, 1),
                ("outside hum", CALFIX_OFF_OUTSIDE_HUM, 1),
            ):
                ee = {
                    "inside temp": CAL_INSIDE_TEMP,
                    "outside temp": CAL_OUTSIDE_TEMP,
                    "inside hum": CAL_INSIDE_HUM,
                    "outside hum": CAL_OUTSIDE_HUM,
                }[name]
                cur = self._eeprom_read(ee.address, 1)
                if cur is None:
                    continue
                cur_off = struct.unpack("b", cur)[0]
                # The offset we are about to change is applied AFTER this
                # un-calibration step, so back out the value currently in
                # effect for every field.
                if size == 2:
                    val = struct.unpack_from("<h", block, blk_off)[0]
                    if val == CALFIX_INVALID_TEMP:
                        continue          # dashed — leave untouched
                    struct.pack_into("<h", block, blk_off, val - cur_off)
                else:
                    val = block[blk_off]
                    if val == CALFIX_INVALID_HUM:
                        continue
                    block[blk_off] = (val - cur_off) & 0xFF

            # 3. write the new offset
            if not self._eeprom_write(field.address, struct.pack("b", offset)):
                logger.error(
                    "write_calibration: EEBWR 0x%02X failed", field.address,
                )
                return False

            # 4. push un-calibrated values so the console re-applies cal
            if not self._calfix(bytes(block)):
                logger.error("write_calibration: CALFIX failed")
                return False

            logger.info(
                "Calibration 0x%02X set to %+d (CALFIX applied)",
                field.address, offset,
            )
            return True

    def clear_calibration(self) -> bool:
        """CLRCAL — zero every temperature and humidity calibration offset.

        Affects ALL temp/humidity offsets at once, not one field.  Does not
        touch barometer calibration, which is set with BAR=.
        """
        with self._io_lock:
            self._wakeup()
            self.serial.flush()
            self.serial.send(cmd_clrcal())
            response = self._read_ok_response()
            ok = "OK" in response or response.strip() == ""
            logger.info("CLRCAL: %s", "cleared" if ok else f"unexpected {response!r}")
            return ok

    async def async_write_calibration(self, field: EEAddr, offset: int) -> bool:
        return await self._run_in_executor(self.write_calibration, field, offset)

    async def async_clear_calibration(self) -> bool:
        return await self._run_in_executor(self.clear_calibration)

    # ---- Archive period ----

    def read_archive_period(self) -> Optional[int]:
        """Read the archive interval from EEPROM, in minutes.

        Reads the register rather than returning the cached
        hw_config.archive_interval, so a value changed by the console's own
        UI (or by another process on the port) is reported accurately.
        """
        with self._io_lock:
            data = self._eeprom_read(ARCHIVE_INTERVAL.address, ARCHIVE_INTERVAL.n_bytes)
            if not data:
                logger.warning("read_archive_period: EEPROM read failed")
                return None
            value = data[0]
            if value not in DAVIS_LEGAL_ARCHIVE_PERIODS:
                # Same guard as LinkDriver.read_archive_period (see #174):
                # a garbage register value must not be presented as truth.
                logger.warning(
                    "read_archive_period: rejecting non-Davis-legal value %d "
                    "(expected one of %s)",
                    value, sorted(DAVIS_LEGAL_ARCHIVE_PERIODS),
                )
                return None
            self.hw_config.archive_interval = value
            return value

    async def async_read_archive_period(self) -> Optional[int]:
        return await self._run_in_executor(self.read_archive_period)

    def set_archive_period(self, minutes: int) -> bool:
        """Set the archive interval via SETPER.

        **This does NOT erase archive memory**, despite manual section
        IX.7 stating that it "automatically clears the archive memory ...
        so that all archived records in the archive memory use the same
        archive interval".  Verified on a Vantage Vue (fw 2.12): the
        interval changed and all 46 existing records survived, giving
        exactly the mixed-interval archive the manual says this prevents.

        So after changing the interval the archive holds records at BOTH
        the old and new spacing, and the record spanning the change covers
        a partial period (observed: 30, 30, 12 min).  Anything consuming
        archive data must either tolerate that or call clear_log() —
        which is irreversible, so sync first.

        Davis firmware honours only {1, 5, 10, 15, 30, 60, 120}; anything
        else is rejected here rather than sent, matching LinkDriver's
        behaviour (see #174, where a 1..120 range check let through values
        like 68 and 102).

        Shorter intervals trade buffer depth for resolution: archive memory
        holds 2560 records, so 1 min ≈ 42 h of history where 30 min ≈ 53
        days.  That bounds how long a logger outage can be before archive
        backfill starts losing data.
        """
        if minutes not in DAVIS_LEGAL_ARCHIVE_PERIODS:
            raise ValueError(
                f"Archive period must be one of "
                f"{sorted(DAVIS_LEGAL_ARCHIVE_PERIODS)} (got {minutes})"
            )

        with self._io_lock:
            self._wakeup()
            self.serial.flush()
            self.serial.send(cmd_setper(minutes))
            # The manual (IX.7) documents an <ACK> reply; fw 2.12 on a Vue
            # answers "\n\rOK\n\r".  Accept either.
            #
            # Do NOT use _read_ok_response() here: it expects OK *plus a
            # payload* (as VER/NVER return) and loops waiting for one, so a
            # bare OK makes it time out and raise "No response received" on
            # a command that actually succeeded.
            ok = self._read_status_reply()
            if ok:
                self.hw_config.archive_interval = minutes
                logger.info(
                    "Archive period set to %d min (console cleared archive memory)",
                    minutes,
                )
            else:
                logger.warning(
                    "SETPER %d: unexpected response %r", minutes, response,
                )
            return ok

    async def async_set_archive_period(self, minutes: int) -> bool:
        return await self._run_in_executor(self.set_archive_period, minutes)

    def clear_variable(self, variable: int) -> bool:
        """CLRVAR — clear one rain or ET accumulator.  **IRREVERSIBLE.**

        `variable` must be one of CLRVAR_VARIABLES (manual section IX.6):
        13 daily rain, 14 storm rain, 16 month rain, 17 year rain,
        25 month ET, 26 day ET, 27 year ET.  The manual states results are
        undefined for any other number, so anything else is rejected here
        rather than sent.

        Verified on a Vantage Vue (fw 2.12): replies with a bare ACK, as
        documented, and clears only the named accumulator — daily rain went
        to 0 while year rain stayed at 2848 clicks.
        """
        if variable not in CLRVAR_VARIABLES:
            raise ValueError(
                f"CLRVAR variable must be one of {sorted(CLRVAR_VARIABLES)} "
                f"(got {variable})"
            )
        name = CLRVAR_NAMES.get(variable, str(variable))
        with self._io_lock:
            self._wakeup()
            self.serial.flush()
            self.serial.send(cmd_clrvar(variable))
            ok = self._read_status_reply()
            logger.info(
                "CLRVAR %d (%s): %s",
                variable, name, "cleared" if ok else "unexpected response",
            )
            return ok

    def clear_rain_daily(self) -> bool:
        """Clear the daily rain accumulator (CLRVAR 13)."""
        return self.clear_variable(CLRVAR_RAIN_DAILY)

    def clear_rain_yearly(self) -> bool:
        """Clear the yearly rain accumulator (CLRVAR 17)."""
        return self.clear_variable(CLRVAR_RAIN_YEAR)

    def clear_highs(self, period: int = CLR_PERIOD_DAILY) -> bool:
        """CLRHIGHS — clear ALL high records for a period.  **IRREVERSIBLE.**

        `period` is 0 daily / 1 monthly / 2 yearly (manual section IX.13).

        This is deliberately not scoped to a single sensor, because the
        protocol cannot do that: section II.4 states "You can not reset
        individual high or low values."  Clearing the daily highs to drop
        one bad reading also drops that day's barometer, wind, humidity and
        inside-temperature highs.  Callers wanting to remove a single
        outlier should know they are trading the whole period for it.
        """
        if period not in CLR_PERIODS:
            raise ValueError(
                f"CLRHIGHS period must be one of {sorted(CLR_PERIODS)} "
                f"(got {period})"
            )
        name = CLR_PERIOD_NAMES.get(period, str(period))
        with self._io_lock:
            self._wakeup()
            self.serial.flush()
            self.serial.send(cmd_clrhighs(period))
            ok = self._read_status_reply()
            logger.info(
                "CLRHIGHS %d (%s highs): %s",
                period, name, "cleared" if ok else "unexpected response",
            )
            return ok

    def clear_lows(self, period: int = CLR_PERIOD_DAILY) -> bool:
        """CLRLOWS — clear ALL low records for a period.  **IRREVERSIBLE.**

        Same period argument and same all-or-nothing caveat as
        clear_highs(); see that docstring.
        """
        if period not in CLR_PERIODS:
            raise ValueError(
                f"CLRLOWS period must be one of {sorted(CLR_PERIODS)} "
                f"(got {period})"
            )
        name = CLR_PERIOD_NAMES.get(period, str(period))
        with self._io_lock:
            self._wakeup()
            self.serial.flush()
            self.serial.send(cmd_clrlows(period))
            ok = self._read_status_reply()
            logger.info(
                "CLRLOWS %d (%s lows): %s",
                period, name, "cleared" if ok else "unexpected response",
            )
            return ok

    async def async_clear_variable(self, variable: int) -> bool:
        return await self._run_in_executor(self.clear_variable, variable)

    async def async_clear_highs(self, period: int = CLR_PERIOD_DAILY) -> bool:
        return await self._run_in_executor(self.clear_highs, period)

    async def async_clear_lows(self, period: int = CLR_PERIOD_DAILY) -> bool:
        return await self._run_in_executor(self.clear_lows, period)

    async def async_clear_rain_daily(self) -> bool:
        return await self._run_in_executor(self.clear_rain_daily)

    async def async_clear_rain_yearly(self) -> bool:
        return await self._run_in_executor(self.clear_rain_yearly)

    def clear_log(self) -> bool:
        """CLRLOG — erase archive memory.  **IRREVERSIBLE.**

        Every archive record is destroyed.  Sync before calling; there is no
        undo and the console holds the only copy.

        The manual states SETPER "automatically clears the archive memory",
        so this ought to be redundant after an interval change.  It is not:
        on a Vue running fw 2.12, SETPER changed the interval but left the
        existing records in place, producing exactly the mixed-interval
        archive the manual says it prevents.  Call this explicitly after
        SETPER if a clean archive matters.
        """
        with self._io_lock:
            self._wakeup()
            self.serial.flush()
            self.serial.send(cmd_clrlog())
            # Manual IX.6 documents '"OK"<LF><CR>' followed by '"DONE"'
            # after a delay.  fw 2.12 on a Vue actually replies with a bare
            # ACK (0x06) and nothing else — verified on hardware, where the
            # erase demonstrably worked (48 records -> 0) while a text-based
            # check reported failure.  Accept either.
            ok = self._read_status_reply()
            logger.info(
                "CLRLOG: %s", "archive erased" if ok else "unexpected response",
            )
            return ok

    async def async_clear_log(self) -> bool:
        return await self._run_in_executor(self.clear_log)

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
            # + CRC (u16 BE) = 6 bytes total.  Reading only the 4 payload
            # bytes strands the CRC in the buffer, where it is then misread
            # as the start of page 0.
            header = self.serial.receive(DMPAFT_HEADER_SIZE)
            if len(header) < DMPAFT_HEADER_SIZE:
                raise ConnectionError(
                    f"DMPAFT: header short read ({len(header)} of "
                    f"{DMPAFT_HEADER_SIZE} bytes)"
                )

            if not crc_validate(header):
                self.serial.send(bytes([ESC]))
                raise ConnectionError("DMPAFT: header CRC failed")

            page_count = struct.unpack_from("<H", header, 0)[0]
            first_offset = struct.unpack_from("<H", header, 2)[0]
            logger.info("DMPAFT: %d pages, first record offset %d", page_count, first_offset)

            if page_count == 0:
                return []

            # The station sends nothing until the header is ACKed.  Without
            # this the first page read blocks until timeout and every
            # subsequent one returns zero bytes.
            self.serial.send(bytes([ACK]))

            records: list[VantageArchiveRecord] = []
            pages_read = 0
            for page_num in range(page_count):
                page_data = None

                # Retry a corrupt or short page in place.  NAK asks the
                # station to resend the SAME page, so advancing the loop
                # counter on failure (as this previously did) desynchronises
                # the stream from the station.
                for attempt in range(MAX_RETRIES):
                    if self._stop_requested:
                        self.serial.send(bytes([ESC]))
                        logger.info("DMPAFT: aborted by stop request at page %d", page_num)
                        page_data = None
                        break

                    chunk = self.serial.receive(ARCHIVE_PAGE_SIZE)
                    if len(chunk) < ARCHIVE_PAGE_SIZE:
                        logger.warning(
                            "DMPAFT page %d: short read (%d of %d bytes), attempt %d/%d",
                            page_num, len(chunk), ARCHIVE_PAGE_SIZE,
                            attempt + 1, MAX_RETRIES,
                        )
                        self.serial.send(bytes([NAK]))
                        continue

                    if not crc_validate(chunk):
                        logger.warning(
                            "DMPAFT page %d: CRC failed, attempt %d/%d",
                            page_num, attempt + 1, MAX_RETRIES,
                        )
                        self.serial.send(bytes([NAK]))
                        continue

                    page_data = chunk
                    break

                if self._stop_requested:
                    break

                if page_data is None:
                    # Out of retries — abort rather than press on against a
                    # stream we can no longer trust.
                    self.serial.send(bytes([ESC]))
                    raise ConnectionError(
                        f"DMPAFT: page {page_num} unreadable after "
                        f"{MAX_RETRIES} attempts"
                    )

                # ACK advances the station to the next page.
                self.serial.send(bytes([ACK]))
                pages_read += 1

                # Parse records
                page_records = parse_archive_page(page_data)
                for offset, record_bytes in page_records:
                    if page_num == 0 and offset < first_offset:
                        continue  # skip records before the requested time

                    record = parse_archive_record(
                        record_bytes, self.hw_config.rain_click_inches,
                    )
                    if record is None:
                        continue

                    # The station sends whole pages, so the final page is
                    # padded with unwritten slots and any page may carry
                    # records older than the request.  first_offset only
                    # covers page 0, so filter on the timestamp too --
                    # otherwise a request for a future time still returns
                    # the tail of the archive.
                    if record.timestamp is None or record.timestamp <= after:
                        continue

                    records.append(record)

            logger.info(
                "DMPAFT: retrieved %d records from %d/%d pages",
                len(records), pages_read, page_count,
            )
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

    # ---- BARDATA: barometer calibration parameters ----

    def bardata(self) -> Optional[BarometerCalibration]:
        """Read barometer calibration parameters via BARDATA (§IX.5).

        Read-only: reports the console's current elevation, offset and the
        intermediate terms of its pressure-correction formula.

        Unlike RXCHECK this is a multi-line text response — nine KEY VALUE
        lines after the OK — so it needs _read_text_block() rather than
        _read_ok_response(), which returns at the first payload line.

        Observed on a Vue (fw 2.12):
            BAR 29916 / ELEVATION 265 / DEW POINT 80 / VIRTUAL TEMP 74
            C 69 / R 1007 / BARCAL 50 / GAIN 0 / OFFSET -44
        """
        with self._io_lock:
            self._wakeup()
            self.serial.flush()
            self.serial.send(cmd_bardata())
            response = self._read_text_block()

        if not response:
            logger.warning("BARDATA: no response")
            return None

        cal = parse_bardata(response)
        if cal is None:
            logger.warning("BARDATA: unparseable response: %r", response)
        else:
            logger.info(
                "BARDATA: bar=%s inHg, elevation=%s ft, barcal=%s inHg",
                cal.barometer_inhg, cal.elevation_ft, cal.barcal_inhg,
            )
        return cal

    # ---- HILOWS: current high/low block ----

    def hilows(self) -> Optional[VantageHighsLows]:
        """Read the console's current high/low block via HILOWS (§IX.2).

        Response: <ACK> then 436 bytes of payload plus a 2-byte CRC.  The
        parser filters dashed sentinels field-by-field so an unpopulated
        extra-temp slot comes back as None rather than -90 °F.

        Advertised via CAP_HILOWS on the driver; before this landed the
        capability was true in name only — the exact "advertise-what-you-
        cannot-do" bug that motivated #221.
        """
        with self._io_lock:
            self._wakeup()
            self.serial.flush()
            self.serial.send(cmd_hilows())

            ack = self.serial.receive_byte()
            if ack != ACK:
                raise ConnectionError("HILOWS: no ACK")

            block = self.serial.receive(HILOWS_TOTAL_SIZE)
            if len(block) < HILOWS_TOTAL_SIZE:
                raise ConnectionError(
                    f"HILOWS: short read ({len(block)} of "
                    f"{HILOWS_TOTAL_SIZE} bytes)"
                )

            if not crc_validate(block[:HILOWS_TOTAL_SIZE]):
                raise ConnectionError("HILOWS: CRC failed")

            return parse_hilows(
                block, rain_click_inches=self.hw_config.rain_click_inches,
            )

    # ---- Text response reader ----

    def _read_status_reply(self, timeout_reads: int = 24) -> bool:
        """Read a bare success reply from a command that returns no payload.

        Vantage acknowledgement styles are not consistent, and the manual
        does not always match the firmware.  Observed on a Vue (fw 2.12):

            SETPER  -> b"\n\rOK\n\r"   (manual documents <ACK>)
            CLRLOG  -> b"\x06"          (manual documents "OK" then "DONE")

        So accept ACK, "OK", or "DONE" in any combination.  Unlike
        _read_ok_response(), this does NOT wait for a payload — that helper
        loops until one arrives and raises "No response received" when a
        command legitimately has nothing more to say.
        """
        buf = b""
        for _ in range(timeout_reads):
            chunk = self.serial.receive(1)
            if not chunk:
                if buf:
                    break          # reply complete, line has gone quiet
                continue           # nothing yet, keep waiting
            buf += chunk
            if ACK in buf or b"OK" in buf or b"DONE" in buf:
                # Consume any trailing LF/CR so the next command starts clean.
                self.serial.receive(4)
                return True
        logger.debug("status reply: got %r", buf)
        return False

    def _read_text_block(self, max_bytes: int = 512,
                         quiet_reads: int = 3) -> str:
        """Read a multi-line text response, stopping when the line goes quiet.

        _read_ok_response() returns as soon as it has one payload line,
        which is right for RXCHECK but truncates BARDATA's nine.  There is
        no length prefix and no terminator distinguishable from the LF CR
        that ends every line, so the only way to know the console has
        finished is that it stops sending.

        Reads until `quiet_reads` consecutive empty reads once something
        has arrived.
        """
        buf = b""
        quiet = 0
        for _ in range(max_bytes):
            chunk = self.serial.receive(1)
            if not chunk:
                if buf:
                    quiet += 1
                    if quiet >= quiet_reads:
                        break
                continue
            quiet = 0
            buf += chunk
        return buf.decode("ascii", errors="replace")

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

    async def async_hilows(self) -> Optional[VantageHighsLows]:
        return await self._run_in_executor(self.hilows)

    async def async_bardata(self) -> Optional[BarometerCalibration]:
        return await self._run_in_executor(self.bardata)
