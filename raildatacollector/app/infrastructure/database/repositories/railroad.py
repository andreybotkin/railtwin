import hashlib
import re

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.railroad.entities import RouteData, StationData
from app.domain.railroad.repository import RailroadRepository

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


class SqlRailroadRepository(RailroadRepository):
    """SQLAlchemy implementation of the railroad network repository.

    Uses raw SQL (via sqlalchemy.text) and PostGIS spatial functions,
    matching the approach used in the original load_kml_data.py script.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def count_stations(self) -> int:
        result = await self._s.execute(sa.text("SELECT COUNT(*) FROM stations"))
        return result.scalar() or 0

    async def count_routes(self) -> int:
        result = await self._s.execute(sa.text("SELECT COUNT(*) FROM routes"))
        return result.scalar() or 0

    async def replace_all(
        self,
        routes: list[RouteData],
        stations: list[StationData],
    ) -> tuple[int, int]:
        # Clear dependent data first; schedules reference stations/route_stations
        logger.info("Clearing existing railroad data")
        await self._s.execute(sa.text("DELETE FROM schedules"))
        await self._s.execute(sa.text("DELETE FROM route_stations"))
        await self._s.execute(sa.text("DELETE FROM routes"))
        await self._s.execute(sa.text("DELETE FROM stations"))

        stations_count = await self._insert_stations(stations)
        routes_count = await self._insert_routes(routes)
        return routes_count, stations_count

    # ---------------------------------------------------------------------- #
    # Private helpers                                                          #
    # ---------------------------------------------------------------------- #

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

            row = await self._s.execute(
                sa.text("""
                    INSERT INTO stations
                        (name, code, location, province, facilities)
                    VALUES (
                        :name, :code,
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                        :province,
                        cast(:facilities AS jsonb)
                    )
                    RETURNING id
                    """),
                {
                    "name": s.name,
                    "code": code,
                    "lon": s.lon,
                    "lat": s.lat,
                    "province": s.folder or None,
                    "facilities": '{"parking": false, "toilet": true, "wifi": false}',
                },
            )
            station_id_map[s.name] = row.scalar_one()

        logger.info("Stations inserted", count=len(station_id_map))
        return len(station_id_map)

    async def _insert_routes(self, routes: list[RouteData]) -> int:
        inserted = 0
        for r in routes:
            coord_str = ", ".join(f"{lon} {lat}" for lon, lat in r.coords)
            wkt = f"LINESTRING({coord_str})"
            distance_km = _approx_distance_km(r.coords)

            row = await self._s.execute(
                sa.text("""
                    INSERT INTO routes
                        (name, name_th, route_type, distance_km, color, line_geometry)
                    VALUES (
                        :name, NULL, :route_type, :distance_km, :color,
                        ST_SetSRID(ST_GeomFromText(:geom), 4326)
                    )
                    RETURNING id
                    """),
                {
                    "name": r.name,
                    "route_type": r.route_type,
                    "distance_km": round(distance_km, 2),
                    "color": r.color or DEFAULT_COLOR.get(r.route_type, "#546E7A"),
                    "geom": wkt,
                },
            )
            route_id = row.scalar_one()
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

        nearby = await self._s.execute(
            sa.text("""
                SELECT id
                FROM stations
                WHERE ST_X(location::geometry) BETWEEN :min_lon AND :max_lon
                  AND ST_Y(location::geometry) BETWEEN :min_lat AND :max_lat
                  AND ST_Distance(
                          location::geography,
                          ST_SetSRID(ST_GeomFromText(:geom), 4326)::geography
                      ) < 2000
                """),
            {
                "geom": wkt,
                "min_lon": min_lon,
                "max_lon": max_lon,
                "min_lat": min_lat,
                "max_lat": max_lat,
            },
        )
        nearby_ids = [row[0] for row in nearby.fetchall()]
        if not nearby_ids:
            return

        ordered = await self._s.execute(
            sa.text("""
                SELECT s.id,
                       ST_LineLocatePoint(
                           ST_SetSRID(ST_GeomFromText(:geom), 4326),
                           s.location::geometry
                       ) AS frac
                FROM stations s
                WHERE s.id = ANY(:ids)
                ORDER BY frac
                """),
            {"geom": wkt, "ids": nearby_ids},
        )
        for seq, row in enumerate(ordered.fetchall()):
            st_id, frac = row[0], float(row[1])
            dist_from_start = round(frac * distance_km, 2)
            await self._s.execute(
                sa.text("""
                    INSERT INTO route_stations
                        (route_id, station_id, sequence, distance_from_start)
                    VALUES (:route_id, :station_id, :sequence, :distance)
                    ON CONFLICT DO NOTHING
                    """),
                {
                    "route_id": route_id,
                    "station_id": st_id,
                    "sequence": seq,
                    "distance": dist_from_start,
                },
            )


def _approx_distance_km(coords: list[tuple[float, float]]) -> float:
    """Crude great-circle approximation using degree-to-km conversion."""
    total = 0.0
    for i in range(1, len(coords)):
        dlon = (coords[i][0] - coords[i - 1][0]) * 111.0 * 0.9
        dlat = (coords[i][1] - coords[i - 1][1]) * 111.0
        total += (dlon**2 + dlat**2) ** 0.5
    return total
