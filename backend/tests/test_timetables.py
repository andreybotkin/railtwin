"""Tests for external timetable support and simulation behavior."""

from datetime import time

import pytest
from pydantic import ValidationError

from app.models.database.models import Schedule, Train
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
async def test_simulation_handles_overnight_day_offsets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Overnight services should remain visible on the map after midnight."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_get_current_time_minutes", lambda: 30)

    train = Train(id=1, train_number="13", train_type="special_express")
    service._delays[train.id] = 0
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
async def test_simulation_prefers_route_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stored route progress should override equal-stop interpolation."""
    service = TrainSimulationService(session=None)  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_get_current_time_minutes", lambda: 11 * 60)

    train = Train(id=2, train_number="109", train_type="rapid")
    service._delays[train.id] = 0
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
