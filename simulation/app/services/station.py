"""Station service for business logic.

This module provides the service layer for station-related operations,
handling business logic between API endpoints and repository layer.
"""

import json
from math import ceil

from geoalchemy2.functions import ST_GeomFromText
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.database.models import Station
from app.repositories.station import StationRepository
from app.services.geo_utils import haversine_km
from app.services.reference_data import RedisReferenceReader, refresh_reference_data
from app.schemas.station import (
    GeoJSONPoint,
    StationCreate,
    StationFacilities,
    StationListResponse,
    StationResponse,
    StationUpdate,
)

logger = get_logger(__name__)


class StationService:
    """Service class for station operations.

    Handles business logic for creating, reading, updating, and
    deleting stations with proper data transformation.
    """

    def __init__(self, session: AsyncSession, redis_client: Redis) -> None:
        """Initialize station service.

        Args:
            session: Async database session.
        """
        self.repository = StationRepository(session)
        self.session = session
        self.redis = redis_client
        self.reader = RedisReferenceReader(redis_client)

    def _payload_to_response(self, station: dict[str, object]) -> StationResponse:
        facilities = station.get("facilities")
        return StationResponse(
            id=station["id"],
            name=station["name"],
            name_th=station.get("name_th"),
            code=station["code"],
            city=station.get("city"),
            province=station.get("province"),
            facilities=(
                StationFacilities.model_validate(facilities)
                if facilities
                else None
            ),
            location=GeoJSONPoint.model_validate(station["location"]),
            created_at=station["created_at"],
            updated_at=station["updated_at"],
        )

    def _station_to_response(self, station: Station) -> StationResponse:
        """Convert station model to response schema.

        Args:
            station: Station database model.

        Returns:
            StationResponse schema.
        """
        # Parse GeoJSON from the attached _geojson attribute
        geojson_str = getattr(station, "_geojson", None)
        if geojson_str:
            geojson_data = json.loads(geojson_str)
            location = GeoJSONPoint(
                type="Point",
                coordinates=geojson_data["coordinates"],
            )
        else:
            location = GeoJSONPoint(type="Point", coordinates=[0, 0])

        return StationResponse(
            id=station.id,
            name=station.name,
            name_th=station.name_th,
            code=station.code,
            city=station.city,
            province=station.province,
            facilities=(
                StationFacilities.model_validate(station.facilities)
                if station.facilities
                else None
            ),
            location=location,
            created_at=station.created_at,
            updated_at=station.updated_at,
        )

    async def get_station(self, station_id: int) -> StationResponse | None:
        """Get a single station by ID.

        Args:
            station_id: Station ID.

        Returns:
            StationResponse or None if not found.
        """
        station = await self.reader.get_station(station_id)
        if not station:
            return None
        return self._payload_to_response(station)

    async def get_station_by_code(self, code: str) -> StationResponse | None:
        """Get a single station by code.

        Args:
            code: Station code.

        Returns:
            StationResponse or None if not found.
        """
        station = await self.reader.get_station_by_code(code)
        if not station:
            return None
        return self._payload_to_response(station)

    async def list_stations(
        self,
        page: int = 1,
        size: int = 20,
    ) -> StationListResponse:
        """List stations with pagination.

        Args:
            page: Page number (1-indexed).
            size: Number of items per page.

        Returns:
            StationListResponse with paginated results.
        """
        stations, total = await self.reader.list_stations(page=page, size=size)

        return StationListResponse(
            items=[self._payload_to_response(s) for s in stations],
            total=total,
            page=page,
            size=size,
            pages=ceil(total / size) if size > 0 else 0,
        )

    async def create_station(self, data: StationCreate) -> StationResponse:
        """Create a new station.

        Args:
            data: Station creation data.

        Returns:
            Created StationResponse.
        """
        # Convert GeoJSON to WKT for PostGIS
        lon, lat = data.location.coordinates
        wkt = f"POINT({lon} {lat})"

        station_data = data.model_dump(exclude={"location"})
        station_data["location"] = ST_GeomFromText(wkt, 4326)

        station = await self.repository.create(station_data)
        await self.session.commit()

        # Fetch with location for response
        station_with_loc = await self.repository.get_by_id_with_location(station.id)
        assert station_with_loc is not None
        await refresh_reference_data(self.session, self.redis)
        logger.info(
            "Station created",
            station_id=station_with_loc.id,
            code=station_with_loc.code,
        )
        return self._station_to_response(station_with_loc)

    async def update_station(
        self,
        station_id: int,
        data: StationUpdate,
    ) -> StationResponse | None:
        """Update an existing station.

        Args:
            station_id: Station ID.
            data: Update data.

        Returns:
            Updated StationResponse or None if not found.
        """
        station = await self.repository.get_by_id(station_id)
        if not station:
            return None

        update_data = data.model_dump(exclude_unset=True, exclude={"location"})

        # Handle location update
        if data.location:
            lon, lat = data.location.coordinates
            wkt = f"POINT({lon} {lat})"
            update_data["location"] = ST_GeomFromText(wkt, 4326)

        await self.repository.update(station, update_data)
        await self.session.commit()

        station_with_loc = await self.repository.get_by_id_with_location(station_id)
        await refresh_reference_data(self.session, self.redis)
        logger.info("Station updated", station_id=station_id)
        return self._station_to_response(station_with_loc) if station_with_loc else None

    async def delete_station(self, station_id: int) -> bool:
        """Delete a station.

        Args:
            station_id: Station ID.

        Returns:
            True if deleted, False if not found.
        """
        station = await self.repository.get_by_id(station_id)
        if not station:
            return False

        await self.repository.delete(station)
        await self.session.commit()
        await refresh_reference_data(self.session, self.redis)
        logger.info("Station deleted", station_id=station_id)
        return True

    async def search_stations(
        self,
        query: str,
        limit: int = 10,
    ) -> list[StationResponse]:
        """Search stations by name or code.

        Args:
            query: Search query string.
            limit: Maximum results.

        Returns:
            List of matching stations.
        """
        stations = await self.reader.search_stations(query, limit)
        return [self._payload_to_response(station) for station in stations]

    async def find_nearby_stations(
        self,
        longitude: float,
        latitude: float,
        radius_km: float = 10.0,
        limit: int = 10,
    ) -> list[dict]:
        """Find stations near a location.

        Args:
            longitude: Center longitude.
            latitude: Center latitude.
            radius_km: Search radius in km.
            limit: Maximum results.

        Returns:
            List of stations with distance.
        """
        stations, _total = await self.reader.list_stations(page=1, size=10000)
        matches = []
        for station in stations:
            station_lon, station_lat = station["location"]["coordinates"]
            distance_km = haversine_km(
                longitude,
                latitude,
                float(station_lon),
                float(station_lat),
            )
            if distance_km <= radius_km:
                matches.append(
                    {
                        "station": self._payload_to_response(station),
                        "distance_m": round(distance_km * 1000, 2),
                    }
                )
        matches.sort(key=lambda item: float(item["distance_m"]))
        return matches[:limit]
