"""APScheduler configuration for RailDataCollector.

Jobs:
  - update_schedules  — monthly (1st, 10:00 Asia/Bangkok): fetch timetable,
                        save to DB + JSON file + Redis.
  - update_delays     — every 30 minutes: fetch real-time delays from TTS,
                        store in Redis.

Database initialization has been moved to the ``raildbsetup`` microservice.
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

# Module-level redis client — set once by setup_scheduler()
_redis_client: aioredis.Redis | None = None

# Status store — accessible from API endpoints
_status: dict[str, dict[str, Any]] = {
    "schedules": {"last_run": None, "last_result": None},
    "delays": {"last_run": None, "last_result": None},
}


def get_status() -> dict[str, dict[str, Any]]:
    return _status


# --------------------------------------------------------------------------- #
# Job runners                                                                  #
# --------------------------------------------------------------------------- #


async def run_update_schedules() -> None:
    """Periodic job: fetch fresh timetable, upsert to DB, cache to file + Redis."""
    _status["schedules"]["last_run"] = datetime.utcnow().isoformat()
    try:
        async with get_session_factory()() as session:
            async with session.begin():
                result = await UpdateSchedulesUseCase(
                    SqlScheduleRepository(session),
                    redis_client=_redis_client,
                ).execute()
        _status["schedules"]["last_result"] = result
    except Exception as exc:
        logger.error("Schedule update job failed", error=str(exc))
        _status["schedules"]["last_result"] = {"success": False, "error": str(exc)}


async def run_update_delays(redis_client: aioredis.Redis) -> None:
    """Periodic job: fetch real-time delays from TTS, store in Redis."""
    _status["delays"]["last_run"] = datetime.utcnow().isoformat()
    try:
        result = await UpdateDelaysUseCase(RedisDelayRepository(redis_client)).execute()
        _status["delays"]["last_result"] = result
    except Exception as exc:
        logger.error("Delay update job failed", error=str(exc))
        _status["delays"]["last_result"] = {"success": False, "error": str(exc)}


# --------------------------------------------------------------------------- #
# Scheduler setup                                                               #
# --------------------------------------------------------------------------- #


def setup_scheduler(redis_client: aioredis.Redis) -> AsyncIOScheduler:
    """Register all periodic jobs and return the scheduler (not yet started)."""
    global _redis_client
    _redis_client = redis_client

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
