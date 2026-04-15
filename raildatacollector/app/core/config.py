from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory: raildatacollector/ (two levels up from app/core/)
_DEFAULT_BASE = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RailDataCollector"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    api_v1_prefix: str = "/api/v1"
    collector_port: int = 8001

    # Shared database (same as simulation)
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@postgres:5432/railway_db"
    )

    # Shared Redis (same as simulation)
    redis_url: str = "redis://redis:6379/0"

    # Local data paths — overridable via env vars in Docker
    kml_local_path: Path = (
        _DEFAULT_BASE / "railroad" / "20260410RailwayMapofThailand.kml"
    )
    schedule_data_dir: Path = _DEFAULT_BASE / "schedule"
    schedule_raw_dir: Path = _DEFAULT_BASE / "schedule" / "raw"

    # Remote KML source
    kml_remote_url: str = (
        "https://www.google.com/maps/d/kml"
        "?mid=1E6wO3YeI2OZwvSaRGc-pPbUEYchbFdY&forcekml=1"
    )

    # TTS real-time system
    tts_server_url: str = "https://ttsview.railway.co.th:5000"

    # Redis keys shared with simulation service
    tts_delays_redis_key: str = "tts:train_delays"
    tts_delays_redis_ttl: int = 7200  # 2 hours

    # Scheduler
    schedule_update_day_of_month: int = 1  # 1st of every month
    schedule_update_hour: int = 10  # 10:00 Asia/Bangkok
    schedule_update_minute: int = 0
    delays_update_interval_seconds: int = 1800  # 30 min

    @property
    def schedule_seed_path(self) -> Path:
        return self.schedule_data_dir / "schedules_seed.json"


settings = Settings()
