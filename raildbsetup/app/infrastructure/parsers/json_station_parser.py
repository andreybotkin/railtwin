"""Parser for thai_railway_stations_full.json.

Converts the curated Wikipedia-sourced JSON into StationData domain entities.
Stations without coordinates (lat/lon missing or zero) are skipped.

JSON schema expected:
  {
    "stations": [
      {
        "name_en": "...",
        "name_th": "...",
        "code": "...",
        "class": "Halt|1|2|3|4|Special",
        "line": "Northern|Northeastern|Eastern|Southern|...",
        "district": "...",
        "province": "...",
        "lat": 13.0,
        "lon": 100.0
      },
      ...
    ]
  }
"""

import json
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.domain.railroad.entities import StationData

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)

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


def parse_stations_json(path: Path) -> list[StationData]:
    """Load and parse thai_railway_stations_full.json into StationData entities."""
    raw = path.read_bytes()
    data = json.loads(raw)

    raw_stations = data.get("stations", [])
    if not raw_stations:
        logger.warning("JSON file contains no stations", path=str(path))
        return []

    stations: list[StationData] = []
    skipped = 0

    for entry in raw_stations:
        lat = entry.get("lat")
        lon = entry.get("lon")

        # Skip entries with missing or obviously-invalid coordinates
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

    logger.info(
        "Stations parsed from JSON",
        total=len(raw_stations),
        loaded=len(stations),
        skipped=skipped,
        path=str(path),
    )
    return stations
