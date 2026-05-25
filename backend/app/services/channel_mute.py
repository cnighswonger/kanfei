"""Per-channel mute state shared across all outbound upload services.

A single source of truth for the operator's "this sensor is out of service"
toggle.  Originally introduced for CWOP/APRS in issue #161; promoted to a
shared module in #162 so Weather Underground (and any future upload
destination such as MQTT) consults the same mute set rather than each
service tracking its own.

State is persisted in ``station_config`` under the keys ``channel_mute_<channel_id>``
(one boolean per channel).  Each upload service reads the set in its
``reload_config()`` call and decides per service how to render a muted
channel — CWOP emits the APRS101 "missing value" sentinel; WU drops the
parameter from the upload entirely.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models.station_config import StationConfigModel


# Channels the operator can mute.  Each id corresponds to one logical
# sensor reading; upload services map these onto their own protocol
# fields (e.g. CWOP "outdoor_temperature" → APRS ``t...``; WU
# "outdoor_temperature" → drop ``tempf``).
MUTE_CHANNELS: tuple[str, ...] = (
    "outdoor_temperature",
    "outdoor_humidity",
    "wind_speed",
    "wind_direction",
    "wind_gust",
    "barometer",
    "rain_daily",
    "rain_hour",
    "rain_24h",
)


def mute_key(channel: str) -> str:
    """Return the station_config key that stores the mute bool for ``channel``."""
    return f"channel_mute_{channel}"


def load_muted_channels(db: Session) -> frozenset[str]:
    """Return the set of channel ids the operator has currently muted.

    Reuses the caller's session — no commit, no close.  Upload services
    call this inside their existing config-reload routine so the mute
    read shares the same DB round-trip as the rest of the service config.
    """
    keys = [mute_key(c) for c in MUTE_CHANNELS]
    rows = (
        db.query(StationConfigModel)
        .filter(StationConfigModel.key.in_(keys))
        .all()
    )
    on = {r.key for r in rows if str(r.value).lower() == "true"}
    return frozenset(c for c in MUTE_CHANNELS if mute_key(c) in on)
