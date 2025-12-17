"""API dependencies for dependency injection.

This module provides common dependencies used across API endpoints,
including database sessions and services.
"""

from typing import Annotated, AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.services.route import RouteService
from app.services.schedule import ScheduleService
from app.services.simulation import TrainSimulationService
from app.services.station import StationService
from app.services.train import TrainService


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency.

    Yields:
        AsyncSession: Database session.
    """
    async for session in get_db():
        yield session


# Type aliases for cleaner dependency injection
DBSession = Annotated[AsyncSession, Depends(get_session)]


async def get_station_service(session: DBSession) -> StationService:
    """Get station service dependency.

    Args:
        session: Database session.

    Returns:
        StationService instance.
    """
    return StationService(session)


async def get_route_service(session: DBSession) -> RouteService:
    """Get route service dependency.

    Args:
        session: Database session.

    Returns:
        RouteService instance.
    """
    return RouteService(session)


async def get_train_service(session: DBSession) -> TrainService:
    """Get train service dependency.

    Args:
        session: Database session.

    Returns:
        TrainService instance.
    """
    return TrainService(session)


async def get_schedule_service(session: DBSession) -> ScheduleService:
    """Get schedule service dependency.

    Args:
        session: Database session.

    Returns:
        ScheduleService instance.
    """
    return ScheduleService(session)


async def get_simulation_service(session: DBSession) -> TrainSimulationService:
    """Get simulation service dependency.

    Args:
        session: Database session.

    Returns:
        TrainSimulationService instance.
    """
    return TrainSimulationService(session)


# Typed dependencies for use in endpoints
StationServiceDep = Annotated[StationService, Depends(get_station_service)]
RouteServiceDep = Annotated[RouteService, Depends(get_route_service)]
TrainServiceDep = Annotated[TrainService, Depends(get_train_service)]
ScheduleServiceDep = Annotated[ScheduleService, Depends(get_schedule_service)]
SimulationServiceDep = Annotated[TrainSimulationService, Depends(get_simulation_service)]
