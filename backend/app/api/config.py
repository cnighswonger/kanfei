"""GET/PUT /api/config - Configuration management."""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..models.database import get_db
from ..models.station_config import StationConfigModel
from .dependencies import require_admin

router = APIRouter()

# Keys whose values must be masked in GET /config responses.
_SECRET_KEYS = frozenset({
    "nowcast_api_key",
    "nowcast_wu_api_key",
    "nowcast_fallback_grok_api_key",
    "nowcast_fallback_openai_api_key",
    "anthropic_admin_api_key",
    "bot_telegram_token",
    "bot_discord_token",
    "wu_station_key",
})


def _mask_value(value: str) -> str:
    if not value or len(value) < 8:
        return "***" if value else ""
    return value[:4] + "*" * min(len(value) - 4, 20)

# Default config items derived from application settings.
# These are shown when the DB has no saved value for a key.
_DEFAULTS: dict[str, object] = {
    "serial_port": settings.serial_port,
    "baud_rate": settings.baud_rate,
    "serial_timeout": settings.serial_timeout,
    "poll_interval": settings.poll_interval_sec,
    "latitude": settings.latitude,
    "longitude": settings.longitude,
    "elevation": settings.elevation_ft,
    "temp_unit": settings.units_temp,
    "pressure_unit": settings.units_pressure,
    "wind_unit": settings.units_wind,
    "rain_unit": settings.units_rain,
    "metar_enabled": settings.metar_enabled,
    "metar_station": settings.metar_station_id,
    "nws_enabled": settings.nws_enabled,
    "setup_complete": False,
    "alert_thresholds": "[]",
    "wu_enabled": False,
    "wu_station_id": "",
    "wu_station_key": "",
    "wu_upload_interval": 60,
    "cwop_enabled": False,
    "cwop_callsign": "",
    "cwop_upload_interval": 300,
    "station_timezone": "",
    "nowcast_enabled": False,
    "nowcast_disclaimer_accepted": False,
    "nowcast_mode": "local",  # "local" = in-process engine, "remote" = HTTP endpoint
    "nowcast_remote_url": "",  # e.g. "http://192.168.1.100:8100"
    "nowcast_api_key": "",
    "nowcast_model": "claude-haiku-4-5-20251001",
    "nowcast_interval": 900,
    "nowcast_horizon": 2,
    "nowcast_max_tokens": 3500,
    "nowcast_radius": 25,
    "nowcast_knowledge_auto_accept_hours": 48,
    "nowcast_radar_enabled": True,
    "nowcast_nearby_iem_enabled": True,
    "nowcast_nearby_wu_enabled": False,
    "nowcast_wu_api_key": "",
    "nowcast_nearby_max_iem": 5,
    "nowcast_nearby_max_wu": 5,
    "nowcast_nearby_aprs_enabled": False,
    "nowcast_nearby_max_aprs": 10,
    "nowcast_nexrad_detection_enabled": True,
    "nowcast_nexrad_detection_mode": "alert",  # "alert" = during NWS alerts only, "always" = every cycle
    "nowcast_fallback_grok_api_key": "",
    "nowcast_fallback_grok_model": "grok-4-1-fast-reasoning",
    "nowcast_fallback_openai_api_key": "",
    "nowcast_fallback_openai_model": "gpt-4o-mini",
    "spray_enabled": False,
    "map_enabled": False,
    "spray_ai_enabled": False,
    "anthropic_admin_api_key": "",
    "usage_budget_monthly_usd": 0,
    "usage_budget_auto_pause": False,
    "usage_budget_paused": False,
    "station_driver_type": "legacy",
    "station_connection_type": "serial",  # "serial", "network", "udp", "http_push"
    "weatherlink_ip": "",
    "weatherlink_port": 22222,
    "ecowitt_ip": "",
    "tempest_hub_sn": "",
    "ambient_listen_port": 8080,
    # Rain midnight auto-reset
    "rain_yesterday": 0.0,
    # UI preferences (persisted server-side so they survive browser resets)
    "ui_sidebar_collapsed": False,
    "ui_theme": "dark",
    "ui_timezone": "auto",
    "ui_weather_bg_enabled": True,
    "ui_weather_bg_intensity": 30,
    "ui_weather_bg_transparency": 15,
    "ui_dashboard_layout": "",
    # Telegram bot
    "bot_telegram_enabled": False,
    "bot_telegram_token": "",
    "bot_telegram_chat_id": "",       # comma-separated for multiple chats
    "bot_telegram_commands": "current,status,help",
    "bot_telegram_notifications": "nowcast,alerts",
    "bot_telegram_last_error": "",
    "bot_telegram_conditions_enabled": False,
    "bot_telegram_conditions_interval": 30,   # minutes
    # Discord bot
    "bot_discord_enabled": False,
    "bot_discord_token": "",
    "bot_discord_guild_id": "",       # target server ID
    "bot_discord_channel_id": "",     # notification channel(s), comma-separated
    "bot_discord_commands": "current,status,help",
    "bot_discord_notifications": "nowcast,alerts",
    "bot_discord_last_error": "",
    "bot_discord_conditions_enabled": False,
    "bot_discord_conditions_interval": 30,    # minutes
    # Backup
    "backup_enabled": False,
    "backup_interval_hours": 24,
    "backup_retention_count": 7,
    "backup_directory": "",
    "backup_schedule_time": "",  # HH:MM for time-of-day scheduling; empty = interval from boot
    "backup_last_success": "",
    "backup_last_error": "",
}


_JS_MAX_SAFE_INTEGER = 2**53 - 1


def _coerce_value(raw: str) -> object:
    """Try to coerce a stored string back to bool/int/float.

    Integers exceeding JavaScript's MAX_SAFE_INTEGER (2^53 - 1) are
    returned as strings to avoid precision loss in JSON serialization.
    Discord/Telegram IDs are 64-bit snowflakes that exceed this limit.
    """
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        val = int(raw)
        if abs(val) > _JS_MAX_SAFE_INTEGER:
            return raw
        return val
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


class ConfigUpdate(BaseModel):
    key: str
    value: str | int | float | bool


def get_effective_config(db: Session) -> dict[str, object]:
    """Return merged config dict: DB overrides take priority over defaults."""
    saved = {item.key: _coerce_value(item.value) for item in db.query(StationConfigModel).all()}
    return {key: saved.get(key, default) for key, default in _DEFAULTS.items()}


# Public feature flags — no auth required.
_PUBLIC_FLAG_KEYS = frozenset({"nowcast_enabled", "spray_enabled", "map_enabled"})


@router.get("/config/flags")
def get_feature_flags(db: Session = Depends(get_db)):
    """Return public feature flags (no authentication required)."""
    saved = {item.key: _coerce_value(item.value) for item in db.query(StationConfigModel).all()}
    return {key: saved.get(key, _DEFAULTS.get(key, False)) for key in _PUBLIC_FLAG_KEYS}


@router.get("/config")
def get_config(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Return all configuration key-value pairs, with defaults for unsaved keys."""
    saved = {item.key: item.value for item in db.query(StationConfigModel).all()}

    result = []
    for key, default in _DEFAULTS.items():
        if key in saved:
            value = _coerce_value(saved[key])
        else:
            value = default
        # Mask secret values so they are never sent to the frontend in full.
        if key in _SECRET_KEYS and isinstance(value, str):
            value = _mask_value(value)
        result.append({"key": key, "value": value})
    return result


@router.put("/config")
def update_config(updates: list[ConfigUpdate], db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Update one or more configuration values."""
    # Pre-read current secret values so we can detect masked round-trips.
    current_secrets = {}
    for key in _SECRET_KEYS:
        row = db.query(StationConfigModel).filter_by(key=key).first()
        if row:
            current_secrets[key] = row.value

    for update in updates:
        # Skip masked secret values — the frontend sends back the masked
        # version from GET /config; writing it would destroy the real secret.
        if update.key in _SECRET_KEYS:
            val_str = str(update.value)
            # Reject if value contains mask characters or matches the mask
            # of the current DB value.
            if "****" in val_str:
                logger.debug("Skipping masked secret %s (contains ****)", update.key)
                continue
            current = current_secrets.get(update.key, "")
            if current and val_str == _mask_value(current):
                logger.debug("Skipping masked secret %s (matches mask of DB value)", update.key)
                continue
            logger.debug("Accepting secret update for %s (len=%d)", update.key, len(val_str))

        # Python's str(True) produces "True" — normalize bools to lowercase
        # so downstream checks like `value == "true"` work consistently.
        val = str(update.value).lower() if isinstance(update.value, bool) else str(update.value)
        existing = db.query(StationConfigModel).filter_by(key=update.key).first()
        if existing:
            existing.value = val
            existing.updated_at = datetime.now(timezone.utc)
        else:
            new_item = StationConfigModel(
                key=update.key,
                value=val,
                updated_at=datetime.now(timezone.utc),
            )
            db.add(new_item)
    db.commit()
    items = db.query(StationConfigModel).all()
    return [{"key": item.key, "value": _coerce_value(item.value)} for item in items]
