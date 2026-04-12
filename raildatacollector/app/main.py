"""RailDataCollector — FastAPI application entry point.

Startup sequence (lifespan):
  1. Configure structured logging.
  2. Connect to Redis (shared with backend).
  3. Wait for the database to be ready (raildbsetup must finish first).
  4. Start background delay fetch from TTS (fire-and-forget).
  5. Start APScheduler:
       - monthly (1st, 10:00 Bangkok) timetable update → DB + file + Redis
       - every 30 min delay update from TTS → Redis

Schema creation and initial data seeding are handled exclusively by
``raildbsetup``. In docker-compose this service depends on raildbsetup
being healthy. In other environments _wait_for_db provides a safety check.

On shutdown the scheduler and Redis connection are closed gracefully.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import redis.asyncio as aioredis
from fastapi import FastAPI
from sqlalchemy import select

from app.api.v1.router import router as v1_router
from app.application.scheduler import (
    run_update_delays,
    setup_scheduler,
)
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.infrastructure.database.session import get_session_factory

logger = get_logger(__name__)


async def _wait_for_db(max_attempts: int = 20, delay: float = 5.0) -> None:
    """Retry until the database is accessible and station-graph topology exists.

    The ``raildbsetup`` service populates the schema before this service
    starts (docker-compose dependency).  This function is a safety
    check for non-compose environments (K8S, local dev without compose).
    """
    for attempt in range(1, max_attempts + 1):
        try:
            async with get_session_factory()() as session:
                from app.infrastructure.database.tables import (
                    t_network_edges,
                    t_stations,
                    t_topology_metadata,
                )

                await session.execute(select(t_stations.c.id).limit(1))
                topology_row = await session.execute(
                    select(t_topology_metadata.c.topology_version).limit(1)
                )
                edge_row = await session.execute(select(t_network_edges.c.id).limit(1))
                if topology_row.scalar_one_or_none() is None or edge_row.scalar_one_or_none() is None:
                    raise RuntimeError("Station-graph topology not ready yet")
            logger.info("Database and station-graph topology are ready")
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

    # Safety check: ensure DB schema is accessible
    await _wait_for_db()

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
