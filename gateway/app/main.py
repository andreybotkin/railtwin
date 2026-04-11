"""Stateless gateway for website traffic and train positions from Redis."""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis

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
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:8002",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    if redis_client is None:
        return {"status": "not_ready"}
    await redis_client.ping()
    return {"status": "ready"}


@app.get("/api/v1/trains/positions")
async def get_positions() -> list[dict[str, Any]]:
    return await _read_positions()


async def _ws_positions_loop(websocket: WebSocket, train_id: int | None = None) -> None:
    await websocket.accept()
    last_payload: str | None = None

    while True:
        positions = await _read_positions()
        payload: dict[str, Any]

        if train_id is None:
            payload = {
                "type": "positions",
                "data": positions,
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

        try:
            message = await asyncio.wait_for(websocket.receive_text(), timeout=settings.ws_poll_interval)
            if message == "ping":
                await websocket.send_text("pong")
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
