import json
from typing import Any

from redis.asyncio import Redis

from app.schemas import Trajectory

REDIS_TRAJECTORIES_KEY = "train:trajectories:latest"
REDIS_TRAJECTORY_KEY_PREFIX = "train:trajectory:"
REDIS_STOPSEQUENCE_KEY_PREFIX = "train:stopsequence:"
REDIS_TOPOLOGY_METADATA_KEY = "system:topology:metadata"
REDIS_MAP_STATIONS_KEY = "map:stations:all"
REDIS_MAP_NETWORK_EDGES_KEY = "map:network_edges:all"
DEFAULT_VIEWPORT_BUFFER_RATIO = 0.1
DEFAULT_VIEWPORT_MIN_BUFFER_DEGREES = 0.05

BBox = tuple[float, float, float, float]


async def read_trajectories(redis_client: Redis | None) -> list[dict[str, Any]]:
    if redis_client is None:
        return []
    raw = await redis_client.get(REDIS_TRAJECTORIES_KEY)
    if not raw:
        return []
    parsed = json.loads(raw)
    validated: list[dict[str, Any]] = []
    for item in parsed:
        try:
            validated.append(Trajectory.model_validate(item).model_dump(mode="json"))
        except Exception:
            continue
    return validated


async def read_trajectory(redis_client: Redis | None, train_id: int) -> dict[str, Any] | None:
    if redis_client is None:
        return None
    raw = await redis_client.get(f"{REDIS_TRAJECTORY_KEY_PREFIX}{train_id}")
    if not raw:
        return None
    try:
        return Trajectory.model_validate(json.loads(raw)).model_dump(mode="json")
    except Exception:
        return None


async def read_stopsequence(redis_client: Redis | None, train_id: int) -> list[dict[str, Any]] | None:
    if redis_client is None:
        return None
    raw = await redis_client.get(f"{REDIS_STOPSEQUENCE_KEY_PREFIX}{train_id}")
    if not raw:
        return None
    return json.loads(raw)


async def read_topology_metadata(redis_client: Redis | None) -> dict[str, Any] | None:
    if redis_client is None:
        return None
    raw = await redis_client.get(REDIS_TOPOLOGY_METADATA_KEY)
    return json.loads(raw) if raw else None


async def read_map_stations(redis_client: Redis | None) -> list[dict[str, Any]]:
    if redis_client is None:
        return []
    raw = await redis_client.get(REDIS_MAP_STATIONS_KEY)
    return json.loads(raw) if raw else []


async def read_map_network_edges(redis_client: Redis | None) -> dict[str, Any]:
    if redis_client is None:
        return {"type": "FeatureCollection", "features": []}
    raw = await redis_client.get(REDIS_MAP_NETWORK_EDGES_KEY)
    return json.loads(raw) if raw else {"type": "FeatureCollection", "features": []}


def parse_bbox(bbox: str | None) -> BBox | None:
    if bbox is None:
        return None
    try:
        raw_min_lon, raw_min_lat, raw_max_lon, raw_max_lat = (float(value) for value in bbox.split(","))
    except (ValueError, TypeError):
        return None
    min_lon, max_lon = sorted((raw_min_lon, raw_max_lon))
    min_lat, max_lat = sorted((raw_min_lat, raw_max_lat))
    return min_lon, min_lat, max_lon, max_lat


def _expand_bbox(bbox: BBox, *, buffer_ratio: float, min_buffer_degrees: float) -> BBox:
    min_lon, min_lat, max_lon, max_lat = bbox
    lon_buffer = max((max_lon - min_lon) * buffer_ratio, min_buffer_degrees)
    lat_buffer = max((max_lat - min_lat) * buffer_ratio, min_buffer_degrees)
    return (min_lon - lon_buffer, min_lat - lat_buffer, max_lon + lon_buffer, max_lat + lat_buffer)


def _contains_point(bbox: BBox, lon: float, lat: float) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def filter_trajectories_by_bbox(
    trajectories: list[dict[str, Any]],
    bbox: str,
    *,
    buffer_ratio: float = DEFAULT_VIEWPORT_BUFFER_RATIO,
    min_buffer_degrees: float = DEFAULT_VIEWPORT_MIN_BUFFER_DEGREES,
) -> list[dict[str, Any]]:
    parsed = parse_bbox(bbox)
    if parsed is None:
        return trajectories
    expanded = _expand_bbox(parsed, buffer_ratio=buffer_ratio, min_buffer_degrees=min_buffer_degrees)
    filtered: list[dict[str, Any]] = []
    for trajectory in trajectories:
        frames = trajectory.get("frames") or []
        if not frames:
            continue
        first = frames[0]
        lon = first.get("lon")
        lat = first.get("lat")
        if lon is None or lat is None:
            continue
        if _contains_point(expanded, float(lon), float(lat)):
            filtered.append(trajectory)
    return filtered


def filter_stations_by_bbox(stations: list[dict[str, Any]], bbox: str, *, buffer_ratio: float = DEFAULT_VIEWPORT_BUFFER_RATIO, min_buffer_degrees: float = DEFAULT_VIEWPORT_MIN_BUFFER_DEGREES) -> list[dict[str, Any]]:
    parsed = parse_bbox(bbox)
    if parsed is None:
        return stations
    expanded = _expand_bbox(parsed, buffer_ratio=buffer_ratio, min_buffer_degrees=min_buffer_degrees)
    out: list[dict[str, Any]] = []
    for station in stations:
        point = station.get("location", {})
        coords = point.get("coordinates", [])
        if len(coords) >= 2 and _contains_point(expanded, float(coords[0]), float(coords[1])):
            out.append(station)
    return out


def filter_feature_collection_by_bbox(collection: dict[str, Any], bbox: str, *, buffer_ratio: float = DEFAULT_VIEWPORT_BUFFER_RATIO, min_buffer_degrees: float = DEFAULT_VIEWPORT_MIN_BUFFER_DEGREES) -> dict[str, Any]:
    parsed = parse_bbox(bbox)
    if parsed is None:
        return collection
    expanded = _expand_bbox(parsed, buffer_ratio=buffer_ratio, min_buffer_degrees=min_buffer_degrees)
    min_lon, min_lat, max_lon, max_lat = expanded
    features = []
    for feature in collection.get("features", []):
        coords = feature.get("geometry", {}).get("coordinates", [])
        flat = coords if feature.get("geometry", {}).get("type") == "Point" else [c for c in coords]
        include = False
        for coord in flat:
            if len(coord) >= 2 and min_lon <= coord[0] <= max_lon and min_lat <= coord[1] <= max_lat:
                include = True
                break
        if include:
            features.append(feature)
    return {"type": "FeatureCollection", "features": features}
