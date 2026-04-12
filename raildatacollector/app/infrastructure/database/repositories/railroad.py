import hashlib
import math
import re

import sqlalchemy as sa
from geoalchemy2 import WKTElement
from geoalchemy2.functions import ST_Distance, ST_LineLocatePoint, ST_X, ST_Y
from geoalchemy2.types import Geography
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.railroad.entities import RouteData, StationData
from app.domain.railroad.repository import RailroadRepository
from app.infrastructure.database.tables import (
    t_route_stations,
    t_routes,
    t_schedules,
    t_stations,
)

logger = get_logger(__name__)

DEFAULT_COLOR = {
    "northern": "#E53935",
    "northeastern": "#1E88E5",
    "western": "#00897B",
    "southern": "#FB8C00",
    "eastern": "#8E24AA",
    "urban": "#43A047",
    "other": "#546E7A",
}


def _make_station_code(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9]", "", name.upper())
    if len(clean) <= 5:
        return clean
    suffix = hashlib.md5(clean.encode()).hexdigest()[:2].upper()
    return clean[:3] + suffix


def _approx_distance_km(coords: list[tuple[float, float]]) -> float:
    """Approximate total route length in km (simple degree-based estimation)."""
    total = 0.0
    for i in range(len(coords) - 1):
        dlon = coords[i + 1][0] - coords[i][0]
        dlat = coords[i + 1][1] - coords[i][1]
        total += math.sqrt(dlon**2 + dlat**2) * 111.0
    return total


class SqlRailroadRepository(RailroadRepository):
    """SQLAlchemy 2 + GeoAlchemy2 implementation of the railroad network repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def count_stations(self) -> int:
        result = await self._s.execute(select(func.count()).select_from(t_stations))
        return result.scalar_one() or 0

    async def count_routes(self) -> int:
        result = await self._s.execute(select(func.count()).select_from(t_routes))
        return result.scalar_one() or 0

    async def replace_all(
        self,
        routes: list[RouteData],
        stations: list[StationData],
    ) -> tuple[int, int]:
        # Clear dependent data first (FK order: schedules → route_stations → routes/stations)
        logger.info("Clearing existing railroad data")
        await self._s.execute(delete(t_schedules))
        await self._s.execute(delete(t_route_stations))
        await self._s.execute(delete(t_routes))
        await self._s.execute(delete(t_stations))

        stations_count = await self._insert_stations(stations)
        routes_count = await self._insert_routes(routes)
        return routes_count, stations_count

    async def _insert_stations(self, stations: list[StationData]) -> int:
        station_id_map: dict[str, int] = {}
        seen_codes: set[str] = set()

        for s in stations:
            if s.name in station_id_map:
                continue

            code = _make_station_code(s.name)
            original = code
            counter = 1
            while code in seen_codes:
                code = original[:4] + str(counter)
                counter += 1
            seen_codes.add(code)

            point = WKTElement(f"POINT({s.lon} {s.lat})", srid=4326)
            stmt = (
                pg_insert(t_stations)
                .values(
                    name=s.name,
                    name_th=s.name_th or None,
                    code=code,
                    location=point,
                    source_route_type=s.route_type or None,
                    city=s.district or None,
                    province=s.folder or None,
                    facilities={"parking": False, "toilet": True, "wifi": False},
                )
                .returning(t_stations.c.id)
            )
            row = await self._s.execute(stmt)
            station_id_map[s.name] = row.scalar_one()

        logger.info("Stations inserted", count=len(station_id_map))
        return len(station_id_map)

    async def _insert_routes(self, routes: list[RouteData]) -> int:
        inserted = 0
        for r in routes:
            coord_str = ", ".join(f"{lon} {lat}" for lon, lat in r.coords)
            wkt = f"LINESTRING({coord_str})"
            distance_km = _approx_distance_km(r.coords)

            line_geom = WKTElement(wkt, srid=4326)
            stmt = (
                pg_insert(t_routes)
                .values(
                    name=r.name,
                    name_th=None,
                    route_type=r.route_type,
                    distance_km=round(distance_km, 2),
                    color=r.color or DEFAULT_COLOR.get(r.route_type, "#546E7A"),
                    line_geometry=line_geom,
                )
                .returning(t_routes.c.id)
            )
            result = await self._s.execute(stmt)
            route_id = result.scalar_one()
            inserted += 1
            await self._assign_stations_to_route(route_id, wkt, distance_km, r.coords)

        logger.info("Routes inserted", count=inserted)
        return inserted

    async def _assign_stations_to_route(
        self,
        route_id: int,
        wkt: str,
        distance_km: float,
        coords: list[tuple[float, float]],
    ) -> None:
        min_lon = min(c[0] for c in coords) - 0.5
        max_lon = max(c[0] for c in coords) + 0.5
        min_lat = min(c[1] for c in coords) - 0.5
        max_lat = max(c[1] for c in coords) + 0.5

        line_geom = WKTElement(wkt, srid=4326)

        # Bbox pre-filter + 2 km distance filter
        nearby_stmt = (
            select(t_stations.c.id)
            .where(
                ST_X(t_stations.c.location) >= min_lon,
                ST_X(t_stations.c.location) <= max_lon,
                ST_Y(t_stations.c.location) >= min_lat,
                ST_Y(t_stations.c.location) <= max_lat,
                ST_Distance(
                    sa.cast(t_stations.c.location, Geography()),
                    sa.cast(line_geom, Geography()),
                )
                < 2000,
            )
        )
        nearby_result = await self._s.execute(nearby_stmt)
        nearby_ids = [row[0] for row in nearby_result.fetchall()]
        if not nearby_ids:
            return

        # Order stations by their fractional position along the route
        frac_expr = ST_LineLocatePoint(line_geom, t_stations.c.location)
        ordered_stmt = (
            select(t_stations.c.id, frac_expr.label("frac"))
            .where(t_stations.c.id.in_(nearby_ids))
            .order_by(frac_expr)
        )
        ordered = (await self._s.execute(ordered_stmt)).fetchall()

        for seq, row in enumerate(ordered):
            st_id, frac = row[0], float(row[1])
            dist_from_start = round(frac * distance_km, 2)
            await self._s.execute(
                pg_insert(t_route_stations)
                .values(
                    route_id=route_id,
                    station_id=st_id,
                    sequence=seq,
                    distance_from_start=dist_from_start,
                )
                .on_conflict_do_nothing()
            )

