"""Read canonical train schedules from individual raw JSON files.

Raw file naming convention: ``{route_type}_train{number}.json``
    e.g. ``eastern_train280.json`` → route_type=eastern, train_number=280

Raw file format::

    {
      "name":      "Ordinary No. 280",
      "link":      "https://...",
      "notes":     "...",
      "timetable": [
        {"station": "Ban Klong Luk Border", "arrival": "-",    "departure": "06:58"},
        {"station": "Aranyaprathet",        "arrival": "07:04","departure": "07:05"},
        ...
      ]
    }

"""

import json
import re
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.schedule.entities import ScheduleStopData, TrainData

logger = get_logger(__name__)

_FILENAME_RE = re.compile(r"^([a-z]+(?:_[a-z]+)*)_train(\d+)\.json$", re.IGNORECASE)

_TRAIN_TYPE_KEYWORDS = [
    ("special express", "special_express"),
    ("express", "express"),
    ("rapid", "rapid"),
    ("sprinter", "sprinter"),
    ("diesel railcar", "ordinary"),
    ("diesel", "ordinary"),
    ("local", "local"),
    ("ordinary", "ordinary"),
]

_ROUTE_NAME_MAP = {
    "eastern": "eastern",
    "northern": "northern",
    "northeastern": "northeastern",
    "southern": "southern",
    "western": "western",
    "urban": "urban",
}


def _time_to_minutes(value: str | None) -> int | None:
    if value is None:
        return None
    hours_text, minutes_text = value.split(":", 1)
    return int(hours_text) * 60 + int(minutes_text)


def _parse_explicit_offset(entry: dict, prefix: str) -> int | None:
    for suffix in ("day_offset", "date_offset"):
        raw_value = entry.get(f"{prefix}_{suffix}")
        if raw_value in (None, "", "-"):
            continue
        return int(str(raw_value))
    return None


def _infer_day_offsets(
    timetable: list[dict],
) -> list[tuple[int, int]]:
    offsets: list[tuple[int, int]] = []
    current_offset = 0
    last_absolute_minutes: int | None = None

    for entry in timetable:
        arrival = _parse_time_value(entry.get("arrival"))
        departure = _parse_time_value(entry.get("departure"))
        arrival_minutes = _time_to_minutes(arrival)
        departure_minutes = _time_to_minutes(departure)
        explicit_arrival_offset = _parse_explicit_offset(entry, "arrival")
        explicit_departure_offset = _parse_explicit_offset(entry, "departure")

        arrival_offset = (
            explicit_arrival_offset
            if explicit_arrival_offset is not None
            else current_offset
        )
        if arrival_minutes is not None:
            if explicit_arrival_offset is None:
                while (
                    last_absolute_minutes is not None
                    and arrival_minutes + arrival_offset * 1440 < last_absolute_minutes
                    and (arrival_minutes + (arrival_offset + 1) * 1440 - last_absolute_minutes) <= 1080
                ):
                    arrival_offset += 1
            arrival_absolute = arrival_minutes + arrival_offset * 1440
        else:
            arrival_absolute = None

        departure_offset = (
            explicit_departure_offset
            if explicit_departure_offset is not None
            else arrival_offset
        )
        reference_absolute = (
            arrival_absolute if arrival_absolute is not None else last_absolute_minutes
        )
        if departure_minutes is not None:
            if explicit_departure_offset is None:
                while (
                    reference_absolute is not None
                    and departure_minutes + departure_offset * 1440 < reference_absolute
                    and (departure_minutes + (departure_offset + 1) * 1440 - reference_absolute) <= 1080
                ):
                    departure_offset += 1
            departure_absolute = departure_minutes + departure_offset * 1440
        else:
            departure_absolute = None

        current_offset = max(current_offset, arrival_offset, departure_offset)
        if departure_absolute is not None:
            last_absolute_minutes = departure_absolute
        elif arrival_absolute is not None:
            last_absolute_minutes = arrival_absolute

        offsets.append((arrival_offset, departure_offset))

    return offsets


def _infer_train_type(name: str) -> str:
    name_lower = name.lower()
    for keyword, train_type in _TRAIN_TYPE_KEYWORDS:
        if keyword in name_lower:
            return train_type
    m = re.search(r"\d+", name)
    if m:
        n = int(m.group())
        if n <= 20:
            return "special_express"
        if n <= 100:
            return "express"
        if n <= 200:
            return "rapid"
    return "ordinary"


def _infer_route_type(route_prefix: str) -> str:
    return _ROUTE_NAME_MAP.get(route_prefix.lower(), "other")


def _parse_time_value(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    if stripped.lower() in {
        "-",
        "",
        "n/a",
        "origin",
        "final stop",
        "terminus",
        "start",
        "end",
    }:
        return None
    return stripped


def _parse_raw_file(path: Path) -> TrainData | None:
    m = _FILENAME_RE.match(path.name)
    if not m:
        logger.warning("Skipping file with unexpected name format", path=str(path))
        return None

    route_prefix = m.group(1)
    train_number = m.group(2)
    route_type = _infer_route_type(route_prefix)

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Cannot read raw schedule file", path=str(path), error=str(exc))
        return None

    name = raw.get("name") or f"Train No. {train_number}"
    notes_text = raw.get("notes", "")
    source_url = raw.get("link", "")
    train_type = _infer_train_type(name)

    stops: list[ScheduleStopData] = []
    timetable = raw.get("timetable", [])
    day_offsets = _infer_day_offsets(timetable)
    for seq, entry in enumerate(timetable):
        station_name = (entry.get("station") or "").strip()
        if not station_name:
            continue

        arrival = _parse_time_value(entry.get("arrival"))
        departure = _parse_time_value(entry.get("departure"))
        arrival_day_offset, departure_day_offset = day_offsets[seq]

        if arrival is None and departure is None:
            continue

        stops.append(
            ScheduleStopData(
                station_name=station_name,
                sequence=seq,
                arrival_time=arrival,
                departure_time=departure,
                arrival_day_offset=arrival_day_offset,
                departure_day_offset=departure_day_offset,
                day_of_week=list(range(7)),
                platform=None,
                distance_from_origin_km=None,
            )
        )

    if not stops:
        logger.warning(
            "Train file produced no stops, skipping",
            train_number=train_number,
            path=str(path),
        )
        return None

    return TrainData(
        train_number=train_number,
        train_type=train_type,
        route_type=route_type,
        name=name,
        operator="State Railway of Thailand",
        source="raw_file",
        source_url=source_url or str(path),
        service_notes={"notes": notes_text} if notes_text else None,
        stops=stops,
    )


def read_all_raw_schedules(raw_dir: Path | None = None) -> list[TrainData]:
    """Read every ``*.json`` file in the raw schedule directory.

    Returns list of successfully parsed TrainData objects sorted by train number.
    """
    if raw_dir is None:
        raw_dir = settings.schedule_raw_dir

    if not raw_dir.exists():
        logger.warning("Raw schedule directory not found", path=str(raw_dir))
        return []

    files = sorted(raw_dir.glob("*.json"))
    if not files:
        logger.warning("No JSON files in raw schedule directory", path=str(raw_dir))
        return []

    logger.info("Scanning raw schedule files", directory=str(raw_dir), files=len(files))

    trains: list[TrainData] = []
    failed = 0

    for path in files:
        train = _parse_raw_file(path)
        if train is not None:
            trains.append(train)
        else:
            failed += 1

    logger.info(
        "Raw schedule scan complete",
        loaded=len(trains),
        failed=failed,
        total=len(files),
    )
    return trains
