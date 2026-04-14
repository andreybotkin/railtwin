"""Application configuration settings.

This module defines all configuration settings for the Thailand Railway Digital Twin
backend application using Pydantic Settings for environment variable management.
"""

import json
from functools import lru_cache
from typing import Annotated, Any

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Attributes:
        app_name: Name of the application.
        app_version: Version of the application.
        debug: Debug mode flag.
        environment: Deployment environment (development, staging, production).
        api_v1_prefix: API version 1 prefix path.
        secret_key: Secret key for JWT token generation.
        access_token_expire_minutes: JWT token expiration time in minutes.
        cors_origins: List of allowed CORS origins.
        database_url: PostgreSQL database connection URL.
        redis_url: Redis connection URL for caching.
        log_level: Logging level.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application settings
    app_name: str = "Thailand Railway Digital Twin"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    # API settings
    api_v1_prefix: str = "/api/v1"

    # Security settings
    secret_key: str = "your-secret-key-change-in-production"
    access_token_expire_minutes: int = 60 * 24  # 24 hours
    algorithm: str = "HS256"

    # CORS settings
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            value = v.strip()

            if not value:
                return []

            if value.startswith("["):
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [
                        str(origin).strip() for origin in parsed if str(origin).strip()
                    ]

            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return list(v)

    # Database settings
    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/railway_db"
    )

    # Redis settings
    redis_url: str = "redis://localhost:6379/0"

    # Logging settings
    log_level: str = "WARNING"

    # Rate limiting
    rate_limit_per_minute: int = 100

    # WebSocket settings
    ws_heartbeat_interval: int = 5  # seconds
    position_cache_interval_seconds: int | None = None
    trajectory_refresh_interval_seconds: int = 10

    # Trajectory generation settings (geops mobility-toolbox-js pattern)
    trajectory_lookahead_seconds: int = 600  # seconds of future movement in time_intervals
    trajectory_step_seconds: int = 10        # time_interval point spacing

    # geops compatibility
    position_tenant: str = "thailand_railway"

    def get_position_cache_interval_seconds(self) -> int:
        """Return the effective cache refresh interval for position snapshots."""
        interval = self.position_cache_interval_seconds or self.ws_heartbeat_interval
        return max(1, interval)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Settings: Application settings singleton.
    """
    return Settings()


settings = get_settings()
