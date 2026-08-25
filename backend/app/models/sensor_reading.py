"""SensorReading ORM model for real-time data log."""

from datetime import datetime, timezone

from sqlalchemy import Integer, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class SensorReadingModel(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
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

    # Evapotranspiration — Day / Month / Year running totals in tenths of a
    # millimetre, same shape as ``rain_total`` (see SENSOR_BOUNDS in
    # sensor_meta.py). Populated on every Vantage poll from LOOP1 offsets
    # 56/58/60. NULL on stations that don't compute ET.
    #
    # Migrated to dedicated columns in beta30 (#329 kept them in
    # extra_json; #237-follow-on graduated them so /api/history can chart
    # them directly). Rows written before the migration retain the values
    # under ``extra_json.et_daily_mm`` etc. — the init-time migration
    # backfills those into the new columns.
    et_daily: Mapped[int | None] = mapped_column(Integer, nullable=True)
    et_monthly: Mapped[int | None] = mapped_column(Integer, nullable=True)
    et_yearly: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Vendor-specific extra data (JSON)
    extra_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Calculated values
    heat_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dew_point: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_chill: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feels_like: Mapped[int | None] = mapped_column(Integer, nullable=True)
    theta_e: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Station-computed, not derived by us: THSW needs solar radiation, so
    # only a station with a solar sensor reports it.  NULL everywhere else.
    thsw_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pressure_trend: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_sensor_timestamp", "timestamp"),
        # Composite indexes that let ``services.daily_extremes._at`` seek
        # by value + timestamp in one pass instead of scanning the whole
        # table for each of the 5 max/min extremes it looks up per period
        # window. Costs ~55 MB per year of data at a 10 s poll cadence
        # per index; measured on a 914 k-row demo, the drop from unindexed
        # scan (2 s per period_extremes call) to indexed seek is 6-7x on
        # weak CPUs. If a deployment needs to reclaim the storage, the
        # operator can prune ancient rows without touching the indexes.
        Index("idx_sensor_outside_temp_ts", "outside_temp", "timestamp"),
        Index("idx_sensor_wind_speed_ts", "wind_speed", "timestamp"),
        Index("idx_sensor_barometer_ts", "barometer", "timestamp"),
    )
