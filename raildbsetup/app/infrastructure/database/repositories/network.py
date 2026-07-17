from datetime import UTC, datetime
from typing import Any

from geoalchemy2 import WKTElement
from geoalchemy2.functions import ST_AsText, ST_Length, ST_LineSubstring, ST_Reverse
from geoalchemy2.types import Geography
from sqlalchemy import Float, cast, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.railroad.network_entities import NetworkTopologyResult
from app.domain.railroad.network_repository import NetworkRepository
from app.infrastructure.database.tables import (
    t_network_edges,
    t_network_links,
    t_network_nodes,
    t_route_edges,
    t_route_stations,
    t_routes,
    t_stations,
    t_topology_metadata,
)

logger = get_logger(__name__)


class SqlNetworkRepository(NetworkRepository):
    """Build a station-only rail graph from route geometry and station locations."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def count_nodes(self) -> int:
        result = await self._s.execute(
            select(func.count()).select_from(t_network_nodes)
        )
        return result.scalar_one() or 0

    async def count_edges(self) -> int:
        result = await self._s.execute(
            select(func.count()).select_from(t_network_edges)
        )
        return result.scalar_one() or 0

    async def count_route_stations(self) -> int:
        result = await self._s.execute(
            select(func.count()).select_from(t_route_stations)
        )
        return result.scalar_one() or 0

    async def build_topology(
        self,
        snap_distance_m: float = 500.0,
    ) -> NetworkTopologyResult:
        try:
            return await self._build(snap_distance_m)
        except Exception as exc:
            await self._s.rollback()
            logger.error("Topology build failed with exception", error=str(exc))
            return NetworkTopologyResult(error=str(exc))

    async def _build(self, snap_distance_m: float) -> NetworkTopologyResult:
        await self._clear_topology()
        unsnapped_stations, max_snap_distance_m = await self._create_station_nodes(
            snap_distance_m
        )
        await self._rebuild_routes_from_station_graph(snap_distance_m)

        nodes_count = await self.count_nodes()
        edges_count = await self.count_edges()
        snapped_count = await self._count_snapped_stations()
        (
            component_count,
            main_component_station_count,
            disconnected_station_count,
        ) = await self._compute_and_store_components()
        await self._persist_topology_metadata(
            nodes_count=nodes_count,
            edges_count=edges_count,
            snapped_count=snapped_count,
            unsnapped_count=len(unsnapped_stations),
            max_snap_distance_m=max_snap_distance_m,
            component_count=component_count,
            main_component_station_count=main_component_station_count,
            disconnected_station_count=disconnected_station_count,
        )

        logger.info(
            "Topology complete",
            nodes=nodes_count,
            edges=edges_count,
            snapped=snapped_count,
            unsnapped=len(unsnapped_stations),
        )
        return NetworkTopologyResult(
            nodes_count=nodes_count,
            edges_count=edges_count,
            snapped_count=snapped_count,
            physical_component_count=component_count,
            station_component_count=component_count,
            main_component_station_count=main_component_station_count,
            disconnected_station_count=disconnected_station_count,
            max_snap_distance_m=max_snap_distance_m,
            unsnapped_stations=unsnapped_stations[:50],
        )

    async def _clear_topology(self) -> None:
        await self._s.execute(
            update(t_stations).values(
                node_id=None,
                snapped_location=None,
                snap_distance_m=None,
            )
        )
        await self._s.execute(delete(t_route_stations))
        await self._s.execute(delete(t_route_edges))
        await self._s.execute(delete(t_topology_metadata))
        await self._s.execute(delete(t_network_links))
        await self._s.execute(delete(t_network_edges))
        await self._s.execute(delete(t_network_nodes))

    async def _create_station_nodes(
        self,
        snap_distance_m: float,
    ) -> tuple[list[str], float | None]:
        stations_stmt = select(
            t_stations.c.id,
            t_stations.c.name,
            t_stations.c.source_route_type,
            ST_AsText(t_stations.c.location).label("location_wkt"),
        ).order_by(t_stations.c.id)
        stations = (await self._s.execute(stations_stmt)).fetchall()

        unsnapped: list[str] = []
        max_snap_distance_m = 0.0
        snapped_any_station = False

        for station in stations:
            station_id = int(station.id)
            station_name = str(station.name)
            location_wkt = str(station.location_wkt)
            source_route_type = (
                str(station.source_route_type) if station.source_route_type else None
            )

            preferred_route = await self._find_preferred_route(
                location_wkt, source_route_type
            )
            node_location_wkt = location_wkt
            update_values: dict[str, Any] = {}

            if preferred_route is None:
                unsnapped.append(station_name)
            else:
                distance_m = float(preferred_route.dist_m or 0.0)
                if distance_m > snap_distance_m:
                    unsnapped.append(station_name)
                    logger.warning(
                        "Station is too far from any route geometry; keeping original station location",
                        station=station_name,
                        distance_m=round(distance_m, 2),
                        warning_threshold_m=snap_distance_m,
                    )
                else:
                    snapped_any_station = True
                    max_snap_distance_m = max(max_snap_distance_m, distance_m)
                    node_location_wkt = str(preferred_route.snapped_wkt)
                    update_values["snapped_location"] = WKTElement(
                        node_location_wkt, srid=4326
                    )
                    update_values["snap_distance_m"] = distance_m

            node_id = await self._create_station_node(station_id, node_location_wkt)
            update_values["node_id"] = node_id

            await self._s.execute(
                update(t_stations)
                .where(t_stations.c.id == station_id)
                .values(**update_values)
            )

        return unsnapped, max_snap_distance_m if snapped_any_station else None

    async def _create_station_node(self, station_id: int, point_wkt: str) -> int:
        stmt = (
            pg_insert(t_network_nodes)
            .values(
                location=WKTElement(point_wkt, srid=4326),
                node_type="station",
                station_id=station_id,
            )
            .returning(t_network_nodes.c.id)
        )
        return int((await self._s.execute(stmt)).scalar_one())

    async def _find_preferred_route(
        self,
        point_wkt: str,
        source_route_type: str | None,
    ) -> Any | None:
        point = WKTElement(point_wkt, srid=4326)
        distance_expr = cast(
            func.ST_Distance(
                cast(t_routes.c.line_geometry, Geography()),
                cast(point, Geography()),
            ),
            Float,
        )

        async def _query(route_type: str | None) -> Any | None:
            stmt = (
                select(
                    t_routes.c.id.label("route_id"),
                    t_routes.c.route_type,
                    ST_AsText(t_routes.c.line_geometry).label("geom_wkt"),
                    ST_AsText(
                        func.ST_ClosestPoint(t_routes.c.line_geometry, point)
                    ).label("snapped_wkt"),
                    distance_expr.label("dist_m"),
                )
                .where(t_routes.c.line_geometry.isnot(None))
                .order_by(distance_expr, t_routes.c.id)
                .limit(1)
            )
            if route_type:
                stmt = stmt.where(t_routes.c.route_type == route_type)
            return (await self._s.execute(stmt)).first()

        normalized = (source_route_type or "").strip().lower()
        if normalized and normalized != "other":
            preferred = await _query(normalized)
            if preferred is not None:
                return preferred
        return await _query(None)

    async def _rebuild_routes_from_station_graph(self, snap_distance_m: float) -> None:
        await self._s.execute(delete(t_route_edges))
        await self._s.execute(delete(t_route_stations))

        routes_stmt = (
            select(
                t_routes.c.id,
                t_routes.c.name,
                t_routes.c.route_type,
                ST_AsText(t_routes.c.line_geometry).label("geom_wkt"),
            )
            .where(t_routes.c.line_geometry.isnot(None))
            .order_by(t_routes.c.id)
        )
        routes = (await self._s.execute(routes_stmt)).fetchall()

        for route in routes:
            route_id = int(route.id)
            route_name = str(route.name)
            route_type = str(route.route_type)
            route_geom_wkt = str(route.geom_wkt)

            route_length_m = await self._measure_geometry(route_geom_wkt)
            station_rows = await self._get_route_station_rows(
                route_geom_wkt=route_geom_wkt,
                route_type=route_type,
                snap_distance_m=snap_distance_m,
            )
            if not station_rows:
                logger.warning(
                    "Route produced no station sequence",
                    route_id=route_id,
                    route=route_name,
                )
                continue

            route_station_rows, route_edge_rows = await self._build_route_rows(
                route_id=route_id,
                route_name=route_name,
                route_type=route_type,
                route_geom_wkt=route_geom_wkt,
                route_length_m=route_length_m,
                station_rows=station_rows,
            )

            if route_edge_rows:
                await self._s.execute(pg_insert(t_route_edges), route_edge_rows)
            if route_station_rows:
                await self._s.execute(pg_insert(t_route_stations), route_station_rows)

            await self._s.execute(
                update(t_routes)
                .where(t_routes.c.id == route_id)
                .values(distance_km=round(route_length_m / 1000.0, 3))
            )

    async def _get_route_station_rows(
        self,
        *,
        route_geom_wkt: str,
        route_type: str,
        snap_distance_m: float,
    ) -> list[dict[str, Any]]:
        route_geom = WKTElement(route_geom_wkt, srid=4326)
        closest_point = func.ST_ClosestPoint(route_geom, t_stations.c.location)
        route_fraction = cast(func.ST_LineLocatePoint(route_geom, closest_point), Float)
        route_distance = cast(
            func.ST_Distance(
                cast(t_stations.c.location, Geography()),
                cast(closest_point, Geography()),
            ),
            Float,
        )
        stmt = (
            select(
                t_stations.c.id,
                t_stations.c.node_id,
                ST_AsText(closest_point).label("snapped_wkt"),
                route_distance.label("snap_distance_m"),
                route_fraction.label("route_fraction"),
            )
            .where(
                t_stations.c.node_id.isnot(None),
                func.ST_DWithin(
                    cast(t_stations.c.location, Geography()),
                    cast(route_geom, Geography()),
                    snap_distance_m,
                ),
            )
            .order_by(route_fraction, t_stations.c.id)
        )
        if route_type and route_type != "other":
            stmt = stmt.where(
                (t_stations.c.source_route_type == route_type)
                | (t_stations.c.source_route_type == "other")
                | (t_stations.c.source_route_type.is_(None))
            )

        rows = (await self._s.execute(stmt)).fetchall()
        station_rows: list[dict[str, Any]] = []
        seen_station_ids: set[int] = set()
        for row in rows:
            station_id = int(row.id)
            if (
                station_id in seen_station_ids
                or row.snapped_wkt is None
                or row.node_id is None
            ):
                continue
            seen_station_ids.add(station_id)
            fraction = max(0.0, min(1.0, float(row.route_fraction or 0.0)))
            if station_rows and fraction < station_rows[-1]["fraction"]:
                continue
            station_rows.append(
                {
                    "station_id": station_id,
                    "node_id": int(row.node_id),
                    "snapped_wkt": str(row.snapped_wkt),
                    "snap_distance_m": float(row.snap_distance_m or 0.0),
                    "fraction": fraction,
                }
            )
        return station_rows

    async def _build_route_rows(
        self,
        *,
        route_id: int,
        route_name: str,
        route_type: str,
        route_geom_wkt: str,
        route_length_m: float,
        station_rows: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        route_station_rows: list[dict[str, Any]] = []
        route_edge_rows: list[dict[str, Any]] = []
        edge_sequence = 0

        previous_row: dict[str, Any] | None = None
        for current_row in station_rows:
            edge_id: int | None = None
            if previous_row is not None:
                edge_id = await self._upsert_station_edge_pair(
                    route_name=route_name,
                    route_type=route_type,
                    route_geom_wkt=route_geom_wkt,
                    from_row=previous_row,
                    to_row=current_row,
                )
                if edge_id is not None:
                    route_edge_rows.append(
                        {
                            "route_id": route_id,
                            "edge_id": edge_id,
                            "sequence": edge_sequence,
                            "direction": "forward",
                        }
                    )
                    edge_sequence += 1

            route_station_rows.append(
                {
                    "route_id": route_id,
                    "station_id": current_row["station_id"],
                    "node_id": current_row["node_id"],
                    "sequence": len(route_station_rows),
                    "distance_from_start": round(
                        (route_length_m * current_row["fraction"]) / 1000.0,
                        3,
                    ),
                    "edge_id": edge_id,
                    "snapped_location": WKTElement(
                        current_row["snapped_wkt"], srid=4326
                    ),
                    "snap_distance_m": current_row["snap_distance_m"],
                }
            )
            previous_row = current_row

        return route_station_rows, route_edge_rows

    async def _upsert_station_edge_pair(
        self,
        *,
        route_name: str,
        route_type: str,
        route_geom_wkt: str,
        from_row: dict[str, Any],
        to_row: dict[str, Any],
    ) -> int | None:
        if from_row["station_id"] == to_row["station_id"]:
            return None

        start_fraction = float(from_row["fraction"])
        end_fraction = float(to_row["fraction"])
        if end_fraction <= start_fraction + settings.topology_fraction_epsilon:
            return None

        segment_wkt = await self._extract_route_segment(
            route_geom_wkt,
            start_fraction,
            end_fraction,
        )
        if segment_wkt is None:
            return None

        forward_edge_id = await self._upsert_edge_record(
            from_node_id=int(from_row["node_id"]),
            to_node_id=int(to_row["node_id"]),
            from_station_id=int(from_row["station_id"]),
            to_station_id=int(to_row["station_id"]),
            geom_wkt=segment_wkt,
            route_type=route_type,
            line_name=route_name,
        )

        reverse_wkt = await self._reverse_geometry(segment_wkt)
        await self._upsert_edge_record(
            from_node_id=int(to_row["node_id"]),
            to_node_id=int(from_row["node_id"]),
            from_station_id=int(to_row["station_id"]),
            to_station_id=int(from_row["station_id"]),
            geom_wkt=reverse_wkt,
            route_type=route_type,
            line_name=route_name,
        )

        return forward_edge_id

    async def _upsert_edge_record(
        self,
        *,
        from_node_id: int,
        to_node_id: int,
        from_station_id: int,
        to_station_id: int,
        geom_wkt: str,
        route_type: str,
        line_name: str,
    ) -> int:
        geometry = WKTElement(geom_wkt, srid=4326)
        length_m = await self._measure_geometry(geom_wkt)
        insert_stmt = (
            pg_insert(t_network_edges)
            .values(
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                from_station_id=from_station_id,
                to_station_id=to_station_id,
                geometry=geometry,
                length_m=round(length_m, 2),
                edge_kind="track",
                route_type=route_type,
                line_name=line_name,
            )
            .on_conflict_do_nothing(constraint="uq_network_edges_station_ids_directed")
            .returning(t_network_edges.c.id)
        )
        inserted_id = (await self._s.execute(insert_stmt)).scalar_one_or_none()
        if inserted_id is not None:
            return int(inserted_id)

        existing_stmt = select(t_network_edges.c.id).where(
            t_network_edges.c.from_station_id == from_station_id,
            t_network_edges.c.to_station_id == to_station_id,
        )
        return int((await self._s.execute(existing_stmt)).scalar_one())

    async def _extract_route_segment(
        self,
        route_geom_wkt: str,
        start_fraction: float,
        end_fraction: float,
    ) -> str | None:
        route_geom = WKTElement(route_geom_wkt, srid=4326)
        stmt = select(
            ST_AsText(
                ST_LineSubstring(
                    route_geom,
                    start_fraction,
                    end_fraction,
                )
            ).label("segment_wkt")
        )
        segment_wkt = (await self._s.execute(stmt)).scalar_one_or_none()
        if segment_wkt in {None, "LINESTRING EMPTY"}:
            return None
        return str(segment_wkt)

    async def _reverse_geometry(self, geom_wkt: str) -> str:
        geometry = WKTElement(geom_wkt, srid=4326)
        stmt = select(ST_AsText(ST_Reverse(geometry)))
        return str((await self._s.execute(stmt)).scalar_one())

    async def _measure_geometry(self, geom_wkt: str) -> float:
        geometry = WKTElement(geom_wkt, srid=4326)
        stmt = select(cast(ST_Length(cast(geometry, Geography())), Float))
        return float((await self._s.execute(stmt)).scalar_one_or_none() or 0.0)

    async def _count_snapped_stations(self) -> int:
        result = await self._s.execute(
            select(func.count())
            .select_from(t_stations)
            .where(t_stations.c.snapped_location.isnot(None))
        )
        return result.scalar_one() or 0

    async def _compute_and_store_components(self) -> tuple[int, int, int]:
        """Compute undirected station-graph components and persist their IDs."""

        node_rows = (
            await self._s.execute(
                select(t_network_nodes.c.id, t_network_nodes.c.station_id)
            )
        ).fetchall()
        edge_rows = (
            await self._s.execute(
                select(
                    t_network_edges.c.id,
                    t_network_edges.c.from_node_id,
                    t_network_edges.c.to_node_id,
                )
            )
        ).fetchall()
        parent = {int(row.id): int(row.id) for row in node_rows}

        def find(node_id: int) -> int:
            while parent[node_id] != node_id:
                parent[node_id] = parent[parent[node_id]]
                node_id = parent[node_id]
            return node_id

        def union(left: int, right: int) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        for edge in edge_rows:
            left, right = int(edge.from_node_id), int(edge.to_node_id)
            if left in parent and right in parent:
                union(left, right)

        members: dict[int, list[int]] = {}
        for node_id in parent:
            members.setdefault(find(node_id), []).append(node_id)
        ordered = sorted(members.values(), key=lambda group: (-len(group), min(group)))
        component_by_node = {
            node_id: component_id
            for component_id, group in enumerate(ordered, start=1)
            for node_id in group
        }
        for node_id, component_id in component_by_node.items():
            await self._s.execute(
                update(t_network_nodes)
                .where(t_network_nodes.c.id == node_id)
                .values(component_id=component_id)
            )
        for edge in edge_rows:
            component_id = component_by_node.get(int(edge.from_node_id))
            await self._s.execute(
                update(t_network_edges)
                .where(t_network_edges.c.id == int(edge.id))
                .values(component_id=component_id)
            )
        main_count = len(ordered[0]) if ordered else 0
        return len(ordered), main_count, max(0, len(node_rows) - main_count)

    async def _persist_topology_metadata(
        self,
        *,
        nodes_count: int,
        edges_count: int,
        snapped_count: int,
        unsnapped_count: int,
        max_snap_distance_m: float | None,
        component_count: int,
        main_component_station_count: int,
        disconnected_station_count: int,
    ) -> None:
        topology_version = (
            f"station-nodes-{nodes_count}-station-edges-{edges_count}"
            f"-stations-{snapped_count}-components-{component_count}"
        )
        await self._s.execute(
            pg_insert(t_topology_metadata).values(
                topology_version=topology_version,
                physical_nodes_count=nodes_count,
                physical_edges_count=edges_count,
                station_nodes_count=nodes_count,
                physical_components_count=component_count,
                station_components_count=component_count,
                operational_links_count=0,
                main_component_station_count=main_component_station_count,
                disconnected_station_count=disconnected_station_count,
                unsnapped_station_count=unsnapped_count,
                max_snap_distance_m=max_snap_distance_m,
                built_at=datetime.now(UTC),
            )
        )
