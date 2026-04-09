"""WebSocket endpoint for real-time train position updates.

Architecture:
  * PositionBroadcaster — single background task that recomputes every
    ws_heartbeat_interval seconds and stores results in Redis under
    REDIS_POSITIONS_KEY.  It also notifies per-connection asyncio.Queue
    instances so WebSocket clients receive the push instantly without any
    extra DB round-trips.
  * REST /trains/positions — reads from Redis cache (see trains.py).
  * WebSocket /ws/trains — subscriber queue; first message served from cache.
"""

import asyncio
import contextlib
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.dependencies import get_redis
from app.core.config import settings
from app.core.logging import get_logger
from app.models.database import async_session_factory
from app.services.simulation import TrainSimulationService

logger = get_logger(__name__)

router = APIRouter()

# Redis key where latest positions are cached
REDIS_POSITIONS_KEY = "train:positions:latest"
REDIS_POSITIONS_TTL = 30  # seconds – expire if broadcaster dies


# ---------------------------------------------------------------------------
# Position broadcaster
# ---------------------------------------------------------------------------


class PositionBroadcaster:
    """Computes train positions every N seconds, caches in Redis, notifies WS clients."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def _run(self) -> None:
        redis = get_redis()
        while True:
            tick_start = asyncio.get_running_loop().time()
            try:
                async with async_session_factory() as session:
                    svc = TrainSimulationService(session, redis_client=redis)
                    positions = await svc.get_all_active_trains()

                payload: dict[str, Any] = {
                    "type": "positions",
                    "data": positions,
                    "timestamp": asyncio.get_running_loop().time(),
                }

                # Store in Redis so REST and new WS connections get data instantly
                await redis.setex(
                    REDIS_POSITIONS_KEY,
                    REDIS_POSITIONS_TTL,
                    json.dumps(positions, default=str),
                )

                # Push to all WebSocket subscriber queues
                for q in list(self._subscribers):
                    with contextlib.suppress(asyncio.QueueFull):
                        q.put_nowait(payload)

            except Exception as exc:
                logger.error("PositionBroadcaster error", error=str(exc))

            elapsed = asyncio.get_running_loop().time() - tick_start
            await asyncio.sleep(max(0.0, settings.ws_heartbeat_interval - elapsed))

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="position_broadcaster")
            logger.info(
                "PositionBroadcaster started", interval=settings.ws_heartbeat_interval
            )

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None


broadcaster = PositionBroadcaster()


# ---------------------------------------------------------------------------
# Helper – read cached positions from Redis
# ---------------------------------------------------------------------------


async def get_cached_positions() -> list[dict]:
    """Return latest positions from Redis cache (empty list if not yet populated)."""
    redis = get_redis()
    raw = await redis.get(REDIS_POSITIONS_KEY)
    if raw:
        return json.loads(raw)
    return []


# ---------------------------------------------------------------------------
# Connection manager (tracks active sockets for logging)
# ---------------------------------------------------------------------------


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket connected", total=len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("WebSocket disconnected", total=len(self.active_connections))


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.websocket("/trains")
async def websocket_trains(websocket: WebSocket) -> None:
    """WebSocket endpoint – instant delivery from Redis cache + push on every tick."""
    await manager.connect(websocket)
    q = broadcaster.subscribe()
    broadcaster.start()  # idempotent

    try:
        # Serve cached data immediately so client doesn't wait for the next tick
        cached = await get_cached_positions()
        await websocket.send_json(
            {
                "type": "positions",
                "data": cached,
                "timestamp": asyncio.get_running_loop().time(),
            }
        )

        while True:
            # Race: next broadcaster payload OR a client message
            done, pending = await asyncio.wait(
                [
                    asyncio.ensure_future(q.get()),
                    asyncio.ensure_future(websocket.receive_text()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                result = task.result()
                if isinstance(result, dict):
                    await websocket.send_json(result)
                elif isinstance(result, str) and result == "ping":
                    await websocket.send_text("pong")

    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        broadcaster.unsubscribe(q)
        manager.disconnect(websocket)


@router.websocket("/trains/{train_id}")
async def websocket_single_train(websocket: WebSocket, train_id: int) -> None:
    """WebSocket endpoint for tracking a single train."""
    await websocket.accept()
    q = broadcaster.subscribe()
    broadcaster.start()

    async def _send_positions(positions: list[dict], timestamp: float) -> None:
        train_pos = next((p for p in positions if p["train_id"] == train_id), None)
        await websocket.send_json(
            {
                "type": "position",
                "train_id": train_id,
                "data": train_pos,
                "timestamp": timestamp,
            }
        )

    try:
        cached = await get_cached_positions()
        await _send_positions(cached, asyncio.get_running_loop().time())

        while True:
            done, pending = await asyncio.wait(
                [
                    asyncio.ensure_future(q.get()),
                    asyncio.ensure_future(websocket.receive_text()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                result = task.result()
                if isinstance(result, dict):
                    await _send_positions(result.get("data", []), result["timestamp"])
                elif isinstance(result, str) and result == "ping":
                    await websocket.send_text("pong")

    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        broadcaster.unsubscribe(q)
        logger.info("Single train WebSocket disconnected", train_id=train_id)
