"""Parser for Thai Railway Stations KML file.

Converts the curated KML station file (ExtendedData format) into StationData
domain entities and exposes alias hints used to resolve schedule strings that
don't match any station name directly.
"""

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from app.core.logging import get_logger
from app.domain.railroad.entities import StationData

logger = get_logger(__name__)

KML_NS = "http://www.opengis.net/kml/2.2"

_LINE_TO_ROUTE_TYPE: dict[str, str] = {
    "northern": "northern",
    "northeastern": "northeastern",
    "eastern": "eastern",
    "southern": "southern",
    "western": "western",
    "maeklong": "other",
    "urban": "urban",
}


def _tag(name: str) -> str:
    return f"{{{KML_NS}}}{name}"


def _line_to_route_type(line: str) -> str:
    return _LINE_TO_ROUTE_TYPE.get(line.lower(), "other")


def _folder_to_route_type(folder_name: str) -> str:
    """Infer route type from KML folder name."""
    lower = folder_name.lower()
    for key, rt in _LINE_TO_ROUTE_TYPE.items():
        if key in lower:
            return rt
    return "other"


def _get_extended_data(pm: ET.Element) -> dict[str, str]:
    """Extract all ExtendedData/Data name=value pairs from a Placemark."""
    result: dict[str, str] = {}
    ext = pm.find(_tag("ExtendedData"))
    if ext is None:
        return result
    for data_el in ext.findall(_tag("Data")):
        name = data_el.get("name")
        val_el = data_el.find(_tag("value"))
        if name and val_el is not None and val_el.text is not None:
            result[name] = val_el.text.strip()
    return result


@dataclass(frozen=True)
class ParsedStations:
    """Stations plus alias hints parsed from the KML file."""

    stations: list[StationData]
    # raw_name (as written in schedules) -> canonical station name_en
    aliases: dict[str, str]


def parse_stations_kml(path: Path) -> ParsedStations:
    """Load and parse the Thai Railway Stations KML file.

    Each Placemark carries ExtendedData fields: name_en, name_th, code,
    class, line, district, province, lat, lon.
    """
    raw = path.read_bytes()
    root = ET.fromstring(raw)  # noqa: S314
    document = root.find(_tag("Document")) or root

    stations: list[StationData] = []
    skipped = 0

    for folder in document.findall(_tag("Folder")):
        name_el = folder.find(_tag("name"))
        folder_name = (
            name_el.text.strip() if name_el is not None and name_el.text else "Unknown"
        )
        folder_route_type = _folder_to_route_type(folder_name)

        for pm in folder.findall(_tag("Placemark")):
            ext = _get_extended_data(pm)

            # Prefer ExtendedData lat/lon; fall back to Point coordinates
            lat_str = ext.get("lat")
            lon_str = ext.get("lon")

            if lat_str is None or lon_str is None:
                pt = pm.find(_tag("Point"))
                if pt is not None:
                    coords_el = pt.find(_tag("coordinates"))
                    if coords_el is not None and coords_el.text:
                        parts = coords_el.text.strip().split(",")
                        if len(parts) >= 2:
                            try:
                                lon_str = parts[0]
                                lat_str = parts[1]
                            except (IndexError, ValueError) as e:
                                logger.warning(
                                    "Failed to parse Placemark coordinates",
                                    error=str(e),
                                    text=coords_el.text,
                                )

            if lat_str is None or lon_str is None:
                skipped += 1
                continue

            try:
                lat = float(lat_str)
                lon = float(lon_str)
            except ValueError:
                skipped += 1
                continue

            if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                skipped += 1
                continue
            if lat == 0.0 and lon == 0.0:
                skipped += 1
                continue

            name = (ext.get("name_en") or "").strip()
            if not name:
                # Fall back to Placemark <name> element
                pm_name_el = pm.find(_tag("name"))
                name = (
                    pm_name_el.text.strip()
                    if pm_name_el is not None and pm_name_el.text
                    else ""
                )
            if not name:
                skipped += 1
                continue

            line = (ext.get("line") or "").strip()
            route_type = _line_to_route_type(line) if line else folder_route_type

            stations.append(
                StationData(
                    name=name,
                    lon=lon,
                    lat=lat,
                    source_line=line,
                    name_th=(ext.get("name_th") or "").strip(),
                    code=(ext.get("code") or "").strip(),
                    station_class=str(ext.get("class") or ""),
                    district=(ext.get("district") or "").strip(),
                    folder=(ext.get("province") or folder_name).strip(),
                    route_type=route_type,
                )
            )

    # Also parse Placemarks directly under Document (outside folders)
    for pm in document.findall(_tag("Placemark")):
        ext = _get_extended_data(pm)
        lat_str = ext.get("lat")
        lon_str = ext.get("lon")

        if lat_str is None or lon_str is None:
            pt = pm.find(_tag("Point"))
            if pt is not None:
                coords_el = pt.find(_tag("coordinates"))
                if coords_el is not None and coords_el.text:
                    parts = coords_el.text.strip().split(",")
                    if len(parts) >= 2:
                        try:
                            lon_str = parts[0]
                            lat_str = parts[1]
                        except (IndexError, ValueError) as e:
                            logger.warning(
                                "Failed to parse Placemark coordinates",
                                error=str(e),
                                text=coords_el.text,
                            )

        if lat_str is None or lon_str is None:
            skipped += 1
            continue

        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except ValueError:
            skipped += 1
            continue

        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            skipped += 1
            continue
        if lat == 0.0 and lon == 0.0:
            skipped += 1
            continue

        name = (ext.get("name_en") or "").strip()
        if not name:
            pm_name_el = pm.find(_tag("name"))
            name = (
                pm_name_el.text.strip()
                if pm_name_el is not None and pm_name_el.text
                else ""
            )
        if not name:
            skipped += 1
            continue

        line = (ext.get("line") or "").strip()
        route_type = _line_to_route_type(line) if line else "other"

        stations.append(
            StationData(
                name=name,
                lon=lon,
                lat=lat,
                source_line=line,
                name_th=(ext.get("name_th") or "").strip(),
                code=(ext.get("code") or "").strip(),
                station_class=str(ext.get("class") or ""),
                district=(ext.get("district") or "").strip(),
                folder=(ext.get("province") or "").strip(),
                route_type=route_type,
            )
        )

    logger.info(
        "Stations parsed from KML",
        loaded=len(stations),
        skipped=skipped,
        path=str(path),
    )
    return ParsedStations(stations=stations, aliases={})
