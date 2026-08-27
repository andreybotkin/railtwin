"""Trajectory endpoints — the canonical "where is the train now and next" API.

The gateway can fall back to these if Redis is cold; the hot path remains
Redis pub/sub populated by :class:`app.services.position_cache.PositionCacheUpdater`.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import SimulationServiceDep
from app.domain.trajectory import Trajectory
from app.services.reference_data import (
    RedisReferenceReader,
    schedule_payloads_to_domain,
    train_payload_to_domain,
)

router = APIRouter()


@router.get(
    "",
    response_model=list[Trajectory],
    summary="All active trajectories",
)
async def list_trajectories(service: SimulationServiceDep) -> list[Trajectory]:
    trajectories, _ = await service.get_all_active_train_data(
        include_stop_sequences=False,
    )
    return trajectories


@router.get(
    "/{train_id}",
    response_model=Trajectory,
    summary="Single train trajectory",
)
async def get_trajectory(
    service: SimulationServiceDep,
    train_id: int,
) -> Trajectory:
    if service.reader is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis reference reader not available",
        )
    train_payload = await service.reader.get_train(train_id)
    if train_payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Train {train_id} not found",
        )
    raw_schedules = await service.reader.get_schedules_by_trains([train_id])
    schedules = schedule_payloads_to_domain(raw_schedules.get(train_id, []))
    train = train_payload_to_domain(train_payload)

    route_coords: list[list[float]] | None = None
    route_distance_km: float | None = None
    route_segments: list[dict[str, Any]] | None = None
    route_stop_positions: list[dict[str, Any]] | None = None
    geometry_map = await service.reader.get_train_geometry_bulk([train_id])
    geometry = geometry_map.get(train_id) or {}
    if not geometry.get("valid"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Train timetable does not form a connected track path",
                "issues": geometry.get("issues")
                or [{"code": "missing_train_geometry"}],
            },
        )
    route_coords = geometry.get("coords")
    route_distance_km = geometry.get("distance_km")
    route_segments = geometry.get("segments")
    route_stop_positions = geometry.get("stop_positions")

    await service._load_delays()
    trajectory = await service.get_train_trajectory(
        train,
        schedules,
        route_coords,
        route_distance_km,
        route_segments=route_segments,
        route_stop_positions=route_stop_positions,
    )
    if trajectory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active trajectory for train {train_id}",
        )
    return trajectory


@router.get(
    "/{train_id}/stopsequence",
    response_model=list[dict[str, Any]],
    summary="Upcoming stop sequence with delays applied",
)
async def get_stopsequence(
    service: SimulationServiceDep,
    train_id: int,
) -> list[dict[str, Any]]:
    if service.reader is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis reference reader not available",
        )
    raw_schedules = await service.reader.get_schedules_by_trains([train_id])
    schedules = schedule_payloads_to_domain(raw_schedules.get(train_id, []))
    if not schedules:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No schedule found for train {train_id}",
        )
    await service._load_delays()
    delay = (
        service._tts_delays.get(
            str(raw_schedules[train_id][0].get("train_number") or ""), 0
        )
        if raw_schedules.get(train_id)
        else 0
    )
    current_minutes = service._get_candidate_current_minutes_with_delay(
        schedules, delay
    )
    if current_minutes is None:
        return []
    # Signature in trajectory_service is (schedules, *, delay, current_minutes)
    # but keep SimulationService.get_stop_sequence helper for consistency.
    train_payload = await service.reader.get_train(train_id)
    train = train_payload_to_domain(train_payload) if train_payload else None
    if train is None:
        return []
    return service.get_stop_sequence(
        train, schedules, delay=delay, current_minutes=current_minutes
    )


__all__ = ["RedisReferenceReader", "router"]
