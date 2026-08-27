"""Background publisher: recomputes trajectories and writes them to Redis.

This replaces the legacy dual snapshot + trajectory model.  The single source
of truth is now :class:`app.domain.trajectory.Trajectory` — one Redis key per
active train plus a latest-list for bulk reads.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.services.reference_data import RedisReferenceDataLoader, RedisReferenceReader
from app.services.simulation import TrainSimulationService

logger = get_logger(__name__)

REDIS_TRAJECTORIES_KEY = "train:trajectories:latest"
REDIS_TRAJECTORY_KEY_PREFIX = "train:trajectory:"
REDIS_STOPSEQUENCE_KEY_PREFIX = "train:stopsequence:"
REDIS_MAP_STATIONS_KEY = "map:stations:all"
REDIS_MAP_NETWORK_EDGES_KEY = "map:network_edges:all"
REDIS_TOPOLOGY_METADATA_KEY = "system:topology:metadata"
REFERENCE_DATA_REBUILD_LOCK_KEY = "system:locks:reference-data-rebuild"

REDIS_TRAJECTORIES_TTL = max(90, settings.trajectory_lookahead_seconds + 30)
REDIS_INDIVIDUAL_TRAJECTORY_TTL = settings.trajectory_lookahead_seconds + 60
REDIS_STOPSEQUENCE_TTL = 3600
REDIS_TOPOLOGY_METADATA_TTL = 3600
REFERENCE_DATA_REBUILD_LOCK_TTL = 300

_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class PositionCacheUpdater:
    """Periodically rebuild trajectories and keep Redis runtime data healthy."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        redis_client: Redis,
        interval_seconds: int,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis_client
        self._interval_seconds = max(5, interval_seconds)
        self._task: asyncio.Task | None = None
        self._static_map_topology_version: str | None = None
        self._reader = RedisReferenceReader(redis_client)

    async def _run(self) -> None:
        while True:
            tick_start = asyncio.get_running_loop().time()
            try:
                await self._tick()
            except Exception as exc:  # noqa: BLE001 - keep background loop alive
                logger.error("PositionCacheUpdater error", error=str(exc))

            elapsed = asyncio.get_running_loop().time() - tick_start
            await asyncio.sleep(max(0.0, self._interval_seconds - elapsed))

    async def _ensure_reference_data(self) -> bool:
        """Restore the PostgreSQL-backed Redis snapshot after cache loss.

        Redis is a cache, so a restart or eviction must not require an operator to
        restart the simulation pod. A distributed lock prevents multiple workers
        from rebuilding and clearing the same namespace concurrently.
        """
        if await self._reader.is_ready():
            return True

        token = secrets.token_urlsafe(24)
        acquired = await self._redis.set(
            REFERENCE_DATA_REBUILD_LOCK_KEY,
            token,
            ex=REFERENCE_DATA_REBUILD_LOCK_TTL,
            nx=True,
        )
        if not acquired:
            logger.info("Reference data rebuild already in progress")
            return False

        try:
            logger.warning(
                "Reference data missing from Redis; rebuilding from PostgreSQL"
            )
            async with self._session_factory() as session:
                loader = RedisReferenceDataLoader(session, self._redis)
                metadata = await loader.load()
            self._static_map_topology_version = None
            logger.info("Reference data recovery completed", **metadata)
            return metadata.get("load_status") == "ready"
        except Exception as exc:
            logger.error("Reference data recovery failed", error=str(exc), exc_info=exc)
            return False
        finally:
            try:
                await self._redis.eval(
                    _RELEASE_LOCK_SCRIPT,
                    1,
                    REFERENCE_DATA_REBUILD_LOCK_KEY,
                    token,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Could not release reference data rebuild lock",
                    error=str(exc),
                )

    async def _tick(self) -> None:
        if not await self._ensure_reference_data():
            return

        topology_payload = await self._reader.get_topology() or {}
        topology_version = topology_payload.get("topology_version")

        async with self._session_factory() as session:
            service = TrainSimulationService(session, redis_client=self._redis)
            trajectories, stop_sequences = await service.get_all_active_train_data(
                topology_version=(
                    str(topology_version) if topology_version is not None else None
                ),
            )

        # Refresh static map payloads after topology changes and after Redis data
        # loss. The in-process version marker alone is insufficient because it
        # survives a Redis restart while the Redis keys do not.
        map_key_count = await self._redis.exists(
            REDIS_MAP_NETWORK_EDGES_KEY,
            REDIS_MAP_STATIONS_KEY,
        )
        static_map_missing = int(map_key_count) < 2
        static_payloads: tuple[dict[str, Any], list[dict[str, Any]]] | None = None
        if topology_version is not None and (
            str(topology_version) != self._static_map_topology_version
            or static_map_missing
        ):
            edges = await self._reader.get_network_edges()
            tracks_only = [
                edge
                for edge in edges
                if edge.get("properties", {}).get("edge_kind") == "track"
            ]
            stations, _ = await self._reader.list_stations(page=1, size=10000)
            station_ids_with_schedules = (
                await self._reader.get_station_ids_with_schedules()
            )
            stations = [
                {
                    **station,
                    "has_schedule": int(station["id"]) in station_ids_with_schedules,
                }
                for station in stations
            ]
            static_payloads = (
                {"type": "FeatureCollection", "features": tracks_only},
                stations,
            )
            self._static_map_topology_version = str(topology_version)

        pipe = self._redis.pipeline()

        trajectories_dump = [t.model_dump(mode="json") for t in trajectories]
        pipe.setex(
            REDIS_TRAJECTORIES_KEY,
            REDIS_TRAJECTORIES_TTL,
            json.dumps(trajectories_dump, default=str),
        )
        for trajectory, dump in zip(trajectories, trajectories_dump, strict=True):
            pipe.setex(
                f"{REDIS_TRAJECTORY_KEY_PREFIX}{trajectory.train_id}",
                REDIS_INDIVIDUAL_TRAJECTORY_TTL,
                json.dumps(dump, default=str),
            )

        for train_id, sequence in stop_sequences.items():
            pipe.setex(
                f"{REDIS_STOPSEQUENCE_KEY_PREFIX}{train_id}",
                REDIS_STOPSEQUENCE_TTL,
                json.dumps(sequence, default=str),
            )

        if topology_payload:
            pipe.setex(
                REDIS_TOPOLOGY_METADATA_KEY,
                REDIS_TOPOLOGY_METADATA_TTL,
                json.dumps(topology_payload, default=str),
            )

        if static_payloads is not None:
            network_edges_payload, stations_payload = static_payloads
            pipe.set(
                REDIS_MAP_NETWORK_EDGES_KEY,
                json.dumps(network_edges_payload, default=str),
            )
            pipe.set(
                REDIS_MAP_STATIONS_KEY,
                json.dumps(stations_payload, default=str),
            )

        await pipe.execute()

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
    return PositionCacheUpdater(
        session_factory=session_factory,
        redis_client=redis_client,
        interval_seconds=settings.get_position_cache_interval_seconds(),
    )
