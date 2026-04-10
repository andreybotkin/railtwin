from abc import ABC, abstractmethod

from app.domain.railroad.entities import RouteData, StationData


class RailroadRepository(ABC):
    """Abstract repository for railroad network persistence."""

    @abstractmethod
    async def count_stations(self) -> int:
        """Return the number of stations currently in the database."""
        ...

    @abstractmethod
    async def count_routes(self) -> int:
        """Return the number of routes currently in the database."""
        ...

    @abstractmethod
    async def replace_all(
        self,
        routes: list[RouteData],
        stations: list[StationData],
    ) -> tuple[int, int]:
        """Replace all railroad data atomically.

        Clears existing routes, stations, route_stations, and schedules
        then inserts fresh data. Returns (routes_inserted, stations_inserted).
        """
        ...
