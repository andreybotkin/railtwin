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


@pytest.mark.asyncio
async def test_simulation_uses_full_subroute_between_service_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A service interval that spans multiple physical segments must use the full subroute."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_get_current_time_minutes", lambda: 11 * 60)

    train = Train(id=5, train_number="305", train_type="rapid")
    service._tts_delays[train.train_number] = 0
    schedules = [
        Schedule(
            train_id=5,
            station_id=10,
            station_name="Alpha",
            departure_time=time(10, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=0,
            day_of_week=None,
            route_progress=0.0,
            route_station=RouteStation(route_id=1, station_id=10, sequence=0, distance_from_start=0.0),
        ),
        Schedule(
            train_id=5,
            station_id=30,
            station_name="Gamma",
            arrival_time=time(12, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=1,
            day_of_week=None,
            route_progress=1.0,
            route_station=RouteStation(route_id=1, station_id=30, sequence=2, edge_id=2, distance_from_start=20.0),
        ),
    ]

    position = await service.get_train_position(
        train,
        schedules,
        route_coords=[[0.0, 0.0], [20.0, 0.0]],
        route_distance_km=20.0,
        route_segments=[
            {
                "edge_id": 1,
                "from_station_id": 10,
                "to_station_id": 20,
                "length_km": 10.0,
                "start_km": 0.0,
                "end_km": 10.0,
                "coords": [[0.0, 0.0], [10.0, 0.0]],
            },
            {
                "edge_id": 2,
                "from_station_id": 20,
                "to_station_id": 30,
                "length_km": 10.0,
                "start_km": 10.0,
                "end_km": 20.0,
                "coords": [[10.0, 0.0], [20.0, 0.0]],
            },
        ],
    )

    assert position is not None
    assert position["location"]["coordinates"][0] == pytest.approx(10.0, abs=0.01)
    assert position["current_edge_id"] in {1, 2}


@pytest.mark.asyncio
async def test_trajectory_uses_full_subroute_between_service_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trajectory movement must cover the whole service interval, not only the last physical edge."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_get_current_time_minutes", lambda: 10 * 60)

    train = Train(id=6, train_number="306", train_type="rapid")
    service._tts_delays[train.train_number] = 0
    schedules = [
        Schedule(
            train_id=6,
            station_id=10,
            station_name="Alpha",
            departure_time=time(10, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=0,
            day_of_week=None,
            route_progress=0.0,
            route_station=RouteStation(route_id=1, station_id=10, sequence=0, distance_from_start=0.0),
        ),
        Schedule(
            train_id=6,
            station_id=30,
            station_name="Gamma",
            arrival_time=time(12, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=1,
            day_of_week=None,
            route_progress=1.0,
            route_station=RouteStation(route_id=1, station_id=30, sequence=2, edge_id=2, distance_from_start=20.0),
        ),
    ]

    trajectory = await service.get_train_trajectory(
        train,
        schedules,
        route_coords=[[0.0, 0.0], [20.0, 0.0]],
        route_distance_km=20.0,
        route_segments=[
            {
                "edge_id": 1,
                "from_station_id": 10,
                "to_station_id": 20,
                "length_km": 10.0,
                "start_km": 0.0,
                "end_km": 10.0,
                "coords": [[0.0, 0.0], [10.0, 0.0]],
            },
            {
                "edge_id": 2,
                "from_station_id": 20,
                "to_station_id": 30,
                "length_km": 10.0,
                "start_km": 10.0,
                "end_km": 20.0,
                "coords": [[10.0, 0.0], [20.0, 0.0]],
            },
        ],
    )

    assert trajectory is not None
    intervals = trajectory["properties"]["time_intervals"]
    assert intervals[0][1] == pytest.approx(0.0, abs=1e-6)
    assert 0.05 < intervals[-1][1] < 0.2


@pytest.mark.asyncio
async def test_reverse_direction_trajectory_uses_decreasing_route_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reverse-direction trains must move from the higher route progress to the lower one."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_get_current_time_minutes", lambda: 20 * 60)

    train = Train(id=7, train_number="6", train_type="special_express")
    service._tts_delays[train.train_number] = 0
    schedules = [
        Schedule(
            train_id=7,
            station_id=30,
            station_name="Chiang Mai",
            departure_time=time(19, 35),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=0,
            day_of_week=None,
            route_progress=1.0,
            route_station=RouteStation(route_id=1, station_id=30, sequence=2, edge_id=2, distance_from_start=20.0),
        ),
        Schedule(
            train_id=7,
            station_id=20,
            station_name="Lamphun",
            arrival_time=time(19, 59),
            departure_time=time(20, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=1,
            day_of_week=None,
            route_progress=0.5,
            route_station=RouteStation(route_id=1, station_id=20, sequence=1, edge_id=1, distance_from_start=10.0),
        ),
        Schedule(
            train_id=7,
            station_id=10,
            station_name="Bangkok",
            arrival_time=time(8, 10),
            arrival_day_offset=1,
            departure_day_offset=1,
            sequence=2,
            day_of_week=None,
            route_progress=0.0,
            route_station=RouteStation(route_id=1, station_id=10, sequence=0, edge_id=1, distance_from_start=0.0),
        ),
    ]

    trajectory = await service.get_train_trajectory(
        train,
        schedules,
        route_coords=[[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]],
        route_distance_km=20.0,
        route_segments=[
            {
                "edge_id": 1,
                "from_station_id": 10,
                "to_station_id": 20,
                "length_km": 10.0,
                "start_km": 0.0,
                "end_km": 10.0,
                "coords": [[0.0, 0.0], [10.0, 0.0]],
            },
            {
                "edge_id": 2,
                "from_station_id": 20,
                "to_station_id": 30,
                "length_km": 10.0,
                "start_km": 10.0,
                "end_km": 20.0,
                "coords": [[10.0, 0.0], [20.0, 0.0]],
            },
        ],
    )

    assert trajectory is not None
    first_point = trajectory["properties"]["coordinate_timestamps"][0][1]
    last_point = trajectory["properties"]["coordinate_timestamps"][-1][1]
    first_interval = trajectory["properties"]["time_intervals"][0][1]
    assert first_interval == pytest.approx(1.0, abs=1e-6)
    assert first_point[0] > last_point[0]


@pytest.mark.asyncio
async def test_reverse_direction_position_moves_towards_lower_route_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Current position for reverse-direction trains must be sampled from the reversed subroute."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_get_current_time_minutes", lambda: 19 * 60 + 47)

    train = Train(id=8, train_number="6", train_type="special_express")
    service._tts_delays[train.train_number] = 0
    schedules = [
        Schedule(
            train_id=8,
            station_id=30,
            station_name="Chiang Mai",
            departure_time=time(19, 35),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=0,
            day_of_week=None,
            route_progress=1.0,
            route_station=RouteStation(route_id=1, station_id=30, sequence=2, edge_id=2, distance_from_start=20.0),
        ),
        Schedule(
            train_id=8,
            station_id=20,
            station_name="Lamphun",
            arrival_time=time(19, 59),
            departure_time=time(20, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=1,
            day_of_week=None,
            route_progress=0.5,
            route_station=RouteStation(route_id=1, station_id=20, sequence=1, edge_id=1, distance_from_start=10.0),
        ),
    ]

    position = await service.get_train_position(
        train,
        schedules,
        route_coords=[[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]],
        route_distance_km=20.0,
        route_segments=[
            {
                "edge_id": 1,
                "from_station_id": 10,
                "to_station_id": 20,
                "length_km": 10.0,
                "start_km": 0.0,
                "end_km": 10.0,
                "coords": [[0.0, 0.0], [10.0, 0.0]],
            },
            {
                "edge_id": 2,
                "from_station_id": 20,
                "to_station_id": 30,
                "length_km": 10.0,
                "start_km": 10.0,
                "end_km": 20.0,
                "coords": [[10.0, 0.0], [20.0, 0.0]],
            },
        ],
    )

    assert position is not None
    assert position["location"]["coordinates"][0] == pytest.approx(15.0, abs=0.1)
    assert 180.0 <= position["heading"] <= 360.0
