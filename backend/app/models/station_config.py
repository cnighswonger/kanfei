"""StationConfig ORM model for key-value configuration storage."""

from datetime import datetime, timezone

from sqlalchemy import Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class StationConfigModel(Base):
    __tablename__ = "station_config"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
