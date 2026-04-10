"""RailDataCollector — FastAPI application entry point.

Startup sequence (lifespan):
  1. Configure structured logging.
  2. Connect to Redis (shared with backend).
  3. Wait for the database to be accessible (tables created by backend alembic).
  4. First-run check: if railroad network is empty → load from local KML.
  5. First-run check: if trains table is empty → load from local seed file.
  6. Start background delay fetch from TTS (fire-and-forget).
  7. Start APScheduler:
       - monthly (1st, 10:00 Bangkok) timetable update
       - every 30 min delay update from TTS

On shutdown the scheduler and Redis connection are closed gracefully.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import redis.asyncio as aioredis
import sqlalchemy as sa
from fastapi import FastAPI

from app.api.v1.router import router as v1_router
from app.application.scheduler import (
    run_init_railroad,
    run_init_schedules,
    run_update_delays,
    setup_scheduler,
)
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.infrastructure.database.session import get_session_factory

logger = get_logger(__name__)


async def _wait_for_db(max_attempts: int = 20, delay: float = 5.0) -> None:
    """Retry until the database tables are accessible.

    The backend runs ``alembic upgrade head`` before starting uvicorn.
    This function ensures raildatacollector does not proceed until the
    shared schema is fully in place.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            async with get_session_factory()() as session:
                await session.execute(sa.text("SELECT 1 FROM stations LIMIT 1"))
            logger.info("Database is ready")
            return
        except Exception as exc:
            logger.warning(
                "Database not ready, retrying",
                attempt=attempt,
                max=max_attempts,
                error=str(exc)[:120],
            )
            if attempt < max_attempts:
                await asyncio.sleep(delay)
    raise RuntimeError(f"Database not accessible after {max_attempts} attempts")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.log_level)
    logger.info(
        "RailDataCollector starting",
        version=settings.app_version,
        environment=settings.environment,
    )

    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    app.state.redis = redis_client

    # --- Wait for DB tables to be ready (backend alembic must finish first) --
    await _wait_for_db()

    # --- First-run: initialize railroad network from local KML ---------------
    # Skipped automatically if stations table is already populated.
    await run_init_railroad(force=False)

    # --- First-run: load train schedules from local seed file ----------------
    # Skipped automatically if trains table is already populated.
    # Runs in background so the HTTP server becomes available immediately.
    asyncio.ensure_future(run_init_schedules())

    # --- Start background delay fetch from TTS --------------------------------
    asyncio.ensure_future(run_update_delays(redis_client))

    # --- Start periodic scheduler --------------------------------------------
    sched = setup_scheduler(redis_client)
    sched.start()
    logger.info(
        "Scheduler started",
        jobs=[job.id for job in sched.get_jobs()],
    )

    yield

    sched.shutdown(wait=False)
    await redis_client.aclose()
    logger.info("RailDataCollector shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Microservice responsible for collecting and maintaining Thailand "
        "Railway data: network topology (once), timetables (daily), and "
        "real-time train delays (every 30 minutes)."
    ),
    lifespan=lifespan,
)

app.include_router(v1_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name}


@app.get("/ready", tags=["ops"])
async def ready() -> dict:
    return {"status": "ready"}
