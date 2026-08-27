"""Train simulation orchestrator.

Handles all I/O (trains, schedules, route geometries from Redis, delay cache)
and delegates *computation* to :mod:`app.services.trajectory_service`, which
returns fully-typed :class:`app.domain.trajectory.Trajectory` objects.
"""

from __future__ import annotations

import asyncio
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.trajectory import Trajectory
from app.models.database.models import Schedule, Train
from app.services import schedule_utils
from app.services.movement_plan_runtime import resolve_trajectory as _resolve_from_plan
from app.services.reference_data import (
    RedisReferenceReader,
    schedule_payloads_to_domain,
    train_payload_to_domain,
)
from app.services.trajectory_service import build_stop_sequence, build_trajectory
from app.services.tts_scraper import get_delays_from_redis

logger = get_logger(__name__)

_COOPERATIVE_YIELD_EVERY = 25


class TrainSimulationService:
    """Load domain data from Redis / DB and build trajectories for active trains."""

    def __init__(
        self,
        session: AsyncSession,
        redis_client: Redis | None = None,
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
        return schedule_utils.get_current_time_minutes()

    def _get_candidate_current_minutes_with_delay(
        self,
        schedules: list[Schedule],
        delay: int,
    ) -> float | None:
        return schedule_utils.candidate_current_minutes(
            schedules,
            self._get_current_time_minutes(),
            delay=delay,
        )

    # ------------------------------------------------------------------ #
    # Single-train public API                                              #
    # ------------------------------------------------------------------ #

    async def get_train_trajectory(
        self,
        train: Train,
        schedules: list[Schedule],
        route_coords: list[list[float]] | None,
        route_distance_km: float | None = None,
        route_segments: list[dict[str, Any]] | None = None,
        route_stop_positions: list[dict[str, Any]] | None = None,
        *,
        topology_version: str | None = None,
    ) -> Trajectory | None:
        delay = self._tts_delays.get(train.train_number, 0)
        current_minutes = self._get_candidate_current_minutes_with_delay(
            schedules, delay
        )
        if current_minutes is None:
            return None
        return build_trajectory(
            train,
            schedules,
            route_coords,
            route_distance_km,
            delay=delay,
            current_minutes=current_minutes,
            topology_version=topology_version,
            route_segments=route_segments,
            route_stop_positions=route_stop_positions,
        )

    def get_stop_sequence(
        self,
        _train: Train,
        schedules: list[Schedule],
        delay: int,
        current_minutes: float,
    ) -> list[dict[str, Any]]:
        return build_stop_sequence(
            schedules, delay=delay, current_minutes=current_minutes
        )

    # ------------------------------------------------------------------ #
    # Bulk public API                                                      #
    # ------------------------------------------------------------------ #

    async def get_all_active_train_data(
        self,
        *,
        include_stop_sequences: bool = True,
        topology_version: str | None = None,
    ) -> tuple[list[Trajectory], dict[int, list[dict[str, Any]]]]:
        """Return ``(trajectories, stop_sequences)`` for every active train.

        Schedules and route geometries are loaded in bulk to avoid N+1
        queries; TTS delays are loaded once per invocation.
        """

        await self._load_delays()

        trajectories: list[Trajectory] = []
        stop_sequences: dict[int, list[dict[str, Any]]] = {}

        if self.reader is None:
            return trajectories, stop_sequences

        batch_size = 100
        skip = 0

        while True:
            train_payloads = await self.reader.get_all_trains_for_simulation(
                skip=skip, limit=batch_size
            )
            if not train_payloads:
                break

            train_ids = [int(payload["id"]) for payload in train_payloads]
            raw_schedules = await self.reader.get_schedules_by_trains(train_ids)
            schedules_by_train = {
                train_id: schedule_payloads_to_domain(payloads)
                for train_id, payloads in raw_schedules.items()
            }

            geometry_by_train = await self.reader.get_train_geometry_bulk(train_ids)

            # Preload movement plans for this batch (no-op when flag is off).
            movement_plans_by_train: dict[int, Any] = {}
            if settings.movement_plan_runtime_enabled and self.reader is not None:
                movement_plans_by_train = await self.reader.get_movement_plans_bulk(
                    train_ids
                )

            for index, payload in enumerate(train_payloads, start=1):
                train = train_payload_to_domain(payload)
                schedules = schedules_by_train.get(train.id, [])
                if not schedules:
                    continue

                route_coords: list[list[float]] | None = None
                route_distance_km: float | None = None
                route_segments: list[dict[str, Any]] | None = None
                route_stop_positions: list[dict[str, Any]] | None = None
                route_payload = geometry_by_train.get(train.id) or {}
                if route_payload.get("valid"):
                    route_coords = route_payload.get("coords")
                    route_distance_km = route_payload.get("distance_km")
                    route_segments = route_payload.get("segments")
                    route_stop_positions = route_payload.get("stop_positions")
                    if not route_coords:
                        route_coords = None
                else:
                    logger.warning(
                        "train_geometry_invalid",
                        train_id=train.id,
                        train_number=train.train_number,
                        issues=route_payload.get("issues")
                        or [{"code": "missing_train_geometry"}],
                    )
                    if index % _COOPERATIVE_YIELD_EVERY == 0:
                        await asyncio.sleep(0)
                    continue

                delay = self._tts_delays.get(train.train_number, 0)
                current_minutes = self._get_candidate_current_minutes_with_delay(
                    schedules, delay
                )
                if current_minutes is None:
                    continue

                trajectory: Trajectory | None = None

                # --- Movement plan fast path (feature-flagged) ----------- #
                if (
                    settings.movement_plan_runtime_enabled
                    and route_payload.get("source") != "station_graph"
                ):
                    planned_run = movement_plans_by_train.get(train.id)
                    if planned_run is not None and planned_run.is_usable():
                        route_length_m = (
                            route_distance_km * 1000.0
                            if route_distance_km is not None
                            else 0.0
                        )
                        try:
                            trajectory = _resolve_from_plan(
                                planned_run=planned_run,
                                route_coords=route_coords or [],
                                route_length_m=route_length_m,
                                current_minutes=current_minutes,
                                delay_minutes=delay,
                                train=train,
                                schedules=schedules,
                                route_segments=route_segments,
                                topology_version=topology_version,
                            )
                            if trajectory is not None:
                                logger.debug(
                                    "movement_plan_runtime_used",
                                    train_id=train.id,
                                )
                            else:
                                logger.debug(
                                    "movement_plan_runtime_no_result",
                                    train_id=train.id,
                                )
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "movement_plan_runtime_error",
                                train_id=train.id,
                                error=str(exc),
                            )
                    else:
                        logger.debug(
                            "movement_plan_runtime_unavailable",
                            train_id=train.id,
                        )

                # --- Fallback to build_trajectory() ---------------------- #
                if trajectory is None:
                    if (
                        settings.movement_plan_runtime_enabled
                        and not settings.movement_plan_fallback_enabled
                    ):
                        # Strict mode: skip trains without a usable plan.
                        if index % _COOPERATIVE_YIELD_EVERY == 0:
                            await asyncio.sleep(0)
                        continue
                    trajectory = build_trajectory(
                        train,
                        schedules,
                        route_coords,
                        route_distance_km,
                        delay=delay,
                        current_minutes=current_minutes,
                        topology_version=topology_version,
                        route_segments=route_segments,
                        route_stop_positions=route_stop_positions,
                    )
                    if (
                        trajectory is not None
                        and settings.movement_plan_runtime_enabled
                    ):
                        logger.debug(
                            "movement_plan_runtime_fallback",
                            train_id=train.id,
                        )

                if trajectory is not None:
                    trajectories.append(trajectory)

                if include_stop_sequences:
                    sequence = build_stop_sequence(
                        schedules, delay=delay, current_minutes=current_minutes
                    )
                    if sequence:
                        stop_sequences[train.id] = sequence

                if index % _COOPERATIVE_YIELD_EVERY == 0:
                    await asyncio.sleep(0)

            if len(train_payloads) < batch_size:
                break
            skip += batch_size

        return trajectories, stop_sequences

    def reset_delays(self) -> None:
        self._tts_delays.clear()
        logger.info("Train delays reset")

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    async def _load_delays(self) -> None:
        if self._redis is not None:
            try:
                self._tts_delays = await get_delays_from_redis(self._redis)
            except Exception as exc:  # noqa: BLE001 - delay data is optional
                logger.warning("Could not load TTS delays from Redis", error=str(exc))
