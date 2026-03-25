"""High-level driver for Davis WeatherLink communication.

Orchestrates serial communication: station detection, LOOP polling,
memory reads, archive sync, and calibration.
"""

import logging
import struct
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .serial_port import SerialPort
from .commands import (
    build_loop_command,
    build_wrd_command,
    build_wwr_command,
    build_rrd_command,
    build_srd_command,
    build_stop_command,
    build_start_command,
    build_crc0_command,
    build_sap_command,
    build_ssp_command,
    build_arc_command,
)
from .crc import crc_validate, crc_calculate
from .constants import (
    StationModel,
    STATION_NAMES,
    LOOP_DATA_SIZE,
    SOH,
    ACK,
    CAN,
    MAX_RETRIES,
)
from .loop_packet import parse_loop_packet
from .station_types import SensorReading
from .memory_map import BasicBank0, BasicBank1, GroWeatherBank1, GroWeatherLinkBank1, LinkBank1, MemAddr
from .base import (
    StationDriver,
    SensorSnapshot,
    HardwareInfo,
    CAP_ARCHIVE_SYNC,
    CAP_CALIBRATION_RW,
    CAP_CLOCK_SYNC,
    CAP_RAIN_RESET,
    CAP_HILOWS,
)

logger = logging.getLogger(__name__)


def bcd_decode(b: int) -> int:
    """Decode a BCD-encoded byte: 0x23 -> 23."""
    return (b >> 4) * 10 + (b & 0x0F)


def _bcd_encode(val: int) -> int:
    """Encode an integer (0-99) as BCD: 23 -> 0x23."""
    return ((val // 10) << 4) | (val % 10)


@dataclass
class CalibrationOffsets:
    """Calibration offsets read from station memory."""
    inside_temp: int = 0    # tenths F to add
    outside_temp: int = 0   # tenths F to add
    barometer: int = 0      # thousandths inHg to subtract
    outside_hum: int = 0    # percent to add
    rain_cal: int = 100     # clicks per inch


class LinkDriver(StationDriver):
    """High-level WeatherLink serial communication driver.

    Implements the StationDriver interface for the legacy Davis WeatherLink
    protocol (Weather Monitor II, Wizard III, GroWeather, Energy, Health).
    """

    def __init__(self, port: str, baud_rate: int = 19200, timeout: float = 2.0):
        self.serial = SerialPort(port, baud_rate, timeout)
        self.station_model: Optional[StationModel] = None
        self.calibration = CalibrationOffsets()
        self.is_rev_e = False
        self._connected = False
        self._stop_requested = False
        self._io_lock = threading.RLock()

    @property
    def connected(self) -> bool:
        return self._connected and self.serial.is_open

    def request_stop(self) -> None:
        """Signal the blocking poll_loop thread to exit early."""
        self._stop_requested = True

    def open(self) -> None:
        """Open serial port and initialize connection."""
        self.serial.open()
        self._connected = True

    def close(self) -> None:
        """Close serial port."""
        self.serial.close()
        self._connected = False

    def detect_station_type(self) -> StationModel:
        """Read model nibble from station memory to determine station type.

        WRD command: 1 nibble from bank 0 at address 0x4D.
        """
        data = self.read_station_memory(
            BasicBank0.MODEL.bank,
            BasicBank0.MODEL.address,
            BasicBank0.MODEL.nibbles,
        )
        if data is None:
            raise ConnectionError("Failed to read station model")

        model_code = data[0] & 0x0F
        try:
            self.station_model = StationModel(model_code)
        except ValueError:
            logger.warning("Unknown model code: 0x%X, defaulting to Monitor", model_code)
            self.station_model = StationModel.MONITOR

        logger.info("Detected station type: %s (code=%d)", self.station_model.name, model_code)
        return self.station_model

    def read_calibration(self) -> CalibrationOffsets:
        """Read calibration offsets from station memory.

        Applies to Monitor/Wizard/Perception stations.
        Reference: techref.txt lines 847-1108.
        """
        self.serial.flush()

        # Inside temp calibration: bank 1, address 0x52, 4 nibbles
        data = self.read_station_memory(
            BasicBank1.INSIDE_TEMP_CAL.bank,
            BasicBank1.INSIDE_TEMP_CAL.address,
            BasicBank1.INSIDE_TEMP_CAL.nibbles,
        )
        if data and len(data) >= 2:
            self.calibration.inside_temp = struct.unpack("<h", data[:2])[0]
        else:
            logger.warning("Failed to read inside temp calibration (data=%s)", data)

        # Outside temp calibration
        data = self.read_station_memory(
            BasicBank1.OUTSIDE_TEMP_CAL.bank,
            BasicBank1.OUTSIDE_TEMP_CAL.address,
            BasicBank1.OUTSIDE_TEMP_CAL.nibbles,
        )
        if data and len(data) >= 2:
            self.calibration.outside_temp = struct.unpack("<h", data[:2])[0]
        else:
            logger.warning("Failed to read outside temp calibration (data=%s)", data)

        # Barometer calibration
        data = self.read_station_memory(
            BasicBank1.BAR_CAL.bank,
            BasicBank1.BAR_CAL.address,
            BasicBank1.BAR_CAL.nibbles,
        )
        if data and len(data) >= 2:
            self.calibration.barometer = struct.unpack("<h", data[:2])[0]
            logger.info("Barometer calibration raw bytes: %s -> %d",
                        data[:2].hex(), self.calibration.barometer)
        else:
            logger.warning("Failed to read barometer calibration (data=%s)", data)

        # Outside humidity calibration
        data = self.read_station_memory(
            BasicBank1.OUTSIDE_HUMIDITY_CAL.bank,
            BasicBank1.OUTSIDE_HUMIDITY_CAL.address,
            BasicBank1.OUTSIDE_HUMIDITY_CAL.nibbles,
        )
        if data and len(data) >= 2:
            self.calibration.outside_hum = struct.unpack("<h", data[:2])[0]
        else:
            logger.warning("Failed to read outside humidity calibration (data=%s)", data)

        # Rain calibration (clicks per inch)
        data = self.read_station_memory(
            BasicBank1.RAIN_CAL.bank,
            BasicBank1.RAIN_CAL.address,
            BasicBank1.RAIN_CAL.nibbles,
        )
        if data and len(data) >= 2:
            cal = struct.unpack("<H", data[:2])[0]
            if cal > 0:
                self.calibration.rain_cal = cal
        else:
            logger.warning("Failed to read rain calibration (data=%s)", data)

        logger.info("Calibration offsets: %s", self.calibration)
        return self.calibration

    def apply_calibration(self, reading: SensorReading) -> SensorReading:
        """Apply calibration offsets to a sensor reading.

        Per techref.txt:
        - calibrated_temp = raw_temp + temp_cal
        - calibrated_bar = raw_bar - bar_cal
        - calibrated_hum = clamp(raw_hum + hum_cal, 1, 100)
        """
        if reading.inside_temp is not None:
            reading.inside_temp += self.calibration.inside_temp
        if reading.outside_temp is not None:
            reading.outside_temp += self.calibration.outside_temp
        if reading.barometer is not None:
            reading.barometer -= self.calibration.barometer
        if reading.outside_humidity is not None:
            reading.outside_humidity = max(1, min(100,
                reading.outside_humidity + self.calibration.outside_hum))
        return reading

    def poll_loop(self) -> Optional[SensorReading]:
        """Send LOOP command and parse the response.

        Returns a calibrated SensorReading, or None on failure.
        """
        if self.station_model is None:
            raise RuntimeError("Station type not detected. Call detect_station_type() first.")

        with self._io_lock:
            for attempt in range(MAX_RETRIES + 1):
                if self._stop_requested:
                    logger.info("LOOP poll aborted (stop requested)")
                    return None
                try:
                    reading = self._send_loop_once()
                    if reading is not None:
                        return self.apply_calibration(reading)
                    else:
                        if self._stop_requested:
                            return None
                        logger.warning("LOOP attempt %d/%d: no response", attempt + 1, MAX_RETRIES + 1)
                except Exception as e:
                    if self._stop_requested:
                        return None
                    logger.warning("LOOP attempt %d/%d failed: %s", attempt + 1, MAX_RETRIES + 1, e)

                if attempt < MAX_RETRIES:
                    self.serial.flush()

        logger.error("LOOP command failed after %d attempts", MAX_RETRIES + 1)
        return None

    def _send_loop_once(self) -> Optional[SensorReading]:
        """Single attempt to send LOOP and parse response."""
        self.serial.flush()
        cmd = build_loop_command(1)
        self.serial.send(cmd)

        if not self.serial.wait_for_ack():
            return None

        # Read SOH + data + CRC
        data_size = LOOP_DATA_SIZE[self.station_model]
        total_size = 1 + data_size + 2  # SOH + data + 2-byte CRC
        raw = self.serial.receive(total_size)

        if len(raw) < total_size:
            logger.warning("Incomplete LOOP response: %d/%d bytes", len(raw), total_size)
            return None

        return parse_loop_packet(raw, self.station_model)

    def read_station_memory(
        self, bank: int, address: int, n_nibbles: int
    ) -> Optional[bytes]:
        """Read station processor memory using WRD command.

        Returns raw nibble data as bytes, or None on failure.
        """
        with self._io_lock:
            for attempt in range(MAX_RETRIES + 1):
                if self._stop_requested:
                    return None
                try:
                    cmd = build_wrd_command(n_nibbles, bank, address)
                    logger.debug(
                        "WRD %d nibbles bank %d addr 0x%02X -> TX: %s",
                        n_nibbles, bank, address, cmd.hex(),
                    )
                    self.serial.send(cmd)

                    if not self.serial.wait_for_ack():
                        if self._stop_requested:
                            return None
                        logger.warning(
                            "WRD bank %d addr 0x%02X attempt %d: no ACK",
                            bank, address, attempt + 1,
                        )
                        continue

                    # Number of bytes = ceil(n_nibbles / 2)
                    n_bytes = (n_nibbles + 1) // 2
                    # Always read data + 2 CRC bytes — the WeatherLink
                    # sends trailing CRC regardless of revision, and leaving
                    # them in the buffer corrupts subsequent reads.
                    read_size = n_bytes + 2
                    data = self.serial.receive(read_size)
                    logger.debug("WRD RX: %s (%d bytes)", data.hex(), len(data))

                    if len(data) < n_bytes:
                        logger.warning(
                            "WRD bank %d addr 0x%02X attempt %d: short read %d/%d",
                            bank, address, attempt + 1, len(data), n_bytes,
                        )
                        continue

                    # Validate CRC if we got the full response
                    if len(data) >= n_bytes + 2:
                        if crc_validate(data[:n_bytes + 2]):
                            logger.debug("WRD CRC OK")
                        else:
                            logger.debug("WRD CRC mismatch (non-Rev-E units may not send valid CRC)")

                    return data[:n_bytes]

                except Exception as e:
                    if self._stop_requested:
                        return None
                    logger.warning("WRD attempt %d failed: %s", attempt + 1, e)

            return None

    def read_link_memory(
        self, bank: int, address: int, n_nibbles: int
    ) -> Optional[bytes]:
        """Read link processor memory using RRD command."""
        with self._io_lock:
            for attempt in range(MAX_RETRIES + 1):
                if self._stop_requested:
                    return None
                try:
                    cmd = build_rrd_command(bank, address, n_nibbles)
                    self.serial.send(cmd)

                    if not self.serial.wait_for_ack():
                        if self._stop_requested:
                            return None
                        continue

                    n_bytes = (n_nibbles + 1) // 2
                    read_size = n_bytes + 2  # try to drain trailing CRC
                    data = self.serial.receive(read_size)

                    if len(data) < n_bytes:
                        if self._stop_requested:
                            return None
                        logger.warning(
                            "RRD bank %d addr 0x%03X attempt %d: short read (%d/%d bytes)",
                            bank, address, attempt + 1, len(data), n_bytes,
                        )
                        continue

                    # Validate CRC if we got the full response (data + 2 CRC bytes).
                    # Older/non-Rev-E units may not send CRC — accept data anyway.
                    if len(data) >= n_bytes + 2:
                        if crc_validate(data[:n_bytes + 2]):
                            logger.debug("RRD CRC OK")
                        else:
                            logger.debug(
                                "RRD bank %d addr 0x%03X: CRC mismatch (may be non-Rev-E unit)",
                                bank, address,
                            )

                    return data[:n_bytes]

                except Exception as e:
                    if self._stop_requested:
                        return None
                    logger.warning("RRD attempt %d failed: %s", attempt + 1, e)

            return None

    def read_archive(self, address: int, n_bytes: int) -> Optional[bytes]:
        """Read archive/SRAM memory using SRD command with retries."""
        with self._io_lock:
            for attempt in range(MAX_RETRIES + 1):
                if self._stop_requested:
                    return None
                try:
                    self.serial.flush()
                    cmd = build_srd_command(address, n_bytes)
                    self.serial.send(cmd)

                    if not self.serial.wait_for_ack():
                        if self._stop_requested:
                            return None
                        logger.warning("SRD addr 0x%04X attempt %d: no ACK", address, attempt + 1)
                        continue

                    # SRD always returns data + 2-byte CRC
                    data = self.serial.receive(n_bytes + 2)
                    if len(data) < n_bytes + 2:
                        if self._stop_requested:
                            return None
                        logger.warning("SRD addr 0x%04X attempt %d: short read", address, attempt + 1)
                        continue

                    if not crc_validate(data):
                        if self._stop_requested:
                            return None
                        logger.warning("SRD addr 0x%04X attempt %d: CRC failed", address, attempt + 1)
                        continue

                    return data[:n_bytes]

                except Exception as e:
                    if self._stop_requested:
                        return None
                    logger.warning("SRD attempt %d failed: %s", attempt + 1, e)

            return None

    def read_archive_pointers(self) -> Optional[tuple]:
        """Read NewPtr and OldPtr from link processor memory.

        Returns (new_ptr, old_ptr) as SRAM addresses, or None on failure.
        """
        if self.station_model is None:
            return None

        is_gro = self.station_model in (
            StationModel.GROWEATHER, StationModel.ENERGY, StationModel.HEALTH,
        )

        if is_gro:
            new_addr = GroWeatherLinkBank1.NEW_ARCHIVE_PTR
            old_addr = GroWeatherLinkBank1.OLD_ARCHIVE_PTR
        else:
            new_addr = LinkBank1.NEW_ARCHIVE_PTR
            old_addr = LinkBank1.OLD_ARCHIVE_PTR

        new_data = self.read_link_memory(new_addr.bank, new_addr.address, new_addr.nibbles)
        if new_data is None or len(new_data) < 2:
            return None

        old_data = self.read_link_memory(old_addr.bank, old_addr.address, old_addr.nibbles)
        if old_data is None or len(old_data) < 2:
            return None

        new_ptr = struct.unpack("<H", new_data[:2])[0]
        old_ptr = struct.unpack("<H", old_data[:2])[0]
        return (new_ptr, old_ptr)

    def read_archive_period(self) -> Optional[int]:
        """Read the archive interval in minutes from link memory."""
        if self.station_model is None:
            return None

        is_gro = self.station_model in (
            StationModel.GROWEATHER, StationModel.ENERGY, StationModel.HEALTH,
        )
        addr = GroWeatherLinkBank1.ARCHIVE_PERIOD if is_gro else LinkBank1.ARCHIVE_PERIOD
        data = self.read_link_memory(addr.bank, addr.address, addr.nibbles)
        if data is None or len(data) < 1:
            return None
        return data[0]

    async def async_read_archive(self, address: int, n_bytes: int) -> Optional[bytes]:
        """Async version of read_archive."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.read_archive, address, n_bytes)

    async def async_read_archive_pointers(self) -> Optional[tuple]:
        """Async version of read_archive_pointers."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.read_archive_pointers)

    async def async_read_archive_period(self) -> Optional[int]:
        """Async version of read_archive_period."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.read_archive_period)

    def write_station_memory(
        self, bank: int, address: int, n_nibbles: int, data: bytes
    ) -> bool:
        """Write station processor memory using WWR command.

        Returns True on success (ACK received), False on failure.
        """
        with self._io_lock:
            for attempt in range(MAX_RETRIES + 1):
                if self._stop_requested:
                    return False
                try:
                    cmd = build_wwr_command(n_nibbles, bank, address, data)
                    logger.debug(
                        "WWR %d nibbles bank %d addr 0x%02X data=%s",
                        n_nibbles, bank, address, data.hex(),
                    )
                    self.serial.send(cmd)

                    if self.serial.wait_for_ack():
                        logger.debug("WWR ACK OK")
                        return True

                    if self._stop_requested:
                        return False
                    logger.warning(
                        "WWR bank %d addr 0x%02X attempt %d: no ACK",
                        bank, address, attempt + 1,
                    )
                except Exception as e:
                    if self._stop_requested:
                        return False
                    logger.warning("WWR attempt %d failed: %s", attempt + 1, e)

            return False

    def read_station_time(self) -> Optional[dict]:
        """Read station time and date from processor memory.

        Returns dict with keys: hour, minute, second, day, month, year.
        Year is None for Monitor/Wizard/Perception (no year nibbles).
        """
        if self.station_model is None:
            return None

        is_gro = self.station_model in (
            StationModel.GROWEATHER,
            StationModel.ENERGY,
            StationModel.HEALTH,
        )

        time_addr = GroWeatherBank1.TIME if is_gro else BasicBank1.TIME
        date_addr = GroWeatherBank1.DATE if is_gro else BasicBank1.DATE
        date_nibbles = 5 if is_gro else 3

        with self._io_lock:
            # Read time (6 nibbles = 3 bytes: BCD hour, minute, second)
            time_data = self.read_station_memory(
                time_addr.bank, time_addr.address, time_addr.nibbles
            )
            if time_data is None or len(time_data) < 3:
                logger.warning("Station time read failed (no data)")
                return None

            # Read date
            date_data = self.read_station_memory(
                date_addr.bank, date_addr.address, date_nibbles
            )
            if date_data is None or len(date_data) < 2:
                logger.warning("Station date read failed (no data)")
                return None

        hour = bcd_decode(time_data[0])
        minute = bcd_decode(time_data[1])
        second = bcd_decode(time_data[2])

        day = bcd_decode(date_data[0])
        # Month is in the low nibble of byte 1
        month = date_data[1] & 0x0F

        year = None
        if is_gro and len(date_data) >= 3:
            # Year = binary value across upper nibble of byte 1 + byte 2
            year = 1900 + ((date_data[2] & 0x0F) << 4) | (date_data[1] >> 4)

        logger.info(
            "Station clock: %02d:%02d:%02d %d/%d%s",
            hour, minute, second, month, day,
            f"/{year}" if year else "",
        )

        return {
            "hour": hour, "minute": minute, "second": second,
            "day": day, "month": month, "year": year,
        }

    def write_station_time(self, dt: datetime) -> bool:
        """Write time and date to station processor memory.

        Sends STOP before writing and START after.
        """
        if self.station_model is None:
            return False

        is_gro = self.station_model in (
            StationModel.GROWEATHER,
            StationModel.ENERGY,
            StationModel.HEALTH,
        )

        time_addr = GroWeatherBank1.TIME if is_gro else BasicBank1.TIME
        date_addr = GroWeatherBank1.DATE if is_gro else BasicBank1.DATE

        # Encode time: 6 nibbles = 3 BCD bytes (hour, minute, second)
        time_bytes = bytes([
            _bcd_encode(dt.hour),
            _bcd_encode(dt.minute),
            _bcd_encode(dt.second),
        ])

        # Encode date
        if is_gro:
            # 5 nibbles: day(2 BCD) + month(1 binary) + year(2 binary)
            yr = (dt.year - 1900) & 0xFF
            date_bytes = bytes([
                _bcd_encode(dt.day),
                (yr & 0x0F) << 4 | (dt.month & 0x0F),
                (yr >> 4) & 0x0F,
            ])
            date_nibbles = 5
        else:
            # 3 nibbles: day(2 BCD) + month(1 binary)
            date_bytes = bytes([
                _bcd_encode(dt.day),
                dt.month & 0x0F,
            ])
            date_nibbles = 3

        with self._io_lock:
            # STOP station polling for reliable writes
            self.stop_polling()

            try:
                ok_time = self.write_station_memory(
                    time_addr.bank, time_addr.address, 6, time_bytes
                )
                ok_date = self.write_station_memory(
                    date_addr.bank, date_addr.address, date_nibbles, date_bytes
                )
            finally:
                self.start_polling()

        if ok_time and ok_date:
            logger.info("Station clock synced to %s", dt.strftime("%H:%M:%S %m/%d/%Y"))
        else:
            logger.warning("Station clock sync partial failure: time=%s date=%s", ok_time, ok_date)

        return ok_time and ok_date

    def stop_polling(self) -> bool:
        """Send STOP command to pause WeatherLink from polling station."""
        self.serial.send(build_stop_command())
        return self.serial.wait_for_ack()

    def start_polling(self) -> bool:
        """Send START command to resume WeatherLink polling."""
        self.serial.send(build_start_command())
        return self.serial.wait_for_ack()

    def read_sample_period(self) -> Optional[int]:
        """Read the sample period in seconds from link memory.

        Raw value is stored as (256 - seconds), so we decode back.
        """
        addr = LinkBank1.SAMPLE_PERIOD
        data = self.read_link_memory(addr.bank, addr.address, addr.nibbles)
        if data is None or len(data) < 1:
            return None
        raw = data[0]
        return (256 - raw) if raw != 0 else 256

    def set_archive_period(self, minutes: int) -> bool:
        """Set the archive period (1-120 minutes) via SAP command.

        Sends SAP with io_lock held.  Returns True on ACK.
        """
        if not 1 <= minutes <= 120:
            raise ValueError("Archive period must be 1-120 minutes")

        with self._io_lock:
            self.serial.flush()
            cmd = build_sap_command(minutes)
            self.serial.send(cmd)
            ok = self.serial.wait_for_ack()
            if ok:
                logger.info("Archive period set to %d minutes", minutes)
            else:
                logger.warning("SAP command not acknowledged")
            return ok

    def set_sample_period(self, seconds: int) -> bool:
        """Set the sample period (1-255 seconds) via SSP command.

        Sends SSP with io_lock held.  Returns True on ACK.
        """
        if not 1 <= seconds <= 255:
            raise ValueError("Sample period must be 1-255 seconds")

        with self._io_lock:
            self.serial.flush()
            cmd = build_ssp_command(seconds)
            self.serial.send(cmd)
            ok = self.serial.wait_for_ack()
            if ok:
                logger.info("Sample period set to %d seconds", seconds)
            else:
                logger.warning("SSP command not acknowledged")
            return ok

    def write_calibration(self, offsets: CalibrationOffsets) -> bool:
        """Write calibration offsets to station memory.

        Sends STOP, writes each offset via WWR, then START.
        Updates self.calibration on success.
        """
        with self._io_lock:
            self.stop_polling()
            try:
                ok = True

                # Inside temp (signed i16, tenths F)
                data = struct.pack("<h", offsets.inside_temp)
                ok &= self.write_station_memory(
                    BasicBank1.INSIDE_TEMP_CAL.bank,
                    BasicBank1.INSIDE_TEMP_CAL.address,
                    BasicBank1.INSIDE_TEMP_CAL.nibbles,
                    data,
                )

                # Outside temp (signed i16, tenths F)
                data = struct.pack("<h", offsets.outside_temp)
                ok &= self.write_station_memory(
                    BasicBank1.OUTSIDE_TEMP_CAL.bank,
                    BasicBank1.OUTSIDE_TEMP_CAL.address,
                    BasicBank1.OUTSIDE_TEMP_CAL.nibbles,
                    data,
                )

                # Barometer (signed i16, thousandths inHg)
                data = struct.pack("<h", offsets.barometer)
                ok &= self.write_station_memory(
                    BasicBank1.BAR_CAL.bank,
                    BasicBank1.BAR_CAL.address,
                    BasicBank1.BAR_CAL.nibbles,
                    data,
                )

                # Outside humidity (signed i16, percent)
                data = struct.pack("<h", offsets.outside_hum)
                ok &= self.write_station_memory(
                    BasicBank1.OUTSIDE_HUMIDITY_CAL.bank,
                    BasicBank1.OUTSIDE_HUMIDITY_CAL.address,
                    BasicBank1.OUTSIDE_HUMIDITY_CAL.nibbles,
                    data,
                )

                # Rain calibration (unsigned u16, clicks per inch)
                data = struct.pack("<H", offsets.rain_cal)
                ok &= self.write_station_memory(
                    BasicBank1.RAIN_CAL.bank,
                    BasicBank1.RAIN_CAL.address,
                    BasicBank1.RAIN_CAL.nibbles,
                    data,
                )

            finally:
                self.start_polling()

        if ok:
            self.calibration = offsets
            logger.info("Calibration offsets written: %s", offsets)
        else:
            logger.warning("Calibration write partial failure")
            # Re-read to get actual state
            self.read_calibration()
        return ok

    def clear_rain_daily(self) -> bool:
        """Clear the daily rain accumulator by writing 0x0000."""
        with self._io_lock:
            self.stop_polling()
            try:
                ok = self.write_station_memory(
                    BasicBank1.RAIN_DAILY.bank,
                    BasicBank1.RAIN_DAILY.address,
                    BasicBank1.RAIN_DAILY.nibbles,
                    b"\x00\x00",
                )
            finally:
                self.start_polling()
        if ok:
            logger.info("Daily rain cleared")
        return ok

    def read_rain_daily(self) -> Optional[int]:
        """Read the daily rain accumulator from station processor memory.

        Returns raw click count (each click = 0.01 in), or None on failure.
        Reading directly from memory avoids LOOP-packet staleness.
        """
        if self.station_model is None:
            return None

        is_gro = self.station_model in (
            StationModel.GROWEATHER, StationModel.ENERGY, StationModel.HEALTH,
        )
        addr = GroWeatherBank1.RAIN_DAILY if is_gro else BasicBank1.RAIN_DAILY

        data = self.read_station_memory(addr.bank, addr.address, addr.nibbles)
        if data is None or len(data) < 2:
            return None

        value = struct.unpack_from("<H", data)[0]
        # GroWeather uses 3 nibbles (12 bits) — mask off the unused nibble
        if addr.nibbles == 3:
            value &= 0x0FFF
        return value

    def read_rain_yearly(self) -> Optional[int]:
        """Read the yearly rain accumulator from station processor memory.

        Returns raw click count (each click = 0.01 in), or None on failure.
        """
        if self.station_model is None:
            return None

        is_gro = self.station_model in (
            StationModel.GROWEATHER, StationModel.ENERGY, StationModel.HEALTH,
        )
        addr = GroWeatherBank1.RAIN_YEARLY if is_gro else BasicBank1.RAIN_YEARLY

        data = self.read_station_memory(addr.bank, addr.address, addr.nibbles)
        if data is None or len(data) < 2:
            return None

        return struct.unpack_from("<H", data)[0]

    def clear_rain_yearly(self) -> bool:
        """Clear the yearly rain accumulator by writing 0x0000."""
        with self._io_lock:
            self.stop_polling()
            try:
                ok = self.write_station_memory(
                    BasicBank1.RAIN_YEARLY.bank,
                    BasicBank1.RAIN_YEARLY.address,
                    BasicBank1.RAIN_YEARLY.nibbles,
                    b"\x00\x00",
                )
            finally:
                self.start_polling()
        if ok:
            logger.info("Yearly rain cleared")
        return ok

    def force_archive(self) -> bool:
        """Send ARC command to force immediate archive write."""
        with self._io_lock:
            self.serial.flush()
            cmd = build_arc_command()
            self.serial.send(cmd)
            ok = self.serial.wait_for_ack()
            if ok:
                logger.info("Archive write forced")
            return ok

    async def async_poll_loop(self) -> Optional[SensorReading]:
        """Async version of poll_loop."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.poll_loop)

    async def async_detect_station_type(self) -> StationModel:
        """Async version of detect_station_type."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.detect_station_type)

    async def async_read_calibration(self) -> CalibrationOffsets:
        """Async version of read_calibration."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.read_calibration)

    async def async_read_station_time(self) -> Optional[dict]:
        """Async version of read_station_time."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.read_station_time)

    async def async_write_station_time(self, dt: datetime) -> bool:
        """Async version of write_station_time."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.write_station_time, dt)

    async def async_read_sample_period(self) -> Optional[int]:
        """Async version of read_sample_period."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.read_sample_period)

    async def async_set_archive_period(self, minutes: int) -> bool:
        """Async version of set_archive_period."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.set_archive_period, minutes)

    async def async_set_sample_period(self, seconds: int) -> bool:
        """Async version of set_sample_period."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.set_sample_period, seconds)

    async def async_write_calibration(self, offsets: CalibrationOffsets) -> bool:
        """Async version of write_calibration."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.write_calibration, offsets)

    async def async_read_rain_daily(self) -> Optional[int]:
        """Async version of read_rain_daily."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.read_rain_daily)

    async def async_read_rain_yearly(self) -> Optional[int]:
        """Async version of read_rain_yearly."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.read_rain_yearly)

    async def async_clear_rain_daily(self) -> bool:
        """Async version of clear_rain_daily."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.clear_rain_daily)

    async def async_clear_rain_yearly(self) -> bool:
        """Async version of clear_rain_yearly."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.clear_rain_yearly)

    async def async_force_archive(self) -> bool:
        """Async version of force_archive."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.force_archive)

    # ---- StationDriver interface ----

    async def connect(self) -> None:
        """Open serial, detect station, read calibration."""
        self.open()
        await self.async_detect_station_type()
        await self.async_read_calibration()

    async def disconnect(self) -> None:
        """Close the serial port."""
        self.close()

    async def detect_hardware(self) -> HardwareInfo:
        """Detect station model and return hardware descriptor."""
        model = await self.async_detect_station_type()
        return HardwareInfo(
            name=STATION_NAMES.get(model, "Unknown"),
            model_code=model.value,
            capabilities=self.capabilities,
        )

    async def poll(self) -> Optional[SensorSnapshot]:
        """Poll the station and return a SensorSnapshot in standard units."""
        reading = await self.async_poll_loop()
        if reading is None:
            return None

        # Read rain accumulators directly from station processor memory
        # instead of relying on the LOOP packet, which can lag behind
        # actual station state after clears or bucket tips.
        daily_clicks: Optional[int] = None
        yearly_clicks: Optional[int] = None
        if self.station_model is not None and not self._stop_requested:
            try:
                daily_clicks = await self.async_read_rain_daily()
            except Exception:
                pass  # fall back to LOOP value below
            try:
                yearly_clicks = await self.async_read_rain_yearly()
            except Exception:
                pass  # non-critical

        # Use direct memory read when available, LOOP packet as fallback
        rain_daily_clicks = (
            daily_clicks if daily_clicks is not None else reading.rain_total
        )

        # SensorReading is now in SI units (tenths °C, tenths hPa, tenths m/s,
        # tenths mm) after _to_si() in loop_packet.py. Convert to SensorSnapshot
        # display floats (°F, inHg, mph, inches) for the broadcast pipeline.
        return SensorSnapshot(
            inside_temp=(
                reading.inside_temp / 10.0 * 9 / 5 + 32
                if reading.inside_temp is not None else None
            ),
            outside_temp=(
                reading.outside_temp / 10.0 * 9 / 5 + 32
                if reading.outside_temp is not None else None
            ),
            inside_humidity=reading.inside_humidity,
            outside_humidity=reading.outside_humidity,
            wind_speed=(
                round(reading.wind_speed / 10.0 * 2.23694)
                if reading.wind_speed is not None else None
            ),
            wind_direction=reading.wind_direction,
            barometer=(
                reading.barometer / 10.0 / 33.8639
                if reading.barometer is not None else None
            ),
            rain_daily=(
                rain_daily_clicks / 10.0 / 25.4
                if rain_daily_clicks is not None else None
            ),
            rain_rate=(
                reading.rain_rate / 10.0 / 25.4
                if reading.rain_rate is not None else None
            ),
            rain_yearly=(
                yearly_clicks / 10.0 / 25.4
                if yearly_clicks is not None else None
            ),
            solar_radiation=reading.solar_radiation,
            uv_index=(
                reading.uv_index / 10.0
                if reading.uv_index is not None else None
            ),
            soil_temp=(
                reading.soil_temp / 10.0 * 9 / 5 + 32
                if reading.soil_temp is not None else None
            ),
            leaf_wetness=reading.leaf_wetness,
            et_daily=(
                reading.et_total * 0.01
                if reading.et_total is not None else None
            ),
        )

    @property
    def station_name(self) -> str:
        """Human-readable name of the connected station model."""
        if self.station_model is None:
            return "Unknown"
        return STATION_NAMES.get(self.station_model, "Unknown")

    @property
    def capabilities(self) -> set[str]:
        """Feature flags for the legacy WeatherLink driver."""
        return {
            CAP_ARCHIVE_SYNC,
            CAP_CALIBRATION_RW,
            CAP_CLOCK_SYNC,
            CAP_RAIN_RESET,
            CAP_HILOWS,
        }
