"""Background updater that computes train positions and caches them in Redis."""

import asyncio
import json
import time as _time

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.services.simulation import TrainSimulationService

logger = get_logger(__name__)

REDIS_POSITIONS_KEY = "train:positions:latest"
REDIS_TRAJECTORIES_KEY = "train:trajectories:latest"
REDIS_POSITIONS_TTL = 30
# Trajectories cover LOOKAHEAD_SECONDS ahead; refresh before they expire.
# TTL is set a bit longer than the update interval to handle slow cycles.
REDIS_TRAJECTORIES_TTL = 90
# Individual trajectory/stopsequence keys for direct lookups by train_id
REDIS_INDIVIDUAL_TRAJECTORY_TTL = 330   # lookahead (300 s) + 30 s buffer
REDIS_STOPSEQUENCE_TTL = 3600           # 1 hour — stop sequences change slowly
# Metrics key for monitoring cycle health
REDIS_METRICS_KEY = "system:position_cache:metrics"
REDIS_METRICS_TTL = 60


class PositionCacheUpdater:
    """Periodically recalculates train positions and stores them in Redis.

    Stores two Redis keys on every cycle:
    - train:positions:latest  — simple position snapshots (backward-compat)
    - train:trajectories:latest — geops-style trajectory objects with time_intervals
      for smooth client-side temporal interpolation (mobility-toolbox-js pattern)
    """

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
            active_trains = 0
            error_count = 0
            try:
                async with self._session_factory() as session:
                    simulation_service = TrainSimulationService(
                        session,
                        redis_client=self._redis,
                    )
                    # Single-pass: TTS delays loaded once, schedules/geometry bulk-loaded
                    positions, trajectories, stop_sequences = (
                        await simulation_service.get_all_active_train_data()
                    )
                active_trains = len(positions)

                # Write all Redis keys in one pipeline round-trip
                pipe = self._redis.pipeline()
                pipe.setex(
                    REDIS_POSITIONS_KEY,
                    REDIS_POSITIONS_TTL,
                    json.dumps(positions, default=str),
                )
                pipe.setex(
                    REDIS_TRAJECTORIES_KEY,
                    REDIS_TRAJECTORIES_TTL,
                    json.dumps(trajectories, default=str),
                )
                for traj in trajectories:
                    train_id = traj["properties"]["train_id"]
                    pipe.setex(
                        f"train:trajectory:{train_id}",
                        REDIS_INDIVIDUAL_TRAJECTORY_TTL,
                        json.dumps(traj, default=str),
                    )
                for train_id, seq in stop_sequences.items():
                    pipe.setex(
                        f"train:stopsequence:{train_id}",
                        REDIS_STOPSEQUENCE_TTL,
                        json.dumps(seq, default=str),
                    )
                await pipe.execute()

            except Exception as exc:
                error_count += 1
                logger.error("PositionCacheUpdater error", error=str(exc))

            # Record cycle metrics for health monitoring
            cycle_ms = int((asyncio.get_running_loop().time() - tick_start) * 1000)
            try:
                await self._redis.setex(
                    REDIS_METRICS_KEY,
                    REDIS_METRICS_TTL,
                    json.dumps({
                        "last_update_ms": int(_time.time() * 1000),
                        "cycle_duration_ms": cycle_ms,
                        "active_trains": active_trains,
                        "error_count": error_count,
                    }),
                )
            except Exception:
                pass  # Never let metrics failure break the main loop

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
