"""Network topology API endpoints.

Returns railway graph data (nodes, edges) as GeoJSON FeatureCollections.
All endpoints accept an optional bounding-box filter (min_lon, min_lat,
max_lon, max_lat); when omitted the full dataset is returned.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.dependencies import get_redis
from app.services.reference_data import RedisReferenceReader

router = APIRouter()


def _feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


@router.get(
    "/nodes",
    summary="Get network nodes",
    description=(
        "Returns railway graph nodes (station vertices) as a GeoJSON "
        "FeatureCollection.  Supply a bounding-box to limit results."
    ),
)
async def get_nodes(
    min_lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    min_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    max_lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    max_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
) -> dict[str, Any]:
    reader = RedisReferenceReader(get_redis())
    features = await reader.get_network_nodes()
    if all(v is not None for v in (min_lon, min_lat, max_lon, max_lat)):
        features = [
            feature
            for feature in features
            if _in_bbox(feature.get("geometry", {}), min_lon, min_lat, max_lon, max_lat)  # type: ignore[arg-type]
        ]
    return _feature_collection(features)


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


@router.get(
    "/edges",
    summary="Get network edges",
    description=(
        "Returns directed station-to-station railway edges as a GeoJSON "
        "FeatureCollection. Each feature includes both node IDs and station IDs, "
        "while the geometry stores the detailed track segment between them."
    ),
)
async def get_edges(
    min_lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    min_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    max_lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    max_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    include_synthetic: bool = False,
) -> dict[str, Any]:
    reader = RedisReferenceReader(get_redis())
    features = await reader.get_network_edges()
    if not include_synthetic:
        features = [
            feature
            for feature in features
            if feature.get("properties", {}).get("edge_kind") == "track"
        ]
    if all(v is not None for v in (min_lon, min_lat, max_lon, max_lat)):
        features = [
            feature
            for feature in features
            if _in_bbox(feature.get("geometry", {}), min_lon, min_lat, max_lon, max_lat)  # type: ignore[arg-type]
        ]
    return _feature_collection(features)


# ---------------------------------------------------------------------------
# Full graph (adjacency + stats)
# ---------------------------------------------------------------------------


@router.get(
    "/graph",
    summary="Get network graph summary",
    description=(
        "Returns the full directed adjacency list together with node/edge counts. "
        "Use this to build client-side graph structures for pathfinding."
    ),
)
async def get_graph() -> dict[str, Any]:
    reader = RedisReferenceReader(get_redis())
    adjacency = await reader.get_adjacency()
    physical_adjacency = await reader.get_adjacency(include_synthetic=False)
    nodes = await reader.get_network_nodes()
    edges = await reader.get_network_edges()
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "physical_edge_count": sum(len(v) for v in physical_adjacency.values()),
        "adjacency": {str(k): v for k, v in adjacency.items()},
        "physical_adjacency": {str(k): v for k, v in physical_adjacency.items()},
    }


@router.get(
    "/metadata",
    summary="Get topology metadata",
    description=(
        "Returns the latest topology build metadata, including graph version, "
        "component counts and station snapping diagnostics."
    ),
)
async def get_topology_metadata() -> dict[str, Any]:
    reader = RedisReferenceReader(get_redis())
    metadata = await reader.get_topology()
    if metadata is None:
        return {"status": "missing"}
    return metadata


# ---------------------------------------------------------------------------
# Route edge sequence
# ---------------------------------------------------------------------------


@router.get(
    "/routes/{route_id}/edges",
    summary="Get edge sequence for a route",
    description=(
        "Returns the ordered list of network edge IDs that make up the given "
        "route, together with their direction (forward/reverse)."
    ),
)
async def get_route_edges(route_id: int) -> dict[str, Any]:
    reader = RedisReferenceReader(get_redis())
    sequence = await reader.get_route_edges(route_id)
    return {"route_id": route_id, "edges": sequence}


def _geometry_bounds(
    geometry: dict[str, Any],
) -> tuple[float, float, float, float] | None:
    coordinates = geometry.get("coordinates")
    geometry_type = geometry.get("type")
    if (
        geometry_type == "Point"
        and isinstance(coordinates, list)
        and len(coordinates) >= 2
    ):
        lon = float(coordinates[0])
        lat = float(coordinates[1])
        return lon, lat, lon, lat
    if (
        geometry_type != "LineString"
        or not isinstance(coordinates, list)
        or not coordinates
    ):
        return None
    lons = [
        float(coord[0])
        for coord in coordinates
        if isinstance(coord, list) and len(coord) >= 2
    ]
    lats = [
        float(coord[1])
        for coord in coordinates
        if isinstance(coord, list) and len(coord) >= 2
    ]
    if not lons or not lats:
        return None
    return min(lons), min(lats), max(lons), max(lats)


def _in_bbox(
    geometry: dict[str, Any],
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
) -> bool:
    bounds = _geometry_bounds(geometry)
    if bounds is None:
        return False
    geom_min_lon, geom_min_lat, geom_max_lon, geom_max_lat = bounds
    return not (
        geom_max_lon < min_lon
        or geom_min_lon > max_lon
        or geom_max_lat < min_lat
        or geom_min_lat > max_lat
    )
