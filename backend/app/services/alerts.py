"""Alert threshold checker for weather conditions.

Compares each sensor reading against user-configured thresholds and
tracks triggered/cleared state with cooldown to avoid alert spam.
"""

import logging
import operator as op
from typing import Optional

logger = logging.getLogger(__name__)

# Map threshold sensor names to paths in the _reading_to_dict() output
SENSOR_PATHS: dict[str, tuple[str, ...]] = {
    "outside_temp": ("temperature", "outside", "value"),
    "inside_temp": ("temperature", "inside", "value"),
    "wind_speed": ("wind", "speed", "value"),
    "barometer": ("barometer", "value"),
    "outside_humidity": ("humidity", "outside", "value"),
    "rain_rate": ("rain", "rate", "value"),
}

OPERATORS = {
    ">=": op.ge,
    "<=": op.le,
    ">": op.gt,
    "<": op.lt,
}


def _extract(data: dict, path: tuple[str, ...]) -> Optional[float]:
    """Walk a nested dict by key path, returning None if any key is missing."""
    obj = data
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
        if obj is None:
            return None
    return obj if isinstance(obj, (int, float)) else None


class AlertChecker:
    """Checks sensor readings against configurable thresholds."""

    def __init__(self):
        self._thresholds: list[dict] = []
        self._triggered: set[str] = set()  # IDs currently in alert state

    def load_thresholds(self, thresholds: list[dict]) -> None:
        """Load threshold definitions. Called at startup and after config changes."""
        self._thresholds = [t for t in thresholds if t.get("enabled", True)]
        # Remove triggered state for thresholds that no longer exist
        active_ids = {t["id"] for t in self._thresholds}
        self._triggered = self._triggered & active_ids
        logger.info("Loaded %d alert thresholds (%d enabled)", len(thresholds), len(self._thresholds))

    @property
    def active_alerts(self) -> list[str]:
        """Return IDs of currently triggered alerts."""
        return list(self._triggered)

    def check(self, reading_dict: dict) -> tuple[list[dict], list[dict]]:
        """Check reading against all thresholds.

        Args:
            reading_dict: The display-unit dict from _reading_to_dict().

        Returns:
            (triggered, cleared) — lists of alert event dicts.
        """
        triggered = []
        cleared = []

        for t in self._thresholds:
            tid = t["id"]
            sensor = t.get("sensor", "")
            path = SENSOR_PATHS.get(sensor)
            if path is None:
                continue

            current_value = _extract(reading_dict, path)
            if current_value is None:
                continue

            comparator = OPERATORS.get(t.get("operator", ""))
            if comparator is None:
                continue

            threshold_value = t.get("value")
            if threshold_value is None:
                continue

            exceeds = comparator(current_value, threshold_value)

            alert_event = {
                "id": tid,
                "label": t.get("label", tid),
                "sensor": sensor,
                "value": current_value,
                "threshold": threshold_value,
                "operator": t.get("operator"),
            }

            if exceeds:
                # Always broadcast so the frontend shows active alerts
                # regardless of when it connected.
                triggered.append(alert_event)

                if tid not in self._triggered:
                    # Newly triggered — log at WARNING
                    self._triggered.add(tid)
                    logger.warning(
                        "Alert TRIGGERED: %s — %s %s %s (current: %s)",
                        t.get("label", tid), sensor, t.get("operator"), threshold_value, current_value,
                    )
            else:
                if tid in self._triggered:
                    # Condition returned to normal
                    self._triggered.discard(tid)
                    cleared.append({
                        "id": tid,
                        "label": t.get("label", tid),
                    })
                    logger.info("Alert CLEARED: %s", t.get("label", tid))

        return triggered, cleared
