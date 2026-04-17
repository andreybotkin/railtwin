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

from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.database.models import Schedule, Train
from app.services import schedule_utils
from app.services.reference_data import (
    RedisReferenceReader,
    schedule_payloads_to_domain,
    train_payload_to_domain,
)
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
        self.session = session
        self._redis = redis_client
        self.reader = (
            RedisReferenceReader(redis_client) if redis_client is not None else None
        )
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

    def _get_candidate_current_minutes(self, schedules: list[Schedule]) -> float | None:
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

    def _build_position_from_trajectory(
        self,
        train: Train,
        trajectory: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Project the current position snapshot from the first trajectory frame."""
        frames = trajectory.get("frames")
        if not isinstance(frames, list) or not frames:
            return None

        frame = frames[0]
        if not isinstance(frame, dict):
            return None

        meta = trajectory.get("meta")
        if not isinstance(meta, dict):
            meta = {}

        lon = frame.get("lon")
        lat = frame.get("lat")
        if not isinstance(lon, int | float) or not isinstance(lat, int | float):
            return None

        return {
            "train_id": train.id,
            "train_number": train.train_number,
            "train_type": train.train_type,
            "location": {"type": "Point", "coordinates": [lon, lat]},
            "speed": frame.get("speed_kmh"),
            "heading": frame.get("rotation_deg"),
            "status": frame.get("status"),
            "delay_minutes": meta.get("delay_minutes", 0),
            "next_station": meta.get("next_station"),
            "prev_station": meta.get("prev_station"),
            "route_progress": frame.get("geom_fraction", 0),
            "route_id": train.current_route_id,
        }

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
        """Legacy helper: derives a position snapshot from trajectory frame 0."""
        trajectory = await self.get_train_trajectory(
            train,
            schedules,
            route_coords,
            route_distance_km,
            route_segments,
        )
        if trajectory is None:
            return None
        return self._build_position_from_trajectory(train, trajectory)

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
        if self.reader is None:
            return []

        while True:
            train_payloads = await self.reader.get_all_trains_for_simulation(
                skip=skip, limit=batch_size
            )
            if not train_payloads:
                break

            geometry_by_route = await self.reader.get_route_geometry_bulk(
                [
                    int(payload["current_route_id"])
                    for payload in train_payloads
                    if payload.get("current_route_id") is not None
                ]
            )

            for train_payload in train_payloads:
                train = train_payload_to_domain(train_payload)
                schedules = schedule_payloads_to_domain(
                    await self.reader.get_train_schedule(train.id)
                )
                if not schedules:
                    continue
                route_payload = geometry_by_route.get(train.current_route_id or -1, {})
                route_coords = route_payload.get("coords") or None
                route_distance_km = route_payload.get("distance_km")
                route_segments = route_payload.get("segments") or None
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

            if len(train_payloads) < batch_size:
                break
            skip += batch_size

        return positions

    async def get_all_active_train_trajectories(self) -> list[dict[str, Any]]:
        """Get geops-compatible trajectory objects for all active trains."""
        await self._load_delays()

        trajectories: list[dict[str, Any]] = []
        batch_size = 100
        skip = 0
        if self.reader is None:
            return []

        while True:
            train_payloads = await self.reader.get_all_trains_for_simulation(
                skip=skip, limit=batch_size
            )
            if not train_payloads:
                break

            geometry_by_route = await self.reader.get_route_geometry_bulk(
                [
                    int(payload["current_route_id"])
                    for payload in train_payloads
                    if payload.get("current_route_id") is not None
                ]
            )

            for train_payload in train_payloads:
                train = train_payload_to_domain(train_payload)
                schedules = schedule_payloads_to_domain(
                    await self.reader.get_train_schedule(train.id)
                )
                if not schedules:
                    continue
                route_payload = geometry_by_route.get(train.current_route_id or -1, {})
                route_coords = route_payload.get("coords") or None
                route_distance_km = route_payload.get("distance_km")
                route_segments = route_payload.get("segments") or None
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

            if len(train_payloads) < batch_size:
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
        if self.reader is None:
            return positions, trajectories, stop_sequences

        while True:
            train_payloads = await self.reader.get_all_trains_for_simulation(
                skip=skip, limit=batch_size
            )
            if not train_payloads:
                break

            train_ids = [int(payload["id"]) for payload in train_payloads]
            schedules_by_train_raw = await self.reader.get_schedules_by_trains(
                train_ids
            )
            schedules_by_train = {
                train_id: schedule_payloads_to_domain(payloads)
                for train_id, payloads in schedules_by_train_raw.items()
            }

            route_ids = list(
                {
                    int(payload["current_route_id"])
                    for payload in train_payloads
                    if payload.get("current_route_id") is not None
                }
            )
            geometry_by_route = (
                await self.reader.get_route_geometry_bulk(route_ids)
                if route_ids
                else {}
            )

            for train_payload in train_payloads:
                train = train_payload_to_domain(train_payload)
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
                        pos = self._build_position_from_trajectory(train, traj)
                        if pos:
                            positions.append(pos)
                else:
                    pos = await self.get_train_position(
                        train,
                        schedules,
                        route_coords,
                        route_distance_km,
                        route_segments,
                    )
                    if pos:
                        positions.append(pos)

                if include_stop_sequences:
                    seq = build_stop_sequence(
                        schedules, delay=delay, current_minutes=current_minutes
                    )
                    if seq:
                        stop_sequences[train.id] = seq

            if len(train_payloads) < batch_size:
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
