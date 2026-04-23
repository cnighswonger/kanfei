"""Database engine and session factory for SQLAlchemy."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from ..config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # SQLite needs this for multi-thread
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Session:
    """Dependency for FastAPI endpoints."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database() -> None:
    """Create all tables.

    Models must be imported before create_all() so they register with Base.metadata.
    """
    from . import sensor_reading  # noqa: F401
    from . import station_config  # noqa: F401
    from . import archive_record  # noqa: F401
    from . import nowcast  # noqa: F401
    from . import spray  # noqa: F401
    from . import auth  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Enable WAL mode so the logger and web app can access the DB concurrently.
    # busy_timeout tells SQLite to wait up to 5s for a lock instead of failing
    # immediately — prevents "database is locked" errors during concurrent writes.
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA busy_timeout=5000"))
        conn.commit()

    # Migrate: add rain_yearly column if missing
    with engine.connect() as conn:
        try:
            conn.execute(text("SELECT rain_yearly FROM sensor_readings LIMIT 1"))
        except Exception:
            conn.execute(text(
                "ALTER TABLE sensor_readings ADD COLUMN rain_yearly INTEGER"
            ))
            conn.commit()

    # Migrate: add extra_json column if missing
    with engine.connect() as conn:
        try:
            conn.execute(text("SELECT extra_json FROM sensor_readings LIMIT 1"))
        except Exception:
            conn.execute(text(
                "ALTER TABLE sensor_readings ADD COLUMN extra_json TEXT"
            ))
            conn.commit()

    # Migrate: add wind_gust column if missing
    with engine.connect() as conn:
        try:
            conn.execute(text("SELECT wind_gust FROM sensor_readings LIMIT 1"))
        except Exception:
            conn.execute(text(
                "ALTER TABLE sensor_readings ADD COLUMN wind_gust INTEGER"
            ))
            conn.commit()
