"""Application configuration using Pydantic Settings."""

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings

# Resolve .env from the project root (one level above backend/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # Serial port
    serial_port: str = "/dev/ttyUSB0"
    baud_rate: int = 2400
    serial_timeout: float = 5.0

    # Polling
    poll_interval_sec: int = 10

    # Location (required for astronomy/forecast)
    latitude: float = 0.0
    longitude: float = 0.0
    elevation_ft: float = 0.0

    # Database
    db_path: str = "davis_wx.db"

    @model_validator(mode="after")
    def _resolve_db_path(self) -> "Settings":
        """Make db_path absolute, relative to the project root."""
        p = Path(self.db_path)
        if not p.is_absolute():
            self.db_path = str(_PROJECT_ROOT / p)
        return self

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    # Units
    units_temp: str = "F"  # F or C
    units_pressure: str = "inHg"  # inHg, hPa, or mb
    units_wind: str = "mph"  # mph, kph, or knots
    units_rain: str = "in"  # in or mm

    # METAR
    metar_enabled: bool = False
    metar_station_id: str = "XXXX"

    # NWS
    nws_enabled: bool = False

    # UI
    theme: str = "dark"

    # IPC (logger <-> web app)
    ipc_port: int = 6514

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {
        "env_prefix": "KANFEI_",
        "env_file": str(_ENV_FILE),
        "extra": "ignore",
    }


settings = Settings()
