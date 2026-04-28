"""Use case: build (or rebuild) precomputed movement plans for all trains.

For each train with current_route_id set:
  1. Load schedule stops and route geometry metadata from the DB.
  2. Resolve each stop's position along the route.
  3. Emit dwell + move segments with quality scores and warning codes.
  4. Persist to planned_train_runs + planned_movement_segments.

The builder always clears then rebuilds (plans are fully derived from
schedules + routes; safe to regenerate).

Runtime trajectory generation is NOT changed here.  Phase 3 only populates
the movement plan tables; the existing build_trajectory() path remains active.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.domain.railroad.movement_plan_service import (
    BuiltRun,
    TrainBuildInput,
    build_movement_plan,
)

if TYPE_CHECKING:
    from app.infrastructure.database.repositories.movement_plan import (
        SqlMovementPlanRepository,
    )

logger = get_logger(__name__)


@dataclass
class MovementPlanBuildResult:
    skipped: bool = False
    success: bool = False
    trains_seen: int = 0
    plans_created: int = 0
    plans_ready: int = 0
    plans_degraded: int = 0
    plans_invalid: int = 0
    segments_created: int = 0
    warnings_count: int = 0
    top_warning_codes: list[str] = field(default_factory=list)
    plan_version: str | None = None
    topology_version: str | None = None
    error: str | None = None


class BuildMovementPlansUseCase:
    def __init__(self, repository: SqlMovementPlanRepository) -> None:
        self._repo = repository

    async def execute(self, *, force: bool = False) -> MovementPlanBuildResult:
        try:
            return await self._run(force=force)
        except Exception as exc:
            logger.error(
                "Movement plan build failed with unexpected exception", error=str(exc)
            )
            return MovementPlanBuildResult(error=str(exc))

    async def _run(self, *, force: bool) -> MovementPlanBuildResult:  # noqa: ARG002
        topology_version = await self._repo.get_topology_version()
        plan_version = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")

        logger.info(
            "Building movement plans",
            plan_version=plan_version,
            topology_version=topology_version,
        )

        # Plans are fully derived data: always clear before rebuilding.
        await self._repo.delete_all_plans()

        trains: list[TrainBuildInput] = await self._repo.load_trains_with_schedules()
        if not trains:
            logger.warning("No trains with routes found; no movement plans to build")
            return MovementPlanBuildResult(
                success=True,
                plan_version=plan_version,
                topology_version=topology_version,
            )

        plans_ready = plans_degraded = plans_invalid = 0
        segments_total = 0
        warning_counts: dict[str, int] = {}

        for train in trains:
            run: BuiltRun = build_movement_plan(train, plan_version, topology_version)
            await self._repo.save_run(run)

            if run.status == "ready":
                plans_ready += 1
            elif run.status == "degraded":
                plans_degraded += 1
            else:
                plans_invalid += 1

            segments_total += len(run.segments)

            for w in run.warnings:
                warning_counts[w] = warning_counts.get(w, 0) + 1
            for seg in run.segments:
                for w in seg.warnings:
                    warning_counts[w] = warning_counts.get(w, 0) + 1

        top_warnings = sorted(
            warning_counts, key=warning_counts.__getitem__, reverse=True
        )[:5]
        total_warnings = sum(warning_counts.values())

        logger.info(
            "Movement plans built",
            trains=len(trains),
            ready=plans_ready,
            degraded=plans_degraded,
            invalid=plans_invalid,
            segments=segments_total,
            warnings=total_warnings,
        )

        return MovementPlanBuildResult(
            success=True,
            trains_seen=len(trains),
            plans_created=len(trains),
            plans_ready=plans_ready,
            plans_degraded=plans_degraded,
            plans_invalid=plans_invalid,
            segments_created=segments_total,
            warnings_count=total_warnings,
            top_warning_codes=top_warnings,
            plan_version=plan_version,
            topology_version=topology_version,
        )
