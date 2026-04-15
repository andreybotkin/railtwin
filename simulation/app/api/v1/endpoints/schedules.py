"""Schedule API endpoints.

This module provides RESTful API endpoints for managing train schedules.
"""

from datetime import datetime, time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import ScheduleServiceDep
from app.schemas.schedule import (
    ScheduleCreate,
    ScheduleListResponse,
    ScheduleResponse,
    ScheduleUpdate,
    StationScheduleResponse,
    TrainScheduleResponse,
)

router = APIRouter()


@router.get(
    "",
    response_model=ScheduleListResponse,
    summary="List all schedules",
    description="Get a paginated list of all schedules with optional filtering.",
)
async def list_schedules(
    service: ScheduleServiceDep,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 50,
    train_id: Annotated[int | None, Query(description="Filter by train ID")] = None,
    station_id: Annotated[int | None, Query(description="Filter by station ID")] = None,
    day_of_week: Annotated[
        int | None, Query(ge=0, le=6, description="Filter by day (0=Mon, 6=Sun)")
    ] = None,
) -> ScheduleListResponse:
    """List all schedules with pagination and filtering.

    Args:
        service: Schedule service dependency.
        page: Page number (1-indexed).
        size: Number of items per page.
        train_id: Filter by train ID.
        station_id: Filter by station ID.
        day_of_week: Filter by day of week.

    Returns:
        ScheduleListResponse with paginated schedules.
    """
    return await service.list_schedules(
        page=page,
        size=size,
        train_id=train_id,
        station_id=station_id,
        day_of_week=day_of_week,
    )


@router.get(
    "/train/{train_id}",
    response_model=TrainScheduleResponse,
    summary="Get train schedule",
    description="Get complete schedule for a specific train.",
)
async def get_train_schedule(
    service: ScheduleServiceDep,
    train_id: int,
    day_of_week: Annotated[
        int | None, Query(ge=0, le=6, description="Filter by day")
    ] = None,
) -> TrainScheduleResponse:
    """Get complete schedule for a train.

    Args:
        service: Schedule service dependency.
        train_id: Train ID.
        day_of_week: Filter by day of week.

    Returns:
        TrainScheduleResponse with all stops.

    Raises:
        HTTPException: If train schedule not found.
    """
    schedule = await service.get_train_schedule(train_id, day_of_week)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule for train {train_id} not found",
        )
    return schedule


@router.get(
    "/station/{station_id}",
    response_model=StationScheduleResponse,
    summary="Get station schedule",
    description="Get all arrivals and departures for a specific station.",
)
async def get_station_schedule(
    service: ScheduleServiceDep,
    station_id: int,
    day_of_week: Annotated[
        int | None, Query(ge=0, le=6, description="Filter by day")
    ] = None,
) -> StationScheduleResponse:
    """Get all arrivals/departures for a station.

    Args:
        service: Schedule service dependency.
        station_id: Station ID.
        day_of_week: Filter by day of week.

    Returns:
        StationScheduleResponse with all trains.

    Raises:
        HTTPException: If station schedule not found.
    """
    schedule = await service.get_station_schedule(station_id, day_of_week)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule for station {station_id} not found",
        )
    return schedule


@router.get(
    "/station/{station_id}/upcoming",
    response_model=list[ScheduleResponse],
    summary="Get upcoming departures",
    description="Get upcoming departures from a station.",
)
async def get_upcoming_departures(
    service: ScheduleServiceDep,
    station_id: int,
    limit: Annotated[int, Query(ge=1, le=50, description="Max results")] = 10,
) -> list[ScheduleResponse]:
    """Get upcoming departures from a station.

    Args:
        service: Schedule service dependency.
        station_id: Station ID.
        limit: Maximum number of results.

    Returns:
        List of upcoming schedule entries.
    """
    now = datetime.now()
    current_time = time(now.hour, now.minute)
    day_of_week = now.weekday()

    return await service.get_upcoming_departures(
        station_id=station_id,
        current_time=current_time,
        day_of_week=day_of_week,
        limit=limit,
    )


@router.get(
    "/{schedule_id}",
    response_model=ScheduleResponse,
    summary="Get schedule details",
    description="Get detailed information about a specific schedule entry.",
)
async def get_schedule(
    service: ScheduleServiceDep,
    schedule_id: int,
) -> ScheduleResponse:
    """Get a single schedule by ID.

    Args:
        service: Schedule service dependency.
        schedule_id: Schedule ID.

    Returns:
        ScheduleResponse with schedule details.

    Raises:
        HTTPException: If schedule not found.
    """
    schedule = await service.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule with id {schedule_id} not found",
        )
    return schedule


@router.post(
    "",
    response_model=ScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a schedule",
    description="Create a new schedule entry.",
)
async def create_schedule(
    service: ScheduleServiceDep,
    data: ScheduleCreate,
) -> ScheduleResponse:
    """Create a new schedule entry.

    Args:
        service: Schedule service dependency.
        data: Schedule creation data.

    Returns:
        Created ScheduleResponse.
    """
    return await service.create_schedule(data)


@router.patch(
    "/{schedule_id}",
    response_model=ScheduleResponse,
    summary="Update a schedule",
    description="Update an existing schedule entry.",
)
async def update_schedule(
    service: ScheduleServiceDep,
    schedule_id: int,
    data: ScheduleUpdate,
) -> ScheduleResponse:
    """Update an existing schedule.

    Args:
        service: Schedule service dependency.
        schedule_id: Schedule ID.
        data: Update data.

    Returns:
        Updated ScheduleResponse.

    Raises:
        HTTPException: If schedule not found.
    """
    schedule = await service.update_schedule(schedule_id, data)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule with id {schedule_id} not found",
        )
    return schedule


@router.delete(
    "/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a schedule",
    description="Delete a schedule entry.",
)
async def delete_schedule(
    service: ScheduleServiceDep,
    schedule_id: int,
) -> None:
    """Delete a schedule entry.

    Args:
        service: Schedule service dependency.
        schedule_id: Schedule ID.

    Raises:
        HTTPException: If schedule not found.
    """
    deleted = await service.delete_schedule(schedule_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule with id {schedule_id} not found",
        )
