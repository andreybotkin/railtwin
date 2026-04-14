import json
from typing import Any

from redis.asyncio import Redis

REDIS_POSITIONS_KEY = "train:positions:latest"
REDIS_POSITION_KEY_PREFIX = "train:position:"
REDIS_TRAJECTORIES_KEY = "train:trajectories:latest"
REDIS_TRAJECTORY_KEY_PREFIX = "train:trajectory:"
REDIS_STOPSEQUENCE_KEY_PREFIX = "train:stopsequence:"
REDIS_TOPOLOGY_METADATA_KEY = "system:topology:metadata"
REDIS_MAP_STATIONS_KEY = "map:stations:all"
REDIS_MAP_NETWORK_EDGES_KEY = "map:network_edges:all"
DEFAULT_VIEWPORT_BUFFER_RATIO = 0.1
DEFAULT_VIEWPORT_MIN_BUFFER_DEGREES = 0.05

type BBox = tuple[float, float, float, float]


async def read_positions(redis_client: Redis | None) -> list[dict[str, Any]]:
    if redis_client is None:
        return []
    raw = await redis_client.get(REDIS_POSITIONS_KEY)
    if not raw:
        return []
    return json.loads(raw)


async def read_position(
    redis_client: Redis | None,
    train_id: int,
) -> dict[str, Any] | None:
    if redis_client is not None:
        raw = await redis_client.get(f"{REDIS_POSITION_KEY_PREFIX}{train_id}")
        if raw:
            return json.loads(raw)
    positions = await read_positions(redis_client)
    return next((position for position in positions if position["train_id"] == train_id), None)


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
) -> dict[str, Any] | None:
    if redis_client is None:
        return None
    raw = await redis_client.get(REDIS_TOPOLOGY_METADATA_KEY)
    if not raw:
        return None
    return json.loads(raw)


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


def _interpolate_linestring_coordinate(
    coordinates: list[list[float]],
    fraction: float,
) -> tuple[float, float] | None:
    if not coordinates:
        return None
    if fraction <= 0:
        return float(coordinates[0][0]), float(coordinates[0][1])
    if fraction >= 1:
        last = coordinates[-1]
        return float(last[0]), float(last[1])

    total_length = 0.0
    segment_lengths: list[float] = []
    for index in range(len(coordinates) - 1):
        start = coordinates[index]
        end = coordinates[index + 1]
        dx = float(end[0]) - float(start[0])
        dy = float(end[1]) - float(start[1])
        length = (dx * dx + dy * dy) ** 0.5
        segment_lengths.append(length)
        total_length += length

    if total_length == 0:
        return float(coordinates[0][0]), float(coordinates[0][1])

    target = fraction * total_length
    accumulated = 0.0
    for index, length in enumerate(segment_lengths):
        if accumulated + length >= target:
            start = coordinates[index]
            end = coordinates[index + 1]
            relative = 0.0 if length == 0 else (target - accumulated) / length
            lon = float(start[0]) + relative * (float(end[0]) - float(start[0]))
            lat = float(start[1]) + relative * (float(end[1]) - float(start[1]))
            return lon, lat
        accumulated += length

    last = coordinates[-1]
    return float(last[0]), float(last[1])


def _trajectory_current_coordinate(
    trajectory: dict[str, Any],
) -> tuple[float, float] | None:
    geometry = trajectory.get("geometry", {})
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if geometry_type == "Point" and isinstance(coordinates, list) and len(coordinates) >= 2:
        return float(coordinates[0]), float(coordinates[1])

    if geometry_type != "LineString" or not isinstance(coordinates, list):
        return None

    props = trajectory.get("properties", {})
    coordinate_timestamps = props.get("coordinate_timestamps")

    if isinstance(coordinate_timestamps, list) and coordinate_timestamps:
        first_point = coordinate_timestamps[0]
        if (
            isinstance(first_point, list)
            and len(first_point) >= 2
            and isinstance(first_point[1], list)
            and len(first_point[1]) >= 2
        ):
            try:
                return float(first_point[1][0]), float(first_point[1][1])
            except (TypeError, ValueError):
                pass

    time_intervals = props.get("time_intervals")
    geom_fraction = 0.0

    if isinstance(time_intervals, list) and time_intervals:
        first_interval = time_intervals[0]
        if isinstance(first_interval, list) and len(first_interval) >= 2:
            try:
                geom_fraction = float(first_interval[1])
            except (TypeError, ValueError):
                geom_fraction = 0.0
    elif props.get("route_progress") is not None:
        try:
            geom_fraction = float(props["route_progress"])
        except (TypeError, ValueError):
            geom_fraction = 0.0

    return _interpolate_linestring_coordinate(coordinates, geom_fraction)


def filter_positions_by_bbox(
    positions: list[dict[str, Any]],
    bbox: str | None,
    *,
    buffer_ratio: float = DEFAULT_VIEWPORT_BUFFER_RATIO,
    min_buffer_degrees: float = DEFAULT_VIEWPORT_MIN_BUFFER_DEGREES,
) -> list[dict[str, Any]]:
    if bbox is None:
        return positions

    parsed_bbox = parse_bbox(bbox)
    if parsed_bbox is None:
        return []

    expanded_bbox = _expand_bbox(
        parsed_bbox,
        buffer_ratio=buffer_ratio,
        min_buffer_degrees=min_buffer_degrees,
    )

    return [
        position
        for position in positions
        if "location" in position
        and _contains_point(
            expanded_bbox,
            float(position["location"]["coordinates"][0]),
            float(position["location"]["coordinates"][1]),
        )
    ]


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
        current_coordinate = _trajectory_current_coordinate(trajectory)
        if current_coordinate is None:
            continue

        lon, lat = current_coordinate
        if _contains_point(expanded_bbox, lon, lat):
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
