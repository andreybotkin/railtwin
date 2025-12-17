"""WebSocket endpoint for real-time train position updates.

This module provides WebSocket connections for streaming live train
position updates to connected clients.
"""

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.logging import get_logger
from app.models.database import async_session_factory
from app.services.simulation import TrainSimulationService

logger = get_logger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections for train position updates.

    Handles connection lifecycle and message broadcasting to
    all connected clients.
    """

    def __init__(self) -> None:
        """Initialize connection manager."""
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection.

        Args:
            websocket: WebSocket connection to accept.
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            "WebSocket connected",
            total_connections=len(self.active_connections),
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket.

        Args:
            websocket: WebSocket connection to remove.
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            "WebSocket disconnected",
            total_connections=len(self.active_connections),
        )

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast a message to all connected clients.

        Args:
            message: Message dictionary to send.
        """
        if not self.active_connections:
            return

        message_str = json.dumps(message, default=str)
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(message_str)
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


# Global connection manager instance
manager = ConnectionManager()


@router.websocket("/trains")
async def websocket_trains(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time train position updates.

    Clients connecting to this endpoint will receive periodic updates
    with current positions of all active trains.

    Args:
        websocket: WebSocket connection.
    """
    await manager.connect(websocket)

    try:
        # Send initial positions immediately
        async with async_session_factory() as session:
            simulation_service = TrainSimulationService(session)
            positions = await simulation_service.get_all_active_trains()
            await websocket.send_json({
                "type": "positions",
                "data": positions,
                "timestamp": asyncio.get_event_loop().time(),
            })

        # Keep connection alive and send updates
        while True:
            try:
                # Wait for any message (heartbeat) from client
                # with a timeout for sending updates
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=settings.ws_heartbeat_interval,
                    )
                    # Handle client messages (ping/pong, etc.)
                    if message == "ping":
                        await websocket.send_text("pong")
                except asyncio.TimeoutError:
                    # Timeout - send position update
                    async with async_session_factory() as session:
                        simulation_service = TrainSimulationService(session)
                        positions = await simulation_service.get_all_active_trains()
                        await websocket.send_json({
                            "type": "positions",
                            "data": positions,
                            "timestamp": asyncio.get_event_loop().time(),
                        })

            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)


@router.websocket("/trains/{train_id}")
async def websocket_single_train(
    websocket: WebSocket,
    train_id: int,
) -> None:
    """WebSocket endpoint for tracking a single train.

    Args:
        websocket: WebSocket connection.
        train_id: Train ID to track.
    """
    await websocket.accept()

    try:
        while True:
            try:
                # Wait for heartbeat with timeout
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=settings.ws_heartbeat_interval,
                    )
                    if message == "ping":
                        await websocket.send_text("pong")
                except asyncio.TimeoutError:
                    # Send update for this specific train
                    async with async_session_factory() as session:
                        simulation_service = TrainSimulationService(session)
                        positions = await simulation_service.get_all_active_trains()

                        # Find position for requested train
                        train_position = next(
                            (p for p in positions if p["train_id"] == train_id),
                            None,
                        )

                        await websocket.send_json({
                            "type": "position",
                            "train_id": train_id,
                            "data": train_position,
                            "timestamp": asyncio.get_event_loop().time(),
                        })

            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    finally:
        logger.info("Single train WebSocket disconnected", train_id=train_id)
