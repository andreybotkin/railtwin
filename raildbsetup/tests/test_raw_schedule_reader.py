from app.domain.schedule.entities import ScheduleStopData, TrainData
from app.infrastructure.parsers.raw_schedule_reader import _infer_day_offsets


def test_infer_day_offsets_for_overnight_service() -> None:
    timetable = [
        {"station": "Origin", "arrival": "-", "departure": "23:40"},
        {"station": "Middle", "arrival": "00:20", "departure": "00:25"},
        {"station": "Terminal", "arrival": "02:15", "departure": "-"},
    ]

    assert _infer_day_offsets(timetable) == [
        (0, 0),
        (1, 1),
        (1, 1),
    ]


def test_infer_day_offsets_prefers_explicit_date_offsets() -> None:
    timetable = [
        {"station": "Origin", "arrival": "-", "departure": "19:35"},
        {"station": "Den Chai", "arrival": "23:55", "departure": "23:56"},
        {
            "station": "Sila At",
            "arrival": "00:48",
            "departure": "00:49",
            "arrival_date_offset": 1,
        },
        {"station": "Terminal", "arrival": "02:21", "departure": "-"},
    ]

    assert _infer_day_offsets(timetable) == [
        (0, 0),
        (0, 0),
        (1, 1),
        (1, 1),
    ]


def test_train_validation_rejects_backwards_interstation_time() -> None:
    train = TrainData(
        train_number="416",
        train_type="local",
        route_type="northeastern",
        stops=[
            ScheduleStopData("Sala Din", 1, departure_time="09:17"),
            ScheduleStopData("Nong Bua Lai", 2, arrival_time="09:11"),
        ],
    )
    assert any("non-positive travel time" in issue for issue in train.validate())


def test_train_validation_accepts_explicit_overnight_offset() -> None:
    train = TrainData(
        train_number="1",
        train_type="express",
        route_type="northern",
        stops=[
            ScheduleStopData("Origin", 1, departure_time="23:50"),
            ScheduleStopData(
                "Terminal", 2, arrival_time="00:20", arrival_day_offset=1
            ),
        ],
    )
    assert train.validate() == []
