"""Tests for automatic recovery after Redis loses its reference snapshot."""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from app.services import position_cache
from app.services.position_cache import (
    REFERENCE_DATA_REBUILD_LOCK_KEY,
    REFERENCE_DATA_REBUILD_LOCK_TTL,
    PositionCacheUpdater,
)


@pytest.mark.asyncio
async def test_missing_reference_data_is_rebuilt_under_lock(monkeypatch) -> None:
    redis_client = AsyncMock()
    redis_client.set.return_value = True
    redis_client.eval.return_value = 1

    session_context = AsyncMock()
    session_context.__aenter__.return_value = MagicMock()
    session_factory = MagicMock(return_value=session_context)

    loader = MagicMock()
    loader.load = AsyncMock(return_value={"load_status": "ready", "stations_count": 10})
    loader_type = MagicMock(return_value=loader)
    monkeypatch.setattr(position_cache, "RedisReferenceDataLoader", loader_type)

    updater = PositionCacheUpdater(session_factory, redis_client, interval_seconds=10)
    reader = AsyncMock()
    reader.is_ready.return_value = False
    updater._reader = reader

    assert await updater._ensure_reference_data() is True
    redis_client.set.assert_awaited_once_with(
        REFERENCE_DATA_REBUILD_LOCK_KEY,
        ANY,
        ex=REFERENCE_DATA_REBUILD_LOCK_TTL,
        nx=True,
    )
    loader.load.assert_awaited_once()
    redis_client.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_rebuild_is_skipped_when_another_worker_holds_lock(monkeypatch) -> None:
    redis_client = AsyncMock()
    redis_client.set.return_value = None
    session_factory = MagicMock()

    loader_type = MagicMock()
    monkeypatch.setattr(position_cache, "RedisReferenceDataLoader", loader_type)

    updater = PositionCacheUpdater(session_factory, redis_client, interval_seconds=10)
    reader = AsyncMock()
    reader.is_ready.return_value = False
    updater._reader = reader

    assert await updater._ensure_reference_data() is False
    session_factory.assert_not_called()
    loader_type.assert_not_called()
    redis_client.eval.assert_not_awaited()
