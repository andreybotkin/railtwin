"""Manual trigger endpoints for data-collection jobs.

These endpoints allow operators to trigger a collection run immediately
without waiting for the scheduler, useful for debugging or after incidents.
"""

from fastapi import APIRouter, BackgroundTasks, Request

from app.application.scheduler import (
    run_init_railroad,
    run_update_delays,
    run_update_schedules,
)

router = APIRouter()


@router.post(
    "/railroad",
    summary="Trigger railroad network initialization",
    description=(
        "Loads routes and stations from the local KML file (or downloads it) "
        "and writes them to the database.  Use force=true to overwrite existing data."
    ),
)
async def trigger_railroad(
    background_tasks: BackgroundTasks,
    force: bool = False,
) -> dict:
    background_tasks.add_task(run_init_railroad, force)
    return {"message": "Railroad initialization triggered", "force": force}


@router.post(
    "/schedules",
    summary="Trigger timetable update",
    description=(
        "Fetches the latest train timetable (local cache → TTS remote) "
        "and upserts train and schedule records in the database."
    ),
)
async def trigger_schedules(background_tasks: BackgroundTasks) -> dict:
    background_tasks.add_task(run_update_schedules)
    return {"message": "Schedule update triggered"}


@router.post(
    "/delays",
    summary="Trigger delay update",
    description=(
        "Connects to the TTS Socket.IO server, fetches current train delays, "
        "and stores them in Redis for immediate use by the backend simulation."
    ),
)
async def trigger_delays(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    redis_client = request.app.state.redis
    background_tasks.add_task(run_update_delays, redis_client)
    return {"message": "Delay update triggered"}
