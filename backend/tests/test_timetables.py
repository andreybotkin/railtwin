"""Tests for external timetable support and simulation behavior."""

from datetime import time

import pytest
from geoalchemy2.elements import WKTElement
from pydantic import ValidationError

from app.models.database.models import Schedule, Station, Train
from app.schemas.schedule import ScheduleCreate
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
