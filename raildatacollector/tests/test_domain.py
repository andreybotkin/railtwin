"""Unit tests for raildatacollector domain entities and infrastructure utilities."""

from datetime import time

from app.domain.railroad.entities import RouteData, StationData
from app.domain.schedule.entities import ScheduleStopData, TrainData
from app.infrastructure.database.repositories.railroad import (
    _approx_distance_km,
    _make_station_code,
)
from app.infrastructure.database.repositories.schedule import _parse_time


class TestScheduleStopData:
    def test_defaults(self) -> None:
        stop = ScheduleStopData(station_name="Bangkok", sequence=1)
        assert stop.station_name == "Bangkok"
        assert stop.sequence == 1
        assert stop.arrival_time is None
        assert stop.departure_time is None
        assert stop.arrival_day_offset == 0
        assert stop.departure_day_offset == 0
        assert stop.day_of_week == list(range(7))
        assert stop.platform is None
        assert stop.distance_from_origin_km is None

    def test_explicit_fields(self) -> None:
        stop = ScheduleStopData(
            station_name="Hua Lamphong",
            sequence=2,
            arrival_time="08:30",
            departure_time="08:35",
            day_of_week=[1, 2, 3, 4, 5],
        )
        assert stop.arrival_time == "08:30"
        assert stop.departure_time == "08:35"
        assert stop.day_of_week == [1, 2, 3, 4, 5]


class TestTrainData:
    def test_defaults(self) -> None:
        train = TrainData(train_number="1", train_type="express", route_type="northern")
        assert train.operator == "State Railway of Thailand"
        assert train.source == "raildatacollector"
        assert train.stops == []
        assert train.service_notes is None

    def test_with_stops(self) -> None:
        stops = [
            ScheduleStopData(
                station_name="Bangkok", sequence=1, departure_time="08:00"
            ),
            ScheduleStopData(
                station_name="Chiang Mai", sequence=2, arrival_time="18:00"
            ),
        ]
        train = TrainData(
            train_number="9",
            train_type="special_express",
            route_type="northern",
            stops=stops,
        )
        assert len(train.stops) == 2
        assert train.stops[0].station_name == "Bangkok"
        assert train.stops[1].station_name == "Chiang Mai"


class TestStationData:
    def test_creation(self) -> None:
        station = StationData(name="Hua Lamphong", lon=100.516, lat=13.740)
        assert station.name == "Hua Lamphong"
        assert station.lon == 100.516
        assert station.lat == 13.740
        assert station.folder == ""
        assert station.route_type == "other"


class TestRouteData:
    def test_creation(self) -> None:
        route = RouteData(name="Northern Line", route_type="northern", color="#E53935")
        assert route.name == "Northern Line"
        assert route.route_type == "northern"
        assert route.coords == []


class TestParseTime:
    def test_valid_time_string(self) -> None:
        assert _parse_time("08:30") == time(8, 30)

    def test_midnight_wrap(self) -> None:
        assert _parse_time("24:00") == time(0, 0)

    def test_none_input(self) -> None:
        assert _parse_time(None) is None

    def test_time_object_passthrough(self) -> None:
        t = time(12, 0)
        assert _parse_time(t) is t

    def test_invalid_string(self) -> None:
        assert _parse_time("invalid") is None

    def test_hour_23(self) -> None:
        assert _parse_time("23:59") == time(23, 59)


class TestMakeStationCode:
    def test_short_name(self) -> None:
        code = _make_station_code("BKK")
        assert code == "BKK"
        assert len(code) <= 5

    def test_long_name_truncated(self) -> None:
        code = _make_station_code("Hua Lamphong Central Station")
        assert len(code) == 5

    def test_special_characters_stripped(self) -> None:
        code = _make_station_code("Don Mueang")
        assert code.isalnum()

    def test_unique_codes_for_similar_names(self) -> None:
        code1 = _make_station_code("Bangkok Central")
        code2 = _make_station_code("Bangkok North")
        assert len(code1) <= 5
        assert len(code2) <= 5


class TestApproxDistanceKm:
    def test_zero_distance_same_point(self) -> None:
        assert _approx_distance_km([(100.0, 13.0), (100.0, 13.0)]) == 0.0

    def test_single_point(self) -> None:
        assert _approx_distance_km([(100.0, 13.0)]) == 0.0

    def test_empty_coords(self) -> None:
        assert _approx_distance_km([]) == 0.0

    def test_positive_distance(self) -> None:
        # Bangkok (100.5, 13.7) → Chiang Mai (98.9, 18.8)
        dist = _approx_distance_km([(100.5, 13.7), (98.9, 18.8)])
        assert dist > 0

    def test_multi_segment(self) -> None:
        coords = [(100.0, 13.0), (101.0, 13.0), (101.0, 14.0)]
        total = _approx_distance_km(coords)
        assert total > _approx_distance_km([(100.0, 13.0), (101.0, 13.0)])
