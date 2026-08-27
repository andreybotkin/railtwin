"""Integration tests: feature-flag routing in TrainSimulationService.

These tests verify that the ``movement_plan_runtime_enabled`` /
``movement_plan_fallback_enabled`` flags correctly gate the movement plan
path and fall through to ``build_trajectory()`` when appropriate.

All I/O (DB, Redis, network) is mocked via monkeypatching.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import app.services.simulation as sim_module
from app.domain.movement_plan import PlannedMovementSegment, PlannedTrainRun
from app.services.simulation import TrainSimulationService

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_ROUTE = [[100.5, 13.75], [100.6, 14.35]]
_NOW_MS = 1_700_000_000_000

_TRAIN_PAYLOAD = {
    "id": 1,
    "train_number": "101",
    "current_route_id": 10,
    "train_type": "express",
    "name": "Test Express",
    "operator": "SRT",
}

_SCHEDULE_PAYLOAD = [
    {
        "id": 1,
        "train_id": 1,
        "station_id": 101,
        "station_name": "Bangkok",
        "station_name_th": "กรุงเทพ",
        "arrival_time_minutes": 600,
        "departure_time_minutes": 600,
        "day_offset": 0,
        "sequence": 1,
    }
]

_ROUTE_GEOMETRY = {
    "coords": _ROUTE,
    "distance_km": 70.0,
    "segments": [],
}

_SENTINEL_TRAJECTORY = object()  # used to distinguish which function produced a result


def _make_move_segment() -> PlannedMovementSegment:
    return PlannedMovementSegment(
        id=1,
        planned_run_id=99,
        sequence=1,
        segment_type="move",
        from_station_id=101,
        to_station_id=102,
        from_schedule_id=1,
        to_schedule_id=1,
        start_time_minutes=600.0,
        end_time_minutes=720.0,
        start_day_offset=0,
        end_day_offset=0,
        start_distance_m=0.0,
        end_distance_m=70_000.0,
        start_geom_fraction=0.0,
        end_geom_fraction=1.0,
        start_edge_id=None,
        end_edge_id=None,
        planned_speed_kmh=60.0,
        quality_score=1.0,
        warnings=[],
    )


def _make_plan(status: str = "ready") -> PlannedTrainRun:
    return PlannedTrainRun(
        id=99,
        train_id=1,
        route_id=10,
        service_date=None,
        plan_version=1,
        topology_version="topo-1",
        quality_score=1.0,
        status=status,  # type: ignore[arg-type]
        warnings=[],
        segments=[_make_move_segment()],
    )


class _DummyReader:
    """Minimal reader that serves one train payload + movement plans on demand."""

    def __init__(
        self,
        *,
        movement_plans: dict[int, PlannedTrainRun | None] | None = None,
    ) -> None:
        self._movement_plans: dict[int, PlannedTrainRun | None] = movement_plans or {}

    async def get_all_trains_for_simulation(
        self, *, skip: int, limit: int
    ) -> list[dict]:
        if skip > 0:
            return []
        return [_TRAIN_PAYLOAD]

    async def get_schedules_by_trains(self, train_ids: list[int]) -> dict[int, list]:
        return dict.fromkeys(train_ids, _SCHEDULE_PAYLOAD)

    async def get_route_geometry_bulk(self, route_ids: list[int]) -> dict[int, dict]:
        return dict.fromkeys(route_ids, _ROUTE_GEOMETRY)

    async def get_train_geometry_bulk(self, train_ids: list[int]) -> dict[int, dict]:
        return {
            train_id: {**_ROUTE_GEOMETRY, "valid": True, "source": "legacy_test"}
            for train_id in train_ids
        }

    async def get_movement_plans_bulk(
        self, train_ids: list[int]
    ) -> dict[int, PlannedTrainRun | None]:
        return {tid: self._movement_plans.get(tid) for tid in train_ids}


def _build_service(reader: _DummyReader) -> TrainSimulationService:
    service = TrainSimulationService(session=SimpleNamespace(), redis_client=None)
    service.reader = reader
    return service


def _patch_common(
    monkeypatch: pytest.MonkeyPatch, service: TrainSimulationService
) -> None:
    """Patch I/O helpers shared by all integration tests."""
    monkeypatch.setattr(service, "_load_delays", _noop_load_delays)
    monkeypatch.setattr(
        service,
        "_get_candidate_current_minutes_with_delay",
        lambda schedules, delay: 660.0,  # midpoint of [600, 720]
    )
    monkeypatch.setattr(
        sim_module,
        "train_payload_to_domain",
        lambda payload: SimpleNamespace(
            id=int(payload["id"]),
            train_number=str(payload["train_number"]),
            train_type=payload.get("train_type"),
            name=payload.get("name"),
            operator=payload.get("operator"),
            current_route_id=payload.get("current_route_id"),
        ),
    )
    monkeypatch.setattr(
        sim_module,
        "schedule_payloads_to_domain",
        lambda payloads: [SimpleNamespace(**p) for p in payloads],
    )
    monkeypatch.setattr(
        sim_module,
        "build_stop_sequence",
        lambda *args, **kwargs: [],
    )


async def _noop_load_delays(self: Any = None) -> None:
    if self is not None and hasattr(self, "_tts_delays"):
        self._tts_delays = {}


# ---------------------------------------------------------------------------
# Test: flag disabled → only build_trajectory is called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_off_uses_only_build_trajectory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sim_module.settings, "movement_plan_runtime_enabled", False)

    resolver_called: list[bool] = []
    build_called: list[bool] = []

    def _fake_resolve(**kwargs: Any) -> object:
        resolver_called.append(True)
        return _SENTINEL_TRAJECTORY

    def _fake_build(*args: Any, **kwargs: Any) -> object:
        build_called.append(True)
        return _SENTINEL_TRAJECTORY

    reader = _DummyReader(movement_plans={1: _make_plan()})
    service = _build_service(reader)
    _patch_common(monkeypatch, service)
    monkeypatch.setattr(sim_module, "_resolve_from_plan", _fake_resolve)
    monkeypatch.setattr(sim_module, "build_trajectory", _fake_build)

    trajectories, _ = await service.get_all_active_train_data()

    assert resolver_called == []
    assert build_called == [True]
    assert len(trajectories) == 1


# ---------------------------------------------------------------------------
# Test: flag enabled + valid plan → resolver is called, fallback is NOT called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_on_valid_plan_uses_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sim_module.settings, "movement_plan_runtime_enabled", True)
    monkeypatch.setattr(sim_module.settings, "movement_plan_fallback_enabled", True)

    resolver_called: list[bool] = []
    build_called: list[bool] = []

    def _fake_resolve(**kwargs: Any) -> object:
        resolver_called.append(True)
        return _SENTINEL_TRAJECTORY

    def _fake_build(*args: Any, **kwargs: Any) -> object:
        build_called.append(True)
        return _SENTINEL_TRAJECTORY

    reader = _DummyReader(movement_plans={1: _make_plan()})
    service = _build_service(reader)
    _patch_common(monkeypatch, service)
    monkeypatch.setattr(sim_module, "_resolve_from_plan", _fake_resolve)
    monkeypatch.setattr(sim_module, "build_trajectory", _fake_build)

    trajectories, _ = await service.get_all_active_train_data()

    assert resolver_called == [True]
    assert build_called == []
    assert len(trajectories) == 1


# ---------------------------------------------------------------------------
# Test: flag enabled + no plan in reader → fallback to build_trajectory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_on_no_plan_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sim_module.settings, "movement_plan_runtime_enabled", True)
    monkeypatch.setattr(sim_module.settings, "movement_plan_fallback_enabled", True)

    build_called: list[bool] = []

    def _fake_build(*args: Any, **kwargs: Any) -> object:
        build_called.append(True)
        return _SENTINEL_TRAJECTORY

    reader = _DummyReader(movement_plans={})  # no plan for train 1
    service = _build_service(reader)
    _patch_common(monkeypatch, service)
    monkeypatch.setattr(sim_module, "build_trajectory", _fake_build)

    trajectories, _ = await service.get_all_active_train_data()

    assert build_called == [True]
    assert len(trajectories) == 1


# ---------------------------------------------------------------------------
# Test: flag enabled + resolver returns None → fallback to build_trajectory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_on_resolver_none_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sim_module.settings, "movement_plan_runtime_enabled", True)
    monkeypatch.setattr(sim_module.settings, "movement_plan_fallback_enabled", True)

    build_called: list[bool] = []

    def _fake_resolve(**kwargs: Any) -> None:
        return None  # resolver yields nothing

    def _fake_build(*args: Any, **kwargs: Any) -> object:
        build_called.append(True)
        return _SENTINEL_TRAJECTORY

    reader = _DummyReader(movement_plans={1: _make_plan()})
    service = _build_service(reader)
    _patch_common(monkeypatch, service)
    monkeypatch.setattr(sim_module, "_resolve_from_plan", _fake_resolve)
    monkeypatch.setattr(sim_module, "build_trajectory", _fake_build)

    trajectories, _ = await service.get_all_active_train_data()

    assert build_called == [True]
    assert len(trajectories) == 1


# ---------------------------------------------------------------------------
# Test: strict mode (fallback disabled) + resolver returns None → train skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strict_mode_no_fallback_skips_train_when_resolver_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sim_module.settings, "movement_plan_runtime_enabled", True)
    monkeypatch.setattr(sim_module.settings, "movement_plan_fallback_enabled", False)

    build_called: list[bool] = []

    def _fake_resolve(**kwargs: Any) -> None:
        return None

    def _fake_build(*args: Any, **kwargs: Any) -> object:
        build_called.append(True)
        return _SENTINEL_TRAJECTORY

    reader = _DummyReader(movement_plans={1: _make_plan()})
    service = _build_service(reader)
    _patch_common(monkeypatch, service)
    monkeypatch.setattr(sim_module, "_resolve_from_plan", _fake_resolve)
    monkeypatch.setattr(sim_module, "build_trajectory", _fake_build)

    trajectories, _ = await service.get_all_active_train_data()

    assert build_called == []  # fallback disabled → not called
    assert trajectories == []  # train skipped


# ---------------------------------------------------------------------------
# Test: invalid plan (status=invalid) is treated as no plan → fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_plan_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sim_module.settings, "movement_plan_runtime_enabled", True)
    monkeypatch.setattr(sim_module.settings, "movement_plan_fallback_enabled", True)

    resolver_called: list[bool] = []
    build_called: list[bool] = []

    def _fake_resolve(**kwargs: Any) -> object:
        resolver_called.append(True)
        return _SENTINEL_TRAJECTORY

    def _fake_build(*args: Any, **kwargs: Any) -> object:
        build_called.append(True)
        return _SENTINEL_TRAJECTORY

    # Plan has status=invalid → is_usable() returns False
    invalid_plan = _make_plan(status="invalid")
    reader = _DummyReader(movement_plans={1: invalid_plan})
    service = _build_service(reader)
    _patch_common(monkeypatch, service)
    monkeypatch.setattr(sim_module, "_resolve_from_plan", _fake_resolve)
    monkeypatch.setattr(sim_module, "build_trajectory", _fake_build)

    trajectories, _ = await service.get_all_active_train_data()

    # resolver should NOT be called (plan is not usable)
    assert resolver_called == []
    assert build_called == [True]
    assert len(trajectories) == 1


# ---------------------------------------------------------------------------
# Test: resolver raises exception → logs warning, falls back
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolver_exception_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sim_module.settings, "movement_plan_runtime_enabled", True)
    monkeypatch.setattr(sim_module.settings, "movement_plan_fallback_enabled", True)

    build_called: list[bool] = []

    def _fake_resolve(**kwargs: Any) -> None:
        raise RuntimeError("boom")

    def _fake_build(*args: Any, **kwargs: Any) -> object:
        build_called.append(True)
        return _SENTINEL_TRAJECTORY

    reader = _DummyReader(movement_plans={1: _make_plan()})
    service = _build_service(reader)
    _patch_common(monkeypatch, service)
    monkeypatch.setattr(sim_module, "_resolve_from_plan", _fake_resolve)
    monkeypatch.setattr(sim_module, "build_trajectory", _fake_build)

    # Should not raise; exception is caught and logged
    trajectories, _ = await service.get_all_active_train_data()

    assert build_called == [True]
    assert len(trajectories) == 1
