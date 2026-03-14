"""Forecast ORM model for cached forecast data."""

from datetime import datetime, timezone

from sqlalchemy import Integer, Text, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ForecastModel(Base):
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    period_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    forecast_text: Mapped[str] = mapped_column(Text, nullable=False)
    temperature: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precipitation_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_forecast_source", "source", "timestamp"),
    )
