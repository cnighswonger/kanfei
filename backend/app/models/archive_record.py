"""ArchiveRecord ORM model for downloaded archive data."""

from datetime import datetime, timezone

from sqlalchemy import Integer, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ArchiveRecordModel(Base):
    __tablename__ = "archive_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    archive_address: Mapped[int] = mapped_column(Integer, nullable=False)
    record_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    station_type: Mapped[int] = mapped_column(Integer, nullable=False)

    # Archive data fields
    barometer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inside_humidity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outside_humidity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rain_in_period: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inside_temp_avg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outside_temp_avg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_speed_avg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_direction: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outside_temp_hi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_gust: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outside_temp_lo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    archive_interval: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Extended fields (GroWeather/Energy/Health)
    solar_rad_avg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    solar_energy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_run: Mapped[int | None] = mapped_column(Integer, nullable=True)
    et: Mapped[int | None] = mapped_column(Integer, nullable=True)
    degree_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uv_avg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uv_dose: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rain_rate_hi: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("archive_address", "record_time", name="uq_archive_addr_time"),
        Index("idx_archive_time", "record_time"),
    )
