"""Tests for graph-aware train simulation behavior."""

from datetime import time

import pytest

from app.models.database.models import RouteStation, Schedule, Train
from app.services.simulation import TrainSimulationService


@pytest.mark.asyncio
async def test_simulation_prefers_graph_edge_segment_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Current train position must follow the active station-to-station graph edge."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_get_current_time_minutes", lambda: 11 * 60)

    train = Train(id=4, train_number="207", train_type="rapid")
    service._tts_delays[train.train_number] = 0
    schedules = [
        Schedule(
            train_id=4,
            station_id=10,
            station_name="Alpha",
            departure_time=time(10, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=0,
            day_of_week=None,
            route_station=RouteStation(
                route_id=1,
                station_id=10,
                sequence=0,
                distance_from_start=2.0,
            ),
        ),
        Schedule(
            train_id=4,
            station_id=20,
            station_name="Beta",
            arrival_time=time(12, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=1,
            day_of_week=None,
            route_station=RouteStation(
                route_id=1,
                station_id=20,
                sequence=1,
                edge_id=99,
                distance_from_start=6.0,
            ),
        ),
    ]

    position = await service.get_train_position(
        train,
        schedules,
        route_coords=[[0.0, 0.0], [10.0, 0.0]],
        route_distance_km=10.0,
        route_segments=[
            {
                "edge_id": 99,
                "from_station_id": 10,
                "to_station_id": 20,
                "length_km": 4.0,
                "start_km": 2.0,
                "end_km": 6.0,
                "coords": [[3.0, 1.0], [3.0, 9.0]],
            }
        ],
    )

    assert position is not None
    assert position["current_edge_id"] == 99
    assert position["graph_from_station_id"] == 10
    assert position["graph_to_station_id"] == 20
    assert position["location"]["coordinates"][0] == pytest.approx(3.0, abs=0.01)
    assert position["location"]["coordinates"][1] == pytest.approx(5.0, abs=0.01)