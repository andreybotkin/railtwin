"""Station repository for database operations.

This module provides repository methods for Station model operations
including geospatial queries using PostGIS.
"""

from typing import Any, cast

from geoalchemy2.functions import ST_AsGeoJSON, ST_Distance, ST_MakePoint
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database.models import Station
from app.repositories.base import BaseRepository


class StationRepository(BaseRepository[Station]):
    """Repository for Station database operations.

    Provides CRUD operations and geospatial queries for stations.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize station repository.

        Args:
            session: Async database session.
        """
        super().__init__(Station, session)

    async def get_by_code(self, code: str) -> Station | None:
        """Get station by unique code.

        Args:
            code: Station code.

        Returns:
            Station or None if not found.
        """
        result = await self.session.execute(select(Station).where(Station.code == code))
        return cast("Station | None", result.scalar_one_or_none())

    async def get_all_with_location(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Station]:
        """Get all stations with GeoJSON location.

        Args:
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of stations with GeoJSON locations.
        """
        result = await self.session.execute(
            select(
                Station,
                ST_AsGeoJSON(Station.location).label("geojson"),
            )
            .offset(skip)
            .limit(limit)
        )
        stations: list[Station] = []
        for row in result.all():
            station: Station = row[0]
            station._geojson = row[1]
            stations.append(station)
        return stations

    async def get_by_id_with_location(self, station_id: int) -> Station | None:
        """Get station by ID with GeoJSON location.

        Args:
            station_id: Station ID.

        Returns:
            Station with GeoJSON location or None.
        """
        result = await self.session.execute(
            select(
                Station,
                ST_AsGeoJSON(Station.location).label("geojson"),
            ).where(Station.id == station_id)
        )
        row = result.first()
        if row:
            station: Station = row[0]
            station._geojson = row[1]
            return station
        return None

    async def find_nearby(
        self,
        longitude: float,
        latitude: float,
        radius_km: float = 10.0,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Find stations within radius of a point.

        Args:
            longitude: Longitude of center point.
            latitude: Latitude of center point.
            radius_km: Search radius in kilometers.
            limit: Maximum number of results.

        Returns:
            List of stations with distance information.
        """
        point = ST_MakePoint(longitude, latitude)
        distance_m = ST_Distance(
            Station.location,
            func.ST_SetSRID(point, 4326),
            True,  # Use spheroid for accurate distance
        )

        result = await self.session.execute(
            select(
                Station,
                ST_AsGeoJSON(Station.location).label("geojson"),
                distance_m.label("distance_m"),
            )
            .where(distance_m <= radius_km * 1000)
            .order_by(distance_m)
            .limit(limit)
        )

        stations = []
        for row in result.all():
            station_dict = {
                "station": row[0],
                "geojson": row[1],
                "distance_m": row[2],
            }
            stations.append(station_dict)
        return stations

    async def search_by_name(
        self,
        query: str,
        limit: int = 10,
    ) -> list[Station]:
        """Search stations by name.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of matching stations.
        """
        result = await self.session.execute(
            select(Station)
            .where(
                Station.name.ilike(f"%{query}%")
                | Station.name_th.ilike(f"%{query}%")
                | Station.code.ilike(f"%{query}%")
            )
            .limit(limit)
        )
        return list(result.scalars().all())
