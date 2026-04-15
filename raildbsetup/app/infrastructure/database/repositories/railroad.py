import hashlib
import math
import re
from typing import TYPE_CHECKING

from geoalchemy2 import WKTElement
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.logging import get_logger
from app.domain.railroad.repository import RailroadRepository
from app.infrastructure.database.tables import (
    t_network_edges,
    t_network_nodes,
    t_route_edges,
    t_route_stations,
    t_routes,
    t_schedules,
    t_station_aliases,
    t_stations,
    t_trains,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.domain.railroad.entities import RouteData, StationData

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
    suffix = (
        hashlib.md5(clean.encode(), usedforsecurity=False).hexdigest()[:2].upper()
    )  # noqa: S324
    return clean[:3] + suffix


def _approx_distance_km(coords: list[tuple[float, float]]) -> float:
    """Approximate total route length in km using the Haversine formula."""
    earth_radius_km = 6371.0
    total = 0.0
    for index in range(len(coords) - 1):
        lon1, lat1 = coords[index]
        lon2, lat2 = coords[index + 1]
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        total += earth_radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return total


class SqlRailroadRepository(RailroadRepository):
    """Persist canonical route and station datasets before graph building."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def count_stations(self) -> int:
        result = await self._s.execute(select(func.count()).select_from(t_stations))
        return result.scalar_one() or 0

    async def count_routes(self) -> int:
        result = await self._s.execute(select(func.count()).select_from(t_routes))
        return result.scalar_one() or 0

    async def replace_routes(self, routes: list[RouteData]) -> int:
        logger.info("Replacing canonical route geometries", routes=len(routes))
        await self._clear_derived_network_data()
        await self._s.execute(delete(t_routes))
        return await self._insert_routes(routes)

    async def replace_stations(self, stations: list[StationData]) -> int:
        logger.info("Replacing canonical station dataset", stations=len(stations))
        await self._s.execute(delete(t_station_aliases))
        await self._s.execute(delete(t_stations))
        return await self._insert_stations(stations)

    async def _clear_derived_network_data(self) -> None:
        await self._s.execute(update(t_schedules).values(route_station_id=None))
        await self._s.execute(update(t_trains).values(current_route_id=None))
        await self._s.execute(
            update(t_stations).values(
                node_id=None,
                snapped_location=None,
                snap_distance_m=None,
            )
        )
        await self._s.execute(delete(t_route_edges))
        await self._s.execute(delete(t_route_stations))
        await self._s.execute(delete(t_network_edges))
        await self._s.execute(delete(t_network_nodes))

    async def _insert_stations(self, stations: list[StationData]) -> int:
        inserted_ids: dict[str, int] = {}
        seen_codes: set[str] = set()

        for station in stations:
            station_key = (station.code or station.name).strip().lower()
            if not station_key or station_key in inserted_ids:
                continue

            base_code = (
                station.code.strip()
                if station.code
                else _make_station_code(station.name)
            )
            code = base_code
            counter = 1
            while code in seen_codes:
                suffix = str(counter)
                code = base_code[: max(1, 5 - len(suffix))] + suffix
                counter += 1
            seen_codes.add(code)

            point = WKTElement(f"POINT({station.lon} {station.lat})", srid=4326)
            stmt = (
                pg_insert(t_stations)
                .values(
                    name=station.name,
                    name_th=station.name_th or None,
                    code=code,
                    station_class=station.station_class or None,
                    source_line=station.source_line or None,
                    location=point,
                    source_route_type=station.route_type or None,
                    city=station.district or None,
                    province=station.folder or None,
                    facilities={"parking": False, "toilet": True, "wifi": False},
                )
                .returning(t_stations.c.id)
            )
            row = await self._s.execute(stmt)
            inserted_ids[station_key] = row.scalar_one()

        logger.info("Stations inserted", count=len(inserted_ids))
        return len(inserted_ids)

    async def _insert_routes(self, routes: list[RouteData]) -> int:
        inserted = 0
        for route in routes:
            coord_str = ", ".join(f"{lon} {lat}" for lon, lat in route.coords)
            line_geom = WKTElement(f"LINESTRING({coord_str})", srid=4326)
            stmt = pg_insert(t_routes).values(
                name=route.name,
                name_th=None,
                source_folder=route.folder or None,
                route_type=route.route_type,
                distance_km=round(_approx_distance_km(route.coords), 2),
                color=route.color or DEFAULT_COLOR.get(route.route_type, "#546E7A"),
                line_geometry=line_geom,
            )
            await self._s.execute(stmt)
            inserted += 1

        logger.info("Routes inserted", count=inserted)
        return inserted
