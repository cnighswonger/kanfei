"""ORM models for spray advisor — products, schedules, and outcomes."""

from datetime import datetime, timezone

from sqlalchemy import Integer, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class SprayProduct(Base):
    """Spray product definition with application constraints."""

    __tablename__ = "spray_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    # Categories: herbicide_contact, herbicide_systemic, fungicide_protectant,
    # fungicide_systemic, insecticide_contact, pgr, custom
    is_preset: Mapped[int] = mapped_column(Integer, default=0)  # bool-as-int for SQLite
    rain_free_hours: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    max_wind_mph: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    min_temp_f: Mapped[float] = mapped_column(Float, nullable=False, default=45.0)
    max_temp_f: Mapped[float] = mapped_column(Float, nullable=False, default=85.0)
    min_humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class SpraySchedule(Base):
    """Planned spray application linked to a product."""

    __tablename__ = "spray_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("spray_products.id"), nullable=False, index=True
    )
    planned_date: Mapped[str] = mapped_column(Text, nullable=False)  # "2026-03-15"
    planned_start: Mapped[str] = mapped_column(Text, nullable=False)  # "08:00"
    planned_end: Mapped[str] = mapped_column(Text, nullable=False)  # "12:00"
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending"
    )  # pending, go, no_go, completed, cancelled
    evaluation: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    ai_commentary: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON (Phase 2)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class SprayOutcome(Base):
    """Farmer-reported outcome for a completed spray application."""

    __tablename__ = "spray_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("spray_schedules.id"), nullable=False, index=True
    )
    logged_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    # Rating: 1=ineffective, 2=poor, 3=fair, 4=good, 5=excellent
    effectiveness: Mapped[int] = mapped_column(Integer, nullable=False)
    # Structured observations
    actual_rain_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_wind_mph: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_temp_f: Mapped[float | None] = mapped_column(Float, nullable=True)
    drift_observed: Mapped[int] = mapped_column(Integer, default=0)  # bool-as-int
    product_efficacy: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "effective", "partial", "ineffective"
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
