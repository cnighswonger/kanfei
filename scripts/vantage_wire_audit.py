"""Vantage Vue Console wire audit — read-only capture.

Sends every documented command in the Davis Serial Communication
Reference to a Vantage station, captures raw response bytes, plus a
full 4096-byte EEPROM dump.  Nothing writes state.  Output is a JSON
blob for offline analysis — pipe to a file, then use whatever
tooling to diff against the reference or a prior capture.

The audit that produced ``reference/vantage_fw433_wire_audit.md`` was
run with this script against the bench Vue on vsits-02 at ``ttyUSB4``.

Usage:
    python3 scripts/vantage_wire_audit.py [--port PORT] [--baud BAUD] > audit.json

Defaults to ``/dev/ttyUSB4`` at 19200 baud (the bench Vue on vsits-02).

Safety:
    - Nothing writes state.  All commands are read-only or, for the
      undocumented probes, expected to fail cleanly.
    - Do NOT run this against a console currently in use by
      ``kanfei-logger`` on the same port — the single-master serial
      contention will produce fake CRC errors and disrupt the poll.
      Stop the service first or use a different port.

The read-until-silence loop in ``capture_multiline`` fixes the
fixed-buffer undersizing bug the audit report calls out — a HELP
response longer than the caller's guess will be truncated by a
plain ``receive(n)`` call.  Prefer this loop for any command whose
response length is unknown.
"""
import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Import the driver from the installed backend rather than pinning a
# path.  If this script is being run from a dev checkout, the caller
# is responsible for having the backend importable — typically that
# means running from the vsits-02 host under the kanfei venv.
try:
    from app.protocol.vantage.driver import VantageDriver
    from app.protocol.vantage.commands import (
        cmd_ver, cmd_nver, cmd_loop, cmd_getee, cmd_gettime,
        cmd_rxcheck, cmd_hilows, cmd_bardata,
    )
except ImportError:
    # Fall back to the vsits-02 install path so this script can run
    # without extra PYTHONPATH juggling on that host.
    sys.path.insert(0, "/opt/kanfei/backend")
    from app.protocol.vantage.driver import VantageDriver
    from app.protocol.vantage.commands import (
        cmd_ver, cmd_nver, cmd_loop, cmd_getee, cmd_gettime,
        cmd_rxcheck, cmd_hilows, cmd_bardata,
    )


class Capture:
    """Accumulate audit findings as an ordered list of dicts."""
    def __init__(self):
        self.results = []
        self.eeprom = None

    def add(self, category, name, **kwargs):
        self.results.append(dict(category=category, name=name, **kwargs))


def send_raw(drv, cmd_bytes, ack_read=True, n_data=0):
    """Send raw bytes, capture an ACK byte (if any) and N following data bytes.

    Fixed-length receive.  Suitable for binary commands with known
    response length (LOOP, HILOWS, GETEE, GETTIME).  For text
    responses of unknown length, use ``capture_multiline`` instead.
    """
    drv._wakeup()
    drv.serial.flush()
    t0 = time.time()
    drv.serial.send(cmd_bytes)
    ack = drv.serial.receive_byte() if ack_read else None
    data = drv.serial.receive(n_data) if n_data else b""
    elapsed_ms = (time.time() - t0) * 1000
    return dict(
        cmd_bytes=cmd_bytes.hex(),
        cmd_str=cmd_bytes.decode("ascii", errors="replace"),
        ack_byte=ack,
        ack_hex=f"0x{ack:02X}" if ack is not None else None,
        data_len=len(data),
        data_hex=data.hex(),
        data_ascii="".join(
            chr(b) if 32 <= b < 127 else "." for b in data
        ),
        elapsed_ms=round(elapsed_ms, 2),
    )


def capture_multiline(drv, cmd_bytes, wait_sec=3, silence_sec=0.5):
    """Send raw bytes, read until console falls silent.

    Read-until-silence: waits up to ``wait_sec`` total, or exits after
    ``silence_sec`` of no bytes if we've already received something.
    Fixes the fixed-buffer undersizing bug the audit report calls out
    — a HELP response of 526 bytes was truncated to 32 by an earlier
    ``receive(32)`` call.
    """
    drv._wakeup()
    drv.serial.flush()
    t0 = time.time()
    drv.serial.send(cmd_bytes)
    buf = bytearray()
    end_by = t0 + wait_sec
    last_byte_at = t0
    while time.time() < end_by:
        b = drv.serial.receive_byte()
        if b is None:
            if time.time() - last_byte_at > silence_sec and len(buf) > 0:
                break
            continue
        buf.append(b)
        last_byte_at = time.time()
    elapsed_ms = (time.time() - t0) * 1000
    data = bytes(buf)
    return dict(
        cmd_bytes=cmd_bytes.hex(),
        cmd_str=cmd_bytes.decode("ascii", errors="replace"),
        data_len=len(data),
        data_hex=data.hex(),
        data_ascii="".join(
            chr(b) if 32 <= b < 127 else "." for b in data
        ),
        elapsed_ms=round(elapsed_ms, 2),
    )


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyUSB4",
                        help="Serial port (default: /dev/ttyUSB4, "
                             "the bench Vue on vsits-02)")
    parser.add_argument("--baud", type=int, default=19200,
                        help="Baud rate (default: 19200)")
    args = parser.parse_args()

    cap = Capture()
    drv = VantageDriver(args.port, args.baud)
    await drv.connect()
    loop = asyncio.get_event_loop()

    cap.add("meta", "unit",
            port=args.port,
            baud=args.baud,
            station_name=drv.station_name,
            firmware_version=drv.hw_config.firmware_version,
            firmware_date=drv.hw_config.firmware_date,
            station_type=drv.hw_config.station_type.value,
            timestamp_utc=datetime.now(timezone.utc).isoformat())

    # ---- Identity (text responses) ----
    r = await loop.run_in_executor(None, capture_multiline, drv, cmd_ver())
    cap.add("identity", "VER", **r)
    r = await loop.run_in_executor(None, capture_multiline, drv, cmd_nver())
    cap.add("identity", "NVER", **r)

    # ---- LOOP frames (binary, 99 bytes) ----
    for i in range(3):
        r = await loop.run_in_executor(None, send_raw, drv, cmd_loop(1), True, 99)
        cap.add("data", f"LOOP_frame_{i+1}", **r)

    # ---- LPS (LOOP2) if supported ----
    r = await loop.run_in_executor(None, send_raw, drv, b"LPS 2 1\n", True, 99)
    cap.add("data", "LPS_LOOP2_frame", **r)

    # ---- Time ----
    r = await loop.run_in_executor(None, send_raw, drv, cmd_gettime(), True, 8)
    cap.add("time", "GETTIME", **r)

    # ---- Signal quality ----
    r = await loop.run_in_executor(None, capture_multiline, drv, cmd_rxcheck())
    cap.add("signal", "RXCHECK", **r)
    r = await loop.run_in_executor(None, send_raw, drv, b"RECEIVERS\n", True, 1)
    cap.add("signal", "RECEIVERS", **r)

    # ---- Config / calibration ----
    r = await loop.run_in_executor(None, capture_multiline, drv, b"GETPER\n")
    cap.add("config", "GETPER", **r)
    r = await loop.run_in_executor(None, send_raw, drv, cmd_hilows(), True, 438)
    cap.add("data", "HILOWS", **r)
    r = await loop.run_in_executor(None, send_raw, drv, cmd_bardata(), True, 76)
    cap.add("calibration", "BARDATA", **r)

    # ---- Full EEPROM dump (4096 + 2 CRC) ----
    r = await loop.run_in_executor(None, send_raw, drv, cmd_getee(), True, 4098)
    cap.add("eeprom", "GETEE_full", **r)
    cap.eeprom = r["data_hex"]

    # ---- Test / echo ----
    r = await loop.run_in_executor(None, send_raw, drv, b"TEST\n", False, 8)
    cap.add("test", "TEST_echo", **r)

    # ---- Undocumented probes (read-until-silence for unknown response length) ----
    probes = (
        b"HELP\n",           # revealed the factory-mode command set on fw 4.33
        b"OPMODE\n",         # radio state and per-unit crystal cal
        b"IDENT\n",          # product SKU
        b"?\n", b"HELP 2\n", b"HELP ALL\n", b"HELP RADIO\n",
        b"MENU\n", b"CMDS\n", b"STATUS\n", b"INFO\n", b"UID\n",
        b"UNIT\n", b"CAP\n", b"WAKEUP\n", b"WAKE\n",
    )
    for probe in probes:
        try:
            r = await loop.run_in_executor(None, capture_multiline, drv, probe)
            cap.add("probe", probe.decode("ascii").strip(), **r)
        except Exception as e:
            cap.add("probe", probe.decode("ascii").strip(), error=str(e))

    await drv.disconnect()

    print(json.dumps(
        {"results": cap.results, "eeprom_hex": cap.eeprom},
        indent=2,
    ))


if __name__ == "__main__":
    asyncio.run(main())
