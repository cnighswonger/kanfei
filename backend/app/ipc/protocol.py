"""IPC wire protocol: JSON-over-newline on TCP localhost.

Every message is a single JSON object followed by a newline character.
Requests include a "cmd" field; responses include "ok" and optionally
"data" or "error".
"""

import json
from typing import Any

# --- Command constants ---

CMD_STATUS = "status"
CMD_PROBE = "probe"
CMD_AUTO_DETECT = "auto_detect"
CMD_CONNECT = "connect"
CMD_RECONNECT = "reconnect"
CMD_SUBSCRIBE = "subscribe"
CMD_UNSUBSCRIBE = "unsubscribe"
CMD_READ_STATION_TIME = "read_station_time"
CMD_SYNC_STATION_TIME = "sync_station_time"
CMD_READ_CONFIG = "read_config"
CMD_WRITE_CONFIG = "write_config"
CMD_CLEAR_RAIN_DAILY = "clear_rain_daily"
CMD_CLEAR_RAIN_YEARLY = "clear_rain_yearly"
CMD_FORCE_ARCHIVE = "force_archive"

# --- Wire helpers ---

IPC_HOST = "127.0.0.1"


def encode_message(msg: dict[str, Any]) -> bytes:
    """Serialize a message dict to JSON bytes + newline."""
    return json.dumps(msg, separators=(",", ":"), default=str).encode() + b"\n"


def decode_message(line: bytes) -> dict[str, Any]:
    """Deserialize a JSON newline-delimited message."""
    return json.loads(line.decode().strip())
