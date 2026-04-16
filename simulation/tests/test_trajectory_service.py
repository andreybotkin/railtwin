from datetime import time
from types import SimpleNamespace

from app.services.trajectory_service import attach_consist, build_train_trajectory


class FakeSchedule(SimpleNamespace):
    pass


def _schedule(sequence: int, arr: time, dep: time, frac: float):
    station = SimpleNamespace(name=f"S{sequence}")
    return FakeSchedule(
        station=station,
        station_name=station.name,
        sequence=sequence,
        arrival_time=arr,
        departure_time=dep,
        arrival_day_offset=0,
        departure_day_offset=0,
        distance_from_origin_km=frac * 100,
        route_progress=frac,
    )


def _train():
    return SimpleNamespace(id=7, train_number="7", train_type="ordinary", current_route_id=1)


def test_build_trajectory_has_moving_frames() -> None:
    schedules = [_schedule(1, time(10, 0), time(10, 0), 0.0), _schedule(2, time(11, 0), time(11, 5), 1.0)]
    traj = build_train_trajectory(_train(), schedules, [[100, 13], [101, 14]], 120, delay=0, current_minutes=10 * 60 + 30)
    assert traj is not None
    assert traj["frames"][0]["status"] in {"moving", "dwelling"}


def test_dwell_frame_has_zero_speed_and_fixed_fraction() -> None:
    schedules = [_schedule(1, time(10, 0), time(10, 0), 0.0), _schedule(2, time(10, 30), time(10, 40), 1.0)]
    traj = build_train_trajectory(_train(), schedules, [[100, 13], [101, 14]], 120, delay=0, current_minutes=10 * 60 + 35)
    assert traj is not None
    frame = traj["frames"][0]
    assert frame["status"] == "dwelling"
    assert frame["speed_kmh"] == 0


def test_end_of_route_marks_arrived() -> None:
    schedules = [_schedule(1, time(10, 0), time(10, 0), 0.0), _schedule(2, time(10, 10), time(10, 10), 1.0)]
    traj = build_train_trajectory(_train(), schedules, [[100, 13], [101, 14]], 120, delay=0, current_minutes=10 * 60 + 9.9)
    assert traj is not None
    assert traj["frames"][-1]["status"] == "arrived"


def test_attach_consist_from_type() -> None:
    consist = attach_consist("special_express")
    assert consist.car_count == 12
    assert consist.total_length_m > 0
