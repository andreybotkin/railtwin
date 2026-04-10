"""Load Thailand Railway KML data from Google My Maps into the database.

Downloads KML from:
  https://www.google.com/maps/d/kml?mid=1E6wO3YeI2OZwvSaRGc-pPbUEYchbFdY&forcekml=1

Parses:
- Railway line geometries (LineString Placemarks)
- Station points (Point Placemarks)

Inserts into:
- routes (name, geometry, route_type, color)
- stations (name, location, code)
- route_stations (linking stations to routes with sequence)

Run inside the backend container:
    python scripts/load_kml_data.py
"""

import asyncio
import hashlib
import re
import sys
import urllib.request
from typing import Any
from xml.etree import ElementTree as ET

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

KML_URL = "https://www.google.com/maps/d/kml?mid=1E6wO3YeI2OZwvSaRGc-pPbUEYchbFdY&forcekml=1"

KML_NS = "http://www.opengis.net/kml/2.2"

# Map folder name keywords → route_type used in the DB schema
FOLDER_TYPE_MAP = {
    "northern": "northern",
    "northeastern": "northeastern",
    "western": "western",
    "southern": "southern",
    "eastern": "eastern",
    "bangkok": "urban",
}

# Infer route_type from route NAME when folder is not descriptive
ROUTE_NAME_TYPE_MAP = [
    # Northern lines
    (re.compile(r"chiang mai|lampang|lamphun|uttaradit|sawankhalok|sila at|den chai|thoen|nakhon lampang", re.I), "northern"),
    # Northeastern lines
    (re.compile(r"ubon|nong khai|bua yai|thanon chira|kaeng khoi|khon kaen|udon", re.I), "northeastern"),
    # Southern lines
    (re.compile(r"padang besar|su.ngai kolok|sungai kolok|hat yai|kantang|nakhon si thammarat|khiri rat|"
                r"chumphon|surat thani|hua hin|samut songkhram|samut sakhon|suphan buri|namtok", re.I), "southern"),
    # Eastern lines
    (re.compile(r"aranyaprathet|ban khlong luk|chachoengsao|eastern|laem chabang|map ta phut|si racha|mae nam", re.I), "eastern"),
    # Urban/Bangkok
    (re.compile(r"skytrain|bts|mrt|airport rail|red line|green line|blue line|purple line|orange line|gold line|"
                r"dark red|light red|dark green|light green", re.I), "urban"),
]

# Route color by route_type (fallback)
DEFAULT_COLOR = {
    "northern": "#E53935",
    "northeastern": "#1E88E5",
    "western": "#00897B",
    "southern": "#FB8C00",
    "eastern": "#8E24AA",
    "urban": "#43A047",
    "other": "#546E7A",
}

# KML style color overrides – styleUrl can carry a hex color
STYLE_COLOR_RE = re.compile(r"#line-([0-9A-Fa-f]{6})-")


def kml_tag(tag: str) -> str:
    return f"{{{KML_NS}}}{tag}"


def parse_coordinates(coords_text: str) -> list[tuple[float, float]]:
    """Parse KML coordinates string → list of (lon, lat) tuples."""
    points: list[tuple[float, float]] = []
    for token in coords_text.split():
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                lon, lat = float(parts[0]), float(parts[1])
                points.append((lon, lat))
            except ValueError:
                continue
    return points


def extract_style_color(style_url: str | None) -> str | None:
    if style_url:
        m = STYLE_COLOR_RE.search(style_url)
        if m:
            return f"#{m.group(1).upper()}"
    return None


def folder_route_type(folder_name: str) -> str:
    lower = folder_name.lower()
    for key, rt in FOLDER_TYPE_MAP.items():
        if key in lower:
            return rt
    return "other"


def route_name_type(name: str) -> str | None:
    for pattern, rt in ROUTE_NAME_TYPE_MAP:
        if pattern.search(name):
            return rt
    return None


def make_station_code(name: str) -> str:
    """Generate a short unique code from a station name."""
    clean = re.sub(r"[^A-Za-z0-9]", "", name.upper())
    if len(clean) <= 5:
        return clean
    # Use first 3 chars + 2-char hash suffix for uniqueness
    suffix = hashlib.md5(clean.encode()).hexdigest()[:2].upper()
    return clean[:3] + suffix


def parse_kml(kml_bytes: bytes) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse KML and return (routes, stations).

    routes: list of dicts with keys:
        name, route_type, color, coords [(lon,lat),...]
    stations: list of dicts with keys:
        name, lon, lat, route_name (folder context)
    """
    root = ET.fromstring(kml_bytes)
    document = root.find(kml_tag("Document"))
    if document is None:
        document = root

    routes: list[dict[str, Any]] = []
    stations: list[dict[str, Any]] = []

    # Process top-level folders (each = a railway line group)
    for folder in document.findall(kml_tag("Folder")):
        folder_name_el = folder.find(kml_tag("name"))
        folder_name = folder_name_el.text.strip() if folder_name_el is not None and folder_name_el.text else "Unknown"
        rt = folder_route_type(folder_name)

        for placemark in folder.findall(kml_tag("Placemark")):
            pm_name_el = placemark.find(kml_tag("name"))
            pm_name = pm_name_el.text.strip() if pm_name_el is not None and pm_name_el.text else "Unnamed"

            style_url_el = placemark.find(kml_tag("styleUrl"))
            style_url = style_url_el.text if style_url_el is not None else None

            # LineString → route
            line_string = placemark.find(kml_tag("LineString"))
            if line_string is not None:
                coords_el = line_string.find(kml_tag("coordinates"))
                if coords_el is not None and coords_el.text:
                    coords = parse_coordinates(coords_el.text)
                    if len(coords) >= 2:
                        color = extract_style_color(style_url) or DEFAULT_COLOR.get(rt, "#546E7A")
                        # Refine route_type from name if folder gave no useful info
                        final_rt = route_name_type(pm_name) or rt
                        color = extract_style_color(style_url) or DEFAULT_COLOR.get(final_rt, "#546E7A")
                        routes.append(
                            {
                                "name": pm_name,
                                "folder": folder_name,
                                "route_type": final_rt,
                                "color": color,
                                "coords": coords,
                            }
                        )

            # Point → station
            point = placemark.find(kml_tag("Point"))
            if point is not None:
                coords_el = point.find(kml_tag("coordinates"))
                if coords_el is not None and coords_el.text:
                    pts = parse_coordinates(coords_el.text.strip())
                    if pts:
                        lon, lat = pts[0]
                        stations.append(
                            {
                                "name": pm_name,
                                "lon": lon,
                                "lat": lat,
                                "folder": folder_name,
                                "route_type": rt,
                            }
                        )

    # Also process placemarks directly under Document (not in a folder)
    for placemark in document.findall(kml_tag("Placemark")):
        pm_name_el = placemark.find(kml_tag("name"))
        pm_name = pm_name_el.text.strip() if pm_name_el is not None and pm_name_el.text else "Unnamed"

        point = placemark.find(kml_tag("Point"))
        if point is not None:
            coords_el = point.find(kml_tag("coordinates"))
            if coords_el is not None and coords_el.text:
                pts = parse_coordinates(coords_el.text.strip())
                if pts:
                    lon, lat = pts[0]
                    stations.append(
                        {
                            "name": pm_name,
                            "lon": lon,
                            "lat": lat,
                            "folder": "Unknown",
                            "route_type": "other",
                        }
                    )

    return routes, stations


async def load_into_db(
    database_url: str,
    routes: list[dict[str, Any]],
    stations: list[dict[str, Any]],
) -> None:
    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        # ------------------------------------------------------------------ #
        # 1. Clear existing seed data (routes, route_stations, stations)       #
        # ------------------------------------------------------------------ #
        print("  Clearing existing data...")
        await conn.execute(sa.text("DELETE FROM route_stations"))
        await conn.execute(sa.text("DELETE FROM routes"))
        await conn.execute(sa.text("DELETE FROM stations"))

        # ------------------------------------------------------------------ #
        # 2. Insert stations (deduplicate by name)                            #
        # ------------------------------------------------------------------ #
        print(f"  Inserting {len(stations)} station candidates...")
        station_id_map: dict[str, int] = {}  # name → id
        seen_codes: set[str] = set()

        for s in stations:
            name = s["name"]
            if name in station_id_map:
                continue  # already inserted

            code = make_station_code(name)
            # Ensure code uniqueness
            original_code = code
            counter = 1
            while code in seen_codes:
                code = original_code[:4] + str(counter)
                counter += 1
            seen_codes.add(code)

            result = await conn.execute(
                sa.text(
                    """
                    INSERT INTO stations (name, code, location, province, facilities)
                    VALUES (:name, :code,
                            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                            :province, cast(:facilities as jsonb))
                    RETURNING id
                    """
                ),
                {
                    "name": name,
                    "code": code,
                    "lon": s["lon"],
                    "lat": s["lat"],
                    "province": s["folder"],
                    "facilities": '{"parking": false, "toilet": true, "wifi": false}',
                },
            )
            station_id_map[name] = result.fetchone()[0]

        print(f"  Inserted {len(station_id_map)} unique stations.")

        # ------------------------------------------------------------------ #
        # 3. Insert routes with PostGIS LineString geometry                  #
        # ------------------------------------------------------------------ #
        print(f"  Inserting {len(routes)} routes...")
        inserted_routes = 0

        for r in routes:
            coords = r["coords"]
            # Build WKT LineString
            coord_str = ", ".join(f"{lon} {lat}" for lon, lat in coords)
            wkt = f"LINESTRING({coord_str})"

            # Approximate distance using simple Euclidean sum (degrees → km ≈ 111km/deg avg)
            distance_km = 0.0
            for i in range(1, len(coords)):
                dlon = (coords[i][0] - coords[i - 1][0]) * 111.0 * 0.9  # crude cos adjustment
                dlat = (coords[i][1] - coords[i - 1][1]) * 111.0
                distance_km += (dlon**2 + dlat**2) ** 0.5

            result = await conn.execute(
                sa.text(
                    """
                    INSERT INTO routes (name, name_th, route_type, distance_km, color, line_geometry)
                    VALUES (:name, NULL, :route_type, :distance_km, :color,
                            ST_SetSRID(ST_GeomFromText(:geom), 4326))
                    RETURNING id
                    """
                ),
                {
                    "name": r["name"],
                    "route_type": r["route_type"],
                    "distance_km": round(distance_km, 2),
                    "color": r["color"],
                    "geom": wkt,
                },
            )
            route_id = result.fetchone()[0]
            inserted_routes += 1

            # ---------------------------------------------------------- #
            # 4. Assign stations to route by proximity                    #
            # Each station point is matched to the nearest point on the   #
            # route linestring; we then order stations by that distance.  #
            # ---------------------------------------------------------- #
            # Collect candidate stations within ~50km bounding box of route
            min_lon = min(c[0] for c in coords) - 0.5
            max_lon = max(c[0] for c in coords) + 0.5
            min_lat = min(c[1] for c in coords) - 0.5
            max_lat = max(c[1] for c in coords) + 0.5

            nearby = await conn.execute(
                sa.text(
                    """
                    SELECT id, name,
                           ST_X(location::geometry) as lon,
                           ST_Y(location::geometry) as lat,
                           ST_Distance(
                               location::geography,
                               ST_SetSRID(ST_GeomFromText(:geom), 4326)::geography
                           ) AS dist_to_line
                    FROM stations
                    WHERE ST_X(location::geometry) BETWEEN :min_lon AND :max_lon
                      AND ST_Y(location::geometry) BETWEEN :min_lat AND :max_lat
                      AND ST_Distance(
                              location::geography,
                              ST_SetSRID(ST_GeomFromText(:geom), 4326)::geography
                          ) < 2000
                    ORDER BY dist_to_line
                    """
                ),
                {
                    "geom": wkt,
                    "min_lon": min_lon,
                    "max_lon": max_lon,
                    "min_lat": min_lat,
                    "max_lat": max_lat,
                },
            )
            nearby_stations = nearby.fetchall()

            if nearby_stations:
                # Order by position along the line
                ordered = await conn.execute(
                    sa.text(
                        """
                        SELECT s.id,
                               ST_LineLocatePoint(
                                   ST_SetSRID(ST_GeomFromText(:geom), 4326),
                                   s.location::geometry
                               ) AS frac
                        FROM stations s
                        WHERE s.id = ANY(:ids)
                        ORDER BY frac
                        """
                    ),
                    {
                        "geom": wkt,
                        "ids": [row[0] for row in nearby_stations],
                    },
                )
                ordered_rows = ordered.fetchall()

                total_dist = distance_km
                n = len(ordered_rows)
                for seq, row in enumerate(ordered_rows):
                    st_id = row[0]
                    frac = float(row[1])
                    dist_from_start = round(frac * total_dist, 2)
                    await conn.execute(
                        sa.text(
                            """
                            INSERT INTO route_stations (route_id, station_id, sequence, distance_from_start)
                            VALUES (:route_id, :station_id, :sequence, :distance)
                            ON CONFLICT DO NOTHING
                            """
                        ),
                        {
                            "route_id": route_id,
                            "station_id": st_id,
                            "sequence": seq,
                            "distance": dist_from_start,
                        },
                    )

        print(f"  Inserted {inserted_routes} routes.")

    await engine.dispose()


async def main() -> None:
    import os

    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@postgres:5432/railway_db",
    )

    print("Downloading KML data...")
    req = urllib.request.Request(KML_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        kml_bytes = resp.read()
    print(f"  Downloaded {len(kml_bytes):,} bytes.")

    print("Parsing KML...")
    routes, stations = parse_kml(kml_bytes)
    print(f"  Found {len(routes)} route geometries and {len(stations)} station points.")

    print("Loading into database...")
    await load_into_db(database_url, routes, stations)

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
