from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.schedule.entities import TrainData


class ScheduleRepository(ABC):
    """Abstract repository for train schedule persistence."""

    @abstractmethod
    async def upsert_train(self, train: TrainData) -> int:
        """Insert or update a train record. Returns the database train id."""
        ...

    @abstractmethod
    async def replace_schedules(self, train_id: int, train: TrainData) -> int:
        """Delete all schedule stops for the given train and insert fresh data.

        Returns the number of stops inserted.
        """
        ...

    @abstractmethod
    async def count_trains(self) -> int:
        """Return the total number of train records in the database."""
        ...

    @abstractmethod
    async def assign_routes_by_station_match(self, min_matches: int = 2) -> int:
        """Assign current_route_id to trains that lack one, using station overlap.

        Returns the number of trains updated.
        """
        ...

    @abstractmethod
    async def bind_route_stations_for_assigned_trains(self) -> int:
        """Bind schedules to route_stations and populate route_progress."""
        ...
