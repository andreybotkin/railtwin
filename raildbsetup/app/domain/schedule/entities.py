import re
from dataclasses import dataclass, field

_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


def _absolute_minutes(value: str, day_offset: int) -> int:
    hours, minutes = (int(part) for part in value.split(":", 1))
    return hours * 60 + minutes + day_offset * 1440

VALID_ROUTE_TYPES = frozenset(
    {
        "northern",
        "northeastern",
        "western",
        "southern",
        "eastern",
        "urban",
        "other",
    }
)

VALID_TRAIN_TYPES = frozenset(
    {
        "special_express",
        "express",
        "rapid",
        "sprinter",
        "ordinary",
        "local",
    }
)


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

    def validate(self, train_number: str) -> list[str]:
        errors: list[str] = []
        if not self.station_name or not self.station_name.strip():
            errors.append(
                f"Train {train_number} seq {self.sequence}: empty station name"
            )
        if self.arrival_time is None and self.departure_time is None:
            errors.append(
                f"Train {train_number} seq {self.sequence} "
                f"'{self.station_name}': both arrival and departure are missing"
            )
        for label, t in [
            ("arrival", self.arrival_time),
            ("departure", self.departure_time),
        ]:
            if t is not None and not _TIME_RE.match(t):
                errors.append(
                    f"Train {train_number} seq {self.sequence} "
                    f"'{self.station_name}': invalid {label} time '{t}' (expected HH:MM)"
                )
        return errors


@dataclass
class TrainData:
    """Domain entity: a train with its full timetable."""

    train_number: str
    train_type: str
    route_type: str
    name: str | None = None
    operator: str = "State Railway of Thailand"
    source: str = "raildbsetup"
    source_url: str | None = None
    service_notes: dict | None = None
    stops: list[ScheduleStopData] = field(default_factory=list)

    def validate(self) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors: list[str] = []
        if not self.train_number or not self.train_number.strip():
            errors.append("Train number is empty")
        if not self.stops:
            errors.append(f"Train {self.train_number}: has no stops")
        elif len(self.stops) < 2:
            errors.append(
                f"Train {self.train_number}: only {len(self.stops)} stop(s), need >= 2"
            )
        if self.route_type not in VALID_ROUTE_TYPES:
            errors.append(
                f"Train {self.train_number}: unknown route_type '{self.route_type}'"
            )
        if self.train_type not in VALID_TRAIN_TYPES:
            errors.append(
                f"Train {self.train_number}: unknown train_type '{self.train_type}'"
            )
        # Check sequence uniqueness
        seqs = [s.sequence for s in self.stops]
        if len(seqs) != len(set(seqs)):
            errors.append(
                f"Train {self.train_number}: duplicate sequence numbers in stops"
            )
        # Validate each stop
        for stop in self.stops:
            errors.extend(stop.validate(self.train_number))
        for left, right in zip(self.stops, self.stops[1:], strict=False):
            left_time = left.departure_time or left.arrival_time
            right_time = right.arrival_time or right.departure_time
            if left_time is None or right_time is None:
                continue
            left_offset = (
                left.departure_day_offset
                if left.departure_time is not None
                else left.arrival_day_offset
            )
            right_offset = (
                right.arrival_day_offset
                if right.arrival_time is not None
                else right.departure_day_offset
            )
            if _absolute_minutes(right_time, right_offset) <= _absolute_minutes(
                left_time, left_offset
            ):
                errors.append(
                    f"Train {self.train_number}: non-positive travel time "
                    f"'{left.station_name}' -> '{right.station_name}'"
                )
        return errors
