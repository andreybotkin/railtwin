"""Thin service layer for movement plan diagnostics.

Wraps :class:`MovementPlanRepository` to keep endpoint handlers free of query
logic.  All methods are read-only.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.movement_plan import MovementPlanRepository
from app.schemas.movement_plan import (
    MovementPlanSummary,
    PlannedRunDetail,
    PlannedRunListResponse,
    PlannedRunSummary,
    PlannedSegmentOut,
    WarningCodeInfo,
    warning_description,
    warning_severity,
)


class MovementPlanService:
    """Read-only service for planned movement plan diagnostics."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = MovementPlanRepository(session)

    async def get_summary(self) -> MovementPlanSummary:
        data = await self._repo.get_summary()
        return MovementPlanSummary(**data)

    async def get_runs_for_train(self, train_id: int) -> list[PlannedRunSummary]:
        runs = await self._repo.get_runs_for_train(train_id)
        return [PlannedRunSummary.model_validate(run) for run in runs]

    async def get_runs_for_route(
        self,
        route_id: int,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PlannedRunListResponse:
        runs, total = await self._repo.get_runs_for_route(
            route_id, status=status, limit=limit, offset=offset
        )
        return PlannedRunListResponse(
            items=[PlannedRunSummary.model_validate(run) for run in runs],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_run_detail(self, run_id: int) -> PlannedRunDetail | None:
        run = await self._repo.get_run_with_segments(run_id)
        if run is None:
            return None
        segments = [
            PlannedSegmentOut.model_validate(seg)
            for seg in sorted(run.segments, key=lambda s: s.sequence)
        ]
        detail = PlannedRunDetail.model_validate(run)
        return detail.model_copy(update={"segments": segments})

    async def get_warning_counts(self) -> list[WarningCodeInfo]:
        rows = await self._repo.get_warning_counts()
        return [
            WarningCodeInfo(
                code=row["code"],
                count=row["count"],
                severity=warning_severity(row["code"]),  # type: ignore[arg-type]
                description=warning_description(row["code"]),
            )
            for row in rows
        ]

    async def get_problems(
        self,
        *,
        warning_code: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PlannedRunListResponse:
        runs, total = await self._repo.get_problems(
            warning_code=warning_code, limit=limit, offset=offset
        )
        return PlannedRunListResponse(
            items=[PlannedRunSummary.model_validate(run) for run in runs],
            total=total,
            limit=limit,
            offset=offset,
        )
