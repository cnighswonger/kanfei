"""SensorReading ORM model for real-time data log."""

from datetime import datetime, timezone

from sqlalchemy import Integer, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class SensorReadingModel(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    station_type: Mapped[int] = mapped_column(Integer, nullable=False)

    # Raw sensor data (native units)
    inside_temp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outside_temp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inside_humidity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outside_humidity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_speed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_gust: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_direction: Mapped[int | None] = mapped_column(Integer, nullable=True)
    barometer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rain_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rain_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rain_yearly: Mapped[int | None] = mapped_column(Integer, nullable=True)
    solar_radiation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uv_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Vendor-specific extra data (JSON)
    extra_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Calculated values
    heat_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dew_point: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_chill: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feels_like: Mapped[int | None] = mapped_column(Integer, nullable=True)
    theta_e: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pressure_trend: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_sensor_timestamp", "timestamp"),
    )
