"""Position-snapshot builder for a single train.

Pure function — no database I/O.  Accepts pre-fetched domain objects and
returns a serialisable ``dict`` (or ``None`` when the train is not active).
"""

from __future__ import annotations

from typing import Any

from geoalchemy2.shape import to_shape

from app.models.database.models import Schedule, Train
from app.services import geo_utils, schedule_utils

__all__ = ["build_train_position"]


def build_train_position(
    train: Train,
    schedules: list[Schedule],
    route_coords: list[list[float]] | None,
    route_distance_km: float | None = None,
    *,
    delay: int,
    current_minutes: float,
) -> dict[str, Any] | None:
    """Calculate a current position snapshot for a single train.

    Args:
        train: Train domain object.
        schedules: Schedule entries in sequence order.
        route_coords: Route geometry as ``[[lon, lat], …]``, or ``None``.
        route_distance_km: Total route length used for progress calculation.
        delay: Current delay in minutes (sourced from TTS).
        current_minutes: Current Bangkok time as fractional minutes since
            midnight (injected by the caller for testability).

    Returns:
        Position dict, or ``None`` if the train is not currently running.
    """
    if not schedules or len(schedules) < 2:
        return None

    # ------------------------------------------------------------------ #
    # 1. Find the segment the train is currently in                        #
    # ------------------------------------------------------------------ #
    prev_stop: Schedule | None = None
    next_stop: Schedule | None = None

    for i, s in enumerate(schedules):
        dep_mins = schedule_utils.get_schedule_minutes(s, prefer_departure=True)
        if dep_mins is None:
            continue
        if dep_mins + delay > current_minutes:
            next_stop = s
            if i > 0:
                prev_stop = schedules[i - 1]
            break
        prev_stop = s

    if prev_stop is None or next_stop is None:
        return None

    # ------------------------------------------------------------------ #
    # 2. Compute progress within the segment                               #
    # ------------------------------------------------------------------ #
    prev_minutes = schedule_utils.get_schedule_minutes(prev_stop, prefer_departure=True)
    next_minutes = schedule_utils.get_schedule_minutes(next_stop, prefer_departure=False)
    if prev_minutes is None or next_minutes is None:
        return None

    prev_minutes += delay
    next_minutes += delay
    segment_duration = next_minutes - prev_minutes
    progress = (
        1.0
        if segment_duration <= 0
        else max(0.0, min(1.0, (current_minutes - prev_minutes) / segment_duration))
    )

    # ------------------------------------------------------------------ #
    # 3. Compute (lon, lat) and heading                                    #
    # ------------------------------------------------------------------ #
    start_p = 0.0
    end_p = 1.0
    heading: float

    if route_coords and len(route_coords) >= 2:
        total_stops = len(schedules)
        prev_index = next(
            (i for i, s in enumerate(schedules) if s is prev_stop), 0
        )
        next_index = next(
            (i for i, s in enumerate(schedules) if s is next_stop), prev_index + 1
        )
        start_p = schedule_utils.get_stop_progress(
            prev_stop, prev_index, total_stops, route_distance_km
        )
        end_p = schedule_utils.get_stop_progress(
            next_stop, next_index, total_stops, route_distance_km
        )
        overall_progress = start_p + (end_p - start_p) * progress
        lon, lat = geo_utils.interpolate_position(route_coords, overall_progress)

        head_p = min(1.0, max(overall_progress + 0.01, end_p))
        nlon, nlat = geo_utils.interpolate_position(route_coords, head_p)
        heading = geo_utils.great_circle_bearing((lon, lat), (nlon, nlat))
    else:
        # Fallback: straight-line interpolation between station coordinates.
        if prev_stop.station is None or next_stop.station is None:
            return None
        prev_pt = to_shape(prev_stop.station.location)
        next_pt = to_shape(next_stop.station.location)
        prev_c = (float(prev_pt.x), float(prev_pt.y))
        next_c = (float(next_pt.x), float(next_pt.y))
        lon = prev_c[0] + (next_c[0] - prev_c[0]) * progress
        lat = prev_c[1] + (next_c[1] - prev_c[1]) * progress
        heading = geo_utils.great_circle_bearing(prev_c, next_c)

    # ------------------------------------------------------------------ #
    # 4. Estimate speed                                                    #
    # ------------------------------------------------------------------ #
    avg_speed = 60.0
    if route_coords and segment_duration > 0:
        dist_km = geo_utils.segment_distance_km(route_coords, start_p, end_p)
        if dist_km > 0:
            avg_speed = dist_km / (segment_duration / 60)

    status = "at_station" if progress < 0.05 or progress > 0.95 else "moving"

    return {
        "train_id": train.id,
        "train_number": train.train_number,
        "train_type": train.train_type,
        "location": {"type": "Point", "coordinates": [lon, lat]},
        "speed": round(avg_speed, 1),
        "heading": round(heading, 1),
        "status": status,
        "delay_minutes": delay,
        "next_station": (
            next_stop.station.name if next_stop.station else next_stop.station_name
        ),
        "prev_station": (
            prev_stop.station.name if prev_stop.station else prev_stop.station_name
        ),
        "progress": round(progress * 100, 1),
    }
