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
CMD_BAROMETER_CAL = "barometer_cal"          # read BARDATA
CMD_SET_BAROMETER = "set_barometer"          # write via BAR=
CMD_SIGNAL_QUALITY = "signal_quality"
CMD_RAIN_PREFLIGHT = "rain_preflight"        # console vs last stored
CMD_SET_YEARLY_RAIN = "set_yearly_rain"      # PUTRAIN — irreversible
CMD_ARCHIVE_PREFLIGHT = "archive_preflight"  # unsynced record count
CMD_CLEAR_ARCHIVE = "clear_archive"          # CLRLOG — irreversible
CMD_HIGHS_LOWS = "highs_lows"                # HILOWS, read-only
CMD_READ_VANTAGE_CAL = "read_vantage_cal"    # temp/humidity offsets
CMD_WRITE_VANTAGE_CAL = "write_vantage_cal"  # one field, via CALED/CALFIX
CMD_CLEAR_VANTAGE_CAL = "clear_vantage_cal"  # CLRCAL — zeroes all
CMD_READ_LOCATION = "read_location"          # console lat/lon from EEPROM
CMD_SET_LOCATION = "set_location"            # write + NEWSETUP
CMD_READ_RAIN_SEASON = "read_rain_season"    # yearly-rain-reset month
CMD_SET_RAIN_SEASON = "set_rain_season"      # RAIN_YEAR_START via EEBWR

# --- Wire helpers ---

IPC_HOST = "127.0.0.1"


def encode_message(msg: dict[str, Any]) -> bytes:
    """Serialize a message dict to JSON bytes + newline."""
    return json.dumps(msg, separators=(",", ":"), default=str).encode() + b"\n"


def decode_message(line: bytes) -> dict[str, Any]:
    """Deserialize a JSON newline-delimited message."""
    return json.loads(line.decode().strip())
