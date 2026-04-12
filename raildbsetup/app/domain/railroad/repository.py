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
    async def replace_routes(self, routes: list[RouteData]) -> int:
        """Replace the canonical route geometries loaded from the KML file."""
        ...

    @abstractmethod
    async def replace_stations(self, stations: list[StationData]) -> int:
        """Replace the canonical station locations loaded from the JSON file."""
        ...
