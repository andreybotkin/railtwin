"""Read-only diagnostics endpoints for precomputed movement plans.

These endpoints are enabled by ``settings.movement_plan_diagnostics_enabled``
(default: ``True``).  They are read-only and safe to serve in production.

Gateway catch-all proxies all ``/api/v1/*`` requests to the simulation
service, so no gateway changes are required.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import DBSession
from app.core.config import settings
from app.schemas.movement_plan import (
    MovementPlanSummary,
    PlannedRunDetail,
    PlannedRunListResponse,
    PlannedRunSummary,
    WarningCodeInfo,
)
from app.services.movement_plan import MovementPlanService

router = APIRouter()

_STATUS_VALUES = Literal["ready", "degraded", "invalid", "all"]


def _require_diagnostics() -> None:
    if not settings.movement_plan_diagnostics_enabled:
        raise HTTPException(
            status_code=404, detail="Movement plan diagnostics disabled"
        )


def _service(session: DBSession) -> MovementPlanService:
    return MovementPlanService(session)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


@router.get(
    "/summary",
    response_model=MovementPlanSummary,
    summary="Aggregate movement plan statistics",
)
async def get_summary(
    session: DBSession,
    _: None = Depends(_require_diagnostics),
) -> MovementPlanSummary:
    """Return aggregate counts, quality statistics, and top warning codes."""
    return await _service(session).get_summary()


# ---------------------------------------------------------------------------
# By train
# ---------------------------------------------------------------------------


@router.get(
    "/trains/{train_id}",
    response_model=list[PlannedRunSummary],
    summary="Planned runs for a specific train",
)
async def get_runs_for_train(
    train_id: int,
    session: DBSession,
    _: None = Depends(_require_diagnostics),
) -> list[PlannedRunSummary]:
    """Return all planned runs for *train_id*, newest first."""
    return await _service(session).get_runs_for_train(train_id)


# ---------------------------------------------------------------------------
# By route
# ---------------------------------------------------------------------------


@router.get(
    "/routes/{route_id}",
    response_model=PlannedRunListResponse,
    summary="Planned runs for a specific route",
)
async def get_runs_for_route(
    route_id: int,
    session: DBSession,
    status: Annotated[str | None, Query(description="Filter by status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    _: None = Depends(_require_diagnostics),
) -> PlannedRunListResponse:
    """Return planned runs for *route_id*, paginated."""
    return await _service(session).get_runs_for_route(
        route_id, status=status, limit=limit, offset=offset
    )


# ---------------------------------------------------------------------------
# Run detail
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{planned_run_id}",
    response_model=PlannedRunDetail,
    summary="Full planned run with ordered segments",
)
async def get_run_detail(
    planned_run_id: int,
    session: DBSession,
    _: None = Depends(_require_diagnostics),
) -> PlannedRunDetail:
    """Return the full planned run including all segments ordered by sequence."""
    detail = await _service(session).get_run_detail(planned_run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Planned run not found")
    return detail


# ---------------------------------------------------------------------------
# Warning codes
# ---------------------------------------------------------------------------


@router.get(
    "/warnings",
    response_model=list[WarningCodeInfo],
    summary="Warning code frequencies across all runs",
)
async def get_warning_counts(
    session: DBSession,
    _: None = Depends(_require_diagnostics),
) -> list[WarningCodeInfo]:
    """Return warning code counts with severity and description metadata."""
    return await _service(session).get_warning_counts()


# ---------------------------------------------------------------------------
# Problems
# ---------------------------------------------------------------------------


@router.get(
    "/problems",
    response_model=PlannedRunListResponse,
    summary="Degraded and invalid runs",
)
async def get_problems(
    session: DBSession,
    warning_code: Annotated[
        str | None, Query(description="Filter to runs containing this warning code")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    _: None = Depends(_require_diagnostics),
) -> PlannedRunListResponse:
    """Return all degraded or invalid runs, optionally filtered by warning code."""
    return await _service(session).get_problems(
        warning_code=warning_code, limit=limit, offset=offset
    )
