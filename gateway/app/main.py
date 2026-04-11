"""Stateless gateway for website traffic and train positions from Redis.

Implements geops mobility-toolbox-js WebSocket trajectory protocol:
- /ws/trains      — position snapshots every N seconds (backward-compat)
- /ws/trajectory  — geops time_intervals trajectory objects for smooth client-side
                    temporal interpolation (60fps animation without server polling)
- /api/v1/trains/trajectories — REST endpoint returning current trajectory objects

TODO (deferred — geops patterns for future iterations):
- Topic-based architecture: route WS subscriptions to separate pub/sub channels
  per topic (e.g., "trains", "stations", "disruptions") like trafimage-maps topics
- Rate limiting per client IP for WS connections
- Message compression (permessage-deflate) for large position payloads
- Prometheus /metrics endpoint for observability
- Graceful shutdown: drain WS clients before stopping
- Per-vehicle subscription channels: GET/SUB/DEL protocol like geops RealtimeAPI
- Station autocomplete search endpoint for typeahead in the frontend map search
- Historical playback: replay past positions from time-series Redis ZSET
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from typing import Annotated

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

REDIS_POSITIONS_KEY = "train:positions:latest"
REDIS_TRAJECTORIES_KEY = "train:trajectories:latest"
REDIS_TRAJECTORY_KEY_PREFIX = "train:trajectory:"
REDIS_STOPSEQUENCE_KEY_PREFIX = "train:stopsequence:"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Thailand Railway Digital Twin Gateway"
    app_version: str = "1.0.0"
    backend_url: str = "http://backend:8000"
    redis_url: str = "redis://redis:6379/0"
    ws_poll_interval: int = 2
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://localhost:8002",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            parsed_value = value.strip()

            if not parsed_value:
                return []

            if parsed_value.startswith("["):
                decoded = json.loads(parsed_value)
                if isinstance(decoded, list):
                    return [
                        str(origin).strip()
                        for origin in decoded
                        if str(origin).strip()
                    ]

            return [origin.strip() for origin in parsed_value.split(",") if origin.strip()]
        return list(value)


settings = Settings()
redis_client: Redis | None = None
http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    global redis_client, http_client
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    http_client = httpx.AsyncClient(
        base_url=settings.backend_url,
        timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0),
    )
    yield
    if http_client is not None:
        await http_client.aclose()
    if redis_client is not None:
        await redis_client.aclose()


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)


# Security headers middleware (OWASP best practices, pattern from trafimage-maps)
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self), microphone=()"
        response.headers["Cache-Control"] = "no-store"
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _read_positions() -> list[dict[str, Any]]:
    if redis_client is None:
        return []
    raw = await redis_client.get(REDIS_POSITIONS_KEY)
    if not raw:
        return []
    return json.loads(raw)


async def _read_trajectories() -> list[dict[str, Any]]:
    """Read trajectory objects from Redis (geops mobility-toolbox-js pattern)."""
    if redis_client is None:
        return []
    raw = await redis_client.get(REDIS_TRAJECTORIES_KEY)
    if not raw:
        return []
    return json.loads(raw)


async def _read_position(train_id: int) -> dict[str, Any] | None:
    positions = await _read_positions()
    return next((position for position in positions if position["train_id"] == train_id), None)


async def _read_individual_trajectory(train_id: int) -> dict[str, Any] | None:
    """Read a single train trajectory from its individual Redis key."""
    if redis_client is None:
        return None
    raw = await redis_client.get(f"{REDIS_TRAJECTORY_KEY_PREFIX}{train_id}")
    if not raw:
        return None
    return json.loads(raw)  # type: ignore[no-any-return]


async def _read_stopsequence(train_id: int) -> list[dict[str, Any]] | None:
    """Read a train's stop sequence from Redis."""
    if redis_client is None:
        return None
    raw = await redis_client.get(f"{REDIS_STOPSEQUENCE_KEY_PREFIX}{train_id}")
    if not raw:
        return None
    return json.loads(raw)  # type: ignore[no-any-return]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    if redis_client is None:
        return {"status": "not_ready"}
    await redis_client.ping()
    return {"status": "ready"}


def _filter_by_bbox(
    positions: list[dict[str, Any]], bbox: str | None
) -> list[dict[str, Any]]:
    """Filter positions by bounding box string 'minLon,minLat,maxLon,maxLat'."""
    if not bbox:
        return positions
    try:
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox.split(","))
    except (ValueError, TypeError):
        return positions
    return [
        p
        for p in positions
        if "location" in p
        and min_lon <= p["location"]["coordinates"][0] <= max_lon
        and min_lat <= p["location"]["coordinates"][1] <= max_lat
    ]


@app.get("/api/v1/trains/positions")
async def get_positions(bbox: str | None = None) -> list[dict[str, Any]]:
    """Get all train positions, optionally filtered by bbox."""
    positions = await _read_positions()
    return _filter_by_bbox(positions, bbox)


@app.get("/api/v1/trains/{train_id}/position")
async def get_train_position(train_id: int) -> dict[str, Any]:
    position = await _read_position(train_id)
    if position is None:
        raise HTTPException(status_code=404, detail=f"Position for train {train_id} not found")

    return {
        "id": train_id,
        "train_id": train_id,
        "location": position["location"],
        "speed": position.get("speed"),
        "heading": position.get("heading"),
        "status": position.get("status", "moving"),
        "delay_minutes": position.get("delay_minutes", 0),
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def _ws_positions_loop(websocket: WebSocket, train_id: int | None = None) -> None:
    """WebSocket loop that supports BBOX command, ping/pong, and server keepalive."""
    await websocket.accept()
    last_payload: str | None = None
    client_bbox: str | None = None
    keepalive_counter = 0

    while True:
        positions = await _read_positions()
        payload: dict[str, Any]

        if train_id is None:
            filtered = _filter_by_bbox(positions, client_bbox)
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

        # Server-side keepalive every ~10s (5 poll cycles of 2s)
        keepalive_counter += 1
        if keepalive_counter >= 5:
            keepalive_counter = 0
            try:
                await websocket.send_json({"type": "keepalive", "timestamp": asyncio.get_running_loop().time()})
            except Exception:
                return

        try:
            message = await asyncio.wait_for(websocket.receive_text(), timeout=settings.ws_poll_interval)
            if message == "ping":
                await websocket.send_text("pong")
            elif message.startswith("BBOX "):
                # Client sends "BBOX minLon,minLat,maxLon,maxLat"
                client_bbox = message[5:].strip() or None
                logger.debug("WS BBOX updated: %s", client_bbox)
        except asyncio.TimeoutError:
            continue


@app.websocket("/ws/trains")
async def ws_trains(websocket: WebSocket) -> None:
    try:
        await _ws_positions_loop(websocket)
    except (WebSocketDisconnect, asyncio.CancelledError):
        return


@app.websocket("/ws/trains/{train_id}")
async def ws_single_train(websocket: WebSocket, train_id: int) -> None:
    try:
        await _ws_positions_loop(websocket, train_id=train_id)
    except (WebSocketDisconnect, asyncio.CancelledError):
        return


def _filter_trajectories_by_bbox(
    trajectories: list[dict[str, Any]], bbox: str | None
) -> list[dict[str, Any]]:
    """Filter trajectory objects by bounding box.

    Uses trajectory.properties.bounds = [minLon, minLat, maxLon, maxLat].
    geops RealtimeEngine pattern: purgeTrajectory() checks extent intersection.
    """
    if not bbox:
        return trajectories
    try:
        bmin_lon, bmin_lat, bmax_lon, bmax_lat = (float(v) for v in bbox.split(","))
    except (ValueError, TypeError):
        return trajectories

    result = []
    for t in trajectories:
        props = t.get("properties", {})
        bounds = props.get("bounds")
        if not bounds or len(bounds) < 4:
            result.append(t)
            continue
        tmin_lon, tmin_lat, tmax_lon, tmax_lat = bounds
        # AABB intersection check
        if tmax_lon < bmin_lon or tmin_lon > bmax_lon:
            continue
        if tmax_lat < bmin_lat or tmin_lat > bmax_lat:
            continue
        result.append(t)
    return result


async def _ws_trajectory_loop(websocket: WebSocket) -> None:
    """WebSocket loop serving geops-compatible trajectory objects.

    Protocol (mirrors geops mobility-toolbox-js WebSocketAPI):
      Client → Server:
        BBOX minLon,minLat,maxLon,maxLat   — update viewport filter
        PING                               — keepalive (server replies 'pong')
        RESET                              — clear subscriptions (client re-sends BBOX)
      Server → Client:
        {"source":"trajectory","content":<trajectory>,"timestamp":<ms>}
        {"source":"deleted_vehicles","content":<train_id>,"timestamp":<ms>}

    Trajectories cover TRAJECTORY_LOOKAHEAD_SECONDS ahead using time_intervals so the
    frontend can interpolate vehicle positions at any point in time without waiting for
    the next server update — enabling truly smooth 60fps animation.

    TODO (deferred):
      - Incremental delta updates: only send changed trajectories instead of full batch
      - Per-train subscription channels (subscribe/unsubscribe individual vehicles)
      - permessage-deflate compression for large payloads
    """
    await websocket.accept()
    client_bbox: str | None = None
    last_train_ids: set[int] = set()
    keepalive_counter = 0

    # Send full batch on connect so the client can start rendering immediately
    trajectories = await _read_trajectories()
    filtered = _filter_trajectories_by_bbox(trajectories, client_bbox)
    now_ms = int(asyncio.get_running_loop().time() * 1000)
    for t in filtered:
        await websocket.send_json(
            {"source": "trajectory", "content": t, "timestamp": now_ms}
        )
    last_train_ids = {t["properties"]["train_id"] for t in filtered}

    # Update loop — refresh every TRAJECTORY_LOOKAHEAD_SECONDS / 2 to ensure
    # time_intervals are always fresh before they expire on the client
    update_interval_s = max(5, 30)  # 30-second refresh cycle

    while True:
        trajectories = await _read_trajectories()
        filtered = _filter_trajectories_by_bbox(trajectories, client_bbox)
        now_ms = int(asyncio.get_running_loop().time() * 1000)
        current_ids = {t["properties"]["train_id"] for t in filtered}

        # Send updated trajectories
        for t in filtered:
            await websocket.send_json(
                {"source": "trajectory", "content": t, "timestamp": now_ms}
            )

        # Send deleted_vehicles for trains that disappeared
        for removed_id in last_train_ids - current_ids:
            await websocket.send_json(
                {"source": "deleted_vehicles", "content": removed_id, "timestamp": now_ms}
            )

        last_train_ids = current_ids

        # Server keepalive ping every N cycles
        keepalive_counter += 1
        if keepalive_counter >= 3:
            keepalive_counter = 0
            try:
                await websocket.send_json(
                    {"source": "keepalive", "timestamp": now_ms}
                )
            except Exception:
                return

        # Wait for next update cycle, handling client commands in the meantime
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
                    last_train_ids = set()
                elif message.startswith("BBOX "):
                    client_bbox = message[5:].strip() or None
                    logger.debug("Trajectory WS BBOX updated: %s", client_bbox)
                    # Re-send all trajectories for the new viewport immediately
                    trajectories = await _read_trajectories()
                    filtered = _filter_trajectories_by_bbox(trajectories, client_bbox)
                    now_ms = int(asyncio.get_running_loop().time() * 1000)
                    for t in filtered:
                        await websocket.send_json(
                            {"source": "trajectory", "content": t, "timestamp": now_ms}
                        )
                    # Send deleted_vehicles for trains outside new BBOX
                    new_ids = {t["properties"]["train_id"] for t in filtered}
                    for removed_id in last_train_ids - new_ids:
                        await websocket.send_json(
                            {"source": "deleted_vehicles", "content": removed_id, "timestamp": now_ms}
                        )
                    last_train_ids = new_ids
                    break  # restart wait loop after BBOX change
            except asyncio.TimeoutError:
                continue


@app.websocket("/ws/trajectory")
async def ws_trajectory(websocket: WebSocket) -> None:
    """WebSocket endpoint serving geops-compatible trajectory objects with time_intervals.

    Connects to this instead of /ws/trains for smooth client-side temporal interpolation.
    """
    try:
        await _ws_trajectory_loop(websocket)
    except (WebSocketDisconnect, asyncio.CancelledError):
        return


@app.get("/api/v1/trains/trajectories")
async def get_trajectories(bbox: str | None = None) -> list[dict[str, Any]]:
    """REST endpoint: get all active train trajectories, optionally filtered by bbox.

    Trajectory objects contain time_intervals for client-side temporal interpolation.
    """
    trajectories = await _read_trajectories()
    return _filter_trajectories_by_bbox(trajectories, bbox)


@app.get("/api/v1/trains/{train_id}/trajectory")
async def get_train_trajectory(train_id: int) -> dict[str, Any]:
    """Get geops-compatible trajectory object for a single train.

    Reads from the individual ``train:trajectory:{id}`` Redis key written by
    position_cache.py — no need to fetch and scan the full list.
    """
    trajectory = await _read_individual_trajectory(train_id)
    if trajectory is None:
        raise HTTPException(
            status_code=404,
            detail=f"Trajectory for train {train_id} not found",
        )
    return trajectory


@app.get("/api/v1/trains/{train_id}/stopsequence")
async def get_train_stopsequence(train_id: int) -> list[dict[str, Any]]:
    """Get the upcoming stop sequence for a specific train."""
    seq = await _read_stopsequence(train_id)
    if seq is None:
        raise HTTPException(
            status_code=404,
            detail=f"Stop sequence for train {train_id} not found",
        )
    return seq


@app.websocket("/ws/stopsequence/{train_id}")
async def ws_stopsequence(websocket: WebSocket, train_id: int) -> None:
    """WebSocket that pushes stop-sequence updates for a specific train.

    Useful for a sidebar panel that shows upcoming stops in real time.
    Sends a full stop-sequence list every ``ws_poll_interval`` seconds when the
    data changes, plus a keepalive every 10 seconds.
    """
    await websocket.accept()
    last_payload: str | None = None
    keepalive_counter = 0

    while True:
        seq = await _read_stopsequence(train_id)
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
                websocket.receive_text(), timeout=settings.ws_poll_interval
            )
            if message == "ping":
                await websocket.send_text("pong")
        except asyncio.TimeoutError:
            continue
        except (WebSocketDisconnect, asyncio.CancelledError):
            return


@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy_to_backend(path: str, request: Request) -> Response:
    """Proxy all non-position API calls to backend."""
    if http_client is None:
        return JSONResponse(status_code=503, content={"detail": "Gateway not ready"})

    try:
        backend_response = await http_client.request(
            method=request.method,
            url=f"/api/v1/{path}",
            params=request.query_params,
            content=await request.body(),
            headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
        )
    except httpx.ReadTimeout:
        logger.warning("Backend read timeout for %s %s", request.method, path)
        return JSONResponse(status_code=504, content={"detail": "Backend read timeout"})
    except httpx.ConnectError:
        logger.warning("Backend connection error for %s %s", request.method, path)
        return JSONResponse(status_code=502, content={"detail": "Backend unavailable"})

    excluded_headers = {"content-encoding", "transfer-encoding", "connection"}
    headers = {
        key: value
        for key, value in backend_response.headers.items()
        if key.lower() not in excluded_headers
    }
    return Response(
        content=backend_response.content,
        status_code=backend_response.status_code,
        headers=headers,
        media_type=backend_response.headers.get("content-type"),
    )
