"""Schedule service for business logic.

This module provides the service layer for schedule-related operations,
handling business logic between API endpoints and repository layer.
"""

from datetime import time
from math import ceil
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.database.models import Schedule
from app.repositories.schedule import ScheduleRepository
from app.repositories.station import StationRepository
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
from app.services.reference_data import RedisReferenceReader, refresh_reference_data

logger = get_logger(__name__)


class ScheduleService:
    """Service class for schedule operations.

    Handles business logic for creating, reading, updating, and
    deleting train schedules.
    """

    def __init__(self, session: AsyncSession, redis_client: Redis) -> None:
        """Initialize schedule service.

        Args:
            session: Async database session.
        """
        self.repository = ScheduleRepository(session)
        self.station_repository = StationRepository(session)
        self.session = session
        self.redis = redis_client
        self.reader = RedisReferenceReader(redis_client)

    async def _resolve_station_name(
        self,
        station_id: int | None,
        station_name: str | None,
    ) -> str | None:
        """Resolve a canonical station name when only station_id is provided."""
        if station_name:
            return station_name
        if station_id is None:
            return None

        station = await self.station_repository.get_by_id(station_id)
        if station:
            return str(station.name)
        return None

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
            station_name=schedule.station_name,
            arrival_time=schedule.arrival_time,
            departure_time=schedule.departure_time,
            arrival_day_offset=schedule.arrival_day_offset,
            departure_day_offset=schedule.departure_day_offset,
            day_of_week=schedule.day_of_week,
            platform=schedule.platform,
            sequence=schedule.sequence,
            route_station_id=schedule.route_station_id,
            distance_from_origin_km=(
                float(schedule.distance_from_origin_km)
                if schedule.distance_from_origin_km is not None
                else None
            ),
            route_progress=(
                float(schedule.route_progress)
                if schedule.route_progress is not None
                else None
            ),
            train=train,
            station=station,
        )

    def _payload_to_response(self, schedule: dict[str, Any]) -> ScheduleResponse:
        return ScheduleResponse(
            id=schedule["id"],
            train_id=schedule["train_id"],
            station_id=schedule.get("station_id"),
            station_name=schedule.get("station_name"),
            arrival_time=schedule.get("arrival_time"),
            departure_time=schedule.get("departure_time"),
            arrival_day_offset=schedule.get("arrival_day_offset", 0),
            departure_day_offset=schedule.get("departure_day_offset", 0),
            day_of_week=schedule.get("day_of_week"),
            platform=schedule.get("platform"),
            sequence=schedule.get("sequence", 0),
            route_station_id=schedule.get("route_station_id"),
            distance_from_origin_km=schedule.get("distance_from_origin_km"),
            route_progress=schedule.get("route_progress"),
            train=(
                TrainSummary.model_validate(schedule["train"])
                if schedule.get("train")
                else None
            ),
            station=(
                StationSummary.model_validate(schedule["station"])
                if schedule.get("station")
                else None
            ),
        )

    async def get_schedule(self, schedule_id: int) -> ScheduleResponse | None:
        """Get a single schedule by ID.

        Args:
            schedule_id: Schedule ID.

        Returns:
            ScheduleResponse or None if not found.
        """
        schedule = await self.reader.get_schedule(schedule_id)
        if not schedule:
            return None
        return self._payload_to_response(schedule)

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
        schedules, total = await self.reader.list_schedules(
            page=page,
            size=size,
            train_id=train_id,
            station_id=station_id,
            day_of_week=day_of_week,
        )

        return ScheduleListResponse(
            items=[self._payload_to_response(s) for s in schedules],
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
        resolved_station_name = await self._resolve_station_name(
            data.station_id,
            data.station_name,
        )
        if resolved_station_name:
            schedule_data["station_name"] = resolved_station_name

        schedule = await self.repository.create(schedule_data)
        await self.session.commit()

        created = await self.repository.get_by_id_with_relations(schedule.id)
        assert created is not None
        await refresh_reference_data(self.session, self.redis)

        logger.info(
            "Schedule created",
            schedule_id=created.id,
            train_id=created.train_id,
        )
        return self._schedule_to_response(created)

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
        if "station_id" in update_data or "station_name" in update_data:
            resolved_station_name = await self._resolve_station_name(
                update_data.get("station_id", schedule.station_id),
                update_data.get("station_name"),
            )
            if resolved_station_name:
                update_data["station_name"] = resolved_station_name

        await self.repository.update(schedule, update_data)
        await self.session.commit()

        updated = await self.repository.get_by_id_with_relations(schedule_id)
        assert updated is not None
        await refresh_reference_data(self.session, self.redis)

        logger.info("Schedule updated", schedule_id=schedule_id)
        return self._schedule_to_response(updated)

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
        await refresh_reference_data(self.session, self.redis)
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
        schedules = await self.reader.get_train_schedule(train_id, day_of_week)
        if not schedules:
            return None

        train = schedules[0].get("train")
        if not train:
            return None

        return TrainScheduleResponse(
            train=TrainSummary.model_validate(train),
            stops=[self._payload_to_response(s) for s in schedules],
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
        schedules = await self.reader.get_station_schedule(station_id, day_of_week)
        if not schedules:
            return None

        station = schedules[0].get("station")
        if not station:
            return None

        return StationScheduleResponse(
            station=StationSummary.model_validate(station),
            schedules=[self._payload_to_response(s) for s in schedules],
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
        schedules = await self.reader.get_upcoming_departures(
            station_id=station_id,
            current_time=current_time,
            day_of_week=day_of_week,
            limit=limit,
        )
        return [self._payload_to_response(s) for s in schedules]
