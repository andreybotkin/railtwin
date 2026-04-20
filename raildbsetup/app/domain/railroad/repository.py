from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
    async def replace_stations(
        self,
        stations: list[StationData],
        aliases: dict[str, str] | None = None,
    ) -> int:
        """Replace the canonical station locations loaded from the JSON file.

        ``aliases`` maps raw schedule names (as written by timetable sources)
        to the canonical station ``name_en`` and is persisted so the schedule
        resolver can hit them before falling back to fuzzy matching.
        """
        ...
