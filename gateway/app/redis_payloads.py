"""Redis read helpers + viewport-filtering utilities.

The gateway is a thin consumer of Redis keys populated by the simulation's
:class:`app.services.position_cache.PositionCacheUpdater`.  All wire formats
are documented in :mod:`app.schemas`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from app.schemas import TopologyMetadata

if TYPE_CHECKING:
    from redis.asyncio import Redis

REDIS_TRAJECTORIES_KEY = "train:trajectories:latest"
REDIS_TRAJECTORY_KEY_PREFIX = "train:trajectory:"
REDIS_STOPSEQUENCE_KEY_PREFIX = "train:stopsequence:"
REDIS_TOPOLOGY_METADATA_KEY = "system:topology:metadata"
REDIS_MAP_STATIONS_KEY = "map:stations:all"
REDIS_MAP_NETWORK_EDGES_KEY = "map:network_edges:all"

DEFAULT_VIEWPORT_BUFFER_RATIO = 0.1
DEFAULT_VIEWPORT_MIN_BUFFER_DEGREES = 0.05

type BBox = tuple[float, float, float, float]


# --------------------------------------------------------------------------- #
# Raw Redis readers                                                            #
# --------------------------------------------------------------------------- #


async def read_trajectories(redis_client: Redis | None) -> list[dict[str, Any]]:
    if redis_client is None:
        return []
    raw = await redis_client.get(REDIS_TRAJECTORIES_KEY)
    if not raw:
        return []
    return json.loads(raw)


async def read_individual_trajectory(
    redis_client: Redis | None,
    train_id: int,
) -> dict[str, Any] | None:
    if redis_client is None:
        return None
    raw = await redis_client.get(f"{REDIS_TRAJECTORY_KEY_PREFIX}{train_id}")
    if not raw:
        return None
    return json.loads(raw)


async def read_stopsequence(
    redis_client: Redis | None,
    train_id: int,
) -> list[dict[str, Any]] | None:
    if redis_client is None:
        return None
    raw = await redis_client.get(f"{REDIS_STOPSEQUENCE_KEY_PREFIX}{train_id}")
    if not raw:
        return None
    return json.loads(raw)


async def read_topology_metadata(
    redis_client: Redis | None,
) -> TopologyMetadata | None:
    if redis_client is None:
        return None
    raw = await redis_client.get(REDIS_TOPOLOGY_METADATA_KEY)
    if not raw:
        return None
    return TopologyMetadata.model_validate(json.loads(raw))


async def read_map_stations(redis_client: Redis | None) -> list[dict[str, Any]]:
    if redis_client is None:
        return []
    raw = await redis_client.get(REDIS_MAP_STATIONS_KEY)
    if not raw:
        return []
    return json.loads(raw)


async def read_map_network_edges(redis_client: Redis | None) -> dict[str, Any]:
    if redis_client is None:
        return {"type": "FeatureCollection", "features": []}
    raw = await redis_client.get(REDIS_MAP_NETWORK_EDGES_KEY)
    if not raw:
        return {"type": "FeatureCollection", "features": []}
    return json.loads(raw)


# --------------------------------------------------------------------------- #
# BBox helpers                                                                 #
# --------------------------------------------------------------------------- #


def parse_bbox(bbox: str | None) -> BBox | None:
    if bbox is None:
        return None
    try:
        raw_min_lon, raw_min_lat, raw_max_lon, raw_max_lat = (
            float(value) for value in bbox.split(",")
        )
    except (ValueError, TypeError):
        return None

    min_lon, max_lon = sorted((raw_min_lon, raw_max_lon))
    min_lat, max_lat = sorted((raw_min_lat, raw_max_lat))
    return min_lon, min_lat, max_lon, max_lat


def _expand_bbox(
    bbox: BBox,
    *,
    buffer_ratio: float,
    min_buffer_degrees: float,
) -> BBox:
    min_lon, min_lat, max_lon, max_lat = bbox
    lon_buffer = max((max_lon - min_lon) * buffer_ratio, min_buffer_degrees)
    lat_buffer = max((max_lat - min_lat) * buffer_ratio, min_buffer_degrees)
    return (
        min_lon - lon_buffer,
        min_lat - lat_buffer,
        max_lon + lon_buffer,
        max_lat + lat_buffer,
    )


def _contains_point(bbox: BBox, lon: float, lat: float) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def _bbox_intersects(left: BBox, right: BBox) -> bool:
    left_min_lon, left_min_lat, left_max_lon, left_max_lat = left
    right_min_lon, right_min_lat, right_max_lon, right_max_lat = right
    return not (
        left_max_lon < right_min_lon
        or right_max_lon < left_min_lon
        or left_max_lat < right_min_lat
        or right_max_lat < left_min_lat
    )


def _geometry_bounds(geometry: dict[str, Any]) -> BBox | None:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if geometry_type == "Point" and isinstance(coordinates, list) and len(coordinates) >= 2:
        lon = float(coordinates[0])
        lat = float(coordinates[1])
        return lon, lat, lon, lat

    if geometry_type != "LineString" or not isinstance(coordinates, list) or not coordinates:
        return None

    lons = [float(coord[0]) for coord in coordinates if isinstance(coord, list) and len(coord) >= 2]
    lats = [float(coord[1]) for coord in coordinates if isinstance(coord, list) and len(coord) >= 2]
    if not lons or not lats:
        return None
    return min(lons), min(lats), max(lons), max(lats)


# --------------------------------------------------------------------------- #
# Filter helpers                                                               #
# --------------------------------------------------------------------------- #


def _trajectory_head_coordinate(
    trajectory: dict[str, Any],
) -> tuple[float, float] | None:
    """Return the head frame (lon, lat) for a trajectory payload."""

    frames = trajectory.get("frames") or []
    if isinstance(frames, list) and frames:
        head = frames[0]
        if isinstance(head, dict):
            lon = head.get("lon")
            lat = head.get("lat")
            if isinstance(lon, (int, float)) and isinstance(lat, (int, float)):
                return float(lon), float(lat)

    # Fallback: use route_coords first point.
    route = trajectory.get("route_coords") or []
    if isinstance(route, list) and route:
        first = route[0]
        if isinstance(first, (list, tuple)) and len(first) >= 2:
            return float(first[0]), float(first[1])
    return None


def filter_trajectories_by_bbox(
    trajectories: list[dict[str, Any]],
    bbox: str | None,
    *,
    buffer_ratio: float = DEFAULT_VIEWPORT_BUFFER_RATIO,
    min_buffer_degrees: float = DEFAULT_VIEWPORT_MIN_BUFFER_DEGREES,
) -> list[dict[str, Any]]:
    if bbox is None:
        return trajectories

    parsed_bbox = parse_bbox(bbox)
    if parsed_bbox is None:
        return []

    expanded_bbox = _expand_bbox(
        parsed_bbox,
        buffer_ratio=buffer_ratio,
        min_buffer_degrees=min_buffer_degrees,
    )

    result: list[dict[str, Any]] = []
    for trajectory in trajectories:
        head = _trajectory_head_coordinate(trajectory)
        if head is None:
            continue
        if _contains_point(expanded_bbox, head[0], head[1]):
            result.append(trajectory)
    return result


def filter_stations_by_bbox(
    stations: list[dict[str, Any]],
    bbox: str | None,
    *,
    buffer_ratio: float = DEFAULT_VIEWPORT_BUFFER_RATIO,
    min_buffer_degrees: float = DEFAULT_VIEWPORT_MIN_BUFFER_DEGREES,
) -> list[dict[str, Any]]:
    if bbox is None:
        return stations

    parsed_bbox = parse_bbox(bbox)
    if parsed_bbox is None:
        return []

    expanded_bbox = _expand_bbox(
        parsed_bbox,
        buffer_ratio=buffer_ratio,
        min_buffer_degrees=min_buffer_degrees,
    )

    return [
        station
        for station in stations
        if "location" in station
        and _contains_point(
            expanded_bbox,
            float(station["location"]["coordinates"][0]),
            float(station["location"]["coordinates"][1]),
        )
    ]


def filter_feature_collection_by_bbox(
    collection: dict[str, Any],
    bbox: str | None,
    *,
    buffer_ratio: float = DEFAULT_VIEWPORT_BUFFER_RATIO,
    min_buffer_degrees: float = DEFAULT_VIEWPORT_MIN_BUFFER_DEGREES,
) -> dict[str, Any]:
    if bbox is None:
        return collection

    parsed_bbox = parse_bbox(bbox)
    if parsed_bbox is None:
        return {"type": collection.get("type", "FeatureCollection"), "features": []}

    expanded_bbox = _expand_bbox(
        parsed_bbox,
        buffer_ratio=buffer_ratio,
        min_buffer_degrees=min_buffer_degrees,
    )

    filtered_features = []
    for feature in collection.get("features", []):
        feature_bounds = _geometry_bounds(feature.get("geometry", {}))
        if feature_bounds is None:
            continue
        if _bbox_intersects(feature_bounds, expanded_bbox):
            filtered_features.append(feature)

    return {
        "type": collection.get("type", "FeatureCollection"),
        "features": filtered_features,
    }


__all__ = [
    "BBox",
    "DEFAULT_VIEWPORT_BUFFER_RATIO",
    "DEFAULT_VIEWPORT_MIN_BUFFER_DEGREES",
    "REDIS_MAP_NETWORK_EDGES_KEY",
    "REDIS_MAP_STATIONS_KEY",
    "REDIS_STOPSEQUENCE_KEY_PREFIX",
    "REDIS_TOPOLOGY_METADATA_KEY",
    "REDIS_TRAJECTORIES_KEY",
    "REDIS_TRAJECTORY_KEY_PREFIX",
    "filter_feature_collection_by_bbox",
    "filter_stations_by_bbox",
    "filter_trajectories_by_bbox",
    "parse_bbox",
    "read_individual_trajectory",
    "read_map_network_edges",
    "read_map_stations",
    "read_stopsequence",
    "read_topology_metadata",
    "read_trajectories",
]
