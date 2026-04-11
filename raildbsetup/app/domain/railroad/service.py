from app.domain.railroad.entities import RouteData, StationData
from app.domain.railroad.repository import RailroadRepository


class RailroadDomainService:
    """Domain service for railroad network management."""

    def __init__(self, repository: RailroadRepository) -> None:
        self._repo = repository

    async def is_initialized(self) -> bool:
        """Return True if the database already contains station records."""
        return await self._repo.count_stations() > 0

    async def replace_network(
        self,
        routes: list[RouteData],
        stations: list[StationData],
    ) -> tuple[int, int]:
        """Replace the entire railroad network dataset.

        Returns (routes_inserted, stations_inserted).
        """
        return await self._repo.replace_all(routes, stations)
