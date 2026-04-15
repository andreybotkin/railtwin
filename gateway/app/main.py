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

from app.redis_payloads import (
    filter_feature_collection_by_bbox,
    filter_positions_by_bbox,
    filter_stations_by_bbox,
    filter_trajectories_by_bbox,
    parse_bbox,
    read_map_network_edges,
    read_map_stations,
    read_individual_trajectory,
    read_position,
    read_positions,
    read_stopsequence,
    read_topology_metadata,
    read_trajectories,
)
from app.websocket_streams import (
    stream_positions,
    stream_stopsequence,
    stream_trajectories,
)

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Thailand Railway Digital Twin Gateway"
    app_version: str = "1.0.0"
    simulation_url: str = "http://simulation:8000"
    redis_url: str = "redis://redis:6379/0"
    ws_poll_interval: int = 10
    trajectory_poll_interval: int = 10
    viewport_buffer_ratio: float = 0.1
    viewport_min_buffer_degrees: float = 0.05
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
        base_url=settings.simulation_url,
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


def _validate_bbox_or_raise(bbox: str) -> None:
    if parse_bbox(bbox) is None:
        raise HTTPException(
            status_code=400,
            detail="bbox must be a comma-separated minLon,minLat,maxLon,maxLat viewport",
        )


def _filter_positions_for_viewport(
    positions: list[dict[str, Any]],
    bbox: str,
) -> list[dict[str, Any]]:
    return filter_positions_by_bbox(
        positions,
        bbox,
        buffer_ratio=settings.viewport_buffer_ratio,
        min_buffer_degrees=settings.viewport_min_buffer_degrees,
    )


def _filter_trajectories_for_viewport(
    trajectories: list[dict[str, Any]],
    bbox: str,
) -> list[dict[str, Any]]:
    return filter_trajectories_by_bbox(
        trajectories,
        bbox,
        buffer_ratio=settings.viewport_buffer_ratio,
        min_buffer_degrees=settings.viewport_min_buffer_degrees,
    )


def _filter_stations_for_viewport(
    stations: list[dict[str, Any]],
    bbox: str,
) -> list[dict[str, Any]]:
    return filter_stations_by_bbox(
        stations,
        bbox,
        buffer_ratio=settings.viewport_buffer_ratio,
        min_buffer_degrees=settings.viewport_min_buffer_degrees,
    )


def _filter_network_for_viewport(
    collection: dict[str, Any],
    bbox: str,
) -> dict[str, Any]:
    return filter_feature_collection_by_bbox(
        collection,
        bbox,
        buffer_ratio=settings.viewport_buffer_ratio,
        min_buffer_degrees=settings.viewport_min_buffer_degrees,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    if redis_client is None:
        return {"status": "not_ready"}
    await redis_client.ping()
    return {"status": "ready"}


@app.get("/api/v1/system/topology")
async def get_topology_metadata() -> dict[str, Any]:
    metadata = await read_topology_metadata(redis_client)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Topology metadata not found")
    return metadata


@app.get("/api/v1/map/all")
async def get_map_all() -> dict[str, Any]:
    """Return the complete railway network map (all stations + all edges) from Redis.

    No bbox filtering — returns the full dataset so the client can render the
    entire network at startup without additional requests.
    """
    stations = await read_map_stations(redis_client)
    network_edges = await read_map_network_edges(redis_client)
    return {
        "stations": stations,
        "network_edges": network_edges,
    }


@app.get("/api/v1/map/viewport")
async def get_map_viewport(bbox: str) -> dict[str, Any]:
    _validate_bbox_or_raise(bbox)
    stations = await read_map_stations(redis_client)
    network_edges = await read_map_network_edges(redis_client)
    topology = await read_topology_metadata(redis_client)
    return {
        "bbox": bbox,
        "topology": topology,
        "stations": _filter_stations_for_viewport(stations, bbox),
        "network_edges": _filter_network_for_viewport(network_edges, bbox),
    }


@app.get("/api/v1/trains/positions")
async def get_positions(bbox: str) -> list[dict[str, Any]]:
    """Get active train positions for the current viewport plus a small buffer."""
    _validate_bbox_or_raise(bbox)
    positions = await read_positions(redis_client)
    return _filter_positions_for_viewport(positions, bbox)


@app.get("/api/v1/trains/{train_id}/position")
async def get_train_position(train_id: int) -> dict[str, Any]:
    position = await read_position(redis_client, train_id)
    if position is None:
        raise HTTPException(status_code=404, detail=f"Position for train {train_id} not found")
    payload = dict(position)
    payload.setdefault("timestamp", datetime.now(UTC).isoformat())
    return payload


@app.websocket("/ws/trains")
async def ws_trains(websocket: WebSocket) -> None:
    try:
        await stream_positions(
            websocket,
            read_positions=lambda: read_positions(redis_client),
            filter_positions=_filter_positions_for_viewport,
            ws_poll_interval=settings.ws_poll_interval,
            logger=logger,
        )
    except (WebSocketDisconnect, asyncio.CancelledError):
        return


@app.websocket("/ws/trains/{train_id}")
async def ws_single_train(websocket: WebSocket, train_id: int) -> None:
    try:
        await stream_positions(
            websocket,
            read_positions=lambda: read_positions(redis_client),
            filter_positions=_filter_positions_for_viewport,
            ws_poll_interval=settings.ws_poll_interval,
            logger=logger,
            train_id=train_id,
        )
    except (WebSocketDisconnect, asyncio.CancelledError):
        return


@app.websocket("/ws/trajectory")
async def ws_trajectory(websocket: WebSocket) -> None:
    """WebSocket endpoint serving geops-compatible trajectory objects with time_intervals.

    Connects to this instead of /ws/trains for smooth client-side temporal interpolation.
    """
    try:
        await stream_trajectories(
            websocket,
            read_trajectories=lambda: read_trajectories(redis_client),
            filter_trajectories=_filter_trajectories_for_viewport,
            update_interval_seconds=settings.trajectory_poll_interval,
        )
    except (WebSocketDisconnect, asyncio.CancelledError):
        return


@app.get("/api/v1/trains/trajectories")
async def get_trajectories(bbox: str) -> list[dict[str, Any]]:
    """REST endpoint: get active train trajectories for the current viewport.

    Trajectory objects contain time_intervals for client-side temporal interpolation.
    """
    _validate_bbox_or_raise(bbox)
    trajectories = await read_trajectories(redis_client)
    return _filter_trajectories_for_viewport(trajectories, bbox)


@app.get("/api/v1/trains/{train_id}/trajectory")
async def get_train_trajectory(train_id: int) -> dict[str, Any]:
    """Get geops-compatible trajectory object for a single train.

    Reads from the individual ``train:trajectory:{id}`` Redis key written by
    position_cache.py — no need to fetch and scan the full list.
    """
    trajectory = await read_individual_trajectory(redis_client, train_id)
    if trajectory is None:
        raise HTTPException(
            status_code=404,
            detail=f"Trajectory for train {train_id} not found",
        )
    return trajectory


@app.get("/api/v1/trains/{train_id}/stopsequence")
async def get_train_stopsequence(train_id: int) -> list[dict[str, Any]]:
    """Get the upcoming stop sequence for a specific train."""
    seq = await read_stopsequence(redis_client, train_id)
    if seq is None:
        raise HTTPException(
            status_code=404,
            detail=f"Stop sequence for train {train_id} not found",
        )
    return seq


@app.websocket("/ws/stopsequence/{train_id}")
async def ws_stopsequence(websocket: WebSocket, train_id: int) -> None:
    """WebSocket that pushes stop-sequence updates for a specific train."""
    try:
        await stream_stopsequence(
            websocket,
            train_id=train_id,
            read_stopsequence=lambda resolved_train_id: read_stopsequence(redis_client, resolved_train_id),
            ws_poll_interval=settings.ws_poll_interval,
        )
    except (WebSocketDisconnect, asyncio.CancelledError):
        return


@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy_to_simulation(path: str, request: Request) -> Response:
    """Proxy all non-position API calls to simulation."""
    if http_client is None:
        return JSONResponse(status_code=503, content={"detail": "Gateway not ready"})

    try:
        simulation_response = await http_client.request(
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
        for key, value in simulation_response.headers.items()
        if key.lower() not in excluded_headers
    }
    return Response(
        content=simulation_response.content,
        status_code=simulation_response.status_code,
        headers=headers,
        media_type=simulation_response.headers.get("content-type"),
    )
