from app.domain.schedule.entities import TrainData
from app.domain.schedule.repository import ScheduleRepository


class ScheduleDomainService:
    """Domain service for train schedule management."""

    def __init__(self, repository: ScheduleRepository) -> None:
        self._repo = repository

    async def is_initialized(self) -> bool:
        return await self._repo.count_trains() > 0

    async def needs_seeding(self, seed_count: int) -> bool:
        """Return True if DB has fewer trains than the seed provides."""
        db_count = await self._repo.count_trains()
        return db_count < seed_count

    async def upsert_single_train(self, train: TrainData) -> int:
        """Upsert one train and its full schedule. Returns 1 on success."""
        train_id = await self._repo.upsert_train(train)
        await self._repo.replace_schedules(train_id, train)
        return 1

    async def assign_routes(self) -> int:
        """Assign routes to trains without one, based on station overlap."""
        return await self._repo.assign_routes_by_station_match()

    async def bind_route_stations(self) -> int:
        """Bind schedule rows to the route-specific stop sequence."""
        return await self._repo.bind_route_stations_for_assigned_trains()
