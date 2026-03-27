"""Kanfei-specific adapter implementations for the nowcast protocol interfaces.

These adapters bridge the nowcast engine's protocol contracts to Kanfei's
SQLAlchemy ORM models, WebSocket manager, and config system.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class KanfeiConfigProvider:
    """Reads config from Kanfei's station_config SQLite table."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def get(self, key: str, default: str = "") -> str:
        from ...models.station_config import StationConfigModel
        db = self._session_factory()
        try:
            row = db.query(StationConfigModel).filter_by(key=key).first()
            return row.value if row else default
        finally:
            db.close()

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.get(key, str(default)))
        except (ValueError, TypeError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.get(key, str(default)))
        except (ValueError, TypeError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        return self.get(key, str(default).lower()).lower() == "true"

    def get_many(self, keys: list[str]) -> dict[str, str]:
        """Bulk read — fetch multiple keys in a single query."""
        from ...models.station_config import StationConfigModel
        db = self._session_factory()
        try:
            rows = db.query(StationConfigModel).filter(
                StationConfigModel.key.in_(keys)
            ).all()
            return {r.key: r.value for r in rows}
        finally:
            db.close()


class KanfeiStorageBackend:
    """Persists nowcast data using Kanfei's SQLAlchemy ORM models.

    Supports both standalone operations (each method opens/closes its own
    session) and grouped transactions via begin()/commit()/rollback().
    """

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Optional[Session] = None

    def begin(self) -> Session:
        """Open a session for a group of related operations."""
        self._session = self._session_factory()
        return self._session

    def commit(self) -> None:
        if self._session:
            self._session.commit()

    def rollback(self) -> None:
        if self._session:
            self._session.rollback()

    def close(self) -> None:
        if self._session:
            self._session.close()
            self._session = None

    def _db(self) -> Session:
        """Return current session or open a standalone one."""
        if self._session:
            return self._session
        return self._session_factory()

    def _close_if_standalone(self, db: Session) -> None:
        """Close session only if it wasn't opened by begin()."""
        if db is not self._session:
            db.close()

    # --- Nowcast history ---

    def store_nowcast(self, record: dict) -> int:
        from ...models.nowcast import NowcastHistory
        db = self._db()
        try:
            obj = NowcastHistory(
                created_at=record["created_at"],
                valid_from=record["valid_from"],
                valid_until=record["valid_until"],
                model_used=record["model_used"],
                summary=record["summary"],
                details=record["details"],
                confidence=record["confidence"],
                sources_used=record["sources_used"],
                raw_response=record["raw_response"],
                input_tokens=record.get("input_tokens"),
                output_tokens=record.get("output_tokens"),
            )
            db.add(obj)
            db.flush()
            return obj.id
        finally:
            self._close_if_standalone(db)

    def get_latest_nowcast(self) -> Optional[dict]:
        from ...models.nowcast import NowcastHistory
        from ...api.nowcast import _history_to_dict
        db = self._db()
        try:
            record = (
                db.query(NowcastHistory)
                .order_by(NowcastHistory.created_at.desc())
                .first()
            )
            if record is None:
                return None
            return _history_to_dict(record)
        finally:
            self._close_if_standalone(db)

    # --- Station data ---

    def get_latest_reading(self) -> Optional[dict]:
        from ...models.sensor_reading import SensorReadingModel
        db = self._db()
        try:
            r = (
                db.query(SensorReadingModel)
                .order_by(SensorReadingModel.timestamp.desc())
                .first()
            )
            if r is None:
                return None
            return {
                "timestamp": r.timestamp,
                "outside_temp": r.outside_temp,
                "inside_temp": r.inside_temp,
                "outside_humidity": r.outside_humidity,
                "inside_humidity": r.inside_humidity,
                "wind_speed": r.wind_speed,
                "wind_direction": r.wind_direction,
                "barometer": r.barometer,
                "rain_total": r.rain_total,
                "rain_rate": r.rain_rate,
                "solar_radiation": r.solar_radiation,
                "uv_index": r.uv_index,
                "dew_point": r.dew_point,
                "heat_index": r.heat_index,
                "wind_chill": r.wind_chill,
                "pressure_trend": r.pressure_trend,
            }
        finally:
            self._close_if_standalone(db)

    def get_readings_since(self, since: datetime) -> list[dict]:
        from ...models.sensor_reading import SensorReadingModel
        db = self._db()
        try:
            rows = (
                db.query(SensorReadingModel)
                .filter(SensorReadingModel.timestamp >= since)
                .order_by(SensorReadingModel.timestamp.asc())
                .all()
            )
            from ...models.sensor_meta import convert
            return [
                {
                    "timestamp": r.timestamp,
                    "outside_temp": convert("outside_temp", r.outside_temp),
                    "inside_temp": convert("inside_temp", r.inside_temp),
                    "outside_humidity": r.outside_humidity,
                    "inside_humidity": r.inside_humidity,
                    "wind_speed": convert("wind_speed", r.wind_speed),
                    "wind_direction": r.wind_direction,
                    "barometer": convert("barometer", r.barometer),
                    "rain_total": convert("rain_total", r.rain_total),
                    "rain_rate": convert("rain_rate", r.rain_rate),
                    "solar_radiation": r.solar_radiation,
                    "uv_index": convert("uv_index", r.uv_index),
                    "dew_point": convert("dew_point", r.dew_point),
                    "heat_index": convert("heat_index", r.heat_index),
                    "wind_chill": convert("wind_chill", r.wind_chill),
                    "pressure_trend": r.pressure_trend,
                }
                for r in rows
            ]
        finally:
            self._close_if_standalone(db)

    # --- Knowledge base ---

    def get_accepted_knowledge(self, limit: int = 20) -> list[str]:
        from ...models.nowcast import NowcastKnowledge
        db = self._session_factory()
        try:
            entries = (
                db.query(NowcastKnowledge)
                .filter(NowcastKnowledge.status == "accepted")
                .order_by(NowcastKnowledge.created_at.desc())
                .limit(limit)
                .all()
            )
            return [f"[{e.category}] {e.content}" for e in entries]
        finally:
            db.close()

    def store_knowledge(self, entry: dict) -> None:
        from ...models.nowcast import NowcastKnowledge
        db = self._db()
        try:
            obj = NowcastKnowledge(
                source=entry.get("source", "ai_proposed"),
                category=entry.get("category", "general"),
                content=entry.get("content", ""),
                status=entry.get("status", "pending"),
                auto_accept_at=entry.get("auto_accept_at"),
            )
            db.add(obj)
        finally:
            self._close_if_standalone(db)

    def get_pending_knowledge(self, auto_accept_cutoff: datetime) -> list[dict]:
        from ...models.nowcast import NowcastKnowledge
        db = self._session_factory()
        try:
            pending = (
                db.query(NowcastKnowledge)
                .filter(
                    NowcastKnowledge.status == "pending",
                    NowcastKnowledge.auto_accept_at.isnot(None),
                    NowcastKnowledge.auto_accept_at <= auto_accept_cutoff,
                )
                .all()
            )
            results = []
            for entry in pending:
                entry.status = "accepted"
                entry.reviewed_at = auto_accept_cutoff
                results.append({"id": entry.id, "category": entry.category, "content": entry.content})
                logger.info("Knowledge auto-accepted: [%s] %s", entry.category, entry.content[:80])
            if pending:
                db.commit()
            return results
        finally:
            db.close()

    def accept_knowledge(self, entry_id: int, reviewed_at: datetime) -> None:
        from ...models.nowcast import NowcastKnowledge
        db = self._session_factory()
        try:
            entry = db.query(NowcastKnowledge).filter_by(id=entry_id).first()
            if entry:
                entry.status = "accepted"
                entry.reviewed_at = reviewed_at
                db.commit()
        finally:
            db.close()

    # --- Radar images ---

    def store_radar_images(self, nowcast_id: int, images: list[dict]) -> None:
        from ...models.nowcast import NowcastRadarImage
        db = self._db()
        try:
            for img in images:
                db.add(NowcastRadarImage(
                    nowcast_id=nowcast_id,
                    image_type=img.get("image_type", "standard"),
                    product_id=img["product_id"],
                    label=img["label"],
                    png_base64=img["png_base64"],
                    width=img["width"],
                    height=img["height"],
                    bbox_json=img["bbox_json"],
                    fetched_at=img["fetched_at"],
                ))
        finally:
            self._close_if_standalone(db)

    # --- Alert snapshots ---

    def store_alert_snapshots(self, nowcast_id: int, alerts: list[dict]) -> None:
        from ...models.nowcast import NowcastAlertSnapshot
        db = self._db()
        try:
            for alert in alerts:
                db.add(NowcastAlertSnapshot(
                    nowcast_id=nowcast_id,
                    alert_id=alert["alert_id"],
                    event=alert["event"],
                    severity=alert["severity"],
                    certainty=alert["certainty"],
                    urgency=alert["urgency"],
                    headline=alert["headline"],
                    description=alert["description"],
                    instruction=alert.get("instruction", ""),
                    onset=alert["onset"],
                    expires=alert["expires"],
                    sender_name=alert.get("sender_name", ""),
                    message_type=alert.get("message_type", "Alert"),
                    response=alert.get("response", "None"),
                ))
        finally:
            self._close_if_standalone(db)

    # --- Nearby station snapshots ---

    def store_nearby_snapshot(self, nowcast_id: int, snapshot: dict) -> None:
        from ...models.nowcast import NowcastNearbySnapshot
        db = self._db()
        try:
            db.add(NowcastNearbySnapshot(
                nowcast_id=nowcast_id,
                observations_json=snapshot["observations_json"],
                station_count=snapshot["station_count"],
            ))
        finally:
            self._close_if_standalone(db)

    def get_nearby_snapshots(self, since: datetime) -> list[dict]:
        from ...models.nowcast import NowcastNearbySnapshot
        db = self._session_factory()
        try:
            snapshots = (
                db.query(NowcastNearbySnapshot)
                .filter(NowcastNearbySnapshot.created_at >= since)
                .order_by(NowcastNearbySnapshot.created_at.asc())
                .all()
            )
            return [
                {
                    "created_at": s.created_at,
                    "observations_json": s.observations_json,
                }
                for s in snapshots
            ]
        finally:
            db.close()

    def cleanup_old_snapshots(self, older_than: datetime) -> int:
        from ...models.nowcast import NowcastNearbySnapshot
        db = self._db()
        try:
            count = (
                db.query(NowcastNearbySnapshot)
                .filter(NowcastNearbySnapshot.created_at < older_than)
                .count()
            )
            if count > 0:
                db.query(NowcastNearbySnapshot).filter(
                    NowcastNearbySnapshot.created_at < older_than
                ).delete(synchronize_session=False)
                db.commit()
                logger.info("Cleaned up %d nearby snapshots", count)
            return count
        finally:
            self._close_if_standalone(db)

    # --- Spray schedules ---

    def get_spray_schedules(self) -> list[dict]:
        from ...models.spray import SpraySchedule, SprayProduct
        db = self._session_factory()
        try:
            schedules = (
                db.query(SpraySchedule)
                .filter(SpraySchedule.status.in_(["pending", "go", "no_go"]))
                .order_by(SpraySchedule.planned_date.asc())
                .limit(10)
                .all()
            )
            results = []
            for s in schedules:
                product = db.query(SprayProduct).filter_by(id=s.product_id).first()
                if product is None:
                    continue
                results.append({
                    "schedule_id": s.id,
                    "product_name": product.name,
                    "category": product.category,
                    "planned_date": s.planned_date,
                    "planned_start": s.planned_start,
                    "planned_end": s.planned_end,
                    "status": s.status,
                    "constraints": {
                        "rain_free_hours": product.rain_free_hours,
                        "max_wind_mph": product.max_wind_mph,
                        "min_temp_f": product.min_temp_f,
                        "max_temp_f": product.max_temp_f,
                        "min_humidity_pct": product.min_humidity_pct,
                        "max_humidity_pct": product.max_humidity_pct,
                    },
                    "notes": s.notes,
                })
            return results
        finally:
            db.close()

    def get_spray_outcomes(self, limit: int = 20) -> list[dict]:
        from ...models.spray import SprayOutcome, SpraySchedule, SprayProduct
        db = self._session_factory()
        try:
            rows = (
                db.query(SprayOutcome, SprayProduct.name, SprayProduct.category)
                .join(SpraySchedule, SprayOutcome.schedule_id == SpraySchedule.id)
                .join(SprayProduct, SpraySchedule.product_id == SprayProduct.id)
                .order_by(SprayOutcome.logged_at.desc())
                .limit(limit)
                .all()
            )
            results = []
            for o, product_name, category in rows:
                results.append({
                    "product_name": product_name,
                    "category": category,
                    "effectiveness": o.effectiveness,
                    "actual_wind_mph": o.actual_wind_mph,
                    "actual_temp_f": o.actual_temp_f,
                    "actual_rain_hours": o.actual_rain_hours,
                    "drift_observed": bool(o.drift_observed),
                    "product_efficacy": o.product_efficacy,
                    "notes": o.notes,
                    "logged_at": o.logged_at.isoformat() if o.logged_at else None,
                })
            return results
        finally:
            db.close()

    def update_spray_commentary(self, schedule_id: int, commentary: dict) -> None:
        from ...models.spray import SpraySchedule
        db = self._db()
        try:
            schedule = db.query(SpraySchedule).filter_by(id=schedule_id).first()
            if schedule:
                schedule.ai_commentary = json.dumps(commentary)
                logger.info("Spray AI commentary written for schedule #%d", schedule_id)
        finally:
            self._close_if_standalone(db)

    # --- Verification ---

    def run_verification(self, auto_accept_hours: int) -> int:
        from kanfei_nowcast.verifier import configure_models, verify_expired_nowcasts
        from ...models.nowcast import NowcastHistory, NowcastVerification, NowcastKnowledge
        from ...models.sensor_reading import SensorReadingModel
        configure_models(
            history=NowcastHistory,
            verification=NowcastVerification,
            knowledge=NowcastKnowledge,
            sensor_reading=SensorReadingModel,
        )
        db = self._session_factory()
        try:
            return verify_expired_nowcasts(db, auto_accept_hours)
        except Exception:
            logger.exception("Verification check failed")
            return 0
        finally:
            db.close()

    # --- Budget ---

    def check_budget(self) -> bool:
        """Check usage budget. Returns True if nowcast was auto-paused."""
        from ...api.usage import check_budget
        from ...models.station_config import StationConfigModel
        db = self._session_factory()
        try:
            if check_budget(db):
                row = db.query(StationConfigModel).filter_by(key="nowcast_enabled").first()
                if row and row.value.lower() != "true":
                    return True
            return False
        finally:
            db.close()


class KanfeiEventEmitter:
    """Broadcasts events to Kanfei's WebSocket clients and registered listeners."""

    def __init__(self, ws_manager: Any) -> None:
        self._ws_manager = ws_manager
        self._listeners: list[Callable] = []

    def add_listener(self, callback: Callable) -> None:
        """Register an async callback to receive all emitted events."""
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable) -> None:
        """Unregister a previously registered callback."""
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    async def emit(self, event_type: str, data: dict) -> None:
        message = {"type": event_type, "data": data}
        try:
            await self._ws_manager.broadcast(message)
        except Exception as exc:
            logger.debug("WS broadcast failed (%s): %s", event_type, exc)
        for listener in self._listeners:
            try:
                await listener(message)
            except Exception as exc:
                logger.debug("Event listener failed (%s): %s", event_type, exc)
