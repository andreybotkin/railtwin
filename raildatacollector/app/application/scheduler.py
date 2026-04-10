"""APScheduler configuration.

Jobs:
  - update_schedules  — daily at 03:00 Asia/Bangkok
  - update_delays     — every 30 minutes (configurable)

The railroad initialization is triggered once at startup from main.py
and is not managed by the scheduler.
"""

from datetime import datetime
from typing import Any

import redis.asyncio as aioredis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.application.use_cases.update_delays import UpdateDelaysUseCase
from app.application.use_cases.update_schedules import UpdateSchedulesUseCase
from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.database.repositories.delays import RedisDelayRepository
from app.infrastructure.database.repositories.schedule import SqlScheduleRepository
from app.infrastructure.database.session import get_session_factory

logger = get_logger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Bangkok")

# Status store — accessible from API endpoints
_status: dict[str, dict[str, Any]] = {
    "railroad": {"last_run": None, "last_result": None},
    "schedules": {"last_run": None, "last_result": None},
    "delays": {"last_run": None, "last_result": None},
}


def get_status() -> dict[str, dict[str, Any]]:
    return _status


# --------------------------------------------------------------------------- #
# Job runners                                                                  #
# --------------------------------------------------------------------------- #


async def run_update_schedules() -> None:
    """Periodic job: fetch fresh timetable and upsert into DB unconditionally."""
    _status["schedules"]["last_run"] = datetime.utcnow().isoformat()
    try:
        async with get_session_factory()() as session:
            async with session.begin():
                result = await UpdateSchedulesUseCase(
                    SqlScheduleRepository(session)
                ).execute()
        _status["schedules"]["last_result"] = result
    except Exception as exc:
        logger.error("Schedule update job failed", error=str(exc))
        _status["schedules"]["last_result"] = {"success": False, "error": str(exc)}


async def run_init_schedules() -> None:
    """Startup job: load ALL schedules from raw files only when the DB is empty.

    Each train is committed in its own transaction so a single bad file
    does not roll back the entire dataset.  Skipped on subsequent restarts.
    """
    from app.application.use_cases.init_schedules import InitSchedulesUseCase

    _status["schedules"]["last_run"] = datetime.utcnow().isoformat()
    try:
        result = await InitSchedulesUseCase.run(get_session_factory())
        _status["schedules"]["last_result"] = result
        if result.get("skipped"):
            logger.info("Schedule init skipped — DB already populated")
        else:
            logger.info("Schedules initialized from raw files", result=result)
    except Exception as exc:
        logger.error("Schedule init failed", error=str(exc))
        _status["schedules"]["last_result"] = {"success": False, "error": str(exc)}


async def run_update_delays(redis_client: aioredis.Redis) -> None:
    _status["delays"]["last_run"] = datetime.utcnow().isoformat()
    try:
        result = await UpdateDelaysUseCase(RedisDelayRepository(redis_client)).execute()
        _status["delays"]["last_result"] = result
    except Exception as exc:
        logger.error("Delay update job failed", error=str(exc))
        _status["delays"]["last_result"] = {"success": False, "error": str(exc)}


async def run_init_railroad(force: bool = False) -> None:
    """Run inside an open DB transaction (called from main.py lifespan)."""
    from app.application.use_cases.init_railroad import InitRailroadUseCase
    from app.infrastructure.database.repositories.railroad import SqlRailroadRepository

    _status["railroad"]["last_run"] = datetime.utcnow().isoformat()
    try:
        async with get_session_factory()() as session:
            async with session.begin():
                result = await InitRailroadUseCase(
                    SqlRailroadRepository(session)
                ).execute(force=force)
        _status["railroad"]["last_result"] = result
        logger.info("Railroad init complete", result=result)
    except Exception as exc:
        logger.error("Railroad init failed", error=str(exc))
        _status["railroad"]["last_result"] = {"success": False, "error": str(exc)}


# --------------------------------------------------------------------------- #
# Scheduler setup                                                               #
# --------------------------------------------------------------------------- #


def setup_scheduler(redis_client: aioredis.Redis) -> AsyncIOScheduler:
    """Register all periodic jobs and return the scheduler (not yet started)."""

    # Monthly timetable update: 1st of each month at 10:00 Bangkok time
    scheduler.add_job(
        run_update_schedules,
        CronTrigger(
            day=settings.schedule_update_day_of_month,
            hour=settings.schedule_update_hour,
            minute=settings.schedule_update_minute,
            timezone="Asia/Bangkok",
        ),
        id="update_schedules",
        name="Monthly timetable update (1st, 10:00)",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Delay update every 30 minutes
    scheduler.add_job(
        run_update_delays,
        IntervalTrigger(seconds=settings.delays_update_interval_seconds),
        args=[redis_client],
        id="update_delays",
        name="30-min delay update",
        replace_existing=True,
        misfire_grace_time=300,
    )

    return scheduler
