"""Tests for external timetable support and simulation behavior."""

from datetime import time

import pytest
from geoalchemy2.elements import WKTElement
from pydantic import ValidationError

from app.models.database.models import Schedule, Station, Train
from app.schemas.schedule import ScheduleCreate
from app.services import trajectory_service
from app.services.simulation import TrainSimulationService


def test_schedule_create_accepts_raw_station_name() -> None:
    """A stop can be created from external timetable data before station mapping exists."""
    schedule = ScheduleCreate(
        train_id=1,
        station_name="Bangkok (Krung Thep Aphiwat)",
        departure_time=time(7, 30),
    )

    assert schedule.station_id is None
    assert schedule.station_name == "Bangkok (Krung Thep Aphiwat)"


def test_schedule_create_requires_station_reference() -> None:
    """A schedule stop must include either canonical station_id or raw station_name."""
    with pytest.raises(ValidationError):
        ScheduleCreate(train_id=1)


@pytest.mark.asyncio
async def test_simulation_handles_overnight_day_offsets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Overnight services should remain visible on the map after midnight."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_get_current_time_minutes", lambda: 30)

    train = Train(id=1, train_number="13", train_type="special_express")
    service._tts_delays[train.train_number] = 0
    schedules = [
        Schedule(
            train_id=1,
            station_name="Bangkok",
            departure_time=time(23, 0),
            departure_day_offset=0,
            arrival_day_offset=0,
            sequence=0,
            day_of_week=None,
            route_progress=0.0,
        ),
        Schedule(
            train_id=1,
            station_name="Ayutthaya",
            arrival_time=time(1, 0),
            departure_time=time(1, 5),
            arrival_day_offset=1,
            departure_day_offset=1,
            sequence=1,
            day_of_week=None,
            route_progress=0.5,
        ),
        Schedule(
            train_id=1,
            station_name="Chiang Mai",
            arrival_time=time(3, 0),
            arrival_day_offset=1,
            departure_day_offset=1,
            sequence=2,
            day_of_week=None,
            route_progress=1.0,
        ),
    ]

    position = await service.get_train_position(
        train,
        schedules,
        route_coords=[[0.0, 0.0], [2.0, 0.0]],
        route_distance_km=200.0,
    )

    assert position is not None
    assert position["next_station"] == "Ayutthaya"
    assert 70.0 <= position["progress"] <= 80.0
    assert position["location"]["coordinates"][0] > 0.3


@pytest.mark.asyncio
async def test_simulation_prefers_route_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stored route progress should override equal-stop interpolation."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_get_current_time_minutes", lambda: 11 * 60)

    train = Train(id=2, train_number="109", train_type="rapid")
    service._tts_delays[train.train_number] = 0
    schedules = [
        Schedule(
            train_id=2,
            station_name="Bangkok",
            departure_time=time(10, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=0,
            day_of_week=None,
            route_progress=0.0,
        ),
        Schedule(
            train_id=2,
            station_name="Nakhon Sawan",
            arrival_time=time(12, 0),
            departure_time=time(12, 10),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=1,
            day_of_week=None,
            route_progress=0.9,
        ),
        Schedule(
            train_id=2,
            station_name="Chiang Mai",
            arrival_time=time(13, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=2,
            day_of_week=None,
            route_progress=1.0,
        ),
    ]

    position = await service.get_train_position(
        train,
        schedules,
        route_coords=[[0.0, 0.0], [10.0, 0.0]],
        route_distance_km=1000.0,
    )

    assert position is not None
    assert position["next_station"] == "Nakhon Sawan"
    assert 4.0 <= position["location"]["coordinates"][0] <= 5.0


@pytest.mark.asyncio
async def test_simulation_falls_back_to_station_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Station coordinates should be enough when route geometry is unavailable."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_get_current_time_minutes", lambda: 11 * 60)

    train = Train(id=3, train_number="171", train_type="rapid")
    service._tts_delays[train.train_number] = 0
    origin = Station(
        id=1,
        name="Bangkok",
        code="BKK",
        location=WKTElement("POINT(0 0)", srid=4326),
    )
    destination = Station(
        id=2,
        name="Ayutthaya",
        code="AYU",
        location=WKTElement("POINT(10 0)", srid=4326),
    )
    schedules = [
        Schedule(
            train_id=3,
            station_id=1,
            station_name="Bangkok",
            station=origin,
            departure_time=time(10, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=0,
            day_of_week=None,
        ),
        Schedule(
            train_id=3,
            station_id=2,
            station_name="Ayutthaya",
            station=destination,
            arrival_time=time(12, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=1,
            day_of_week=None,
        ),
    ]

    position = await service.get_train_position(
        train,
        schedules,
        route_coords=None,
        route_distance_km=None,
    )

    assert position is not None
    assert position["next_station"] == "Ayutthaya"
    assert 4.5 <= position["location"]["coordinates"][0] <= 5.5


@pytest.mark.asyncio
async def test_get_all_active_trains_reads_all_batches() -> None:
    """Cache refresh should iterate through all trains, not only the first page."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    calls: list[tuple[int, int]] = []

    async def fake_get_all_with_route(skip: int = 0, limit: int = 100) -> list[Train]:
        calls.append((skip, limit))
        if skip == 0:
            return [
                Train(
                    id=index,
                    train_number=str(index),
                    train_type="ordinary",
                    current_route_id=1,
                )
                for index in range(1, 101)
            ]
        if skip == 100:
            return [
                Train(
                    id=101,
                    train_number="101",
                    train_type="ordinary",
                    current_route_id=1,
                )
            ]
        return []

    async def fake_get_by_train(_train_id: int) -> list[Schedule]:
        return [
            Schedule(
                train_id=1,
                station_name="Bangkok",
                sequence=0,
                day_of_week=None,
            )
        ]

    async def fake_get_by_id_with_geometry(_route_id: int) -> None:
        return None

    async def fake_get_train_position(
        train: Train,
        schedules: list[Schedule],
        route_coords: list[list[float]] | None,
        route_distance_km: float | None = None,
    ) -> dict[str, int]:
        return {"train_id": train.id}

    service.train_repo.get_all_with_route = fake_get_all_with_route  # type: ignore[method-assign]
    service.schedule_repo.get_by_train = fake_get_by_train  # type: ignore[method-assign]
    service.route_repo.get_by_id_with_geometry = fake_get_by_id_with_geometry  # type: ignore[method-assign]
    service.get_train_position = fake_get_train_position  # type: ignore[method-assign]

    positions = await service.get_all_active_trains()

    assert len(positions) == 101
    assert calls == [(0, 100), (100, 100)]


# ---------------------------------------------------------------------------
# Great Circle bearing tests
# ---------------------------------------------------------------------------


def test_heading_north() -> None:
    """A point directly north should give ~0°."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    heading = service._calculate_heading((100.0, 13.0), (100.0, 14.0))
    assert abs(heading - 0.0) < 1.0, f"Expected ~0 (North), got {heading}"


def test_heading_east() -> None:
    """A point directly east should give ~90°."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    heading = service._calculate_heading((100.0, 13.0), (101.0, 13.0))
    assert abs(heading - 90.0) < 2.0, f"Expected ~90 (East), got {heading}"


def test_heading_south() -> None:
    """A point directly south should give ~180°."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    heading = service._calculate_heading((100.0, 14.0), (100.0, 13.0))
    assert abs(heading - 180.0) < 1.0, f"Expected ~180 (South), got {heading}"


def test_heading_west() -> None:
    """A point directly west should give ~270°."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    heading = service._calculate_heading((101.0, 13.0), (100.0, 13.0))
    assert abs(heading - 270.0) < 2.0, f"Expected ~270 (West), got {heading}"


def test_heading_same_point_returns_zero() -> None:
    """Same point should return 0°, not raise."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    assert service._calculate_heading((100.0, 13.0), (100.0, 13.0)) == 0.0


# ---------------------------------------------------------------------------
# geops TrackerTrajectory field tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trajectory_is_geojson_feature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_train_trajectory() must return a GeoJSON Feature with type='Feature'."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_get_current_time_minutes", lambda: 11 * 60)

    train = Train(id=1, train_number="1", train_type="special_express")
    service._tts_delays[train.train_number] = 0
    schedules = [
        Schedule(
            train_id=1,
            station_name="Bangkok",
            departure_time=time(10, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=0,
            day_of_week=None,
            route_progress=0.0,
        ),
        Schedule(
            train_id=1,
            station_name="Chiang Mai",
            arrival_time=time(14, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=1,
            day_of_week=None,
            route_progress=1.0,
        ),
    ]

    traj = await service.get_train_trajectory(
        train,
        schedules,
        route_coords=[[0.0, 0.0], [10.0, 0.0]],
        route_distance_km=1000.0,
    )

    assert traj is not None
    assert traj["type"] == "Feature"
    props = traj["properties"]
    assert "delay" in props                          # seconds
    assert "delay_minutes" in props                  # minutes (legacy)
    assert props["delay"] == props["delay_minutes"] * 60
    assert props["route_id"] == train.current_route_id
    assert props["status"] in ("moving", "at_station")
    assert props["progress"] is not None
    assert props["route_progress"] is not None
    assert "state" in props
    assert props["state"] in ("BOARDING", "DRIVING", "JOURNEY_CANCELLED")
    assert props["type"] == "rail"
    assert "tenant" in props
    assert "timestamp" in props
    assert props["has_journey"] is True
    assert props["has_realtime"] is True
    assert props["has_realtime_journey"] is True
    assert isinstance(props["gen_range"], list)
    assert "graph" in props
    assert "operator_provides_realtime_journey" in props
    assert "route_identifier" in props
    assert "line" in props
    line = props["line"]
    assert "id" in line
    assert "tags" in line


# ---------------------------------------------------------------------------
# Stop-sequence tests
# ---------------------------------------------------------------------------


def test_get_stop_sequence_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_stop_sequence() should correctly label PASSED, BOARDING and PENDING stops."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    train = Train(id=1, train_number="1", train_type="ordinary")
    schedules = [
        Schedule(
            train_id=1,
            station_name="Bangkok",
            departure_time=time(10, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=0,
            day_of_week=None,
        ),
        Schedule(
            train_id=1,
            station_name="Ayutthaya",
            arrival_time=time(11, 0),
            departure_time=time(11, 5),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=1,
            day_of_week=None,
        ),
        Schedule(
            train_id=1,
            station_name="Chiang Mai",
            arrival_time=time(15, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=2,
            day_of_week=None,
        ),
    ]

    # Current time = 11:04 — Ayutthaya is BOARDING, Bangkok PASSED, Chiang Mai PENDING
    seq = service.get_stop_sequence(train, schedules, delay=0, current_minutes=11 * 60 + 4)

    assert len(seq) == 3
    states = {s["station_name"]: s["state"] for s in seq}
    assert states["Bangkok"] == "PASSED"
    assert states["Ayutthaya"] == "BOARDING"
    assert states["Chiang Mai"] == "PENDING"


@pytest.mark.asyncio
async def test_get_all_active_train_data_returns_three_lists() -> None:
    """get_all_active_train_data() should return (positions, trajectories, stop_sequences)."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]

    async def fake_get_all_with_route(skip: int = 0, limit: int = 100) -> list[Train]:
        if skip == 0:
            return [Train(id=1, train_number="1", train_type="ordinary", current_route_id=None)]
        return []

    async def fake_get_by_trains(train_ids: list[int]) -> dict[int, list[Schedule]]:
        return {}

    service.train_repo.get_all_with_route = fake_get_all_with_route  # type: ignore[method-assign]
    service.schedule_repo.get_by_trains = fake_get_by_trains  # type: ignore[method-assign]

    positions, trajectories, stop_sequences = await service.get_all_active_train_data()

    assert isinstance(positions, list)
    assert isinstance(trajectories, list)
    assert isinstance(stop_sequences, dict)


@pytest.mark.asyncio
async def test_get_all_active_train_data_can_skip_trajectory_generation() -> None:
    """Position-only cache refreshes should skip heavy trajectory generation."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]

    async def fake_get_all_with_route(skip: int = 0, limit: int = 100) -> list[Train]:
        if skip == 0:
            return [Train(id=1, train_number="1", train_type="ordinary", current_route_id=1)]
        return []

    async def fake_get_by_trains(train_ids: list[int]) -> dict[int, list[Schedule]]:
        return {
            1: [
                Schedule(
                    train_id=1,
                    station_name="Bangkok",
                    departure_time=time(10, 0),
                    arrival_day_offset=0,
                    departure_day_offset=0,
                    sequence=0,
                    day_of_week=None,
                    route_progress=0.0,
                ),
                Schedule(
                    train_id=1,
                    station_name="Ayutthaya",
                    arrival_time=time(11, 0),
                    arrival_day_offset=0,
                    departure_day_offset=0,
                    sequence=1,
                    day_of_week=None,
                    route_progress=1.0,
                ),
            ]
        }

    service.train_repo.get_all_with_route = fake_get_all_with_route  # type: ignore[method-assign]
    service.schedule_repo.get_by_trains = fake_get_by_trains  # type: ignore[method-assign]
    async def fake_get_graph_geometry_bulk(
        route_ids: list[int],
    ) -> dict[int, dict[str, object]]:
        return {
            route_id: {
                "coords": [[0.0, 0.0], [1.0, 1.0]],
                "distance_km": 10.0,
                "segments": [],
            }
            for route_id in route_ids
        }

    service.route_repo.get_graph_geometry_bulk = fake_get_graph_geometry_bulk  # type: ignore[method-assign]
    service._get_candidate_current_minutes_with_delay = (  # type: ignore[method-assign]
        lambda schedules, delay=0: 10 * 60 + 30
    )

    positions, trajectories, stop_sequences = await service.get_all_active_train_data(
        include_trajectories=False,
        include_stop_sequences=False,
    )

    assert len(positions) == 1
    assert trajectories == []
    assert stop_sequences == {}


@pytest.mark.asyncio
async def test_trajectory_contains_station_dwell_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trajectory should contain exact arrival/departure markers for station dwell."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_get_current_time_minutes", lambda: 10 * 60 + 58)
    monkeypatch.setattr(trajectory_service._time, "time", lambda: 1000.0)
    monkeypatch.setattr(
        trajectory_service.settings,
        "trajectory_lookahead_seconds",
        600,
    )
    monkeypatch.setattr(
        trajectory_service.settings,
        "trajectory_step_seconds",
        60,
    )

    train = Train(id=7, train_number="7", train_type="rapid")
    service._tts_delays[train.train_number] = 0
    schedules = [
        Schedule(
            train_id=7,
            station_name="Bangkok",
            departure_time=time(10, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=0,
            day_of_week=None,
            route_progress=0.0,
        ),
        Schedule(
            train_id=7,
            station_name="Ayutthaya",
            arrival_time=time(11, 0),
            departure_time=time(11, 5),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=1,
            day_of_week=None,
            route_progress=0.5,
        ),
        Schedule(
            train_id=7,
            station_name="Chiang Mai",
            arrival_time=time(12, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=2,
            day_of_week=None,
            route_progress=1.0,
        ),
    ]

    trajectory = await service.get_train_trajectory(
        train,
        schedules,
        route_coords=[[0.0, 0.0], [10.0, 0.0]],
        route_distance_km=1000.0,
    )

    assert trajectory is not None
    props = trajectory["properties"]
    events = {
        (event["station_name"], event["event_type"]): event
        for event in props["schedule_events"]
    }
    assert events[("Ayutthaya", "arrival")]["timestamp"] == 1_120_000
    assert events[("Ayutthaya", "departure")]["timestamp"] == 1_420_000
    assert events[("Ayutthaya", "arrival")]["coordinates"] == [5.0, 0.0]

    time_intervals = {
        interval[0]: interval[1]
        for interval in props["time_intervals"]
    }
    assert time_intervals[1_120_000] == 0.5
    assert time_intervals[1_420_000] == 0.5
    coordinate_timestamps = {
        item[0]: item[1]
        for item in props["coordinate_timestamps"]
    }
    assert coordinate_timestamps[1_120_000] == [5.0, 0.0]
    assert coordinate_timestamps[1_420_000] == [5.0, 0.0]


@pytest.mark.asyncio
async def test_trajectory_schedule_events_shift_with_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Arrival and departure markers should shift by the current train delay."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_get_current_time_minutes", lambda: 11 * 60 + 4)
    monkeypatch.setattr(trajectory_service._time, "time", lambda: 1000.0)
    monkeypatch.setattr(
        trajectory_service.settings,
        "trajectory_lookahead_seconds",
        600,
    )
    monkeypatch.setattr(
        trajectory_service.settings,
        "trajectory_step_seconds",
        60,
    )

    train = Train(id=8, train_number="8", train_type="ordinary")
    service._tts_delays[train.train_number] = 7
    schedules = [
        Schedule(
            train_id=8,
            station_name="Bangkok",
            departure_time=time(10, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=0,
            day_of_week=None,
            route_progress=0.0,
        ),
        Schedule(
            train_id=8,
            station_name="Ayutthaya",
            arrival_time=time(11, 0),
            departure_time=time(11, 5),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=1,
            day_of_week=None,
            route_progress=0.5,
        ),
        Schedule(
            train_id=8,
            station_name="Chiang Mai",
            arrival_time=time(12, 0),
            arrival_day_offset=0,
            departure_day_offset=0,
            sequence=2,
            day_of_week=None,
            route_progress=1.0,
        ),
    ]

    trajectory = await service.get_train_trajectory(
        train,
        schedules,
        route_coords=[[0.0, 0.0], [10.0, 0.0]],
        route_distance_km=1000.0,
    )

    assert trajectory is not None
    events = trajectory["properties"]["schedule_events"]
    ayutthaya_events = {
        event["event_type"]: event for event in events if event["station_name"] == "Ayutthaya"
    }
    assert ayutthaya_events["arrival"]["timestamp"] == 1_180_000
    assert ayutthaya_events["departure"]["timestamp"] == 1_480_000
    assert ayutthaya_events["arrival"]["adjusted_minutes"] == 11 * 60 + 7
    assert ayutthaya_events["departure"]["adjusted_minutes"] == 11 * 60 + 12
