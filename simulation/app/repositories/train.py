"""Train repository for database operations.

This module provides repository methods for Train model CRUD operations.
Trajectory generation replaces the old TrainPosition snapshot table — the
simulation service writes fully-formed Trajectories directly to Redis.
"""

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.database.models import Train
from app.repositories.base import BaseRepository


class TrainRepository(BaseRepository[Train]):
    """Repository for Train database CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize train repository.

        Args:
            session: Async database session.
        """
        super().__init__(Train, session)

    async def get_by_train_number(self, train_number: str) -> Train | None:
        """Get train by unique train number.

        Args:
            train_number: Train number/identifier.

        Returns:
            Train or None if not found.
        """
        result = await self.session.execute(
            select(Train)
            .options(selectinload(Train.current_route))
            .where(Train.train_number == train_number)
        )
        return cast("Train | None", result.scalar_one_or_none())

    async def get_all_with_route(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Train]:
        """Get all trains with their current route.

        Args:
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of trains with route information.
        """
        result = await self.session.execute(
            select(Train)
            .options(selectinload(Train.current_route))
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_type(
        self,
        train_type: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Train]:
        """Get trains by type.

        Args:
            train_type: Type of train.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of trains matching the type.
        """
        result = await self.session.execute(
            select(Train)
            .options(selectinload(Train.current_route))
            .where(Train.train_type == train_type)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_route(
        self,
        route_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Train]:
        """Get trains on a specific route.

        Args:
            route_id: Route ID.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of trains on the route.
        """
        result = await self.session.execute(
            select(Train)
            .options(selectinload(Train.current_route))
            .where(Train.current_route_id == route_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

