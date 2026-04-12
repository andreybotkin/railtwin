import json
from typing import Any

from redis.asyncio import Redis

REDIS_POSITIONS_KEY = "train:positions:latest"
REDIS_TRAJECTORIES_KEY = "train:trajectories:latest"
REDIS_TRAJECTORY_KEY_PREFIX = "train:trajectory:"
REDIS_STOPSEQUENCE_KEY_PREFIX = "train:stopsequence:"
REDIS_TOPOLOGY_METADATA_KEY = "system:topology:metadata"


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


def filter_positions_by_bbox(
    positions: list[dict[str, Any]],
    bbox: str | None,
) -> list[dict[str, Any]]:
    if not bbox:
        return positions
    try:
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox.split(","))
    except (ValueError, TypeError):
        return positions
    return [
        position
        for position in positions
        if "location" in position
        and min_lon <= position["location"]["coordinates"][0] <= max_lon
        and min_lat <= position["location"]["coordinates"][1] <= max_lat
    ]


def filter_trajectories_by_bbox(
    trajectories: list[dict[str, Any]],
    bbox: str | None,
) -> list[dict[str, Any]]:
    if not bbox:
        return trajectories
    try:
        bmin_lon, bmin_lat, bmax_lon, bmax_lat = (float(v) for v in bbox.split(","))
    except (ValueError, TypeError):
        return trajectories

    result: list[dict[str, Any]] = []
    for trajectory in trajectories:
        props = trajectory.get("properties", {})
        bounds = props.get("bounds")
        if not bounds or len(bounds) < 4:
            result.append(trajectory)
            continue
        tmin_lon, tmin_lat, tmax_lon, tmax_lat = bounds
        if tmax_lon < bmin_lon or tmin_lon > bmax_lon:
            continue
        if tmax_lat < bmin_lat or tmin_lat > bmax_lat:
            continue
        result.append(trajectory)
    return result