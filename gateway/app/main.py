"""Stateless gateway for website traffic and train positions from Redis.

TODO (deferred — geops patterns for future iterations):
- Topic-based architecture: route WS subscriptions to separate pub/sub channels
  per topic (e.g., "trains", "stations", "disruptions") like trafimage-maps topics
- Rate limiting per client IP for WS connections
- Message compression (permessage-deflate) for large position payloads
- Prometheus /metrics endpoint for observability
- Graceful shutdown: drain WS clients before stopping
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
    http_client = httpx.AsyncClient(base_url=settings.backend_url, timeout=15.0)
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


async def _read_position(train_id: int) -> dict[str, Any] | None:
    positions = await _read_positions()
    return next((position for position in positions if position["train_id"] == train_id), None)


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


@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy_to_backend(path: str, request: Request) -> Response:
    """Proxy all non-position API calls to backend."""
    if http_client is None:
        return JSONResponse(status_code=503, content={"detail": "Gateway not ready"})

    backend_response = await http_client.request(
        method=request.method,
        url=f"/api/v1/{path}",
        params=request.query_params,
        content=await request.body(),
        headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
    )

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
