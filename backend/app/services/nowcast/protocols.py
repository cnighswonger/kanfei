"""Protocol interfaces for decoupling the nowcast engine from host applications.

These protocols define the contracts that any host (Kanfei, standalone service,
test harness) must implement to provide data, config, storage, and event
delivery to the nowcast system.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class ConfigProvider(Protocol):
    """Provides configuration values to the nowcast engine."""

    def get(self, key: str, default: str = "") -> str: ...

    def get_int(self, key: str, default: int = 0) -> int: ...

    def get_float(self, key: str, default: float = 0.0) -> float: ...

    def get_bool(self, key: str, default: bool = False) -> bool: ...


@runtime_checkable
class StorageBackend(Protocol):
    """Persists nowcast results, knowledge, and ancillary data."""

    # --- Nowcast history ---
    def store_nowcast(self, record: dict) -> int:
        """Store a nowcast result. Returns the new record ID."""
        ...

    def get_latest_nowcast(self) -> Optional[dict]:
        """Return the most recent nowcast record, or None."""
        ...

    # --- Station data ---
    def get_latest_reading(self) -> Optional[dict]:
        """Return the most recent sensor reading, or None."""
        ...

    def get_readings_since(self, since: datetime) -> list[dict]:
        """Return sensor readings since the given time, ordered asc."""
        ...

    # --- Knowledge base ---
    def store_knowledge(self, entry: dict) -> None: ...

    def get_accepted_knowledge(self, limit: int = 20) -> list[str]:
        """Return accepted knowledge entries as formatted strings."""
        ...

    def get_pending_knowledge(self, auto_accept_cutoff: datetime) -> list[dict]: ...

    def accept_knowledge(self, entry_id: int, reviewed_at: datetime) -> None: ...

    # --- Radar images ---
    def store_radar_images(self, nowcast_id: int, images: list[dict]) -> None: ...

    # --- Alert snapshots ---
    def store_alert_snapshots(self, nowcast_id: int, alerts: list[dict]) -> None: ...

    # --- Nearby station snapshots ---
    def store_nearby_snapshot(self, nowcast_id: int, snapshot: dict) -> None: ...

    def get_nearby_snapshots(self, since: datetime) -> list[dict]: ...

    def cleanup_old_snapshots(self, older_than: datetime) -> int: ...

    # --- Spray schedules ---
    def get_spray_schedules(self) -> list[dict]:
        """Return pending spray schedules with product info."""
        ...

    def get_spray_outcomes(self, limit: int = 20) -> list[dict]:
        """Return recent spray outcomes with product info."""
        ...

    def update_spray_commentary(self, schedule_id: int, commentary: dict) -> None: ...

    # --- Verification ---
    def run_verification(self, auto_accept_hours: int) -> int:
        """Verify expired nowcasts. Returns count of verified records."""
        ...

    # --- Budget ---
    def check_budget(self) -> bool:
        """Check usage budget. Returns True if nowcast should be paused."""
        ...

    def begin(self) -> Any: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


@runtime_checkable
class EventEmitter(Protocol):
    """Pushes real-time updates to connected clients."""

    async def emit(self, event_type: str, data: dict) -> None: ...
