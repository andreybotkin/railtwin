"""Station service for business logic.

This module provides the service layer for station-related operations,
handling business logic between API endpoints and repository layer.
"""

import json
from math import ceil

from geoalchemy2.functions import ST_GeomFromText
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.database.models import Station
from app.repositories.station import StationRepository
from app.schemas.station import (
    GeoJSONPoint,
    StationCreate,
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

    def __init__(self, session: AsyncSession) -> None:
        """Initialize station service.

        Args:
            session: Async database session.
        """
        self.repository = StationRepository(session)
        self.session = session

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
            facilities=station.facilities,
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
        station = await self.repository.get_by_id_with_location(station_id)
        if not station:
            return None
        return self._station_to_response(station)

    async def get_station_by_code(self, code: str) -> StationResponse | None:
        """Get a single station by code.

        Args:
            code: Station code.

        Returns:
            StationResponse or None if not found.
        """
        station = await self.repository.get_by_code(code)
        if not station:
            return None
        # Need to fetch with location
        station = await self.repository.get_by_id_with_location(station.id)
        return self._station_to_response(station)

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
        skip = (page - 1) * size
        stations = await self.repository.get_all_with_location(skip=skip, limit=size)
        total = await self.repository.count()

        return StationListResponse(
            items=[self._station_to_response(s) for s in stations],
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
        station = await self.repository.get_by_id_with_location(station.id)
        logger.info("Station created", station_id=station.id, code=station.code)
        return self._station_to_response(station)

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

        station = await self.repository.get_by_id_with_location(station_id)
        logger.info("Station updated", station_id=station_id)
        return self._station_to_response(station)

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
        stations = await self.repository.search_by_name(query, limit)
        # Fetch each with location for proper GeoJSON
        results = []
        for station in stations:
            station_with_loc = await self.repository.get_by_id_with_location(station.id)
            if station_with_loc:
                results.append(self._station_to_response(station_with_loc))
        return results

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
        results = await self.repository.find_nearby(
            longitude, latitude, radius_km, limit
        )
        return [
            {
                "station": self._station_to_response(r["station"]),
                "distance_m": r["distance_m"],
            }
            for r in results
        ]
