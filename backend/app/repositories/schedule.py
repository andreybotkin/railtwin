"""Schedule repository for database operations.

This module provides repository methods for Schedule model operations.
"""

from datetime import time
from typing import Any, cast

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.database.models import Schedule
from app.repositories.base import BaseRepository


class ScheduleRepository(BaseRepository[Schedule]):
    """Repository for Schedule database operations.

    Provides CRUD operations and queries for train schedules.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize schedule repository.

        Args:
            session: Async database session.
        """
        super().__init__(Schedule, session)

    async def get_by_id_with_relations(self, schedule_id: int) -> Schedule | None:
        """Get a single schedule entry with related train and station data."""
        result = await self.session.execute(
            select(Schedule)
            .options(
                selectinload(Schedule.train),
                selectinload(Schedule.station),
            )
            .where(Schedule.id == schedule_id)
        )
        return cast("Schedule | None", result.scalar_one_or_none())

    async def get_by_train(
        self,
        train_id: int,
        day_of_week: int | None = None,
    ) -> list[Schedule]:
        """Get all schedule entries for a train.

        Args:
            train_id: Train ID.
            day_of_week: Filter by day (0=Monday, 6=Sunday).

        Returns:
            List of schedules ordered by sequence.
        """
        query = (
            select(Schedule)
            .options(
                selectinload(Schedule.train),
                selectinload(Schedule.station),
            )
            .where(Schedule.train_id == train_id)
            .order_by(Schedule.sequence)
        )

        if day_of_week is not None:
            query = query.where(Schedule.day_of_week.contains([day_of_week]))

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_station(
        self,
        station_id: int,
        day_of_week: int | None = None,
    ) -> list[Schedule]:
        """Get all schedule entries for a station.

        Args:
            station_id: Station ID.
            day_of_week: Filter by day (0=Monday, 6=Sunday).

        Returns:
            List of schedules ordered by departure time.
        """
        query = (
            select(Schedule)
            .options(
                selectinload(Schedule.train),
                selectinload(Schedule.station),
            )
            .where(Schedule.station_id == station_id)
            .order_by(Schedule.departure_time)
        )

        if day_of_week is not None:
            query = query.where(Schedule.day_of_week.contains([day_of_week]))

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_all_with_relations(
        self,
        skip: int = 0,
        limit: int = 100,
        train_id: int | None = None,
        station_id: int | None = None,
        day_of_week: int | None = None,
    ) -> list[Schedule]:
        """Get schedules with optional filters and related data.

        Args:
            skip: Number of records to skip.
            limit: Maximum number of records to return.
            train_id: Filter by train ID.
            station_id: Filter by station ID.
            day_of_week: Filter by day of week.

        Returns:
            List of schedules with train and station info.
        """
        query = select(Schedule).options(
            selectinload(Schedule.train),
            selectinload(Schedule.station),
        )

        filters = []
        if train_id is not None:
            filters.append(Schedule.train_id == train_id)
        if station_id is not None:
            filters.append(Schedule.station_id == station_id)
        if day_of_week is not None:
            filters.append(Schedule.day_of_week.contains([day_of_week]))

        if filters:
            query = query.where(and_(*filters))

        query = query.order_by(Schedule.departure_time).offset(skip).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_upcoming_departures(
        self,
        station_id: int,
        current_time: time,
        day_of_week: int,
        limit: int = 10,
    ) -> list[Schedule]:
        """Get upcoming departures from a station.

        Args:
            station_id: Station ID.
            current_time: Current time.
            day_of_week: Current day (0=Monday, 6=Sunday).
            limit: Maximum number of results.

        Returns:
            List of upcoming schedules.
        """
        result = await self.session.execute(
            select(Schedule)
            .options(
                selectinload(Schedule.train),
                selectinload(Schedule.station),
            )
            .where(
                and_(
                    Schedule.station_id == station_id,
                    Schedule.departure_time >= current_time,
                    Schedule.day_of_week.contains([day_of_week]),
                )
            )
            .order_by(Schedule.departure_time)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_schedule_between_stations(
        self,
        train_id: int,
        from_station_id: int,
        to_station_id: int,
    ) -> dict[str, Any] | None:
        """Get schedule info between two stations for a train.

        Args:
            train_id: Train ID.
            from_station_id: Departure station ID.
            to_station_id: Arrival station ID.

        Returns:
            Dict with departure and arrival schedules or None.
        """
        from_schedule = await self.session.execute(
            select(Schedule).where(
                and_(
                    Schedule.train_id == train_id,
                    Schedule.station_id == from_station_id,
                )
            )
        )
        to_schedule = await self.session.execute(
            select(Schedule).where(
                and_(
                    Schedule.train_id == train_id,
                    Schedule.station_id == to_station_id,
                )
            )
        )

        from_result = from_schedule.scalar_one_or_none()
        to_result = to_schedule.scalar_one_or_none()

        if from_result and to_result:
            return {
                "departure": from_result,
                "arrival": to_result,
            }
        return None
