"""Use case: one-time initialization of the railroad network.

Strategy:
  1. If the database already contains stations and force=False → skip.
  2. Validate all routes and stations from the KML file.
  3. Load from the local KML file (download if missing).
  4. Persist the validated data.
"""

import urllib.request
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.railroad.repository import RailroadRepository
from app.domain.railroad.service import RailroadDomainService
from app.infrastructure.parsers.kml_parser import parse_kml_bytes

logger = get_logger(__name__)


@dataclass
class RailroadInitResult:
    skipped: bool = False
    success: bool = False
    routes_inserted: int = 0
    stations_inserted: int = 0
    validation_errors: list[str] | None = None
    error: str | None = None


class InitRailroadUseCase:
    def __init__(self, repository: RailroadRepository) -> None:
        self._svc = RailroadDomainService(repository)

    async def execute(self, force: bool = False) -> RailroadInitResult:
        if not force and await self._svc.is_initialized():
            logger.info("Railroad network already present, skipping initialization")
            return RailroadInitResult(skipped=True)

        kml_bytes = await self._load_kml()
        if kml_bytes is None:
            return RailroadInitResult(error="KML data unavailable")

        routes, stations = parse_kml_bytes(kml_bytes)
        logger.info("KML parsed", routes=len(routes), stations=len(stations))

        # Validate all parsed data before touching the database
        validation_errors: list[str] = []
        for route in routes:
            validation_errors.extend(route.validate())
        for station in stations:
            validation_errors.extend(station.validate())

        if validation_errors:
            msg = f"Parsed KML data failed validation ({len(validation_errors)} errors)"
            logger.error(msg, first_errors=validation_errors[:5])
            # Non-fatal: log errors but continue if we have enough data
            if len(stations) < settings.min_stations_expected:
                return RailroadInitResult(
                    validation_errors=validation_errors,
                    error=f"{msg}. Too few valid stations to proceed.",
                )
            logger.warning(
                "Proceeding despite validation errors",
                error_count=len(validation_errors),
            )

        if len(stations) < settings.min_stations_expected:
            return RailroadInitResult(
                error=f"Too few stations in KML: {len(stations)} < "
                      f"{settings.min_stations_expected} expected"
            )
        if len(routes) < settings.min_routes_expected:
            return RailroadInitResult(
                error=f"Too few routes in KML: {len(routes)} < "
                      f"{settings.min_routes_expected} expected"
            )

        routes_count, stations_count = await self._svc.replace_network(routes, stations)
        logger.info(
            "Railroad network initialized",
            routes=routes_count,
            stations=stations_count,
        )
        return RailroadInitResult(
            success=True,
            routes_inserted=routes_count,
            stations_inserted=stations_count,
            validation_errors=validation_errors if validation_errors else None,
        )

    async def _load_kml(self) -> bytes | None:
        local_path = settings.kml_local_path
        if local_path.exists():
            logger.info("Loading KML from local file", path=str(local_path))
            return local_path.read_bytes()

        logger.info("Local KML not found, downloading from remote")
        try:
            req = urllib.request.Request(
                settings.kml_remote_url,
                headers={"User-Agent": "Mozilla/5.0 (RailDbSetup/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                kml_bytes = resp.read()
            logger.info("KML downloaded", bytes=len(kml_bytes))
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(kml_bytes)
            return kml_bytes
        except Exception as exc:
            logger.error("Failed to download KML", error=str(exc))
            return None
