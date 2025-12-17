"""API v1 router configuration.

This module combines all endpoint routers for API version 1.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import routes, schedules, stations, trains

api_router = APIRouter()

api_router.include_router(
    stations.router,
    prefix="/stations",
    tags=["Stations"],
)

api_router.include_router(
    routes.router,
    prefix="/routes",
    tags=["Routes"],
)

api_router.include_router(
    trains.router,
    prefix="/trains",
    tags=["Trains"],
)

api_router.include_router(
    schedules.router,
    prefix="/schedules",
    tags=["Schedules"],
)
