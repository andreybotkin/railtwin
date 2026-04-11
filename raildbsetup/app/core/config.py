from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory: raildbsetup/ (two levels up from app/core/)
_DEFAULT_BASE = Path(__file__).resolve().parents[2]

_ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RailDbSetup"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    api_v1_prefix: str = "/api/v1"
    setup_port: int = 8003

    # Shared database (same as backend)
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@postgres:5432/railway_db"
    )

    # Local data paths — overridable via env vars in Docker
    kml_local_path: Path = (
        _DEFAULT_BASE / "railroad" / "20260410RailwayMapofThailand.kml"
    )
    schedule_raw_dir: Path = _DEFAULT_BASE / "schedule" / "raw"
    schedule_seed_path: Path = _DEFAULT_BASE / "schedule" / "schedules_seed.json"

    # Remote KML fallback (only used if local file is absent)
    kml_remote_url: str = (
        "https://www.google.com/maps/d/kml"
        "?mid=1E6wO3YeI2OZwvSaRGc-pPbUEYchbFdY&forcekml=1"
    )

    # Validation thresholds
    min_routes_expected: int = 1
    min_stations_expected: int = 10
    min_trains_expected: int = 1


settings = Settings()
