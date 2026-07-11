import asyncio
from typing import Any

from app.websocket_streams import _send_trajectory_delta, _send_trajectory_snapshot


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.messages.append(payload)


def test_snapshot_is_sent_as_one_message() -> None:
    websocket = FakeWebSocket()
    trajectories = [
        {"train_id": 1, "generated_at_ms": 100},
        {"train_id": 2, "generated_at_ms": 200},
    ]

    versions = asyncio.run(_send_trajectory_snapshot(websocket, trajectories, 500))

    assert versions == {1: 100, 2: 200}
    assert websocket.messages == [
        {"source": "snapshot", "content": trajectories, "timestamp": 500}
    ]


def test_delta_only_sends_changed_and_deleted_trains() -> None:
    websocket = FakeWebSocket()
    trajectories = [
        {"train_id": 1, "generated_at_ms": 100},
        {"train_id": 2, "generated_at_ms": 201},
    ]

    versions = asyncio.run(
        _send_trajectory_delta(
            websocket,
            trajectories,
            {1: 100, 2: 200, 3: 300},
            600,
        )
    )

    assert versions == {1: 100, 2: 201}
    assert websocket.messages == [
        {"source": "trajectory", "content": trajectories[1], "timestamp": 600},
        {"source": "deleted_vehicles", "content": 3, "timestamp": 600},
    ]
