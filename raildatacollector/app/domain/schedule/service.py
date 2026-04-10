from app.domain.schedule.entities import TrainData
from app.domain.schedule.repository import ScheduleRepository


class ScheduleDomainService:
    """Domain service for train schedule management."""

    def __init__(self, repository: ScheduleRepository) -> None:
        self._repo = repository

    async def is_initialized(self) -> bool:
        return await self._repo.count_trains() > 0

    async def needs_seeding(self, seed_count: int) -> bool:
        """Return True if DB has fewer trains than the seed provides.

        Used to distinguish between an empty database (first run) and a
        populated one (subsequent restarts).  Re-seeding is triggered only
        when db_count < seed_count.
        """
        db_count = await self._repo.count_trains()
        return db_count < seed_count

    async def upsert_single_train(self, train: TrainData) -> int:
        """Upsert one train and its full schedule. Returns 1 on success."""
        train_id = await self._repo.upsert_train(train)
        await self._repo.replace_schedules(train_id, train)
        return 1

    async def upsert_trains(self, trains: list[TrainData]) -> int:
        """Upsert all trains and their schedules. Returns count of trains processed."""
        count = 0
        for train in trains:
            count += await self.upsert_single_train(train)
        return count

    async def assign_routes(self) -> int:
        """Assign routes to trains without one, based on station overlap."""
        return await self._repo.assign_routes_by_station_match()
