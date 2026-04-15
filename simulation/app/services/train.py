"""Train service for business logic.

This module provides the service layer for train-related operations,
handling business logic between API endpoints and repository layer.
"""

import json
from math import ceil

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.database.models import Train
from app.repositories.train import TrainRepository
from app.services.reference_data import RedisReferenceReader, refresh_reference_data
from app.schemas.route import RouteSummary
from app.schemas.station import GeoJSONPoint
from app.schemas.train import (
    TrainCreate,
    TrainListResponse,
    TrainPositionResponse,
    TrainResponse,
    TrainUpdate,
)

logger = get_logger(__name__)


class TrainService:
    """Service class for train operations.

    Handles business logic for creating, reading, updating, and
    deleting trains and their positions.
    """

    def __init__(self, session: AsyncSession, redis_client: Redis) -> None:
        """Initialize train service.

        Args:
            session: Async database session.
        """
        self.repository = TrainRepository(session)
        self.session = session
        self.redis = redis_client
        self.reader = RedisReferenceReader(redis_client)

    def _payload_to_response(self, train: dict[str, object]) -> TrainResponse:
        current_route = (
            RouteSummary.model_validate(train["current_route"])
            if train.get("current_route")
            else None
        )
        return TrainResponse(
            id=train["id"],
            train_number=train["train_number"],
            train_type=train["train_type"],
            name=train.get("name"),
            capacity=train.get("capacity"),
            operator=train["operator"],
            source=train["source"],
            source_url=train.get("source_url"),
            service_notes=train.get("service_notes"),
            current_route_id=train.get("current_route_id"),
            current_route=current_route,
            created_at=train["created_at"],
        )

    def _train_to_response(self, train: Train) -> TrainResponse:
        """Convert train model to response schema.

        Args:
            train: Train database model.

        Returns:
            TrainResponse schema.
        """
        current_route = None
        if train.current_route:
            current_route = RouteSummary(
                id=train.current_route.id,
                name=train.current_route.name,
                route_type=train.current_route.route_type,
                color=train.current_route.color,
            )

        return TrainResponse(
            id=train.id,
            train_number=train.train_number,
            train_type=train.train_type,
            name=train.name,
            capacity=train.capacity,
            operator=train.operator,
            source=train.source,
            source_url=train.source_url,
            service_notes=train.service_notes,
            current_route_id=train.current_route_id,
            current_route=current_route,
            created_at=train.created_at,
        )

    async def get_train(self, train_id: int) -> TrainResponse | None:
        """Get a single train by ID.

        Args:
            train_id: Train ID.

        Returns:
            TrainResponse or None if not found.
        """
        train = await self.reader.get_train(train_id)
        if not train:
            return None
        return self._payload_to_response(train)

    async def get_train_by_number(self, train_number: str) -> TrainResponse | None:
        """Get a single train by train number.

        Args:
            train_number: Train number.

        Returns:
            TrainResponse or None if not found.
        """
        train = await self.reader.get_train_by_number(train_number)
        if not train:
            return None
        return self._payload_to_response(train)

    async def list_trains(
        self,
        page: int = 1,
        size: int = 20,
        train_type: str | None = None,
        route_id: int | None = None,
    ) -> TrainListResponse:
        """List trains with pagination and filtering.

        Args:
            page: Page number (1-indexed).
            size: Number of items per page.
            train_type: Filter by train type.
            route_id: Filter by current route.

        Returns:
            TrainListResponse with paginated results.
        """
        trains, total = await self.reader.list_trains(
            page=page,
            size=size,
            train_type=train_type,
            route_id=route_id,
        )

        return TrainListResponse(
            items=[self._payload_to_response(t) for t in trains],
            total=total,
            page=page,
            size=size,
            pages=ceil(total / size) if size > 0 else 0,
        )

    async def create_train(self, data: TrainCreate) -> TrainResponse:
        """Create a new train.

        Args:
            data: Train creation data.

        Returns:
            Created TrainResponse.
        """
        train_data = data.model_dump()
        train = await self.repository.create(train_data)
        await self.session.commit()
        await refresh_reference_data(self.session, self.redis)

        logger.info("Train created", train_id=train.id, number=train.train_number)
        return self._train_to_response(train)

    async def update_train(
        self,
        train_id: int,
        data: TrainUpdate,
    ) -> TrainResponse | None:
        """Update an existing train.

        Args:
            train_id: Train ID.
            data: Update data.

        Returns:
            Updated TrainResponse or None if not found.
        """
        train = await self.repository.get_by_id(train_id)
        if not train:
            return None

        update_data = data.model_dump(exclude_unset=True)
        await self.repository.update(train, update_data)
        await self.session.commit()
        await refresh_reference_data(self.session, self.redis)

        logger.info("Train updated", train_id=train_id)
        return self._train_to_response(train)

    async def delete_train(self, train_id: int) -> bool:
        """Delete a train.

        Args:
            train_id: Train ID.

        Returns:
            True if deleted, False if not found.
        """
        train = await self.repository.get_by_id(train_id)
        if not train:
            return False

        await self.repository.delete(train)
        await self.session.commit()
        await refresh_reference_data(self.session, self.redis)
        logger.info("Train deleted", train_id=train_id)
        return True

    async def get_train_position(
        self,
        train_id: int,
    ) -> TrainPositionResponse | None:
        """Get the latest position for a train.

        Args:
            train_id: Train ID.

        Returns:
            TrainPositionResponse or None if not found.
        """
        result = await self.repository.get_latest_position(train_id)
        if not result:
            return None

        position = result["position"]
        geojson_data = json.loads(result["geojson"])

        return TrainPositionResponse(
            id=position.id,
            train_id=position.train_id,
            location=GeoJSONPoint(
                type="Point",
                coordinates=geojson_data["coordinates"],
            ),
            speed=float(position.speed) if position.speed else None,
            heading=float(position.heading) if position.heading else None,
            status=position.status,
            delay_minutes=position.delay_minutes,
            timestamp=position.timestamp,
        )

    async def get_all_positions(self) -> list[dict]:
        """Get current positions for all active trains.

        Returns:
            List of position data with train info.
        """
        positions = await self.repository.get_all_current_positions()
        results = []

        for p in positions:
            geojson_data = json.loads(p["geojson"])
            position = p["position"]
            train = p["train"]

            results.append(
                {
                    "train_id": train.id,
                    "train_number": train.train_number,
                    "train_type": train.train_type,
                    "location": {
                        "type": "Point",
                        "coordinates": geojson_data["coordinates"],
                    },
                    "speed": float(position.speed) if position.speed else None,
                    "heading": float(position.heading) if position.heading else None,
                    "status": position.status,
                    "delay_minutes": position.delay_minutes,
                    "timestamp": position.timestamp.isoformat(),
                }
            )

        return results

    async def update_position(
        self,
        train_id: int,
        longitude: float,
        latitude: float,
        speed: float | None = None,
        heading: float | None = None,
        status: str = "moving",
        delay_minutes: int = 0,
    ) -> TrainPositionResponse:
        """Update train position.

        Args:
            train_id: Train ID.
            longitude: Current longitude.
            latitude: Current latitude.
            speed: Current speed in km/h.
            heading: Direction in degrees.
            status: Train status.
            delay_minutes: Delay in minutes.

        Returns:
            Created TrainPositionResponse.
        """
        wkt = f"POINT({longitude} {latitude})"
        position = await self.repository.create_position(
            train_id=train_id,
            location_wkt=wkt,
            speed=speed,
            heading=heading,
            status=status,
            delay_minutes=delay_minutes,
        )
        await self.session.commit()

        return TrainPositionResponse(
            id=position.id,
            train_id=position.train_id,
            location=GeoJSONPoint(
                type="Point",
                coordinates=[longitude, latitude],
            ),
            speed=speed,
            heading=heading,
            status=status,
            delay_minutes=delay_minutes,
            timestamp=position.timestamp,
        )
