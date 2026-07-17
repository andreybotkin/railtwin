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

    # Shared database (same as simulation)
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@postgres:5432/railway_db"
    )

    # Local data paths — overridable via env vars in Docker
    kml_local_path: Path = (
        _DEFAULT_BASE / "railroad" / "20260428RailwayMapofThailand.kml"
    )
    stations_kml_path: Path = (
        _DEFAULT_BASE / "railroad" / "20260428Thai_railway_stations.kml"
    )
    schedule_raw_dir: Path = _DEFAULT_BASE / "schedule" / "raw"

    # Validation thresholds
    min_routes_expected: int = 1
    min_stations_expected: int = 10
    min_trains_expected: int = 1

    # Network topology settings
    # Maximum distance (metres) between a station point and a route LineString
    # for the station to be considered part of that route.
    # Stations farther away than this are not allowed to become members of a
    # route. A wide (2 km) corridor produced false matches across branches.
    topology_snap_distance_m: float = 500.0
    # Route rebuild tolerance: stations are considered part of a route when the
    # route LineString passes close enough to the station point.
    topology_route_match_distance_m: float = 25.0
    # Numerical epsilon used when ordering station projections on a route and
    # when extracting non-zero station-to-station edge segments.
    topology_fraction_epsilon: float = 1e-6


settings = Settings()
