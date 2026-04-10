from dataclasses import dataclass, field


@dataclass
class ScheduleStopData:
    """A single stop entry in a train's timetable."""

    station_name: str
    sequence: int
    arrival_time: str | None = None  # "HH:MM" or None for first stop
    departure_time: str | None = None  # "HH:MM" or None for last stop
    arrival_day_offset: int = 0
    departure_day_offset: int = 0
    day_of_week: list[int] = field(default_factory=lambda: list(range(7)))
    platform: str | None = None
    distance_from_origin_km: float | None = None


@dataclass
class TrainData:
    """Domain entity representing a train with its full timetable."""

    train_number: str
    train_type: str
    route_type: str
    name: str | None = None
    operator: str = "State Railway of Thailand"
    source: str = "raildatacollector"
    source_url: str | None = None
    service_notes: dict | None = None
    stops: list[ScheduleStopData] = field(default_factory=list)
