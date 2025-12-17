"""Train repository for database operations.

This module provides repository methods for Train and TrainPosition
model operations including geospatial queries using PostGIS.
"""

from datetime import datetime, timedelta
from typing import Any

from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.database.models import Train, TrainPosition
from app.repositories.base import BaseRepository


class TrainRepository(BaseRepository[Train]):
    """Repository for Train database operations.

    Provides CRUD operations for trains and their positions.
    """

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
        return result.scalar_one_or_none()

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

    async def get_latest_position(
        self,
        train_id: int,
    ) -> dict[str, Any] | None:
        """Get the latest position for a train.

        Args:
            train_id: Train ID.

        Returns:
            Latest position with GeoJSON or None.
        """
        result = await self.session.execute(
            select(
                TrainPosition,
                ST_AsGeoJSON(TrainPosition.location).label("geojson"),
            )
            .where(TrainPosition.train_id == train_id)
            .order_by(TrainPosition.timestamp.desc())
            .limit(1)
        )
        row = result.first()
        if row:
            return {
                "position": row[0],
                "geojson": row[1],
            }
        return None

    async def get_all_current_positions(self) -> list[dict[str, Any]]:
        """Get current positions for all active trains.

        Returns positions from the last 5 minutes.

        Returns:
            List of train positions with GeoJSON.
        """
        cutoff_time = datetime.utcnow() - timedelta(minutes=5)

        # Subquery for latest position per train
        subq = (
            select(
                TrainPosition.train_id,
                TrainPosition.timestamp.label("max_time"),
            )
            .where(TrainPosition.timestamp >= cutoff_time)
            .group_by(TrainPosition.train_id)
            .subquery()
        )

        result = await self.session.execute(
            select(
                TrainPosition,
                ST_AsGeoJSON(TrainPosition.location).label("geojson"),
            )
            .join(
                subq,
                (TrainPosition.train_id == subq.c.train_id)
                & (TrainPosition.timestamp == subq.c.max_time),
            )
            .options(selectinload(TrainPosition.train))
        )

        positions = []
        for row in result.all():
            positions.append({
                "position": row[0],
                "geojson": row[1],
                "train": row[0].train,
            })
        return positions

    async def create_position(
        self,
        train_id: int,
        location_wkt: str,
        speed: float | None = None,
        heading: float | None = None,
        status: str = "moving",
        delay_minutes: int = 0,
    ) -> TrainPosition:
        """Create a new train position record.

        Args:
            train_id: Train ID.
            location_wkt: Location as WKT POINT string.
            speed: Current speed in km/h.
            heading: Direction in degrees.
            status: Train status.
            delay_minutes: Delay in minutes.

        Returns:
            Created TrainPosition record.
        """
        from geoalchemy2.functions import ST_GeomFromText

        position = TrainPosition(
            train_id=train_id,
            location=ST_GeomFromText(location_wkt, 4326),
            speed=speed,
            heading=heading,
            status=status,
            delay_minutes=delay_minutes,
        )
        self.session.add(position)
        await self.session.flush()
        await self.session.refresh(position)
        return position
