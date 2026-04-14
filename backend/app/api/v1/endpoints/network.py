"""Network topology API endpoints.

Returns railway graph data (nodes, edges) as GeoJSON FeatureCollections.
All endpoints accept an optional bounding-box filter (min_lon, min_lat,
max_lon, max_lat); when omitted the full dataset is returned.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.dependencies import DBSession
from app.repositories.network import NetworkRepository

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
    session: DBSession,
    min_lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    min_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    max_lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    max_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
) -> dict[str, Any]:
    repo = NetworkRepository(session)
    if all(v is not None for v in (min_lon, min_lat, max_lon, max_lat)):
        features = await repo.get_nodes_in_bbox(
            min_lon, min_lat, max_lon, max_lat  # type: ignore[arg-type]
        )
    else:
        features = await repo.get_all_nodes()
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
    session: DBSession,
    min_lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    min_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    max_lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    max_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    include_synthetic: bool = False,
) -> dict[str, Any]:
    repo = NetworkRepository(session)
    if all(v is not None for v in (min_lon, min_lat, max_lon, max_lat)):
        features = await repo.get_edges_in_bbox(
            min_lon, min_lat, max_lon, max_lat, include_synthetic  # type: ignore[arg-type]
        )
    else:
        features = await repo.get_all_edges(include_synthetic=include_synthetic)
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
async def get_graph(session: DBSession) -> dict[str, Any]:
    repo = NetworkRepository(session)
    adjacency, node_count, edge_count = (
        await repo.get_adjacency_list(),
        await repo.count_nodes(),
        await repo.count_edges(),
    )
    physical_adjacency = await repo.get_adjacency_list(include_synthetic=False)
    return {
        "node_count": node_count,
        "edge_count": edge_count,
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
async def get_topology_metadata(session: DBSession) -> dict[str, Any]:
    repo = NetworkRepository(session)
    metadata = await repo.get_topology_metadata()
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
async def get_route_edges(route_id: int, session: DBSession) -> dict[str, Any]:
    repo = NetworkRepository(session)
    sequence = await repo.get_route_edge_sequence(route_id)
    return {"route_id": route_id, "edges": sequence}
