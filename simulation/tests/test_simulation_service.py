"""Tests for cooperative yielding in bulk simulation processing."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import app.services.simulation as module
from app.services.simulation import TrainSimulationService


class _DummyReader:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self._payloads = payloads

    async def get_all_trains_for_simulation(
        self,
        *,
        skip: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        return self._payloads[skip : skip + limit]

    async def get_schedules_by_trains(
        self,
        train_ids: list[int],
    ) -> dict[int, list[dict[str, int]]]:
        return {train_id: [{"train_id": train_id}] for train_id in train_ids}


@pytest.mark.asyncio
async def test_get_all_active_train_data_yields_control_during_bulk_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload_count = module._COOPERATIVE_YIELD_EVERY + 5
    payloads = [
        {"id": train_id, "train_number": str(train_id), "current_route_id": None}
        for train_id in range(1, payload_count + 1)
    ]

    service = TrainSimulationService(session=SimpleNamespace(), redis_client=None)
    service.reader = _DummyReader(payloads)

    async def _fake_load_delays() -> None:
        service._tts_delays = {}

    sleep_calls: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(service, "_load_delays", _fake_load_delays)
    monkeypatch.setattr(
        service,
        "_get_candidate_current_minutes_with_delay",
        lambda schedules, delay: 123.0,
    )
    monkeypatch.setattr(
        module,
        "train_payload_to_domain",
        lambda payload: SimpleNamespace(
            id=int(payload["id"]),
            train_number=str(payload["train_number"]),
            current_route_id=payload.get("current_route_id"),
        ),
    )
    monkeypatch.setattr(module, "schedule_payloads_to_domain", lambda payloads: payloads)
    monkeypatch.setattr(module, "build_trajectory", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(module, "build_stop_sequence", lambda *args, **kwargs: [{"ok": True}])
    monkeypatch.setattr(module.asyncio, "sleep", _fake_sleep)

    trajectories, stop_sequences = await service.get_all_active_train_data()

    assert len(trajectories) == payload_count
    assert len(stop_sequences) == payload_count
    assert sleep_calls == [0]
    