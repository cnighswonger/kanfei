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
from ..services.public_mode import invalidate_cache as invalidate_public_mode_cache
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
    # Shared secret between the private-station relay and the public
    # droplet's ingest endpoints (issue #336 Phase 2).  Masked so a
    # curious viewer of GET /api/config cannot lift it and impersonate
    # the local relay.
    "public_mode_ingest_secret",
    # Same secret as ``public_mode_ingest_secret`` but stored on the
    # PRIVATE station side (issue #336 Phase 3).  The private-station
    # relay sends this as the bearer credential when POSTing to the
    # droplet's ingest endpoints.  Masked for the same reason.
    "public_relay_secret",
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
    "solar_energy_unit": settings.units_solar_energy,
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
    # Per-channel mute toggles.  When true, the channel is suppressed from
    # every outbound upload (CWOP/APRS, Weather Underground, future
    # destinations).  See backend/app/services/channel_mute.py.
    "channel_mute_outdoor_temperature": False,
    "channel_mute_outdoor_humidity": False,
    "channel_mute_wind_speed": False,
    "channel_mute_wind_direction": False,
    "channel_mute_wind_gust": False,
    "channel_mute_barometer": False,
    "channel_mute_rain_daily": False,
    "channel_mute_rain_hour": False,
    "channel_mute_rain_24h": False,
    "channel_mute_solar_radiation": False,
    "channel_mute_uv_index": False,
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
    "map_isobar_interval": 1,
    "map_default_layer": "Roads",
    "map_max_radius": 450,
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
    "ui_persona": "everyday",
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
    # Public-relay ingest secret (issue #336 Phase 2).  Shared between the
    # private-station relay and the public droplet; the droplet's ingest
    # endpoints reject any push whose bearer token does not match this.
    # Masked in GET /api/config via _SECRET_KEYS above.
    "public_mode_ingest_secret": "",
    # Private-side relay (issue #336 Phase 3).  These live on the
    # private station's Kanfei; the relay task in kanfei-logger reads
    # them each poll cycle so a config change takes effect without a
    # restart (same pattern as WU/CWOP).  ``public_relay_last_error``
    # is written by the sender and read-only from the UI's point of
    # view — the field surfaces a stale error so operators know the
    # push has been failing, and clears itself on the next success.
    "public_relay_enabled": False,
    "public_relay_target_url": "",       # e.g. https://droplet.example.com
    "public_relay_secret": "",           # bearer; must match droplet's
    "public_relay_last_error": "",
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
_PUBLIC_FLAG_KEYS = frozenset({
    "nowcast_enabled", "spray_enabled", "map_enabled",
    # Public-droplet read-only mode indicator (issue #336 Phase 4).
    # Computed from ``station_driver_type`` rather than a stored flag,
    # so a driver flip takes effect without a second config row to keep
    # in sync — see the ``public_mode_active`` branch in
    # ``get_feature_flags`` below.
    "public_mode_active",
})


@router.get("/config/flags")
def get_feature_flags(db: Session = Depends(get_db)):
    """Return public feature flags (no authentication required)."""
    from ..services.public_mode import is_public_mode

    saved = {item.key: _coerce_value(item.value) for item in db.query(StationConfigModel).all()}
    result = {
        key: saved.get(key, _DEFAULTS.get(key, False))
        for key in _PUBLIC_FLAG_KEYS
    }
    # ``public_mode_active`` is COMPUTED, not stored — a droplet is
    # identified by its driver type, and having two rows to keep in
    # sync would let them drift.
    result["public_mode_active"] = is_public_mode()
    return result


# Keys omitted from ``GET /api/config`` when the caller is a guest on a
# public droplet.  These fields either
#
#   - identify third-party accounts the operator has connected (Discord
#     guild / channel IDs, Telegram chat IDs, WU station ID, CWOP
#     callsign, METAR station), or
#
#   - are ops metadata the read-only Settings UI doesn't render
#     (``*_last_error``, ``backup_last_success``,
#     ``nowcast_disclaimer_accepted``, backup ops fields).
#
# A real admin (same endpoint, authenticated) sees everything as
# before.  Red-team finding #1, 2026-08-15.
_PUBLIC_MODE_HIDDEN_KEYS = frozenset({
    # Third-party account identifiers.
    "wu_station_id",
    "cwop_callsign",
    "bot_telegram_chat_id",
    "bot_discord_guild_id",
    "bot_discord_channel_id",
    "metar_station",
    # Ops metadata / stale error surfaces.
    "backup_enabled",
    "backup_interval_hours",
    "backup_retention_count",
    "backup_schedule_time",
    "backup_directory",
    "backup_last_success",
    "backup_last_error",
    "bot_telegram_last_error",
    "bot_discord_last_error",
    "public_relay_last_error",
    "nowcast_disclaimer_accepted",
})


@router.get("/config")
def get_config(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Return all configuration key-value pairs, with defaults for unsaved keys.

    On a public droplet (``require_admin`` bypass in effect for the
    read-only Settings UI), ops-metadata and third-party-account keys
    are dropped from the response — the read-only Settings surface
    doesn't render them, and they're the kind of thing an
    unauthenticated observer has no business seeing.  Real admins
    keep the full view.  See ``_PUBLIC_MODE_HIDDEN_KEYS`` above.
    """
    from ..services.public_mode import is_public_mode

    saved = {item.key: item.value for item in db.query(StationConfigModel).all()}
    hide = _PUBLIC_MODE_HIDDEN_KEYS if is_public_mode() else frozenset()

    result = []
    for key, default in _DEFAULTS.items():
        if key in hide:
            continue
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

    # Track whether this update touches the public-mode indicator so the
    # 30 s cache can be dropped after commit.  Every path that mutates
    # ``station_driver_type`` must do this; without it the read-only
    # gate goes stale for up to 30 s after the flip (issue #336,
    # PR #337 Codex round 1).
    driver_type_touched = False

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

        if update.key == "station_driver_type":
            driver_type_touched = True

    db.commit()

    if driver_type_touched:
        # Drop the cached is_public_mode() value so the next request
        # sees the new state immediately.  Deferred until after commit
        # so a rolled-back write cannot re-poison the cache.
        invalidate_public_mode_cache()

    items = db.query(StationConfigModel).all()
    return [{"key": item.key, "value": _coerce_value(item.value)} for item in items]
