"""Route service for business logic.

This module provides the service layer for route-related operations,
handling business logic between API endpoints and repository layer.
"""

import json
from math import ceil

from geoalchemy2.functions import ST_GeomFromText
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.database.models import Route
from app.repositories.route import RouteRepository
from app.schemas.route import (
    GeoJSONLineString,
    RouteCreate,
    RouteListResponse,
    RouteResponse,
    RouteStationInfo,
    RouteUpdate,
)

logger = get_logger(__name__)


class RouteService:
    """Service class for route operations.

    Handles business logic for creating, reading, updating, and
    deleting routes with proper data transformation.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize route service.

        Args:
            session: Async database session.
        """
        self.repository = RouteRepository(session)
        self.session = session

    def _route_to_response(self, route: Route) -> RouteResponse:
        """Convert route model to response schema.

        Args:
            route: Route database model.

        Returns:
            RouteResponse schema.
        """
        # Parse GeoJSON from the attached _geojson attribute
        geojson_str = getattr(route, "_geojson", None)
        line_geometry = None
        if geojson_str:
            geojson_data = json.loads(geojson_str)
            line_geometry = GeoJSONLineString(
                type="LineString",
                coordinates=geojson_data["coordinates"],
            )

        # Build stations list from route_stations relationship
        stations = []
        if route.route_stations:
            for rs in sorted(route.route_stations, key=lambda x: x.sequence):
                if rs.station:
                    stations.append(
                        RouteStationInfo(
                            id=rs.station.id,
                            name=rs.station.name,
                            code=rs.station.code,
                            sequence=rs.sequence,
                            distance_from_start=(
                                float(rs.distance_from_start)
                                if rs.distance_from_start
                                else None
                            ),
                        )
                    )

        return RouteResponse(
            id=route.id,
            name=route.name,
            name_th=route.name_th,
            route_type=route.route_type,
            distance_km=float(route.distance_km) if route.distance_km else None,
            color=route.color,
            line_geometry=line_geometry,
            stations=stations,
            created_at=route.created_at,
        )

    async def get_route(self, route_id: int) -> RouteResponse | None:
        """Get a single route by ID.

        Args:
            route_id: Route ID.

        Returns:
            RouteResponse or None if not found.
        """
        route = await self.repository.get_by_id_with_geometry(route_id)
        if not route:
            return None
        return self._route_to_response(route)

    async def list_routes(
        self,
        page: int = 1,
        size: int = 20,
        route_type: str | None = None,
    ) -> RouteListResponse:
        """List routes with pagination.

        Args:
            page: Page number (1-indexed).
            size: Number of items per page.
            route_type: Filter by route type.

        Returns:
            RouteListResponse with paginated results.
        """
        skip = (page - 1) * size

        if route_type:
            routes = await self.repository.get_by_type(
                route_type, skip=skip, limit=size
            )
        else:
            routes = await self.repository.get_all_with_geometry(skip=skip, limit=size)

        total = await self.repository.count()

        return RouteListResponse(
            items=[self._route_to_response(r) for r in routes],
            total=total,
            page=page,
            size=size,
            pages=ceil(total / size) if size > 0 else 0,
        )

    async def create_route(self, data: RouteCreate) -> RouteResponse:
        """Create a new route.

        Args:
            data: Route creation data.

        Returns:
            Created RouteResponse.
        """
        route_data = data.model_dump(exclude={"line_geometry"})

        # Convert GeoJSON to WKT for PostGIS
        if data.line_geometry:
            coords = data.line_geometry.coordinates
            coords_str = ", ".join([f"{c[0]} {c[1]}" for c in coords])
            wkt = f"LINESTRING({coords_str})"
            route_data["line_geometry"] = ST_GeomFromText(wkt, 4326)

        route = await self.repository.create(route_data)
        await self.session.commit()

        created = await self.repository.get_by_id_with_geometry(route.id)
        assert created is not None
        logger.info("Route created", route_id=created.id, name=created.name)
        return self._route_to_response(created)

    async def update_route(
        self,
        route_id: int,
        data: RouteUpdate,
    ) -> RouteResponse | None:
        """Update an existing route.

        Args:
            route_id: Route ID.
            data: Update data.

        Returns:
            Updated RouteResponse or None if not found.
        """
        route = await self.repository.get_by_id(route_id)
        if not route:
            return None

        update_data = data.model_dump(exclude_unset=True, exclude={"line_geometry"})

        if data.line_geometry:
            coords = data.line_geometry.coordinates
            coords_str = ", ".join([f"{c[0]} {c[1]}" for c in coords])
            wkt = f"LINESTRING({coords_str})"
            update_data["line_geometry"] = ST_GeomFromText(wkt, 4326)

        await self.repository.update(route, update_data)
        await self.session.commit()

        updated = await self.repository.get_by_id_with_geometry(route_id)
        logger.info("Route updated", route_id=route_id)
        return self._route_to_response(updated) if updated else None

    async def delete_route(self, route_id: int) -> bool:
        """Delete a route.

        Args:
            route_id: Route ID.

        Returns:
            True if deleted, False if not found.
        """
        route = await self.repository.get_by_id(route_id)
        if not route:
            return False

        await self.repository.delete(route)
        await self.session.commit()
        logger.info("Route deleted", route_id=route_id)
        return True

    async def add_station_to_route(
        self,
        route_id: int,
        station_id: int,
        sequence: int,
        distance_from_start: float | None = None,
    ) -> RouteResponse | None:
        """Add a station to a route.

        Args:
            route_id: Route ID.
            station_id: Station ID.
            sequence: Order of station on route.
            distance_from_start: Distance from start in km.

        Returns:
            Updated RouteResponse or None if route not found.
        """
        route = await self.repository.get_by_id(route_id)
        if not route:
            return None

        await self.repository.add_station_to_route(
            route_id, station_id, sequence, distance_from_start
        )
        await self.session.commit()

        route = await self.repository.get_by_id_with_geometry(route_id)
        logger.info(
            "Station added to route",
            route_id=route_id,
            station_id=station_id,
            sequence=sequence,
        )
        return self._route_to_response(route) if route else None
