"""Train API endpoints.

This module provides RESTful API endpoints for managing trains and their positions.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import SimulationServiceDep, TrainServiceDep
from app.schemas.train import (
    TrainCreate,
    TrainListResponse,
    TrainPositionResponse,
    TrainResponse,
    TrainUpdate,
)

router = APIRouter()


@router.get(
    "",
    response_model=TrainListResponse,
    summary="List all trains",
    description="Get a paginated list of all trains.",
)
async def list_trains(
    service: TrainServiceDep,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    train_type: Annotated[str | None, Query(description="Filter by train type")] = None,
    route_id: Annotated[int | None, Query(description="Filter by route")] = None,
) -> TrainListResponse:
    """List all trains with pagination and optional filtering.

    Args:
        service: Train service dependency.
        page: Page number (1-indexed).
        size: Number of items per page.
        train_type: Filter by train type.
        route_id: Filter by current route.

    Returns:
        TrainListResponse with paginated trains.
    """
    return await service.list_trains(
        page=page,
        size=size,
        train_type=train_type,
        route_id=route_id,
    )


@router.get(
    "/positions",
    response_model=list[dict],
    summary="Get all train positions",
    description="Get current positions for all active trains.",
)
async def get_all_positions(
    simulation_service: SimulationServiceDep,
) -> list[dict]:
    """Get current positions for all active trains.

    This endpoint provides simulated real-time positions based on
    the train schedules and route geometry.

    Args:
        simulation_service: Simulation service dependency.

    Returns:
        List of train positions with coordinates and status.
    """
    return await simulation_service.get_all_active_trains()


@router.get(
    "/{train_id}",
    response_model=TrainResponse,
    summary="Get train details",
    description="Get detailed information about a specific train.",
)
async def get_train(
    service: TrainServiceDep,
    train_id: int,
) -> TrainResponse:
    """Get a single train by ID.

    Args:
        service: Train service dependency.
        train_id: Train ID.

    Returns:
        TrainResponse with train details.

    Raises:
        HTTPException: If train not found.
    """
    train = await service.get_train(train_id)
    if not train:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Train with id {train_id} not found",
        )
    return train


@router.get(
    "/{train_id}/position",
    response_model=TrainPositionResponse,
    summary="Get train position",
    description="Get the current position of a specific train.",
)
async def get_train_position(
    service: TrainServiceDep,
    train_id: int,
) -> TrainPositionResponse:
    """Get the latest position for a train.

    Args:
        service: Train service dependency.
        train_id: Train ID.

    Returns:
        TrainPositionResponse with current position.

    Raises:
        HTTPException: If train or position not found.
    """
    position = await service.get_train_position(train_id)
    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position for train {train_id} not found",
        )
    return position


@router.post(
    "",
    response_model=TrainResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a train",
    description="Create a new train.",
)
async def create_train(
    service: TrainServiceDep,
    data: TrainCreate,
) -> TrainResponse:
    """Create a new train.

    Args:
        service: Train service dependency.
        data: Train creation data.

    Returns:
        Created TrainResponse.
    """
    return await service.create_train(data)


@router.patch(
    "/{train_id}",
    response_model=TrainResponse,
    summary="Update a train",
    description="Update an existing train.",
)
async def update_train(
    service: TrainServiceDep,
    train_id: int,
    data: TrainUpdate,
) -> TrainResponse:
    """Update an existing train.

    Args:
        service: Train service dependency.
        train_id: Train ID.
        data: Update data.

    Returns:
        Updated TrainResponse.

    Raises:
        HTTPException: If train not found.
    """
    train = await service.update_train(train_id, data)
    if not train:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Train with id {train_id} not found",
        )
    return train


@router.delete(
    "/{train_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a train",
    description="Delete a train.",
)
async def delete_train(
    service: TrainServiceDep,
    train_id: int,
) -> None:
    """Delete a train.

    Args:
        service: Train service dependency.
        train_id: Train ID.

    Raises:
        HTTPException: If train not found.
    """
    deleted = await service.delete_train(train_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Train with id {train_id} not found",
        )
