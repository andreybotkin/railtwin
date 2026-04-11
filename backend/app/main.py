"""Thailand Railway Digital Twin - FastAPI Application.

This is the main entry point for the backend application, configuring
FastAPI with all middleware, routes, and event handlers.

TODO (deferred — geops patterns for future iterations):
- OpenAPI schema enrichment: add detailed examples, tags, and descriptions
  for openapi-typescript auto-generation (mobility-toolbox-js pattern)
- Structured logging with correlation IDs per request
- Background task scheduler for cache warming and stale-data cleanup
"""

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.dependencies import get_redis
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.models.database import async_session_factory
from app.services.position_cache import build_position_cache_updater
from app.services.tts_scraper import tts_scraper_loop

# Initialize logging
setup_logging()
logger = get_logger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles startup and shutdown events for the application.

    Args:
        app: FastAPI application instance.

    Yields:
        None after startup tasks complete.
    """
    # Startup
    logger.info(
        "Starting Thailand Railway Digital Twin API",
        version=settings.app_version,
        environment=settings.environment,
    )

    redis_client = get_redis()
    scraper_task = asyncio.create_task(
        tts_scraper_loop(redis_client, interval_seconds=3600),
        name="tts_scraper",
    )
    logger.info("TTS scraper background task started")

    position_cache_updater = build_position_cache_updater(async_session_factory, redis_client)
    position_cache_updater.start()

    yield

    # Shutdown
    await position_cache_updater.stop()
    scraper_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await scraper_task
    await redis_client.aclose()
    logger.info("Shutting down Thailand Railway Digital Twin API")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="""
    Thailand Railway Digital Twin backend provides timetable, station,
    route, and train data for the Thai railway network.

    ## Features

    * **Stations**: Browse and search railway stations
    * **Routes**: View railway routes with geographic data
    * **Trains**: Track trains and their current positions
    * **Schedules**: Access train schedules and timetables
    * **Position Cache**: Recalculate active train positions and publish them to Redis
    * **Gateway Integration**: Website-facing realtime traffic is served by the gateway service
    """,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler for unhandled errors.

    Args:
        request: FastAPI request object.
        exc: Exception that was raised.

    Returns:
        JSONResponse with error details.
    """
    logger.error(
        "Unhandled exception",
        exc_info=exc,
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal server error occurred",
            "type": type(exc).__name__,
        },
    )


# Include API routes
app.include_router(
    api_router,
    prefix=settings.api_v1_prefix,
)


@app.get("/", tags=["Health"])
async def root() -> dict[str, str]:
    """Root endpoint with API information.

    Returns:
        Dict with API name and version.
    """
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Dict with health status.
    """
    return {"status": "healthy"}


@app.get("/ready", tags=["Health"])
async def readiness_check() -> dict[str, str]:
    """Readiness check endpoint.

    Checks if the application is ready to receive traffic.

    Returns:
        Dict with readiness status.
    """
    from sqlalchemy import text

    from app.models.database import async_session_factory

    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "detail": "Database connection failed"},
        )
    return {"status": "ready"}
