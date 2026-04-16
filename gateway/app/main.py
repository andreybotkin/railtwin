import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Annotated

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
    filter_stations_by_bbox,
    filter_trajectories_by_bbox,
    parse_bbox,
    read_map_network_edges,
    read_map_stations,
    read_stopsequence,
    read_topology_metadata,
    read_trajectories,
    read_trajectory,
)
from app.schemas import Trajectory
from app.websocket_streams import stream_stopsequence, stream_trajectories

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    app_name: str = "Thailand Railway Digital Twin Gateway"
    app_version: str = "1.0.0"
    simulation_url: str = "http://simulation:8000"
    redis_url: str = "redis://redis:6379/0"
    trajectory_poll_interval: int = 10
    ws_poll_interval: int = 10
    viewport_buffer_ratio: float = 0.1
    viewport_min_buffer_degrees: float = 0.05
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000", "http://localhost:8002"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            if value.startswith("["):
                decoded = json.loads(value)
                return [str(origin).strip() for origin in decoded if str(origin).strip()]
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return list(value)


settings = Settings()
redis_client: Redis | None = None
http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    global redis_client, http_client
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    http_client = httpx.AsyncClient(base_url=settings.simulation_url, timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0))
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
        response.headers["Cache-Control"] = "no-store"
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def _validate_bbox_or_raise(bbox: str) -> None:
    if parse_bbox(bbox) is None:
        raise HTTPException(status_code=400, detail="bbox must be minLon,minLat,maxLon,maxLat")


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


@app.get("/api/v1/map/topology")
async def get_map_topology(request: Request, bbox: str | None = None) -> Response:
    stations = await read_map_stations(redis_client)
    edges = await read_map_network_edges(redis_client)
    if bbox:
        _validate_bbox_or_raise(bbox)
        stations = filter_stations_by_bbox(
            stations,
            bbox,
            buffer_ratio=settings.viewport_buffer_ratio,
            min_buffer_degrees=settings.viewport_min_buffer_degrees,
        )
        edges = filter_feature_collection_by_bbox(
            edges,
            bbox,
            buffer_ratio=settings.viewport_buffer_ratio,
            min_buffer_degrees=settings.viewport_min_buffer_degrees,
        )
    payload = {"stations": stations, "edges": edges}
    encoded = json.dumps(payload, separators=(",", ":"))
    etag = hashlib.sha1(encoded.encode("utf-8")).hexdigest()  # noqa: S324
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return Response(content=encoded, media_type="application/json", headers={"ETag": etag})


@app.get("/api/v1/trains/trajectories", response_model=list[Trajectory])
async def get_trajectories(bbox: str | None = None) -> list[dict[str, Any]]:
    trajectories = await read_trajectories(redis_client)
    if bbox is None:
        return trajectories
    _validate_bbox_or_raise(bbox)
    return filter_trajectories_by_bbox(
        trajectories,
        bbox,
        buffer_ratio=settings.viewport_buffer_ratio,
        min_buffer_degrees=settings.viewport_min_buffer_degrees,
    )


@app.get("/api/v1/trains/{train_id}/trajectory", response_model=Trajectory)
async def get_train_trajectory(train_id: int) -> dict[str, Any]:
    trajectory = await read_trajectory(redis_client, train_id)
    if trajectory is None:
        raise HTTPException(status_code=404, detail=f"Trajectory for train {train_id} not found")
    return trajectory


@app.get("/api/v1/trains/{train_id}/stopsequence")
async def get_train_stopsequence(train_id: int) -> list[dict[str, Any]]:
    seq = await read_stopsequence(redis_client, train_id)
    if seq is None:
        raise HTTPException(status_code=404, detail=f"Stop sequence for train {train_id} not found")
    return seq


@app.websocket("/ws/trajectory")
async def ws_trajectory(websocket: WebSocket) -> None:
    try:
        await stream_trajectories(
            websocket,
            read_trajectories=lambda: read_trajectories(redis_client),
            filter_trajectories=lambda data, bbox: filter_trajectories_by_bbox(data, bbox, buffer_ratio=settings.viewport_buffer_ratio, min_buffer_degrees=settings.viewport_min_buffer_degrees),
            update_interval_seconds=settings.trajectory_poll_interval,
        )
    except (WebSocketDisconnect, asyncio.CancelledError):
        return


@app.websocket("/ws/stopsequence/{train_id}")
async def ws_stopsequence(websocket: WebSocket, train_id: int) -> None:
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
        return JSONResponse(status_code=504, content={"detail": "Backend read timeout"})
    except httpx.ConnectError:
        return JSONResponse(status_code=502, content={"detail": "Backend unavailable"})

    excluded_headers = {"content-encoding", "transfer-encoding", "connection"}
    headers = {k: v for k, v in simulation_response.headers.items() if k.lower() not in excluded_headers}
    return Response(content=simulation_response.content, status_code=simulation_response.status_code, headers=headers, media_type=simulation_response.headers.get("content-type"))
