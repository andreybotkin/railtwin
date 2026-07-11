"""Public edge gateway for the Thailand Railway Digital Twin."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from contextlib import asynccontextmanager
from time import perf_counter
from typing import TYPE_CHECKING, Annotated, Any

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from app.redis_payloads import (
    filter_feature_collection_by_bbox,
    filter_stations_by_bbox,
    filter_trajectories_by_bbox,
    parse_bbox,
    read_individual_trajectory,
    read_map_network_edges,
    read_map_stations,
    read_stopsequence,
    read_topology_metadata,
    read_trajectories,
)
from app.schemas import MapSnapshot, StopSequenceItem, TopologyMetadata, Trajectory
from app.websocket_streams import stream_stopsequence, stream_trajectories

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Thailand Railway Digital Twin Gateway"
    app_version: str = "2.1.0"
    simulation_url: str = "http://simulation:8000"
    redis_url: str = "redis://redis:6379/0"
    trajectory_poll_interval: int = 10
    ws_poll_interval: int = 10
    viewport_buffer_ratio: float = 0.1
    viewport_min_buffer_degrees: float = 0.05
    gzip_minimum_size: int = 1_024
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
                        str(origin).strip() for origin in decoded if str(origin).strip()
                    ]
            return [
                origin.strip() for origin in parsed_value.split(",") if origin.strip()
            ]
        return list(value)


settings = Settings()
redis_client: Redis | None = None
http_client: httpx.AsyncClient | None = None
_map_snapshot_cache: tuple[str, bytes, str] | None = None
_map_snapshot_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    global redis_client, http_client, _map_snapshot_cache
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    http_client = httpx.AsyncClient(
        base_url=settings.simulation_url,
        timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0),
    )
    _map_snapshot_cache = None
    yield
    if http_client is not None:
        await http_client.aclose()
    if redis_client is not None:
        await redis_client.aclose()


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self), microphone=()"
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=settings.gzip_minimum_size)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=[
        "ETag",
        "Server-Timing",
        "X-Topology-Cache",
        "X-Trajectory-Count",
    ],
)


def _validate_bbox_or_raise(bbox: str) -> None:
    if parse_bbox(bbox) is None:
        raise HTTPException(
            status_code=400,
            detail="bbox must be a comma-separated minLon,minLat,maxLon,maxLat viewport",
        )


def _filter_trajectories_for_viewport(
    trajectories: list[dict[str, Any]],
    bbox: str | None,
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


@app.get("/ready", response_model=None)
async def ready() -> dict[str, str] | JSONResponse:
    if redis_client is None:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "detail": "Redis client not initialized"},
        )
    try:
        await redis_client.ping()
        topology = await read_topology_metadata(redis_client)
        if topology is None:
            raise RuntimeError("Topology snapshot is not available")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gateway readiness check failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "detail": "Runtime cache not ready"},
        )
    return {"status": "ready"}


@app.get("/api/v1/system/topology", response_model=TopologyMetadata | None)
async def get_topology_metadata() -> TopologyMetadata:
    metadata = await read_topology_metadata(redis_client)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Topology metadata not found")
    return metadata


def _etag_for_topology_version(version: str) -> str:
    digest = hashlib.sha256(version.encode()).hexdigest()[:20]
    return f'W/"{digest}"'


async def _get_cached_map_snapshot() -> tuple[bytes, str, bool]:
    global _map_snapshot_cache

    topology = await read_topology_metadata(redis_client)
    topology_version = topology.topology_version if topology else "missing"
    cached = _map_snapshot_cache
    if cached is not None and cached[0] == topology_version:
        return cached[1], cached[2], True

    async with _map_snapshot_lock:
        cached = _map_snapshot_cache
        if cached is not None and cached[0] == topology_version:
            return cached[1], cached[2], True

        stations, network_edges = await asyncio.gather(
            read_map_stations(redis_client),
            read_map_network_edges(redis_client),
        )
        body = (
            MapSnapshot(
                topology=topology,
                stations=stations,
                network_edges=network_edges,
            )
            .model_dump_json()
            .encode()
        )
        etag = _etag_for_topology_version(topology_version)
        _map_snapshot_cache = (topology_version, body, etag)
        return body, etag, False


@app.get("/api/v1/map/topology")
async def get_map_topology(request: Request) -> Response:
    started_at = perf_counter()
    body, etag, cache_hit = await _get_cached_map_snapshot()
    duration_ms = (perf_counter() - started_at) * 1_000
    cache_status = "HIT" if cache_hit else "MISS"
    headers = {
        "ETag": etag,
        "Cache-Control": "public, max-age=300, stale-while-revalidate=86400",
        "Vary": "Accept-Encoding",
        "X-Topology-Cache": cache_status,
        "Server-Timing": f'topology;dur={duration_ms:.2f};desc="{cache_status}"',
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


@app.get("/api/v1/trains/trajectories", response_model=list[Trajectory])
async def get_trajectories(
    response: Response,
    bbox: str | None = None,
) -> list[dict[str, Any]]:
    started_at = perf_counter()
    trajectories = await read_trajectories(redis_client)
    if bbox is not None:
        _validate_bbox_or_raise(bbox)
        trajectories = _filter_trajectories_for_viewport(trajectories, bbox)
    duration_ms = (perf_counter() - started_at) * 1_000
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Trajectory-Count"] = str(len(trajectories))
    response.headers["Server-Timing"] = f"trajectories;dur={duration_ms:.2f}"
    return trajectories


@app.get("/api/v1/trains/{train_id}/trajectory", response_model=Trajectory)
async def get_train_trajectory(train_id: int) -> dict[str, Any]:
    trajectory = await read_individual_trajectory(redis_client, train_id)
    if trajectory is None:
        raise HTTPException(
            status_code=404,
            detail=f"Trajectory for train {train_id} not found",
        )
    return trajectory


@app.get(
    "/api/v1/trains/{train_id}/stopsequence",
    response_model=list[StopSequenceItem],
)
async def get_train_stopsequence(train_id: int) -> list[dict[str, Any]]:
    sequence = await read_stopsequence(redis_client, train_id)
    if sequence is None:
        raise HTTPException(
            status_code=404,
            detail=f"Stop sequence for train {train_id} not found",
        )
    return sequence


@app.websocket("/ws/trajectory")
async def ws_trajectory(websocket: WebSocket) -> None:
    initial_bbox = websocket.query_params.get("bbox")
    if initial_bbox is not None and parse_bbox(initial_bbox) is None:
        await websocket.accept()
        await websocket.close(code=1008, reason="Invalid bbox")
        return
    try:
        await stream_trajectories(
            websocket,
            read_trajectories=lambda: read_trajectories(redis_client),
            filter_trajectories=_filter_trajectories_for_viewport,
            update_interval_seconds=settings.trajectory_poll_interval,
            initial_bbox=initial_bbox,
        )
    except (WebSocketDisconnect, asyncio.CancelledError):
        return


@app.websocket("/ws/stopsequence/{train_id}")
async def ws_stopsequence(websocket: WebSocket, train_id: int) -> None:
    try:
        await stream_stopsequence(
            websocket,
            train_id=train_id,
            read_stopsequence=lambda resolved_id: read_stopsequence(
                redis_client, resolved_id
            ),
            ws_poll_interval=settings.ws_poll_interval,
        )
    except (WebSocketDisconnect, asyncio.CancelledError):
        return


SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "x-api-key",
    "x-auth-token",
}
ALLOWED_HEADERS = {
    "accept",
    "accept-encoding",
    "accept-language",
    "content-type",
    "content-length",
    "if-none-match",
    "if-modified-since",
}


def _validate_path(path: str) -> None:
    if not path:
        return
    lower_path = path.lower()
    if (
        "://" in lower_path
        or lower_path.startswith("//")
        or lower_path.startswith("/http")
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid path: potential SSRF attack detected",
        )
    if " " in path or "\0" in path:
        raise HTTPException(status_code=400, detail="Invalid path: malformed path")


@app.api_route("/api/v1/{path:path}", methods=["GET", "OPTIONS", "HEAD"])
async def proxy_to_simulation(path: str, request: Request) -> Response:
    _validate_path(path)
    if http_client is None:
        return JSONResponse(status_code=503, content={"detail": "Gateway not ready"})

    forward_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() in ALLOWED_HEADERS
    }
    try:
        simulation_response = await http_client.request(
            method=request.method,
            url=f"/api/v1/{path}",
            params=request.query_params,
            content=await request.body(),
            headers=forward_headers,
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
