"""Trajectory-first train API endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import SimulationServiceDep
from app.services.reference_data import schedule_payloads_to_domain, train_payload_to_domain

router = APIRouter()


async def _build_single_trajectory_payload(
    simulation_service: SimulationServiceDep,
    train_id: int,
) -> tuple[dict | None, list[dict] | None]:
    await simulation_service._load_delays()  # noqa: SLF001
    reader = simulation_service.reader
    if reader is None:
        return None, None

    train_payload = await reader.get_train(train_id)
    if train_payload is None:
        return None, None

    train = train_payload_to_domain(train_payload)
    schedules = schedule_payloads_to_domain(await reader.get_train_schedule(train_id))
    if not schedules:
        return None, None

    route_payload = (
        await reader.get_route_geometry_bulk([train.current_route_id or -1])
    ).get(train.current_route_id or -1, {})
    route_coords = route_payload.get("coords") or None
    route_distance_km = route_payload.get("distance_km")
    route_segments = route_payload.get("segments") or None

    trajectory = await simulation_service.get_train_trajectory(
        train,
        schedules,
        route_coords,
        route_distance_km,
        route_segments,
    )
    stop_sequence = simulation_service.get_stop_sequence(
        train,
        schedules,
        simulation_service._tts_delays.get(train.train_number, 0),  # noqa: SLF001
        simulation_service._get_current_time_minutes(),  # noqa: SLF001
    )
    return trajectory, stop_sequence


@router.get(
    "/trajectories",
    summary="Get active train trajectories",
    description="Get latest trajectories for all active trains.",
)
async def get_train_trajectories(
    service: SimulationServiceDep,
) -> list[dict]:
    _, trajectories, _ = await service.get_all_active_train_data(
        include_trajectories=True,
        include_stop_sequences=False,
    )
    return trajectories


@router.get(
    "/{train_id:int}/trajectory",
    summary="Get a train trajectory",
    description="Get latest trajectory for a specific train.",
)
async def get_train_trajectory(
    service: SimulationServiceDep,
    train_id: int,
) -> dict:
    trajectory, _ = await _build_single_trajectory_payload(service, train_id)
    if trajectory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trajectory for train {train_id} not found",
        )
    return trajectory


@router.get(
    "/{train_id:int}/stopsequence",
    summary="Get stop sequence",
    description="Get current stop-sequence for a specific train.",
)
async def get_train_stopsequence(
    service: SimulationServiceDep,
    train_id: int,
) -> list[dict]:
    _, stop_sequence = await _build_single_trajectory_payload(service, train_id)
    if stop_sequence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stop sequence for train {train_id} not found",
        )
    return stop_sequence
