"""Tests for Kubernetes-facing operational behaviour."""

import json
import logging
from types import SimpleNamespace

import pytest

from app.core.logging import ProbeAccessFilter
from app.main import app, ready


def _access_record(path: str, status_code: int) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:1234", "GET", path, "1.1", status_code),
        exc_info=None,
    )


def test_probe_access_filter_suppresses_health_and_ready() -> None:
    access_filter = ProbeAccessFilter()

    assert access_filter.filter(_access_record("/health", 200)) is False
    assert access_filter.filter(_access_record("/ready", 200)) is False
    assert access_filter.filter(_access_record("/ready?verbose=true", 200)) is False
    assert access_filter.filter(_access_record("/api/v1/setup/status", 200)) is True


@pytest.mark.asyncio
async def test_ready_returns_ok_while_initializing() -> None:
    app.state.runner = SimpleNamespace(
        is_ready=False,
        is_failed=False,
        error=None,
        current_step="schedules",
        status={},
    )

    response = await ready()

    assert response.status_code == 200
    assert json.loads(response.body) == {
        "status": "initializing",
        "step": "schedules",
    }


@pytest.mark.asyncio
async def test_ready_still_fails_for_setup_error() -> None:
    app.state.runner = SimpleNamespace(
        is_ready=False,
        is_failed=True,
        error="database unavailable",
        current_step="migrations",
        status={},
    )

    response = await ready()

    assert response.status_code == 500
    assert json.loads(response.body) == {
        "status": "failed",
        "error": "database unavailable",
    }
