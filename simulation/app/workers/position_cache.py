"""In-process background runtime for refreshing the Redis position cache."""

from __future__ import annotations

import asyncio
import threading

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.services.position_cache import build_position_cache_updater
from app.services.reference_data import RedisReferenceReader

setup_logging()
logger = get_logger(__name__)


class PositionCacheRuntime:
    """Owns a background thread for the Redis position cache updater."""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._thread_main,
            name="position_cache_runtime",
            daemon=True,
        )
        self._thread.start()
        logger.info("Position cache runtime thread started")

    async def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            await asyncio.to_thread(thread.join, 30)
            if thread.is_alive():
                logger.warning("Position cache runtime thread did not stop cleanly")
            self._thread = None

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:  # noqa: BLE001
            logger.error("Position cache runtime crashed", error=str(exc))

    async def _wait_for_reference_data(self, redis_client: Redis) -> None:
        reader = RedisReferenceReader(redis_client)
        while not self._stop_event.is_set():
            try:
                if await reader.is_ready():
                    return
            except Exception as exc:  # noqa: BLE001
                logger.warning("Waiting for reference data", error=str(exc))

            logger.info("Reference data not ready yet; retrying")
            await asyncio.sleep(5)

    async def _run(self) -> None:
        engine = create_async_engine(
            str(settings.database_url),
            echo=settings.debug,
            future=True,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
        session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        redis_client = Redis.from_url(str(settings.redis_url), decode_responses=True)
        updater = None

        try:
            await redis_client.ping()
            await self._wait_for_reference_data(redis_client)

            updater = build_position_cache_updater(session_factory, redis_client)
            updater.start()
            logger.info(
                "Position cache runtime ready",
                interval=settings.get_position_cache_interval_seconds(),
            )

            while not self._stop_event.is_set():
                await asyncio.sleep(1)
        finally:
            if updater is not None:
                await updater.stop()
            await redis_client.aclose()
            await engine.dispose()
            logger.info("Position cache runtime stopped")


def build_position_cache_runtime() -> PositionCacheRuntime:
    return PositionCacheRuntime()
