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

    # Migrate: cwop_mute_* → channel_mute_* (issue #162)
    # Mute keys were CWOP-specific in beta16; from beta17 they gate every
    # outbound upload, so the prefix is generalised.  Copy old → new for
    # any value the operator set, then drop the old rows.  Idempotent.
    # ``updated_at`` is NOT NULL with an ORM-level default; raw SQL needs
    # to provide CURRENT_TIMESTAMP explicitly or INSERT OR IGNORE will
    # silently skip the row.
    with engine.connect() as conn:
        try:
            rows = conn.execute(text(
                "SELECT key, value FROM station_config WHERE key LIKE 'cwop_mute_%'"
            )).fetchall()
            for old_key, value in rows:
                new_key = old_key.replace("cwop_mute_", "channel_mute_", 1)
                conn.execute(text(
                    "INSERT OR IGNORE INTO station_config "
                    "(key, value, updated_at) "
                    "VALUES (:k, :v, CURRENT_TIMESTAMP)"
                ), {"k": new_key, "v": value})
            if rows:
                conn.execute(text(
                    "DELETE FROM station_config WHERE key LIKE 'cwop_mute_%'"
                ))
            conn.commit()
        except Exception:
            pass
