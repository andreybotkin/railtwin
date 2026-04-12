from app.domain.railroad.entities import RouteData, StationData
from app.domain.railroad.repository import RailroadRepository


class RailroadDomainService:
    """Domain service for railroad network management."""

    def __init__(self, repository: RailroadRepository) -> None:
        self._repo = repository

    async def is_initialized(self) -> bool:
        """Return True if the database already contains both routes and stations."""
        return await self._repo.count_routes() > 0 and await self._repo.count_stations() > 0

    async def replace_routes(self, routes: list[RouteData]) -> int:
        """Replace the canonical route geometry dataset."""
        return await self._repo.replace_routes(routes)

    async def replace_stations(self, stations: list[StationData]) -> int:
        """Replace the canonical station dataset."""
        return await self._repo.replace_stations(stations)
