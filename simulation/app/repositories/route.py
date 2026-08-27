"""Route repository for database operations.

This module provides repository methods for Route model operations
including geospatial queries using PostGIS.
"""

import json
import time as _time
from typing import Any, ClassVar

from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.database.models import NetworkEdge, Route, RouteEdge, RouteStation
from app.repositories.base import BaseRepository


class RouteRepository(BaseRepository[Route]):
    """Repository for Route database operations.

    Provides CRUD operations and geospatial queries for routes.
    """

    # Class-level geometry cache: route_id -> (coords, distance_km)
    # Shared across all RouteRepository instances; route geometry is static.
    _geometry_cache: ClassVar[dict[int, tuple[list, float | None]]] = {}
    _graph_geometry_cache: ClassVar[dict[int, dict[str, Any]]] = {}
    _geometry_cache_expires: float = 0.0
    _GEOMETRY_CACHE_TTL: float = 300.0  # 5 minutes

    def __init__(self, session: AsyncSession) -> None:
        """Initialize route repository.

        Args:
            session: Async database session.
        """
        super().__init__(Route, session)

    @staticmethod
    def _merge_edge_coordinates(segments: list[list[list[float]]]) -> list[list[float]]:
        merged: list[list[float]] = []
        for coordinates in segments:
            if not coordinates:
                continue
            if not merged:
                merged.extend(coordinates)
                continue
            if merged[-1] == coordinates[0]:
                merged.extend(coordinates[1:])
            else:
                merged.extend(coordinates)
        return merged

    async def _get_graph_payloads(
        self,
        route_ids: list[int],
    ) -> dict[int, dict[str, Any]]:
        edge_rows = await self.session.execute(
            select(
                RouteEdge.route_id,
                RouteEdge.sequence,
                RouteEdge.direction,
                NetworkEdge.id.label("edge_id"),
                NetworkEdge.from_station_id,
                NetworkEdge.to_station_id,
                NetworkEdge.length_m,
                NetworkEdge.max_speed_kmh,
                NetworkEdge.elevation_profile,
                NetworkEdge.speed_limit_zones,
                ST_AsGeoJSON(NetworkEdge.geometry).label("edge_geojson"),
            )
            .join(NetworkEdge, NetworkEdge.id == RouteEdge.edge_id)
            .where(
                RouteEdge.route_id.in_(route_ids),
                RouteEdge.direction == "forward",
            )
            .order_by(RouteEdge.route_id, RouteEdge.sequence)
        )

        grouped_segments: dict[int, list[list[list[float]]]] = {}
        grouped_edges: dict[int, list[dict[str, Any]]] = {}
        cumulative_by_route: dict[int, float] = {}
        for row in edge_rows.all():
            geojson = json.loads(row.edge_geojson)
            coords = geojson.get("coordinates", [])
            route_id = int(row.route_id)
            grouped_segments.setdefault(route_id, []).append(coords)
            start_km = cumulative_by_route.get(route_id, 0.0)
            length_km = float(row.length_m or 0.0) / 1000.0
            end_km = start_km + length_km
            cumulative_by_route[route_id] = end_km
            grouped_edges.setdefault(route_id, []).append(
                {
                    "edge_id": int(row.edge_id),
                    "sequence": int(row.sequence),
                    "direction": row.direction,
                    "from_station_id": int(row.from_station_id),
                    "to_station_id": int(row.to_station_id),
                    "length_km": length_km,
                    "max_speed_kmh": row.max_speed_kmh,
                    "elevation_profile": row.elevation_profile or [],
                    "speed_limit_zones": row.speed_limit_zones or [],
                    "start_km": start_km,
                    "end_km": end_km,
                    "coords": coords,
                }
            )

        route_rows = await self.session.execute(
            select(
                Route.id,
                Route.distance_km,
                ST_AsGeoJSON(Route.line_geometry).label("fallback_geojson"),
            ).where(Route.id.in_(route_ids))
        )

        payloads: dict[int, dict[str, Any]] = {}
        for row in route_rows.all():
            route_id = int(row.id)
            coords = self._merge_edge_coordinates(grouped_segments.get(route_id, []))
            if not coords:
                fallback_coords: list = []
                if row.fallback_geojson:
                    fallback_geojson = json.loads(row.fallback_geojson)
                    fallback_coords = fallback_geojson.get("coordinates", [])
                coords = fallback_coords
            distance_km = (
                float(row.distance_km)
                if row.distance_km is not None
                else cumulative_by_route.get(route_id)
            )
            payloads[route_id] = {
                "coords": coords,
                "distance_km": distance_km,
                "geojson": (
                    json.dumps({"type": "LineString", "coordinates": coords})
                    if coords
                    else row.fallback_geojson
                ),
                "segments": grouped_edges.get(route_id, []),
            }
        return payloads

    async def _get_geometry_payloads(
        self,
        route_ids: list[int],
    ) -> dict[int, tuple[list, float | None, str | None]]:
        payloads: dict[int, tuple[list, float | None, str | None]] = {}
        graph_payloads = await self._get_graph_payloads(route_ids)
        for route_id, payload in graph_payloads.items():
            payloads[route_id] = (
                payload["coords"],
                payload["distance_km"],
                payload["geojson"],
            )
        return payloads

    async def get_graph_geometry_bulk(
        self,
        route_ids: list[int],
    ) -> dict[int, dict[str, Any]]:
        if not route_ids:
            return {}

        now = _time.monotonic()
        if now < RouteRepository._geometry_cache_expires:
            cached = {
                rid: RouteRepository._graph_geometry_cache[rid]
                for rid in route_ids
                if rid in RouteRepository._graph_geometry_cache
            }
            missing = [
                rid
                for rid in route_ids
                if rid not in RouteRepository._graph_geometry_cache
            ]
        else:
            RouteRepository._geometry_cache.clear()
            RouteRepository._graph_geometry_cache.clear()
            cached = {}
            missing = list(route_ids)

        if not missing:
            return cached

        fetched = await self._get_graph_payloads(missing)
        RouteRepository._graph_geometry_cache.update(fetched)
        if fetched:
            RouteRepository._geometry_cache_expires = (
                now + RouteRepository._GEOMETRY_CACHE_TTL
            )

        return {**cached, **fetched}

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
            select(Route)
            .options(
                selectinload(Route.route_stations).selectinload(RouteStation.station)
            )
            .order_by(Route.id)
            .offset(skip)
            .limit(limit)
        )
        routes = list(result.scalars().all())
        if not routes:
            return []

        payloads = await self._get_geometry_payloads([route.id for route in routes])
        for route in routes:
            route._geojson = payloads.get(route.id, ([], None, None))[2]
        return routes

    async def get_by_id_with_geometry(self, route_id: int) -> Route | None:
        """Get route by ID with GeoJSON geometry and stations.

        Args:
            route_id: Route ID.

        Returns:
            Route with GeoJSON geometry or None.
        """
        result = await self.session.execute(
            select(Route)
            .options(
                selectinload(Route.route_stations).selectinload(RouteStation.station)
            )
            .where(Route.id == route_id)
        )
        route = result.scalar_one_or_none()
        if route is None:
            return None

        payloads = await self._get_geometry_payloads([route_id])
        route._geojson = payloads.get(route_id, ([], None, None))[2]
        return route

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
            missing = [
                rid for rid in route_ids if rid not in RouteRepository._geometry_cache
            ]
        else:
            RouteRepository._geometry_cache.clear()
            cached = {}
            missing = list(route_ids)

        if not missing:
            return cached

        fetched: dict[int, tuple[list, float | None]] = {}
        payloads = await self._get_geometry_payloads(missing)
        for route_id, (coords, distance_km, _) in payloads.items():
            fetched[route_id] = (coords, distance_km)

        RouteRepository._geometry_cache.update(fetched)
        if fetched:
            RouteRepository._geometry_cache_expires = (
                now + RouteRepository._GEOMETRY_CACHE_TTL
            )

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
            select(Route)
            .options(
                selectinload(Route.route_stations).selectinload(RouteStation.station)
            )
            .where(Route.route_type == route_type)
            .order_by(Route.id)
            .offset(skip)
            .limit(limit)
        )
        routes = list(result.scalars().all())
        if not routes:
            return []

        payloads = await self._get_geometry_payloads([route.id for route in routes])
        for route in routes:
            route._geojson = payloads.get(route.id, ([], None, None))[2]
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
