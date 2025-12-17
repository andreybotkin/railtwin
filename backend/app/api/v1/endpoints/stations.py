"""Station API endpoints.

This module provides RESTful API endpoints for managing railway stations.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import StationServiceDep
from app.schemas.station import (
    StationCreate,
    StationListResponse,
    StationResponse,
    StationUpdate,
)

router = APIRouter()


@router.get(
    "",
    response_model=StationListResponse,
    summary="List all stations",
    description="Get a paginated list of all railway stations.",
)
async def list_stations(
    service: StationServiceDep,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> StationListResponse:
    """List all stations with pagination.

    Args:
        service: Station service dependency.
        page: Page number (1-indexed).
        size: Number of items per page.

    Returns:
        StationListResponse with paginated stations.
    """
    return await service.list_stations(page=page, size=size)


@router.get(
    "/search",
    response_model=list[StationResponse],
    summary="Search stations",
    description="Search stations by name or code.",
)
async def search_stations(
    service: StationServiceDep,
    q: Annotated[str, Query(min_length=1, description="Search query")],
    limit: Annotated[int, Query(ge=1, le=50, description="Max results")] = 10,
) -> list[StationResponse]:
    """Search stations by name or code.

    Args:
        service: Station service dependency.
        q: Search query string.
        limit: Maximum number of results.

    Returns:
        List of matching stations.
    """
    return await service.search_stations(query=q, limit=limit)


@router.get(
    "/nearby",
    response_model=list[dict],
    summary="Find nearby stations",
    description="Find stations within a radius of a location.",
)
async def find_nearby_stations(
    service: StationServiceDep,
    longitude: Annotated[float, Query(ge=-180, le=180, description="Longitude")],
    latitude: Annotated[float, Query(ge=-90, le=90, description="Latitude")],
    radius_km: Annotated[float, Query(ge=0.1, le=100, description="Radius in km")] = 10.0,
    limit: Annotated[int, Query(ge=1, le=50, description="Max results")] = 10,
) -> list[dict]:
    """Find stations near a location.

    Args:
        service: Station service dependency.
        longitude: Center point longitude.
        latitude: Center point latitude.
        radius_km: Search radius in kilometers.
        limit: Maximum number of results.

    Returns:
        List of stations with distance information.
    """
    return await service.find_nearby_stations(
        longitude=longitude,
        latitude=latitude,
        radius_km=radius_km,
        limit=limit,
    )


@router.get(
    "/{station_id}",
    response_model=StationResponse,
    summary="Get station details",
    description="Get detailed information about a specific station.",
)
async def get_station(
    service: StationServiceDep,
    station_id: int,
) -> StationResponse:
    """Get a single station by ID.

    Args:
        service: Station service dependency.
        station_id: Station ID.

    Returns:
        StationResponse with station details.

    Raises:
        HTTPException: If station not found.
    """
    station = await service.get_station(station_id)
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station with id {station_id} not found",
        )
    return station


@router.post(
    "",
    response_model=StationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a station",
    description="Create a new railway station.",
)
async def create_station(
    service: StationServiceDep,
    data: StationCreate,
) -> StationResponse:
    """Create a new station.

    Args:
        service: Station service dependency.
        data: Station creation data.

    Returns:
        Created StationResponse.
    """
    return await service.create_station(data)


@router.patch(
    "/{station_id}",
    response_model=StationResponse,
    summary="Update a station",
    description="Update an existing station.",
)
async def update_station(
    service: StationServiceDep,
    station_id: int,
    data: StationUpdate,
) -> StationResponse:
    """Update an existing station.

    Args:
        service: Station service dependency.
        station_id: Station ID.
        data: Update data.

    Returns:
        Updated StationResponse.

    Raises:
        HTTPException: If station not found.
    """
    station = await service.update_station(station_id, data)
    if not station:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station with id {station_id} not found",
        )
    return station


@router.delete(
    "/{station_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a station",
    description="Delete a station.",
)
async def delete_station(
    service: StationServiceDep,
    station_id: int,
) -> None:
    """Delete a station.

    Args:
        service: Station service dependency.
        station_id: Station ID.

    Raises:
        HTTPException: If station not found.
    """
    deleted = await service.delete_station(station_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station with id {station_id} not found",
        )
