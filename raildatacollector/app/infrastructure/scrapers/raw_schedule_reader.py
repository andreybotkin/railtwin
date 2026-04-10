"""Read real train schedules from individual raw JSON files.

Each file in ``schedule/raw/`` represents one train timetable scraped
from the Thai Railway official timetable website.

File naming convention: ``{route_type}_train{number}.json``
    e.g. ``eastern_train280.json`` → route_type=eastern, train_number=280

File format::

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


def _infer_train_type(name: str) -> str:
    name_lower = name.lower()
    for keyword, train_type in _TRAIN_TYPE_KEYWORDS:
        if keyword in name_lower:
            return train_type
    # Fall back to number-based heuristic when name has no keyword
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
    """Return None for missing/dash values, otherwise return stripped HH:MM string."""
    if not value:
        return None
    stripped = value.strip()
    if stripped in ("-", "", "N/A", "n/a"):
        return None
    return stripped


def _parse_raw_file(path: Path) -> TrainData | None:
    """Parse a single raw schedule JSON file into a TrainData domain object.

    Returns None if the file cannot be parsed or produces no stops.
    """
    m = _FILENAME_RE.match(path.name)
    if not m:
        logger.warning("Skipping file with unexpected name format", path=str(path))
        return None

    route_prefix = m.group(1)  # e.g. "eastern"
    train_number = m.group(2)  # e.g. "280"
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
    for seq, entry in enumerate(raw.get("timetable", [])):
        station_name = (entry.get("station") or "").strip()
        if not station_name:
            continue

        arrival = _parse_time_value(entry.get("arrival"))
        departure = _parse_time_value(entry.get("departure"))

        # At least one of arrival or departure must be present (ignore blank stops)
        if arrival is None and departure is None:
            logger.debug(
                "Stop has no time data, skipping",
                train=train_number,
                station=station_name,
                seq=seq,
            )
            continue

        stops.append(
            ScheduleStopData(
                station_name=station_name,
                sequence=seq,
                arrival_time=arrival,
                departure_time=departure,
                arrival_day_offset=0,
                departure_day_offset=0,
                day_of_week=list(range(7)),  # all 7 days by default
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

    Files are processed one by one to allow granular progress logging.
    Results are returned sorted by train number for predictable ordering.

    Args:
        raw_dir: Override directory path. Defaults to ``settings.schedule_raw_dir``.

    Returns:
        List of successfully parsed TrainData objects.
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

    logger.info(
        "Starting raw schedule files scan", directory=str(raw_dir), files=len(files)
    )

    trains: list[TrainData] = []
    failed = 0

    for path in files:
        train = _parse_raw_file(path)
        if train is not None:
            trains.append(train)
            logger.debug(
                "Parsed raw schedule file",
                train_number=train.train_number,
                stops=len(train.stops),
                file=path.name,
            )
        else:
            failed += 1

    logger.info(
        "Raw schedule scan complete",
        total_files=len(files),
        parsed=len(trains),
        failed=failed,
    )
    return trains
