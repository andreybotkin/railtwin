"""Route repository for database operations.

This module provides repository methods for Route model operations
including geospatial queries using PostGIS.
"""

import json
import time as _time

from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.database.models import Route, RouteStation
from app.repositories.base import BaseRepository


class RouteRepository(BaseRepository[Route]):
    """Repository for Route database operations.

    Provides CRUD operations and geospatial queries for routes.
    """

    # Class-level geometry cache: route_id -> (coords, distance_km)
    # Shared across all RouteRepository instances; route geometry is static.
    _geometry_cache: dict[int, tuple[list, float | None]] = {}
    _geometry_cache_expires: float = 0.0
    _GEOMETRY_CACHE_TTL: float = 300.0  # 5 minutes

    def __init__(self, session: AsyncSession) -> None:
        """Initialize route repository.

        Args:
            session: Async database session.
        """
        super().__init__(Route, session)

    async def get_all_with_geometry(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Route]:
        """Get all routes with GeoJSON geometry.

        Args:
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of routes with GeoJSON geometry.
        """
        result = await self.session.execute(
            select(
                Route,
                ST_AsGeoJSON(Route.line_geometry).label("geojson"),
            )
            .options(
                selectinload(Route.route_stations).selectinload(RouteStation.station)
            )
            .offset(skip)
            .limit(limit)
        )
        routes = []
        for row in result.all():
            route = row[0]
            route._geojson = row[1]
            routes.append(route)
        return routes

    async def get_by_id_with_geometry(self, route_id: int) -> Route | None:
        """Get route by ID with GeoJSON geometry and stations.

        Args:
            route_id: Route ID.

        Returns:
            Route with GeoJSON geometry or None.
        """
        result = await self.session.execute(
            select(
                Route,
                ST_AsGeoJSON(Route.line_geometry).label("geojson"),
            )
            .options(
                selectinload(Route.route_stations).selectinload(RouteStation.station)
            )
            .where(Route.id == route_id)
        )
        row = result.first()
        if row:
            route: Route = row[0]
            route._geojson = row[1]
            return route
        return None

    async def get_geometry_bulk(
        self,
        route_ids: list[int],
    ) -> dict[int, tuple[list, float | None]]:
        """Get route geometries for multiple routes in one query.

        Uses a class-level in-memory cache (TTL 300 s) because route geometry
        is static — avoids repeated PostGIS round-trips every update cycle.

        Args:
            route_ids: List of route IDs to fetch.

        Returns:
            Dict mapping route_id -> (coords_list, distance_km | None).
        """
        if not route_ids:
            return {}
        now = _time.monotonic()

        if now < RouteRepository._geometry_cache_expires:
            cached = {
                rid: RouteRepository._geometry_cache[rid]
                for rid in route_ids
                if rid in RouteRepository._geometry_cache
            }
            missing = [rid for rid in route_ids if rid not in RouteRepository._geometry_cache]
        else:
            RouteRepository._geometry_cache.clear()
            cached = {}
            missing = list(route_ids)

        if not missing:
            return cached

        result = await self.session.execute(
            select(
                Route.id,
                ST_AsGeoJSON(Route.line_geometry).label("geojson"),
                Route.distance_km,
            ).where(Route.id.in_(missing))
        )
        fetched: dict[int, tuple[list, float | None]] = {}
        for row in result.all():
            route_id, geojson_str, distance_km = row
            coords: list = []
            if geojson_str:
                geojson = json.loads(geojson_str)
                coords = geojson.get("coordinates", [])
            dist = float(distance_km) if distance_km is not None else None
            fetched[route_id] = (coords, dist)

        RouteRepository._geometry_cache.update(fetched)
        if fetched:
            RouteRepository._geometry_cache_expires = now + RouteRepository._GEOMETRY_CACHE_TTL

        return {**cached, **fetched}

    async def get_by_type(
        self,
        route_type: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Route]:
        """Get routes by type.

        Args:
            route_type: Type of route (northern, northeastern, etc.).
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of routes matching the type.
        """
        result = await self.session.execute(
            select(
                Route,
                ST_AsGeoJSON(Route.line_geometry).label("geojson"),
            )
            .where(Route.route_type == route_type)
            .offset(skip)
            .limit(limit)
        )
        routes = []
        for row in result.all():
            route = row[0]
            route._geojson = row[1]
            routes.append(route)
        return routes

    async def add_station_to_route(
        self,
        route_id: int,
        station_id: int,
        sequence: int,
        distance_from_start: float | None = None,
    ) -> RouteStation:
        """Add a station to a route.

        Args:
            route_id: Route ID.
            station_id: Station ID.
            sequence: Order of station on route.
            distance_from_start: Distance from route start in km.

        Returns:
            Created RouteStation junction record.
        """
        route_station = RouteStation(
            route_id=route_id,
            station_id=station_id,
            sequence=sequence,
            distance_from_start=distance_from_start,
        )
        self.session.add(route_station)
        await self.session.flush()
        return route_station

    async def get_route_stations(self, route_id: int) -> list[RouteStation]:
        """Get all stations for a route in order.

        Args:
            route_id: Route ID.

        Returns:
            List of route stations with station info.
        """
        result = await self.session.execute(
            select(RouteStation)
            .options(selectinload(RouteStation.station))
            .where(RouteStation.route_id == route_id)
            .order_by(RouteStation.sequence)
        )
        return list(result.scalars().all())
