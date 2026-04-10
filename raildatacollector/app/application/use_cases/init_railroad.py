"""Use case: one-time initialization of the railroad network.

Strategy:
  1. If the database already contains stations and force=False → skip.
  2. Try to load from the local KML file.
  3. If the local file is missing → download from Google My Maps and cache it.
"""

import urllib.request

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.railroad.repository import RailroadRepository
from app.domain.railroad.service import RailroadDomainService
from app.infrastructure.scrapers.kml_parser import parse_kml_bytes

logger = get_logger(__name__)


class InitRailroadUseCase:
    def __init__(self, repository: RailroadRepository) -> None:
        self._svc = RailroadDomainService(repository)

    async def execute(self, force: bool = False) -> dict:
        if not force and await self._svc.is_initialized():
            logger.info("Railroad network already present, skipping initialization")
            return {"skipped": True, "reason": "already_initialized"}

        kml_bytes = await self._load_kml()
        if kml_bytes is None:
            return {"success": False, "error": "KML data unavailable"}

        routes, stations = parse_kml_bytes(kml_bytes)
        logger.info("KML parsed", routes=len(routes), stations=len(stations))

        routes_count, stations_count = await self._svc.replace_network(routes, stations)
        logger.info(
            "Railroad network initialized",
            routes=routes_count,
            stations=stations_count,
        )
        return {
            "success": True,
            "routes_inserted": routes_count,
            "stations_inserted": stations_count,
        }

    async def _load_kml(self) -> bytes | None:
        local_path = settings.kml_local_path
        if local_path.exists():
            logger.info("Loading KML from local file", path=str(local_path))
            return local_path.read_bytes()

        logger.info("Local KML not found, downloading from remote")
        try:
            req = urllib.request.Request(
                settings.kml_remote_url,
                headers={"User-Agent": "Mozilla/5.0 (RailDataCollector/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                kml_bytes = resp.read()
            logger.info("KML downloaded", bytes=len(kml_bytes))
            # Cache locally for future restarts
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(kml_bytes)
            return kml_bytes
        except Exception as exc:
            logger.error("Failed to download KML", error=str(exc))
            return None
