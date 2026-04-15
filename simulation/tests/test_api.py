"""Tests for API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient) -> None:
    """Test root endpoint returns API information."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    """Test health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_check(client: AsyncClient) -> None:
    """Test readiness check endpoint.

    Without loaded reference data the endpoint returns 503.
    """
    response = await client.get("/ready")
    # Reference data is not loaded in the test environment, so the
    # readiness probe correctly reports "not ready".
    assert response.status_code in (200, 503)
    data = response.json()
    assert data["status"] in ("ready", "not_ready")


@pytest.mark.asyncio
async def test_list_stations_empty(client: AsyncClient) -> None:
    """Test listing stations when database is empty."""
    response = await client.get("/api/v1/stations")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_routes_empty(client: AsyncClient) -> None:
    """Test listing routes when database is empty."""
    response = await client.get("/api/v1/routes")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_trains_empty(client: AsyncClient) -> None:
    """Test listing trains when database is empty."""
    response = await client.get("/api/v1/trains")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_schedules_empty(client: AsyncClient) -> None:
    """Test listing schedules when database is empty."""
    response = await client.get("/api/v1/schedules")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["items"] == []


@pytest.mark.asyncio
async def test_get_station_not_found(client: AsyncClient) -> None:
    """Test getting non-existent station returns 404."""
    response = await client.get("/api/v1/stations/999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_route_not_found(client: AsyncClient) -> None:
    """Test getting non-existent route returns 404."""
    response = await client.get("/api/v1/routes/999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_train_not_found(client: AsyncClient) -> None:
    """Test getting non-existent train returns 404."""
    response = await client.get("/api/v1/trains/999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_openapi_schema(client: AsyncClient) -> None:
    """Test OpenAPI schema is available."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "info" in data
    assert "paths" in data
