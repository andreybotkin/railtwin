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


def _is_dwell_window(
    schedule: Schedule,
    *,
    current_minutes: float,
    delay: int,
) -> bool:
    arrival_minutes, departure_minutes = schedule_utils.get_arrival_departure_minutes(
        schedule
    )
    if arrival_minutes is None or departure_minutes is None:
        return False
    if departure_minutes <= arrival_minutes:
        return False

    adjusted_arrival = arrival_minutes + delay
    adjusted_departure = departure_minutes + delay
    return adjusted_arrival <= current_minutes <= adjusted_departure


def _merge_segment_coordinates(segments: list[list[list[float]]]) -> list[list[float]]:
    merged: list[list[float]] = []
    for coordinates in segments:
        if not coordinates:
            continue
        if not merged:
            merged.extend(coordinates)
            continue
        if merged[-1] == coordinates[0]:
            merged.extend(coordinates[1:])
        else:
            merged.extend(coordinates)
    return merged


def _segment_total_distance_km(
    route_segments: list[dict[str, Any]] | None,
) -> float | None:
    if not route_segments:
        return None
    last_end = route_segments[-1].get("end_km")
    if last_end is None:
        return None
    return float(last_end)


def _segment_for_route_progress(
    route_segments: list[dict[str, Any]] | None,
    route_progress: float,
) -> dict[str, Any] | None:
    if not route_segments:
        return None

    total_distance_km = _segment_total_distance_km(route_segments)
    if not total_distance_km or total_distance_km <= 0:
        return None

    target_distance_km = max(
        0.0, min(total_distance_km, route_progress * total_distance_km)
    )
    epsilon = 1e-6

    for segment in route_segments:
        start_km = float(segment.get("start_km") or 0.0)
        end_km = float(segment.get("end_km") or start_km)
        if start_km - epsilon <= target_distance_km <= end_km + epsilon:
            return segment

    return route_segments[-1]


def _build_subroute_coords(
    route_segments: list[dict[str, Any]] | None,
    start_progress: float,
    end_progress: float,
) -> list[list[float]] | None:
    if not route_segments:
        return None

    total_distance_km = _segment_total_distance_km(route_segments)
    if not total_distance_km or total_distance_km <= 0:
        return None

    start_distance_km = max(
        0.0, min(total_distance_km, start_progress * total_distance_km)
    )
    end_distance_km = max(0.0, min(total_distance_km, end_progress * total_distance_km))
    reversed_direction = end_distance_km < start_distance_km
    min_distance_km = min(start_distance_km, end_distance_km)
    max_distance_km = max(start_distance_km, end_distance_km)
    epsilon = 1e-6

    overlapping_segments = [
        segment.get("coords", [])
        for segment in route_segments
        if float(segment.get("end_km") or 0.0) > min_distance_km + epsilon
        and float(segment.get("start_km") or 0.0) < max_distance_km - epsilon
    ]
    if not overlapping_segments:
        return None
    merged = _merge_segment_coordinates(overlapping_segments)
    if reversed_direction:
        return list(reversed(merged))
    return merged


def _minutes_to_hhmm(minutes: float) -> str:
    """Convert fractional minutes-since-midnight to 'HH:MM' string (handles day overflow)."""
    total = int(round(minutes)) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def build_train_position(
    train: Train,
    schedules: list[Schedule],
    route_coords: list[list[float]] | None,
    route_distance_km: float | None = None,
    route_segments: list[dict[str, Any]] | None = None,
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
    next_minutes = schedule_utils.get_schedule_minutes(
        next_stop, prefer_departure=False
    )
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
    is_dwelling = _is_dwell_window(
        next_stop,
        current_minutes=current_minutes,
        delay=delay,
    )

    # ------------------------------------------------------------------ #
    # 3. Compute (lon, lat) and heading                                    #
    # ------------------------------------------------------------------ #
    start_p = 0.0
    end_p = 1.0
    heading: float
    overall_progress = progress
    current_edge_id: int | None = None
    graph_from_station_id: int | None = None
    graph_to_station_id: int | None = None
    _segment_length_km: float | None = None

    if route_coords and len(route_coords) >= 2:
        total_stops = len(schedules)
        prev_index = next((i for i, s in enumerate(schedules) if s is prev_stop), 0)
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

        active_coords = _build_subroute_coords(route_segments, start_p, end_p)
        if active_coords:
            lon, lat = geo_utils.interpolate_position(active_coords, progress)
            head_p = min(1.0, progress + 0.01)
            nlon, nlat = geo_utils.interpolate_position(active_coords, head_p)
        else:
            lon, lat = geo_utils.interpolate_position(route_coords, overall_progress)
            heading_progress = max(
                0.0,
                min(1.0, overall_progress + (0.01 if end_p >= start_p else -0.01)),
            )
            nlon, nlat = geo_utils.interpolate_position(route_coords, heading_progress)
        heading = geo_utils.great_circle_bearing((lon, lat), (nlon, nlat))

        current_segment = _segment_for_route_progress(route_segments, overall_progress)
        if current_segment is not None:
            current_edge_id = int(current_segment["edge_id"])
            graph_from_station_id = int(current_segment["from_station_id"])
            graph_to_station_id = int(current_segment["to_station_id"])
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
    if is_dwelling:
        avg_speed = 0.0
    elif route_coords and segment_duration > 0:
        dist_km = geo_utils.segment_distance_km(route_coords, start_p, end_p)
        if dist_km > 0:
            avg_speed = dist_km / (segment_duration / 60)

    status = (
        "at_station" if is_dwelling or progress < 0.05 or progress > 0.95 else "moving"
    )

    return {
        "train_id": train.id,
        "train_number": train.train_number,
        "train_type": train.train_type,
        "route_id": train.current_route_id,
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
        "eta_next_station": _minutes_to_hhmm(next_minutes),
        "progress": round(progress * 100, 1),
        "route_progress": round(max(0.0, min(1.0, overall_progress)), 6),
        "segment_progress": round(progress, 6),
        "current_edge_id": current_edge_id,
        "graph_from_station_id": graph_from_station_id,
        "graph_to_station_id": graph_to_station_id,
    }
