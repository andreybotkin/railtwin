"""RailDbSetup — FastAPI microservice for database initialization.

Responsibilities:
  1. Run Alembic migrations (CREATE TABLE, extensions, schema changes).
  2. Seed the railroad network from the local KML file (idempotent).
  3. Seed train schedules from local JSON files (idempotent).
  4. Expose /health and /ready probes so dependent services can wait.

Startup sequence (lifespan):
  1. Configure structured logging.
  2. Wait for PostgreSQL to accept connections (SELECT 1).
  3. Launch SetupRunner in background:
       a. alembic upgrade head      — creates / migrates schema
       b. InitRailroadUseCase        — loads KML → routes + stations
       c. InitSchedulesUseCase       — loads JSON → trains + schedules
  4. /ready returns 503 during init, 200 on success, 500 on failure.

This service is the ONLY place where database schema and seed data are managed.
The backend must declare a dependency on this service before starting.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.v1.router import router as v1_router
from app.application.runner import SetupRunner
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)

# Global runner instance — shared between lifespan and endpoints
_runner: SetupRunner | None = None


async def _wait_for_postgres(max_attempts: int = 30, delay: float = 5.0) -> None:
    """Retry until PostgreSQL accepts a connection.

    Does NOT check for any particular table — tables are created by the
    Alembic migrations that run immediately after this check.
    """
    from app.infrastructure.database.session import get_session_factory

    for attempt in range(1, max_attempts + 1):
        try:
            async with get_session_factory()() as session:
                await session.execute(sa.text("SELECT 1"))
            logger.info("PostgreSQL is accessible")
            return
        except Exception as exc:
            logger.warning(
                "PostgreSQL not accessible, retrying",
                attempt=attempt,
                max=max_attempts,
                error=str(exc)[:120],
            )
            if attempt < max_attempts:
                await asyncio.sleep(delay)
    raise RuntimeError(
        f"PostgreSQL not accessible after {max_attempts} attempts."
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _runner
    configure_logging(settings.log_level)
    logger.info(
        "RailDbSetup starting",
        version=settings.app_version,
        environment=settings.environment,
    )

    _runner = SetupRunner()
    app.state.runner = _runner

    # Wait for PostgreSQL to be accessible (before running migrations)
    try:
        await _wait_for_postgres()
    except RuntimeError as exc:
        logger.error("Cannot reach PostgreSQL, aborting initialization", error=str(exc))
        _runner.mark_failed(str(exc))
        yield
        return

    # Run initialization in background so lifespan completes and HTTP server starts
    asyncio.ensure_future(_runner.run_all())

    yield

    logger.info("RailDbSetup shutdown")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Stateless microservice that initializes the Thailand Railway database "
        "from local data files (KML map, raw JSON timetables).  "
        "Idempotent: safe to restart; skips already-loaded data."
    ),
    lifespan=lifespan,
)

app.include_router(v1_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    """Always returns 200 — the process is alive."""
    return {"status": "ok", "service": settings.app_name}


@app.get("/ready", tags=["ops"])
async def ready() -> JSONResponse:
    """Returns 200 when all initialization steps have completed, 503 otherwise."""
    runner: SetupRunner | None = getattr(app.state, "runner", None)
    if runner is None:
        return JSONResponse(status_code=503, content={"status": "initializing"})
    if runner.is_ready:
        return JSONResponse(status_code=200, content={"status": "ready", "result": runner.status})
    if runner.is_failed:
        return JSONResponse(
            status_code=500,
            content={"status": "failed", "error": runner.error},
        )
    return JSONResponse(
        status_code=503,
        content={"status": "initializing", "step": runner.current_step},
    )
