"""Use case: load the canonical railway network sources into the database.

Order:
    1. Load routes from the local KML file.
    2. Load stations from the local station JSON file.
    3. Validate both source datasets.
    4. Replace routes, then replace stations.
"""

from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.railroad.repository import RailroadRepository
from app.domain.railroad.service import RailroadDomainService
from app.infrastructure.parsers.json_station_parser import parse_stations_json
from app.infrastructure.parsers.kml_parser import parse_kml_routes

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
            return RailroadInitResult(skipped=True, success=True)

        kml_path = settings.kml_local_path
        if not kml_path.exists():
            return RailroadInitResult(error=f"KML file not found: {kml_path}")

        kml_bytes = kml_path.read_bytes()
        logger.info("Loading canonical route geometry from KML", path=str(kml_path))

        routes = parse_kml_routes(kml_bytes)
        logger.info("KML routes parsed", routes=len(routes))

        stations_path = settings.stations_json_path
        if not stations_path.exists():
            return RailroadInitResult(error=f"Stations JSON not found: {stations_path}")
        stations = parse_stations_json(stations_path)
        logger.info("Station JSON parsed", stations=len(stations))

        validation_errors: list[str] = []
        for route in routes:
            validation_errors.extend(route.validate())
        for station in stations:
            validation_errors.extend(station.validate())

        if validation_errors:
            msg = f"Canonical source data failed validation ({len(validation_errors)} errors)"
            logger.error(msg, first_errors=validation_errors[:5])
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
                error=f"Too few stations in JSON: {len(stations)} < "
                      f"{settings.min_stations_expected} expected"
            )
        if len(routes) < settings.min_routes_expected:
            return RailroadInitResult(
                error=f"Too few routes in KML: {len(routes)} < "
                      f"{settings.min_routes_expected} expected"
            )

        routes_count = await self._svc.replace_routes(routes)
        stations_count = await self._svc.replace_stations(stations)
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
