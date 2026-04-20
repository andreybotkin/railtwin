"""Parser for thai_railway_stations_full.json.

Converts the curated Wikipedia-sourced JSON into StationData domain entities
and exposes alias hints used to resolve schedule strings that don't match any
station name directly.
"""

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.domain.railroad.entities import StationData

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)


@dataclass(frozen=True)
class ParsedStations:
    """Stations plus alias hints parsed from the curated JSON file."""

    stations: list[StationData]
    # raw_name (as written in schedules) -> canonical station name_en
    aliases: dict[str, str]


# Hard-coded safety net for aliases not covered by the JSON file but still
# present in Wikipedia-sourced schedules. Keep this list tiny — prefer adding
# entries to thai_railway_stations_full.json::schedule_aliases when possible.
_EXTRA_ALIASES: dict[str, str] = {
    "Pathiu": "Pathio",
    "Pathiu ": "Pathio",
}

_LINE_TO_ROUTE_TYPE: dict[str, str] = {
    "northern": "northern",
    "northeastern": "northeastern",
    "eastern": "eastern",
    "southern": "southern",
    "western": "western",
    "maeklong": "other",
    "urban": "urban",
}


def _line_to_route_type(line: str) -> str:
    return _LINE_TO_ROUTE_TYPE.get(line.lower(), "other")


def parse_stations_json(path: Path) -> ParsedStations:
    """Load and parse thai_railway_stations_full.json.

    Returns both the station entities and an alias map built from the JSON's
    ``schedule_aliases`` block and any per-station ``schedule_name`` fields.
    """

    raw = path.read_bytes()
    data = json.loads(raw)

    raw_stations = data.get("stations", [])
    if not raw_stations:
        logger.warning("JSON file contains no stations", path=str(path))
        return ParsedStations(stations=[], aliases={})

    stations: list[StationData] = []
    skipped = 0
    # Station names actually loaded into the DB (used to filter aliases whose
    # targets no longer exist).
    known_names: set[str] = set()
    per_station_aliases: dict[str, str] = {}

    for entry in raw_stations:
        lat = entry.get("lat")
        lon = entry.get("lon")

        if lat is None or lon is None:
            skipped += 1
            continue
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            skipped += 1
            continue
        if lat == 0.0 and lon == 0.0:
            skipped += 1
            continue

        name = (entry.get("name_en") or "").strip()
        if not name:
            skipped += 1
            continue
        known_names.add(name)

        schedule_name = (entry.get("schedule_name") or "").strip()
        if schedule_name and schedule_name != name:
            per_station_aliases[schedule_name] = name

        stations.append(
            StationData(
                name=name,
                lon=float(lon),
                lat=float(lat),
                source_line=(entry.get("line") or "").strip(),
                name_th=(entry.get("name_th") or "").strip(),
                code=(entry.get("code") or "").strip(),
                station_class=str(entry.get("class") or ""),
                district=(entry.get("district") or "").strip(),
                folder=(entry.get("province") or "").strip(),
                route_type=_line_to_route_type(entry.get("line") or ""),
            )
        )

    raw_aliases: dict[str, str] = {}
    for key, value in (data.get("schedule_aliases") or {}).items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        raw_aliases[key.strip()] = value.strip()
    for key, value in _EXTRA_ALIASES.items():
        raw_aliases.setdefault(key, value)
    raw_aliases.update(per_station_aliases)

    aliases: dict[str, str] = {}
    dropped = 0
    for alias, target in raw_aliases.items():
        if not alias or not target:
            continue
        if target not in known_names:
            dropped += 1
            continue
        aliases[alias] = target

    logger.info(
        "Stations parsed from JSON",
        total=len(raw_stations),
        loaded=len(stations),
        skipped=skipped,
        aliases=len(aliases),
        aliases_dropped=dropped,
        path=str(path),
    )
    return ParsedStations(stations=stations, aliases=aliases)
