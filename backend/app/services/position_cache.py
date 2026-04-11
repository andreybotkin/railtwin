"""Background updater that computes train positions and caches them in Redis."""

import asyncio
import json

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.services.simulation import TrainSimulationService

logger = get_logger(__name__)

REDIS_POSITIONS_KEY = "train:positions:latest"
REDIS_POSITIONS_TTL = 30


class PositionCacheUpdater:
    """Periodically recalculates train positions and stores them in Redis."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        redis_client: Redis,
        interval_seconds: int,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis_client
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None

    async def _run(self) -> None:
        while True:
            tick_start = asyncio.get_running_loop().time()
            try:
                async with self._session_factory() as session:
                    simulation_service = TrainSimulationService(
                        session,
                        redis_client=self._redis,
                    )
                    positions = await simulation_service.get_all_active_trains()

                await self._redis.setex(
                    REDIS_POSITIONS_KEY,
                    REDIS_POSITIONS_TTL,
                    json.dumps(positions, default=str),
                )
            except Exception as exc:
                logger.error("PositionCacheUpdater error", error=str(exc))

            elapsed = asyncio.get_running_loop().time() - tick_start
            await asyncio.sleep(max(0.0, self._interval_seconds - elapsed))

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="position_cache_updater")
            logger.info("PositionCacheUpdater started", interval=self._interval_seconds)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


def build_position_cache_updater(
    session_factory: async_sessionmaker,
    redis_client: Redis,
) -> PositionCacheUpdater:
    """Factory for a Redis train positions cache updater."""
    return PositionCacheUpdater(
        session_factory=session_factory,
        redis_client=redis_client,
        interval_seconds=settings.ws_heartbeat_interval,
    )
