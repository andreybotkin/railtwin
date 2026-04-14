"""Train simulation service — thin orchestrator.

Handles all database I/O (trains, schedules, route geometries) and Redis
delay loading, then delegates position / trajectory / stop-sequence
*computation* to the purpose-built pure modules:

    geo_utils          — geometry maths (interpolation, bearing, Haversine)
    schedule_utils     — schedule / time helpers
    position_service   — build_train_position()
    trajectory_service — build_train_trajectory(), build_stop_sequence()

Keeping I/O and computation separate makes the business logic trivially
unit-testable without any database or Redis.
"""

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.database.models import Schedule, Train
from app.repositories.route import RouteRepository
from app.repositories.schedule import ScheduleRepository
from app.repositories.train import TrainRepository
from app.services import schedule_utils
from app.services.position_service import build_train_position
from app.services.trajectory_service import build_stop_sequence, build_train_trajectory
from app.services.tts_scraper import get_delays_from_redis

logger = get_logger(__name__)


class TrainSimulationService:
    """Orchestrates train simulation: loads data, delegates computation.

    Public API:
        get_train_position()       — single-train position snapshot
        get_train_trajectory()     — single-train geops trajectory
        get_stop_sequence()        — single-train stop sequence
        get_all_active_trains()    — bulk position snapshots (legacy)
        get_all_active_train_trajectories() — bulk trajectories (legacy)
        get_all_active_train_data()         — optimised unified bulk query
        reset_delays()             — clear cached TTS delays
    """

    def __init__(
        self, session: AsyncSession, redis_client: Redis | None = None
    ) -> None:
        self.train_repo = TrainRepository(session)
        self.schedule_repo = ScheduleRepository(session)
        self.route_repo = RouteRepository(session)
        self.session = session
        self._redis = redis_client
        # Cache of TTS delays: {train_number: delay_minutes}
        self._tts_delays: dict[str, int] = {}

    # ------------------------------------------------------------------ #
    # Time helpers kept on the class so tests can monkeypatch them         #
    # ------------------------------------------------------------------ #

    def _get_current_time_minutes(self) -> float:
        """Current Bangkok time as fractional minutes since midnight.

        Kept as an *instance method* so tests can monkeypatch it without
        patching the module-level function in ``schedule_utils``.
        """
        return schedule_utils.get_current_time_minutes()

    def _get_candidate_current_minutes(
        self, schedules: list[Schedule]
    ) -> float | None:
        """Backward-compatible wrapper without realtime delay correction."""
        return schedule_utils.candidate_current_minutes(
            schedules,
            self._get_current_time_minutes(),
        )

    def _get_candidate_current_minutes_with_delay(
        self,
        schedules: list[Schedule],
        delay: int,
    ) -> float | None:
        """Resolve the active service window after applying realtime deviation."""
        return schedule_utils.candidate_current_minutes(
            schedules,
            self._get_current_time_minutes(),
            delay=delay,
        )

    def _calculate_heading(
        self,
        from_coord: tuple[float, float],
        to_coord: tuple[float, float],
    ) -> float:
        """Backward-compat alias → :func:`geo_utils.great_circle_bearing`."""
        from app.services import geo_utils as _geo

        return _geo.great_circle_bearing(from_coord, to_coord)

    # ------------------------------------------------------------------ #
    # Single-train public API                                              #
    # ------------------------------------------------------------------ #

    async def get_train_position(
        self,
        train: Train,
        schedules: list[Schedule],
        route_coords: list[list[float]] | None,
        route_distance_km: float | None = None,
        route_segments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Calculate a current position snapshot for a single train."""
        delay = self._tts_delays.get(train.train_number, 0)
        current_minutes = self._get_candidate_current_minutes_with_delay(
            schedules,
            delay,
        )
        if current_minutes is None:
            return None
        return build_train_position(
            train,
            schedules,
            route_coords,
            route_distance_km,
            route_segments,
            delay=delay,
            current_minutes=current_minutes,
        )

    async def get_train_trajectory(
        self,
        train: Train,
        schedules: list[Schedule],
        route_coords: list[list[float]] | None,
        route_distance_km: float | None = None,
        route_segments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Generate a geops-compatible trajectory object with ``time_intervals``."""
        delay = self._tts_delays.get(train.train_number, 0)
        current_minutes = self._get_candidate_current_minutes_with_delay(
            schedules,
            delay,
        )
        if current_minutes is None:
            return None
        return build_train_trajectory(
            train,
            schedules,
            route_coords,
            route_distance_km,
            route_segments,
            delay=delay,
            current_minutes=current_minutes,
        )

    def get_stop_sequence(
        self,
        _train: Train,
        schedules: list[Schedule],
        delay: int,
        current_minutes: float,
    ) -> list[dict[str, Any]]:
        """Generate an ordered stop-sequence list for a train."""
        return build_stop_sequence(
            schedules, delay=delay, current_minutes=current_minutes
        )

    # ------------------------------------------------------------------ #
    # Bulk public API                                                      #
    # ------------------------------------------------------------------ #

    async def get_all_active_trains(self) -> list[dict[str, Any]]:
        """Get current position snapshots for all active trains."""
        await self._load_delays()

        positions: list[dict[str, Any]] = []
        batch_size = 100
        skip = 0

        while True:
            trains = await self.train_repo.get_all_with_route(
                skip=skip, limit=batch_size
            )
            if not trains:
                break

            for train in trains:
                schedules = await self.schedule_repo.get_by_train(train.id)
                if not schedules:
                    continue
                route_coords, route_distance_km, route_segments = await self._load_route(train)
                if route_segments:
                    pos = await self.get_train_position(
                        train,
                        schedules,
                        route_coords,
                        route_distance_km,
                        route_segments=route_segments,
                    )
                else:
                    pos = await self.get_train_position(
                        train,
                        schedules,
                        route_coords,
                        route_distance_km,
                    )
                if pos:
                    positions.append(pos)

            if len(trains) < batch_size:
                break
            skip += batch_size

        return positions

    async def get_all_active_train_trajectories(self) -> list[dict[str, Any]]:
        """Get geops-compatible trajectory objects for all active trains."""
        await self._load_delays()

        trajectories: list[dict[str, Any]] = []
        batch_size = 100
        skip = 0

        while True:
            trains = await self.train_repo.get_all_with_route(
                skip=skip, limit=batch_size
            )
            if not trains:
                break

            for train in trains:
                schedules = await self.schedule_repo.get_by_train(train.id)
                if not schedules:
                    continue
                route_coords, route_distance_km, route_segments = await self._load_route(train)
                if route_segments:
                    traj = await self.get_train_trajectory(
                        train,
                        schedules,
                        route_coords,
                        route_distance_km,
                        route_segments=route_segments,
                    )
                else:
                    traj = await self.get_train_trajectory(
                        train,
                        schedules,
                        route_coords,
                        route_distance_km,
                    )
                if traj:
                    trajectories.append(traj)

            if len(trains) < batch_size:
                break
            skip += batch_size

        return trajectories

    async def get_all_active_train_data(
        self,
        *,
        include_trajectories: bool = True,
        include_stop_sequences: bool = True,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        dict[int, list[dict[str, Any]]],
    ]:
        """Unified computation: positions + trajectories + stop sequences in one pass.

        Optimisations over calling the three methods separately:

        * TTS delays loaded only once.
        * Schedules loaded in bulk per batch: one ``WHERE train_id IN (…)``
          instead of N individual queries.
        * Route geometries loaded in bulk via ``get_geometry_bulk()`` which
          keeps an in-memory TTL cache.

        Returns:
            ``(positions, trajectories, stop_sequences)`` where
            *stop_sequences* is ``dict[train_id, list[stop_dict]]``.
        """
        await self._load_delays()

        positions: list[dict[str, Any]] = []
        trajectories: list[dict[str, Any]] = []
        stop_sequences: dict[int, list[dict[str, Any]]] = {}

        batch_size = 100
        skip = 0

        while True:
            trains = await self.train_repo.get_all_with_route(
                skip=skip, limit=batch_size
            )
            if not trains:
                break

            # Bulk-load all schedules for this batch.
            train_ids = [t.id for t in trains]
            schedules_by_train = await self.schedule_repo.get_by_trains(train_ids)

            # Collect distinct route IDs, bulk-load geometries (cache-friendly).
            route_ids = list(
                {t.current_route_id for t in trains if t.current_route_id}
            )
            geometry_by_route = (
                await self.route_repo.get_graph_geometry_bulk(route_ids)
                if route_ids
                else {}
            )

            for train in trains:
                schedules = schedules_by_train.get(train.id, [])
                if not schedules:
                    continue

                route_coords: list[list[float]] | None = None
                route_distance_km: float | None = None
                route_segments: list[dict[str, Any]] | None = None
                if (
                    train.current_route_id
                    and train.current_route_id in geometry_by_route
                ):
                    route_payload = geometry_by_route[train.current_route_id]
                    route_coords = route_payload.get("coords")
                    route_distance_km = route_payload.get("distance_km")
                    route_segments = route_payload.get("segments")
                    if not route_coords:
                        route_coords = None

                delay = self._tts_delays.get(train.train_number, 0)
                current_minutes = self._get_candidate_current_minutes_with_delay(
                    schedules,
                    delay,
                )
                if current_minutes is None:
                    continue

                pos = build_train_position(
                    train,
                    schedules,
                    route_coords,
                    route_distance_km,
                    route_segments,
                    delay=delay,
                    current_minutes=current_minutes,
                )
                if pos:
                    positions.append(pos)

                if include_trajectories:
                    traj = build_train_trajectory(
                        train,
                        schedules,
                        route_coords,
                        route_distance_km,
                        route_segments,
                        delay=delay,
                        current_minutes=current_minutes,
                    )
                    if traj:
                        trajectories.append(traj)

                if include_stop_sequences:
                    seq = build_stop_sequence(
                        schedules, delay=delay, current_minutes=current_minutes
                    )
                    if seq:
                        stop_sequences[train.id] = seq

            if len(trains) < batch_size:
                break
            skip += batch_size

        return positions, trajectories, stop_sequences

    def reset_delays(self) -> None:
        """Reset cached TTS delay corrections."""
        self._tts_delays.clear()
        logger.info("Train delays reset")

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    async def _load_delays(self) -> None:
        """Refresh TTS delay cache from Redis (silent on failure)."""
        if self._redis is not None:
            try:
                self._tts_delays = await get_delays_from_redis(self._redis)
            except Exception as exc:
                logger.warning("Could not load TTS delays from Redis", error=str(exc))

    async def _load_route(
        self, train: Train
    ) -> tuple[list[list[float]] | None, float | None, list[dict[str, Any]] | None]:
        """Load route geometry for a single train (used by legacy bulk methods)."""
        if not train.current_route_id:
            return None, None, None
        route_payload = None
        try:
            route_payload = (
                await self.route_repo.get_graph_geometry_bulk([train.current_route_id])
            ).get(train.current_route_id)
        except Exception:
            route_payload = None
        if route_payload is None:
            route = await self.route_repo.get_by_id_with_geometry(train.current_route_id)
            if route and hasattr(route, "_geojson") and route._geojson:
                geojson = json.loads(route._geojson)
                coords = geojson.get("coordinates", [])
                dist_km = float(route.distance_km) if route.distance_km else None
                return coords, dist_km, None
            return None, None, None
        coords = route_payload.get("coords") or None
        dist_km = route_payload.get("distance_km")
        segments = route_payload.get("segments") or None
        return coords, dist_km, segments
