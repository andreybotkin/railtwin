from datetime import time

import pytest

from app.models.database.models import Schedule
from app.services.schedule_utils import candidate_current_minutes
from app.services.trajectory_service import build_stop_sequence
from app.services.tts_scraper import _parse_tts_data, store_delays_in_redis


def test_candidate_current_minutes_accepts_negative_delay_before_schedule_start() -> None:
    schedules = [
        Schedule(
            train_id=1,
            station_name="Bangkok",
            departure_time=time(10, 0),
            departure_day_offset=0,
            arrival_day_offset=0,
            sequence=0,
            day_of_week=None,
        ),
        Schedule(
            train_id=1,
            station_name="Ayutthaya",
            arrival_time=time(12, 0),
            departure_day_offset=0,
            arrival_day_offset=0,
            sequence=1,
            day_of_week=None,
        ),
    ]

    current_minutes = candidate_current_minutes(
        schedules,
        9 * 60 + 55,
        delay=-10,
    )

    assert current_minutes == 9 * 60 + 55


def test_build_stop_sequence_marks_station_as_boarding_during_dwell_with_delay() -> None:
    schedules = [
        Schedule(
            train_id=7,
            station_name="Bangkok",
            departure_time=time(10, 0),
            departure_day_offset=0,
            arrival_day_offset=0,
            sequence=0,
            day_of_week=None,
        ),
        Schedule(
            train_id=7,
            station_name="Ayutthaya",
            arrival_time=time(11, 0),
            departure_time=time(11, 5),
            departure_day_offset=0,
            arrival_day_offset=0,
            sequence=1,
            day_of_week=None,
        ),
    ]

    sequence = build_stop_sequence(
        schedules,
        delay=2,
        current_minutes=11 * 60 + 4,
    )

    states = {item["station_name"]: item["state"] for item in sequence}
    assert states["Bangkok"] == "PASSED"
    assert states["Ayutthaya"] == "BOARDING"


def test_parse_tts_data_keeps_negative_delay_values() -> None:
    data = [
        {"train_code": "135", "act_dep_late": -3},
        {"train_code": "136", "act_arr_late": 7},
        {"train_code": "137", "act_dep_late": 0},
    ]

    assert _parse_tts_data(data) == {"135": -3, "136": 7}


@pytest.mark.asyncio
async def test_store_delays_in_redis_writes_empty_payload_to_clear_stale_state() -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, int]] = []

        async def set(self, key: str, value: str, ex: int) -> None:
            self.calls.append((key, value, ex))

    fake_redis = FakeRedis()
    await store_delays_in_redis(fake_redis, {})

    assert fake_redis.calls
    assert fake_redis.calls[0][1] == "{}"