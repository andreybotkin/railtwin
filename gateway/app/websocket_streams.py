import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import WebSocket

PositionReader = Callable[[], Awaitable[list[dict[str, Any]]]]
TrajectoryReader = Callable[[], Awaitable[list[dict[str, Any]]]]
StopSequenceReader = Callable[[int], Awaitable[list[dict[str, Any]] | None]]
PositionFilter = Callable[[list[dict[str, Any]], str | None], list[dict[str, Any]]]
TrajectoryFilter = Callable[[list[dict[str, Any]], str | None], list[dict[str, Any]]]


def _trajectory_version(trajectory: dict[str, Any]) -> int:
    props = trajectory.get("properties", {})
    raw_version = props.get("timestamp", 0)
    if isinstance(raw_version, (int, float)):
        return int(raw_version)
    return 0


async def _send_trajectory_delta(
    websocket: WebSocket,
    trajectories: list[dict[str, Any]],
    last_versions: dict[int, int],
    now_ms: int,
) -> dict[int, int]:
    current_versions: dict[int, int] = {}

    for trajectory in trajectories:
        train_id = int(trajectory["properties"]["train_id"])
        version = _trajectory_version(trajectory)
        current_versions[train_id] = version
        if last_versions.get(train_id) != version:
            await websocket.send_json(
                {"source": "trajectory", "content": trajectory, "timestamp": now_ms}
            )

    for removed_id in set(last_versions) - set(current_versions):
        await websocket.send_json(
            {"source": "deleted_vehicles", "content": removed_id, "timestamp": now_ms}
        )

    return current_versions


async def stream_positions(
    websocket: WebSocket,
    *,
    read_positions: PositionReader,
    filter_positions: PositionFilter,
    ws_poll_interval: int,
    logger: logging.Logger,
    train_id: int | None = None,
) -> None:
    await websocket.accept()
    last_payload: str | None = None
    client_bbox: str | None = None
    keepalive_counter = 0

    while True:
        positions = await read_positions()
        payload: dict[str, Any]

        if train_id is None:
            filtered = filter_positions(positions, client_bbox)
            payload = {
                "type": "positions",
                "data": filtered,
                "timestamp": asyncio.get_running_loop().time(),
            }
        else:
            position = next((p for p in positions if p["train_id"] == train_id), None)
            payload = {
                "type": "position",
                "train_id": train_id,
                "data": position,
                "timestamp": asyncio.get_running_loop().time(),
            }

        serialized = json.dumps(payload, sort_keys=True, default=str)
        if serialized != last_payload:
            await websocket.send_json(payload)
            last_payload = serialized

        keepalive_counter += 1
        if keepalive_counter >= 5:
            keepalive_counter = 0
            try:
                await websocket.send_json({"type": "keepalive", "timestamp": asyncio.get_running_loop().time()})
            except Exception:
                return

        try:
            message = await asyncio.wait_for(websocket.receive_text(), timeout=ws_poll_interval)
            if message == "ping":
                await websocket.send_text("pong")
            elif message.startswith("BBOX "):
                client_bbox = message[5:].strip() or None
                logger.debug("WS BBOX updated: %s", client_bbox)
        except asyncio.TimeoutError:
            continue


async def stream_trajectories(
    websocket: WebSocket,
    *,
    read_trajectories: TrajectoryReader,
    filter_trajectories: TrajectoryFilter,
    update_interval_seconds: int,
) -> None:
    await websocket.accept()
    client_bbox: str | None = None
    last_versions: dict[int, int] = {}
    keepalive_counter = 0

    update_interval_s = max(1, update_interval_seconds)

    while True:
        trajectories = await read_trajectories()
        filtered = filter_trajectories(trajectories, client_bbox)
        now_ms = int(asyncio.get_running_loop().time() * 1000)
        last_versions = await _send_trajectory_delta(
            websocket,
            filtered,
            last_versions,
            now_ms,
        )
        keepalive_counter += 1
        if keepalive_counter >= 3:
            keepalive_counter = 0
            try:
                await websocket.send_json({"source": "keepalive", "timestamp": now_ms})
            except Exception:
                return

        deadline = asyncio.get_running_loop().time() + update_interval_s
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            try:
                message = await asyncio.wait_for(
                    websocket.receive_text(), timeout=min(remaining, 1.0)
                )
                if message == "PING":
                    await websocket.send_text("pong")
                elif message == "RESET":
                    client_bbox = None
                    last_versions = {}
                    break
                elif message.startswith("BBOX "):
                    client_bbox = message[5:].strip() or None
                    last_versions = {}
                    break
            except asyncio.TimeoutError:
                continue


async def stream_stopsequence(
    websocket: WebSocket,
    *,
    train_id: int,
    read_stopsequence: StopSequenceReader,
    ws_poll_interval: int,
) -> None:
    await websocket.accept()
    last_payload: str | None = None
    keepalive_counter = 0

    while True:
        seq = await read_stopsequence(train_id)
        payload: dict[str, Any] = {
            "type": "stopsequence",
            "train_id": train_id,
            "data": seq,
            "timestamp": asyncio.get_running_loop().time(),
        }
        serialized = json.dumps(payload, sort_keys=True, default=str)
        if serialized != last_payload:
            await websocket.send_json(payload)
            last_payload = serialized

        keepalive_counter += 1
        if keepalive_counter >= 5:
            keepalive_counter = 0
            try:
                await websocket.send_json(
                    {"type": "keepalive", "timestamp": asyncio.get_running_loop().time()}
                )
            except Exception:
                return

        try:
            message = await asyncio.wait_for(
                websocket.receive_text(), timeout=ws_poll_interval
            )
            if message == "ping":
                await websocket.send_text("pong")
        except asyncio.TimeoutError:
            continue