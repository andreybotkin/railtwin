"""Network repository for railway topology graph queries.

Provides PostGIS-backed methods to fetch network nodes, edges, and
the full adjacency list from the topology built by raildbsetup.
"""

import json
from typing import Any

from geoalchemy2.functions import ST_AsGeoJSON, ST_MakeEnvelope
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database.models import (
    NetworkEdge,
    NetworkLink,
    NetworkNode,
    RouteEdge,
    TopologyMetadata,
)
from app.repositories.base import BaseRepository


class NetworkRepository(BaseRepository[NetworkEdge]):
    """Repository for railway network topology queries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(NetworkEdge, session)

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    async def get_edges_in_bbox(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        include_synthetic: bool = False,
    ) -> list[dict[str, Any]]:
        """Return edges whose geometry intersects the given bounding box.

        The result is a list of GeoJSON Feature dicts ready to be placed
        inside a FeatureCollection.
        """
        bbox = ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
        stmt = (
            select(
                NetworkEdge.id,
                NetworkEdge.from_node_id,
                NetworkEdge.to_node_id,
                NetworkEdge.from_station_id,
                NetworkEdge.to_station_id,
                NetworkEdge.length_m,
                NetworkEdge.edge_kind,
                NetworkEdge.component_id,
                NetworkEdge.route_type,
                NetworkEdge.line_name,
                NetworkEdge.max_speed_kmh,
                ST_AsGeoJSON(NetworkEdge.geometry).label("geojson"),
            )
            .where(
                func.ST_Intersects(NetworkEdge.geometry, bbox),
            )
            .order_by(NetworkEdge.id)
        )
        if not include_synthetic:
            stmt = stmt.where(NetworkEdge.edge_kind == "track")
        rows = (await self.session.execute(stmt)).all()
        features: list[dict[str, Any]] = []
        for row in rows:
            features.append(
                {
                    "type": "Feature",
                    "id": row.id,
                    "geometry": json.loads(row.geojson),
                    "properties": {
                        "from_node_id": row.from_node_id,
                        "to_node_id": row.to_node_id,
                        "from_station_id": row.from_station_id,
                        "to_station_id": row.to_station_id,
                        "length_m": float(row.length_m) if row.length_m else None,
                        "edge_kind": row.edge_kind,
                        "component_id": row.component_id,
                        "route_type": row.route_type,
                        "line_name": row.line_name,
                        "max_speed_kmh": row.max_speed_kmh,
                    },
                }
            )
        if include_synthetic:
            link_rows = (
                await self.session.execute(
                    select(
                        NetworkLink.id,
                        NetworkLink.from_node_id,
                        NetworkLink.to_node_id,
                        NetworkLink.length_m,
                        NetworkLink.link_kind,
                        NetworkLink.from_component_id,
                        NetworkLink.to_component_id,
                        NetworkLink.notes,
                        ST_AsGeoJSON(NetworkLink.geometry).label("geojson"),
                    )
                    .where(func.ST_Intersects(NetworkLink.geometry, bbox))
                    .order_by(NetworkLink.id)
                )
            ).all()
            for row in link_rows:
                features.append(
                    {
                        "type": "Feature",
                        "id": f"link-{row.id}",
                        "geometry": json.loads(row.geojson),
                        "properties": {
                            "from_node_id": row.from_node_id,
                            "to_node_id": row.to_node_id,
                            "length_m": float(row.length_m) if row.length_m else None,
                            "edge_kind": row.link_kind,
                            "component_id": None,
                            "route_type": None,
                            "line_name": row.notes,
                            "from_component_id": row.from_component_id,
                            "to_component_id": row.to_component_id,
                        },
                    }
                )
        return features

    async def get_all_edges(
        self, include_synthetic: bool = False
    ) -> list[dict[str, Any]]:
        """Return all edges as GeoJSON Feature dicts (for small networks)."""
        stmt = select(
            NetworkEdge.id,
            NetworkEdge.from_node_id,
            NetworkEdge.to_node_id,
            NetworkEdge.from_station_id,
            NetworkEdge.to_station_id,
            NetworkEdge.length_m,
            NetworkEdge.edge_kind,
            NetworkEdge.component_id,
            NetworkEdge.route_type,
            NetworkEdge.line_name,
            NetworkEdge.max_speed_kmh,
            ST_AsGeoJSON(NetworkEdge.geometry).label("geojson"),
        ).order_by(NetworkEdge.id)
        if not include_synthetic:
            stmt = stmt.where(NetworkEdge.edge_kind == "track")
        rows = (await self.session.execute(stmt)).all()
        features: list[dict[str, Any]] = []
        for row in rows:
            features.append(
                {
                    "type": "Feature",
                    "id": row.id,
                    "geometry": json.loads(row.geojson),
                    "properties": {
                        "from_node_id": row.from_node_id,
                        "to_node_id": row.to_node_id,
                        "from_station_id": row.from_station_id,
                        "to_station_id": row.to_station_id,
                        "length_m": float(row.length_m) if row.length_m else None,
                        "edge_kind": row.edge_kind,
                        "component_id": row.component_id,
                        "route_type": row.route_type,
                        "line_name": row.line_name,
                        "max_speed_kmh": row.max_speed_kmh,
                    },
                }
            )
        if include_synthetic:
            link_rows = (
                await self.session.execute(
                    select(
                        NetworkLink.id,
                        NetworkLink.from_node_id,
                        NetworkLink.to_node_id,
                        NetworkLink.length_m,
                        NetworkLink.link_kind,
                        NetworkLink.from_component_id,
                        NetworkLink.to_component_id,
                        NetworkLink.notes,
                        ST_AsGeoJSON(NetworkLink.geometry).label("geojson"),
                    ).order_by(NetworkLink.id)
                )
            ).all()
            for row in link_rows:
                features.append(
                    {
                        "type": "Feature",
                        "id": f"link-{row.id}",
                        "geometry": json.loads(row.geojson),
                        "properties": {
                            "from_node_id": row.from_node_id,
                            "to_node_id": row.to_node_id,
                            "length_m": float(row.length_m) if row.length_m else None,
                            "edge_kind": row.link_kind,
                            "component_id": None,
                            "route_type": None,
                            "line_name": row.notes,
                            "from_component_id": row.from_component_id,
                            "to_component_id": row.to_component_id,
                        },
                    }
                )
        return features

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    async def get_nodes_in_bbox(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
    ) -> list[dict[str, Any]]:
        """Return nodes inside the given bounding box as GeoJSON Features."""
        bbox = ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
        stmt = (
            select(
                NetworkNode.id,
                NetworkNode.node_type,
                NetworkNode.station_id,
                NetworkNode.component_id,
                ST_AsGeoJSON(NetworkNode.location).label("geojson"),
            )
            .where(func.ST_Within(NetworkNode.location, bbox))
            .order_by(NetworkNode.id)
        )
        rows = (await self.session.execute(stmt)).all()
        features: list[dict[str, Any]] = []
        for row in rows:
            features.append(
                {
                    "type": "Feature",
                    "id": row.id,
                    "geometry": json.loads(row.geojson),
                    "properties": {
                        "node_type": row.node_type,
                        "station_id": row.station_id,
                        "component_id": row.component_id,
                    },
                }
            )
        return features

    async def get_all_nodes(self) -> list[dict[str, Any]]:
        """Return all nodes as GeoJSON Feature dicts."""
        stmt = select(
            NetworkNode.id,
            NetworkNode.node_type,
            NetworkNode.station_id,
            NetworkNode.component_id,
            ST_AsGeoJSON(NetworkNode.location).label("geojson"),
        ).order_by(NetworkNode.id)
        rows = (await self.session.execute(stmt)).all()
        features: list[dict[str, Any]] = []
        for row in rows:
            features.append(
                {
                    "type": "Feature",
                    "id": row.id,
                    "geometry": json.loads(row.geojson),
                    "properties": {
                        "node_type": row.node_type,
                        "station_id": row.station_id,
                        "component_id": row.component_id,
                    },
                }
            )
        return features

    # ------------------------------------------------------------------
    # Graph / adjacency
    # ------------------------------------------------------------------

    async def get_adjacency_list(
        self, include_synthetic: bool = True
    ) -> dict[int, list[int]]:
        """Return the full directed adjacency list: {node_id: [neighbour_ids]}."""
        stmt = select(NetworkEdge.from_node_id, NetworkEdge.to_node_id)
        rows = (await self.session.execute(stmt)).all()
        adj: dict[int, list[int]] = {}
        for row in rows:
            adj.setdefault(row.from_node_id, []).append(row.to_node_id)
        if include_synthetic:
            link_rows = (
                await self.session.execute(
                    select(NetworkLink.from_node_id, NetworkLink.to_node_id)
                )
            ).all()
            for row in link_rows:
                adj.setdefault(row.from_node_id, []).append(row.to_node_id)
        return adj

    async def get_topology_metadata(self) -> dict[str, Any] | None:
        row = (
            await self.session.execute(
                select(TopologyMetadata)
                .order_by(TopologyMetadata.built_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "topology_version": row.topology_version,
            "physical_nodes_count": row.physical_nodes_count,
            "physical_edges_count": row.physical_edges_count,
            "station_nodes_count": row.station_nodes_count,
            "physical_components_count": row.physical_components_count,
            "station_components_count": row.station_components_count,
            "operational_links_count": row.operational_links_count,
            "main_component_station_count": row.main_component_station_count,
            "disconnected_station_count": row.disconnected_station_count,
            "unsnapped_station_count": row.unsnapped_station_count,
            "max_snap_distance_m": (
                float(row.max_snap_distance_m)
                if row.max_snap_distance_m is not None
                else None
            ),
            "built_at": row.built_at.isoformat(),
        }

    async def get_route_edge_sequence(self, route_id: int) -> list[dict[str, Any]]:
        """Return the ordered sequence of edge IDs for a given route."""
        stmt = (
            select(RouteEdge.sequence, RouteEdge.edge_id, RouteEdge.direction)
            .where(RouteEdge.route_id == route_id)
            .order_by(RouteEdge.sequence)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            {"sequence": r.sequence, "edge_id": r.edge_id, "direction": r.direction}
            for r in rows
        ]

    async def count_nodes(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(NetworkNode)
        )
        return result.scalar_one()

    async def count_edges(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(NetworkEdge)
        )
        return result.scalar_one()
