"""Test configuration and fixtures."""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.api.dependencies as _deps
from app.main import app
from app.models.database import Base, get_db

# Use DATABASE_URL from environment (set by CI) or fall back to SQLite.
# PostGIS-dependent tests are skipped automatically when SQLite is used.
_DATABASE_URL = os.environ.get("DATABASE_URL")
TEST_DATABASE_URL = _DATABASE_URL or "sqlite+aiosqlite:///:memory:"

# event_loop fixture removed: pytest-asyncio 1.x manages the loop via
# asyncio_default_fixture_loop_scope in pyproject.toml.


@pytest_asyncio.fixture(autouse=True)
async def _reset_redis_singleton() -> AsyncGenerator[None]:
    """Reset the module-level Redis singleton so each test gets a fresh connection."""
    _deps._redis_client = None
    yield
    if _deps._redis_client is not None:
        try:
            await _deps._redis_client.aclose()
        except Exception:
            pass
    _deps._redis_client = None


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[AsyncSession]:
    """Create test database session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"Database schema creation failed (PostGIS unavailable?): {exc}")
        return

    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_db: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """Create test client with overridden database dependency."""

    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
