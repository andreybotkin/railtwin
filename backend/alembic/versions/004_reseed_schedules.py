"""Reseed schedules and link trains to KML routes.

Revision ID: 004_reseed_schedules
Revises: 003_support_external_timetables
Create Date: 2026-04-10 00:00:00.000000
"""

from datetime import time
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "004_reseed_schedules"
down_revision = "003_support_external_timetables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Maps train_number -> (route_name_substring, base_dep_minutes, train_type)
# Base departure is minutes past midnight from the origin station.
TRAIN_ROUTE_CONFIG = [
    # Northern line (Krung Thep Aphiwat → Chiang Mai, ~733 km)
    {"train_number": "9",   "route_type": "northern", "base_dep": 18 * 60,      "speed": 80},  # 18:00
    {"train_number": "13",  "route_type": "northern", "base_dep": 6 * 60,       "speed": 80},  # 06:00
    {"train_number": "51",  "route_type": "northern", "base_dep": 7 * 60 + 30,  "speed": 60},  # 07:30
    {"train_number": "109", "route_type": "northern", "base_dep": 5 * 60,       "speed": 45},  # 05:00
    # Northeastern Ubon (→ Ubon Ratchathani, ~539 km)
    {"train_number": "21",  "route_type": "northeastern_ubon", "base_dep": 20 * 60,     "speed": 80},  # 20:00
    {"train_number": "67",  "route_type": "northeastern_ubon", "base_dep": 7 * 60,      "speed": 60},  # 07:00
    {"train_number": "139", "route_type": "northeastern_ubon", "base_dep": 5 * 60 + 30, "speed": 45},  # 05:30
    # Northeastern Nong Khai (→ Nong Khai, ~632 km)
    {"train_number": "25",  "route_type": "northeastern_nk",   "base_dep": 20 * 60,     "speed": 80},  # 20:00
    {"train_number": "75",  "route_type": "northeastern_nk",   "base_dep": 8 * 60,      "speed": 60},  # 08:00
    {"train_number": "133", "route_type": "northeastern_nk",   "base_dep": 6 * 60,      "speed": 45},  # 06:00
    # Southern line (→ Sungai Kolok, ~1124 km)
    {"train_number": "31",  "route_type": "southern",  "base_dep": 15 * 60,     "speed": 80},  # 15:00
    {"train_number": "37",  "route_type": "southern",  "base_dep": 22 * 60,     "speed": 80},  # 22:00
    {"train_number": "83",  "route_type": "southern",  "base_dep": 13 * 60,     "speed": 60},  # 13:00
    {"train_number": "171", "route_type": "southern",  "base_dep": 6 * 60,      "speed": 45},  # 06:00
    # Eastern line (→ Ban Klong Luk Border, ~245 km)
    {"train_number": "281", "route_type": "eastern",   "base_dep": 7 * 60 + 55, "speed": 60},  # 07:55
    {"train_number": "283", "route_type": "eastern",   "base_dep": 11 * 60,     "speed": 45},  # 11:00
]

# Route type → route_id selector query fragment
# We pick the longest route of each type as the main line.
ROUTE_QUERY = {
    "northern":       "SELECT id FROM routes WHERE route_type = 'northern' ORDER BY distance_km DESC LIMIT 1",
    "northeastern_ubon": """
        SELECT id FROM routes WHERE route_type = 'northeastern'
        AND name ILIKE '%Ubon%' ORDER BY distance_km DESC LIMIT 1
    """,
    "northeastern_nk": """
        SELECT id FROM routes WHERE route_type = 'northeastern'
        AND name ILIKE '%Nong Khai%' ORDER BY distance_km DESC LIMIT 1
    """,
    "southern":       "SELECT id FROM routes WHERE route_type = 'southern' ORDER BY distance_km DESC LIMIT 1",
    "eastern":        """
        SELECT id FROM routes WHERE route_type = 'eastern'
        AND name ILIKE '%Luk%' ORDER BY distance_km DESC LIMIT 1
    """,
}


def _minutes_to_time(minutes: int) -> time:
    """Convert absolute minutes (can exceed 1440 for overnight) to time object."""
    minutes = minutes % (24 * 60)
    return time(minutes // 60, minutes % 60)


def upgrade() -> None:
    """Reseed schedules using real KML route data and update train route assignments."""
    conn = op.get_bind()

    # Resolve route IDs
    route_ids: dict[str, int] = {}
    for key, query in ROUTE_QUERY.items():
        row = conn.execute(sa.text(query)).fetchone()
        if row:
            route_ids[key] = row[0]

    if not route_ids:
        return  # No routes available – skip silently

    # Clear any existing schedules (clean reseed)
    conn.execute(sa.text("DELETE FROM schedules"))

    for cfg in TRAIN_ROUTE_CONFIG:
        train_number = cfg["train_number"]
        route_key = cfg["route_type"]
        base_dep = cfg["base_dep"]
        speed_kmh = cfg["speed"]

        route_id = route_ids.get(route_key)
        if route_id is None:
            continue

        # Fetch train
        train_row = conn.execute(
            sa.text("SELECT id FROM trains WHERE train_number = :num"),
            {"num": train_number},
        ).fetchone()
        if not train_row:
            continue
        train_id = train_row[0]

        # Assign train to route
        conn.execute(
            sa.text("UPDATE trains SET current_route_id = :route_id WHERE id = :train_id"),
            {"route_id": route_id, "train_id": train_id},
        )

        # Fetch route_stations ordered by sequence with station info
        stops = conn.execute(
            sa.text("""
                SELECT rs.id, rs.sequence, rs.distance_from_start,
                       s.id as station_id, s.name as station_name,
                       CAST(r.distance_km AS FLOAT) as route_distance_km
                FROM route_stations rs
                JOIN stations s ON s.id = rs.station_id
                JOIN routes r ON r.id = rs.route_id
                WHERE rs.route_id = :route_id
                ORDER BY rs.sequence
            """),
            {"route_id": route_id},
        ).fetchall()

        if len(stops) < 2:
            continue

        route_distance_km = float(stops[0].route_distance_km or 1)

        for seq, stop in enumerate(stops):
            dist_km = float(stop.distance_from_start or 0)
            # Travel time in minutes from origin at given speed
            travel_minutes = int((dist_km / speed_kmh) * 60)
            dwell_minutes = 2  # Short stop at each intermediate station

            arr_abs = base_dep + travel_minutes
            dep_abs = arr_abs + dwell_minutes

            arr_time = _minutes_to_time(arr_abs) if seq > 0 else None
            dep_time = _minutes_to_time(dep_abs) if seq < len(stops) - 1 else None

            # Calculate route_progress for this stop
            route_progress = dist_km / route_distance_km if route_distance_km > 0 else 0.0

            conn.execute(
                sa.text("""
                    INSERT INTO schedules (
                        train_id, station_id, route_station_id,
                        station_name, arrival_time, departure_time,
                        day_of_week, platform, sequence,
                        distance_from_origin_km, route_progress,
                        arrival_day_offset, departure_day_offset
                    ) VALUES (
                        :train_id, :station_id, :rs_id,
                        :station_name, :arrival, :departure,
                        :days, :platform, :seq,
                        :distance, :progress,
                        :arr_offset, :dep_offset
                    )
                """),
                {
                    "train_id": train_id,
                    "station_id": stop.station_id,
                    "rs_id": stop.id,
                    "station_name": stop.station_name,
                    "arrival": arr_time,
                    "departure": dep_time,
                    "days": [0, 1, 2, 3, 4, 5, 6],
                    "platform": str((seq % 4) + 1),
                    "seq": seq,
                    "distance": round(dist_km, 2),
                    "progress": round(min(1.0, route_progress), 6),
                    "arr_offset": arr_abs // (24 * 60),
                    "dep_offset": dep_abs // (24 * 60),
                },
            )


def downgrade() -> None:
    """Remove reseeded schedules and clear train route assignments."""
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM schedules"))
    conn.execute(sa.text("UPDATE trains SET current_route_id = NULL"))
