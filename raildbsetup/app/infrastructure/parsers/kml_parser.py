"""KML parser for Thailand Railway map data.

Converts Google My Maps KML into domain entities (RouteData, StationData).
"""

import re
from xml.etree import ElementTree as ET

from app.domain.railroad.entities import RouteData, StationData

KML_NS = "http://www.opengis.net/kml/2.2"

FOLDER_TYPE_MAP = {
    "northern": "northern",
    "northeastern": "northeastern",
    "western": "western",
    "southern": "southern",
    "eastern": "eastern",
    "bangkok": "urban",
}

ROUTE_NAME_TYPE_MAP = [
    (
        re.compile(
            r"chiang mai|lampang|lamphun|uttaradit|sawankhalok|"
            r"sila at|den chai|thoen|nakhon lampang",
            re.I,
        ),
        "northern",
    ),
    (
        re.compile(
            r"ubon|nong khai|bua yai|thanon chira|kaeng khoi|khon kaen|udon",
            re.I,
        ),
        "northeastern",
    ),
    (
        re.compile(
            r"padang besar|su.ngai kolok|sungai kolok|hat yai|kantang|"
            r"nakhon si thammarat|khiri rat|chumphon|surat thani|hua hin|"
            r"samut songkhram|samut sakhon|suphan buri|namtok",
            re.I,
        ),
        "southern",
    ),
    (
        re.compile(
            r"aranyaprathet|ban khlong luk|chachoengsao|eastern|"
            r"laem chabang|map ta phut|si racha|mae nam",
            re.I,
        ),
        "eastern",
    ),
    (
        re.compile(
            r"skytrain|bts|mrt|airport rail|red line|green line|blue line|"
            r"purple line|orange line|gold line|dark red|light red|"
            r"dark green|light green",
            re.I,
        ),
        "urban",
    ),
]

DEFAULT_COLOR = {
    "northern": "#E53935",
    "northeastern": "#1E88E5",
    "western": "#00897B",
    "southern": "#FB8C00",
    "eastern": "#8E24AA",
    "urban": "#43A047",
    "other": "#546E7A",
}

_STYLE_COLOR_RE = re.compile(r"#line-([0-9A-Fa-f]{6})-")


def _tag(name: str) -> str:
    return f"{{{KML_NS}}}{name}"


def _parse_coords(text: str) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for token in text.split():
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                pts.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
    return pts


def _normalize_coords(coords: list[tuple[float, float]]) -> list[tuple[float, float]]:
    normalized: list[tuple[float, float]] = []
    for coord in coords:
        if normalized and normalized[-1] == coord:
            continue
        normalized.append(coord)
    if len(normalized) > 2 and normalized[0] == normalized[-1]:
        normalized.pop()
    return normalized


def _extract_color(style_url: str | None) -> str | None:
    if style_url:
        m = _STYLE_COLOR_RE.search(style_url)
        if m:
            return f"#{m.group(1).upper()}"
    return None


def _folder_type(folder_name: str) -> str:
    lower = folder_name.lower()
    for key, rt in FOLDER_TYPE_MAP.items():
        if key in lower:
            return rt
    return "other"


def _name_type(name: str) -> str | None:
    for pattern, rt in ROUTE_NAME_TYPE_MAP:
        if pattern.search(name):
            return rt
    return None


def _pm_name(pm: ET.Element) -> str:
    el = pm.find(_tag("name"))
    return el.text.strip() if el is not None and el.text else "Unknown"


def _style_url(pm: ET.Element) -> str | None:
    el = pm.find(_tag("styleUrl"))
    return el.text.strip() if el is not None and el.text else None


def _iter_line_strings(pm: ET.Element) -> list[ET.Element]:
    line_strings = list(pm.findall(_tag("LineString")))
    multi_geometry = pm.find(_tag("MultiGeometry"))
    if multi_geometry is not None:
        line_strings.extend(multi_geometry.findall(f".//{_tag('LineString')}"))
    return line_strings


def parse_kml_bytes(kml_bytes: bytes) -> tuple[list[RouteData], list[StationData]]:
    """Parse KML bytes and return (routes, stations) as domain entities."""
    root = ET.fromstring(kml_bytes)
    document = root.find(_tag("Document")) or root

    routes: list[RouteData] = []
    stations: list[StationData] = []

    for folder in document.findall(_tag("Folder")):
        name_el = folder.find(_tag("name"))
        folder_name = (
            name_el.text.strip() if name_el is not None and name_el.text else "Unknown"
        )
        rt = _folder_type(folder_name)

        for pm in folder.findall(_tag("Placemark")):
            pm_name = _pm_name(pm)
            style_url = _style_url(pm)

            for ls in _iter_line_strings(pm):
                coords_el = ls.find(_tag("coordinates"))
                if coords_el is not None and coords_el.text:
                    coords = _normalize_coords(_parse_coords(coords_el.text))
                    if len(coords) >= 2:
                        final_rt = _name_type(pm_name) or rt
                        color = _extract_color(style_url) or DEFAULT_COLOR.get(
                            final_rt, "#546E7A"
                        )
                        routes.append(
                            RouteData(
                                name=pm_name,
                                route_type=final_rt,
                                color=color,
                                coords=coords,
                                folder=folder_name,
                            )
                        )

            pt = pm.find(_tag("Point"))
            if pt is not None:
                coords_el = pt.find(_tag("coordinates"))
                if coords_el is not None and coords_el.text:
                    pts = _parse_coords(coords_el.text.strip())
                    if pts:
                        lon, lat = pts[0]
                        stations.append(
                            StationData(
                                name=pm_name,
                                lon=lon,
                                lat=lat,
                                folder=folder_name,
                                route_type=rt,
                            )
                        )

    # Placemarks directly under Document (not inside a Folder)
    for pm in document.findall(_tag("Placemark")):
        pt = pm.find(_tag("Point"))
        if pt is not None:
            coords_el = pt.find(_tag("coordinates"))
            if coords_el is not None and coords_el.text:
                pts = _parse_coords(coords_el.text.strip())
                if pts:
                    lon, lat = pts[0]
                    pm_name = _pm_name(pm)
                    stations.append(
                        StationData(
                            name=pm_name,
                            lon=lon,
                            lat=lat,
                            folder="",
                            route_type="other",
                        )
                    )

    return routes, stations


def parse_kml_routes(kml_bytes: bytes) -> list[RouteData]:
    """Parse KML bytes and return only routes (LineStrings), ignoring Point placemarks.

    Use this when station data is loaded from a separate source (e.g. JSON).
    """
    root = ET.fromstring(kml_bytes)
    document = root.find(_tag("Document")) or root

    routes: list[RouteData] = []

    for folder in document.findall(_tag("Folder")):
        name_el = folder.find(_tag("name"))
        folder_name = (
            name_el.text.strip() if name_el is not None and name_el.text else "Unknown"
        )
        rt = _folder_type(folder_name)

        for pm in folder.findall(_tag("Placemark")):
            pm_name = _pm_name(pm)
            style_url = _style_url(pm)
            for ls in _iter_line_strings(pm):
                coords_el = ls.find(_tag("coordinates"))
                if coords_el is None or not coords_el.text:
                    continue
                coords = _normalize_coords(_parse_coords(coords_el.text))
                if len(coords) < 2:
                    continue
                final_rt = _name_type(pm_name) or rt
                color = _extract_color(style_url) or DEFAULT_COLOR.get(final_rt, "#546E7A")
                routes.append(
                    RouteData(
                        name=pm_name,
                        route_type=final_rt,
                        color=color,
                        coords=coords,
                        folder=folder_name,
                    )
                )

    return routes
