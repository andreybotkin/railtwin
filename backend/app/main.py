"""Thailand Railway Digital Twin - FastAPI Application.

This is the main entry point for the backend application, configuring
FastAPI with all middleware, routes, and event handlers.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.dependencies import get_redis
from app.api.v1.router import api_router
from app.api.v1.endpoints.websocket import router as websocket_router, broadcaster
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.services.tts_scraper import tts_scraper_loop

# Initialize logging
setup_logging()
logger = get_logger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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

    # Start the position broadcaster (single shared DB query for all WS clients)
    broadcaster.start()

    yield

    # Shutdown
    broadcaster.stop()
    scraper_task.cancel()
    try:
        await scraper_task
    except asyncio.CancelledError:
        pass
    await redis_client.aclose()
    logger.info("Shutting down Thailand Railway Digital Twin API")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="""
    Thailand Railway Digital Twin API provides real-time tracking and 
    information about the Thai railway network.
    
    ## Features
    
    * **Stations**: Browse and search railway stations
    * **Routes**: View railway routes with geographic data
    * **Trains**: Track trains and their current positions
    * **Schedules**: Access train schedules and timetables
    * **Real-time Updates**: WebSocket connections for live train positions
    
    ## WebSocket Endpoints
    
    * `/ws/trains` - Stream all train positions
    * `/ws/trains/{train_id}` - Stream a single train's position
    """,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

# Include WebSocket routes
app.include_router(
    websocket_router,
    prefix="/ws",
    tags=["WebSocket"],
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
    # TODO: Add database connectivity check
    return {"status": "ready"}
