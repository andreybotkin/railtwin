"""Route API endpoints.

This module provides RESTful API endpoints for managing railway routes.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import RouteServiceDep
from app.schemas.route import (
    RouteCreate,
    RouteListResponse,
    RouteResponse,
    RouteUpdate,
)

router = APIRouter()


@router.get(
    "",
    response_model=RouteListResponse,
    summary="List all routes",
    description="Get a paginated list of all railway routes.",
)
async def list_routes(
    service: RouteServiceDep,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    route_type: Annotated[str | None, Query(description="Filter by route type")] = None,
) -> RouteListResponse:
    """List all routes with pagination and optional filtering.

    Args:
        service: Route service dependency.
        page: Page number (1-indexed).
        size: Number of items per page.
        route_type: Filter by route type (northern, northeastern, etc.).

    Returns:
        RouteListResponse with paginated routes.
    """
    return await service.list_routes(page=page, size=size, route_type=route_type)


@router.get(
    "/{route_id}",
    response_model=RouteResponse,
    summary="Get route details",
    description="Get detailed information about a specific route including geometry.",
)
async def get_route(
    service: RouteServiceDep,
    route_id: int,
) -> RouteResponse:
    """Get a single route by ID with full geometry.

    Args:
        service: Route service dependency.
        route_id: Route ID.

    Returns:
        RouteResponse with route details and geometry.

    Raises:
        HTTPException: If route not found.
    """
    route = await service.get_route(route_id)
    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route with id {route_id} not found",
        )
    return route


@router.post(
    "",
    response_model=RouteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a route",
    description="Create a new railway route.",
)
async def create_route(
    service: RouteServiceDep,
    data: RouteCreate,
) -> RouteResponse:
    """Create a new route.

    Args:
        service: Route service dependency.
        data: Route creation data.

    Returns:
        Created RouteResponse.
    """
    return await service.create_route(data)


@router.patch(
    "/{route_id}",
    response_model=RouteResponse,
    summary="Update a route",
    description="Update an existing route.",
)
async def update_route(
    service: RouteServiceDep,
    route_id: int,
    data: RouteUpdate,
) -> RouteResponse:
    """Update an existing route.

    Args:
        service: Route service dependency.
        route_id: Route ID.
        data: Update data.

    Returns:
        Updated RouteResponse.

    Raises:
        HTTPException: If route not found.
    """
    route = await service.update_route(route_id, data)
    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route with id {route_id} not found",
        )
    return route


@router.delete(
    "/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a route",
    description="Delete a route.",
)
async def delete_route(
    service: RouteServiceDep,
    route_id: int,
) -> None:
    """Delete a route.

    Args:
        service: Route service dependency.
        route_id: Route ID.

    Raises:
        HTTPException: If route not found.
    """
    deleted = await service.delete_route(route_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route with id {route_id} not found",
        )


@router.post(
    "/{route_id}/stations/{station_id}",
    response_model=RouteResponse,
    summary="Add station to route",
    description="Add a station to a route at a specific sequence position.",
)
async def add_station_to_route(
    service: RouteServiceDep,
    route_id: int,
    station_id: int,
    sequence: Annotated[int, Query(ge=0, description="Station sequence on route")],
    distance_from_start: Annotated[float | None, Query(description="Distance from start in km")] = None,
) -> RouteResponse:
    """Add a station to a route.

    Args:
        service: Route service dependency.
        route_id: Route ID.
        station_id: Station ID to add.
        sequence: Order of station on route.
        distance_from_start: Distance from route start in km.

    Returns:
        Updated RouteResponse.

    Raises:
        HTTPException: If route not found.
    """
    route = await service.add_station_to_route(
        route_id=route_id,
        station_id=station_id,
        sequence=sequence,
        distance_from_start=distance_from_start,
    )
    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route with id {route_id} not found",
        )
    return route
