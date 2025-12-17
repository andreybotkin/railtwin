"""Schedule service for business logic.

This module provides the service layer for schedule-related operations,
handling business logic between API endpoints and repository layer.
"""

from datetime import time
from math import ceil

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.database.models import Schedule
from app.repositories.schedule import ScheduleRepository
from app.schemas.schedule import (
    ScheduleCreate,
    ScheduleListResponse,
    ScheduleResponse,
    ScheduleUpdate,
    StationScheduleResponse,
    TrainScheduleResponse,
)
from app.schemas.station import StationSummary
from app.schemas.train import TrainSummary

logger = get_logger(__name__)


class ScheduleService:
    """Service class for schedule operations.

    Handles business logic for creating, reading, updating, and
    deleting train schedules.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize schedule service.

        Args:
            session: Async database session.
        """
        self.repository = ScheduleRepository(session)
        self.session = session

    def _schedule_to_response(self, schedule: Schedule) -> ScheduleResponse:
        """Convert schedule model to response schema.

        Args:
            schedule: Schedule database model.

        Returns:
            ScheduleResponse schema.
        """
        train = None
        if schedule.train:
            train = TrainSummary(
                id=schedule.train.id,
                train_number=schedule.train.train_number,
                train_type=schedule.train.train_type,
                name=schedule.train.name,
            )

        station = None
        if schedule.station:
            station = StationSummary(
                id=schedule.station.id,
                name=schedule.station.name,
                code=schedule.station.code,
            )

        return ScheduleResponse(
            id=schedule.id,
            train_id=schedule.train_id,
            station_id=schedule.station_id,
            arrival_time=schedule.arrival_time,
            departure_time=schedule.departure_time,
            day_of_week=schedule.day_of_week,
            platform=schedule.platform,
            sequence=schedule.sequence,
            train=train,
            station=station,
        )

    async def get_schedule(self, schedule_id: int) -> ScheduleResponse | None:
        """Get a single schedule by ID.

        Args:
            schedule_id: Schedule ID.

        Returns:
            ScheduleResponse or None if not found.
        """
        schedule = await self.repository.get_by_id(schedule_id)
        if not schedule:
            return None
        return self._schedule_to_response(schedule)

    async def list_schedules(
        self,
        page: int = 1,
        size: int = 50,
        train_id: int | None = None,
        station_id: int | None = None,
        day_of_week: int | None = None,
    ) -> ScheduleListResponse:
        """List schedules with pagination and filtering.

        Args:
            page: Page number (1-indexed).
            size: Number of items per page.
            train_id: Filter by train ID.
            station_id: Filter by station ID.
            day_of_week: Filter by day of week.

        Returns:
            ScheduleListResponse with paginated results.
        """
        skip = (page - 1) * size
        schedules = await self.repository.get_all_with_relations(
            skip=skip,
            limit=size,
            train_id=train_id,
            station_id=station_id,
            day_of_week=day_of_week,
        )
        total = await self.repository.count()

        return ScheduleListResponse(
            items=[self._schedule_to_response(s) for s in schedules],
            total=total,
            page=page,
            size=size,
            pages=ceil(total / size) if size > 0 else 0,
        )

    async def create_schedule(self, data: ScheduleCreate) -> ScheduleResponse:
        """Create a new schedule.

        Args:
            data: Schedule creation data.

        Returns:
            Created ScheduleResponse.
        """
        schedule_data = data.model_dump()
        schedule = await self.repository.create(schedule_data)
        await self.session.commit()

        # Reload with relations
        schedules = await self.repository.get_all_with_relations(
            train_id=schedule.train_id,
            station_id=schedule.station_id,
            limit=1,
        )
        if schedules:
            schedule = schedules[0]

        logger.info(
            "Schedule created",
            schedule_id=schedule.id,
            train_id=schedule.train_id,
        )
        return self._schedule_to_response(schedule)

    async def update_schedule(
        self,
        schedule_id: int,
        data: ScheduleUpdate,
    ) -> ScheduleResponse | None:
        """Update an existing schedule.

        Args:
            schedule_id: Schedule ID.
            data: Update data.

        Returns:
            Updated ScheduleResponse or None if not found.
        """
        schedule = await self.repository.get_by_id(schedule_id)
        if not schedule:
            return None

        update_data = data.model_dump(exclude_unset=True)
        await self.repository.update(schedule, update_data)
        await self.session.commit()

        # Reload with relations
        schedules = await self.repository.get_all_with_relations(
            train_id=schedule.train_id,
            station_id=schedule.station_id,
            limit=1,
        )
        if schedules:
            schedule = schedules[0]

        logger.info("Schedule updated", schedule_id=schedule_id)
        return self._schedule_to_response(schedule)

    async def delete_schedule(self, schedule_id: int) -> bool:
        """Delete a schedule.

        Args:
            schedule_id: Schedule ID.

        Returns:
            True if deleted, False if not found.
        """
        schedule = await self.repository.get_by_id(schedule_id)
        if not schedule:
            return False

        await self.repository.delete(schedule)
        await self.session.commit()
        logger.info("Schedule deleted", schedule_id=schedule_id)
        return True

    async def get_train_schedule(
        self,
        train_id: int,
        day_of_week: int | None = None,
    ) -> TrainScheduleResponse | None:
        """Get complete schedule for a train.

        Args:
            train_id: Train ID.
            day_of_week: Filter by day of week.

        Returns:
            TrainScheduleResponse with all stops or None.
        """
        schedules = await self.repository.get_by_train(train_id, day_of_week)
        if not schedules:
            return None

        train = schedules[0].train
        if not train:
            return None

        return TrainScheduleResponse(
            train=TrainSummary(
                id=train.id,
                train_number=train.train_number,
                train_type=train.train_type,
                name=train.name,
            ),
            stops=[self._schedule_to_response(s) for s in schedules],
        )

    async def get_station_schedule(
        self,
        station_id: int,
        day_of_week: int | None = None,
    ) -> StationScheduleResponse | None:
        """Get all arrivals/departures for a station.

        Args:
            station_id: Station ID.
            day_of_week: Filter by day of week.

        Returns:
            StationScheduleResponse with all trains or None.
        """
        schedules = await self.repository.get_by_station(station_id, day_of_week)
        if not schedules:
            return None

        station = schedules[0].station
        if not station:
            return None

        return StationScheduleResponse(
            station=StationSummary(
                id=station.id,
                name=station.name,
                code=station.code,
            ),
            schedules=[self._schedule_to_response(s) for s in schedules],
        )

    async def get_upcoming_departures(
        self,
        station_id: int,
        current_time: time,
        day_of_week: int,
        limit: int = 10,
    ) -> list[ScheduleResponse]:
        """Get upcoming departures from a station.

        Args:
            station_id: Station ID.
            current_time: Current time.
            day_of_week: Current day of week.
            limit: Maximum results.

        Returns:
            List of upcoming schedules.
        """
        schedules = await self.repository.get_upcoming_departures(
            station_id, current_time, day_of_week, limit
        )
        return [self._schedule_to_response(s) for s in schedules]
