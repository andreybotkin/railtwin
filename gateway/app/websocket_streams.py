"""WebSocket stream helpers.

The first payload and every viewport reset are sent as one batch snapshot.
Subsequent updates use per-train deltas, keeping both cold-start latency and
steady-state bandwidth low.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)

TrajectoryReader = Callable[[], Awaitable[list[dict[str, Any]]]]
StopSequenceReader = Callable[[int], Awaitable[list[dict[str, Any]] | None]]
TrajectoryFilter = Callable[[list[dict[str, Any]], str | None], list[dict[str, Any]]]


def _trajectory_version(trajectory: dict[str, Any]) -> int:
    raw_version = trajectory.get("generated_at_ms", 0)
    if isinstance(raw_version, (int, float)):
        return int(raw_version)
    return 0


def _trajectory_versions(trajectories: list[dict[str, Any]]) -> dict[int, int]:
    return {
        int(trajectory["train_id"]): _trajectory_version(trajectory)
        for trajectory in trajectories
    }


async def _send_trajectory_snapshot(
    websocket: WebSocket,
    trajectories: list[dict[str, Any]],
    now_ms: int,
) -> dict[int, int]:
    await websocket.send_json(
        {"source": "snapshot", "content": trajectories, "timestamp": now_ms}
    )
    return _trajectory_versions(trajectories)


async def _send_trajectory_delta(
    websocket: WebSocket,
    trajectories: list[dict[str, Any]],
    last_versions: dict[int, int],
    now_ms: int,
) -> dict[int, int]:
    current_versions = _trajectory_versions(trajectories)

    for trajectory in trajectories:
        train_id = int(trajectory["train_id"])
        version = current_versions[train_id]
        if last_versions.get(train_id) != version:
            await websocket.send_json(
                {"source": "trajectory", "content": trajectory, "timestamp": now_ms}
            )

    for removed_id in set(last_versions) - set(current_versions):
        await websocket.send_json(
            {"source": "deleted_vehicles", "content": removed_id, "timestamp": now_ms}
        )

    return current_versions


async def stream_trajectories(
    websocket: WebSocket,
    *,
    read_trajectories: TrajectoryReader,
    filter_trajectories: TrajectoryFilter,
    update_interval_seconds: int,
    initial_bbox: str | None = None,
) -> None:
    await websocket.accept()
    client_bbox = initial_bbox
    last_versions: dict[int, int] = {}
    keepalive_counter = 0
    send_snapshot = True

    update_interval_s = max(1, update_interval_seconds)

    while True:
        trajectories = await read_trajectories()
        filtered = (
            trajectories
            if client_bbox is None
            else filter_trajectories(trajectories, client_bbox)
        )
        now_ms = int(asyncio.get_running_loop().time() * 1000)
        try:
            if send_snapshot:
                last_versions = await _send_trajectory_snapshot(
                    websocket, filtered, now_ms
                )
                send_snapshot = False
            else:
                last_versions = await _send_trajectory_delta(
                    websocket, filtered, last_versions, now_ms
                )
        except Exception as exc:
            logger.debug("WebSocket send error, disconnecting client: %s", exc)
            return

        keepalive_counter += 1
        if keepalive_counter >= 3:
            keepalive_counter = 0
            try:
                await websocket.send_json({"source": "keepalive", "timestamp": now_ms})
            except Exception as exc:
                logger.debug("WebSocket keepalive send error: %s", exc)
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
                    send_snapshot = True
                    break
                elif message.startswith("BBOX "):
                    next_bbox = message[5:].strip() or None
                    if next_bbox != client_bbox:
                        client_bbox = next_bbox
                        send_snapshot = True
                        break
            except TimeoutError:
                continue
            except Exception as exc:
                logger.debug("WebSocket receive error, disconnecting client: %s", exc)
                return


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
            try:
                await websocket.send_json(payload)
            except Exception as exc:
                logger.debug("WebSocket send error for train %s: %s", train_id, exc)
                return
            last_payload = serialized

        keepalive_counter += 1
        if keepalive_counter >= 5:
            keepalive_counter = 0
            try:
                await websocket.send_json(
                    {
                        "type": "keepalive",
                        "timestamp": asyncio.get_running_loop().time(),
                    }
                )
            except Exception as exc:
                logger.debug(
                    "WebSocket keepalive error for train %s: %s", train_id, exc
                )
                return

        try:
            message = await asyncio.wait_for(
                websocket.receive_text(), timeout=ws_poll_interval
            )
            if message == "ping":
                await websocket.send_text("pong")
        except TimeoutError:
            continue
        except Exception as exc:
            logger.debug("WebSocket receive error for train %s: %s", train_id, exc)
            return


__all__ = ["stream_stopsequence", "stream_trajectories"]
