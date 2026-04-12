"""Trajectory and stop-sequence builders for geops mobility-toolbox-js pattern.

Pure functions — no database I/O.  All inputs are pre-fetched domain objects;
outputs are serialisable dicts ready for JSON encoding.

geops pattern:
  time_intervals: [[unix_ms, geom_fraction, rotation_deg], ...]
  The frontend finds the bracket [t_j, t_j+1] for the current time, then
  interpolates ``geom_fraction`` and calls ``getCoordinateAt(frac)`` for
  sub-second smooth movement at 60 fps without any round-trips to the server.
"""

from __future__ import annotations

import time as _time
from typing import Any

from geoalchemy2.shape import to_shape

from app.core.config import settings
from app.models.database.models import Schedule, Train
from app.services import geo_utils, schedule_utils

__all__ = ["build_train_trajectory", "build_stop_sequence"]


def _minutes_to_hhmm(minutes: float) -> str:
    """Convert fractional minutes-since-midnight to 'HH:MM' string."""
    total = int(round(minutes)) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _find_initial_route_segment(
    schedules: list[Schedule],
    route_segments: list[dict[str, Any]] | None,
    current_minutes: float,
    delay: int,
) -> dict[str, Any] | None:
    if not route_segments or len(schedules) < 2:
        return None

    prev_stop: Schedule | None = None
    next_stop: Schedule | None = None
    for i, schedule in enumerate(schedules):
        dep_mins = schedule_utils.get_schedule_minutes(schedule, prefer_departure=True)
        if dep_mins is None:
            continue
        if dep_mins + delay > current_minutes:
            next_stop = schedule
            if i > 0:
                prev_stop = schedules[i - 1]
            break
        prev_stop = schedule

    if prev_stop is None or next_stop is None:
        return None

    next_route_station = getattr(next_stop, "route_station", None)
    next_edge_id = getattr(next_route_station, "edge_id", None)
    if next_edge_id is not None:
        return next(
            (
                segment
                for segment in route_segments
                if segment.get("edge_id") == int(next_edge_id)
            ),
            None,
        )
    return None

# Train-type colours — must match ``TYPE_COLORS`` in the frontend.
_TRAIN_TYPE_COLORS: dict[str, str] = {
    "special_express": "#E53935",
    "rapid": "#1E88E5",
    "ordinary": "#43A047",
}


def build_train_trajectory(
    train: Train,
    schedules: list[Schedule],
    route_coords: list[list[float]] | None,
    route_distance_km: float | None = None,
    route_segments: list[dict[str, Any]] | None = None,
    *,
    delay: int,
    current_minutes: float,
) -> dict[str, Any] | None:
    """Generate a geops-compatible trajectory feature with ``time_intervals``.

    Instead of a single position snapshot, the trajectory covers
    ``settings.trajectory_lookahead_seconds`` of future movement, letting the
    frontend interpolate the vehicle position at *any* sub-second granularity
    using only local arithmetic — no round-trip needed per animation frame.

    Args:
        train: Train domain object.
        schedules: Schedule entries in sequence order.
        route_coords: Route geometry as ``[[lon, lat], …]``, or ``None``.
        route_distance_km: Total route length for progress calculation.
        delay: Current delay in minutes (sourced from TTS).
        current_minutes: Current Bangkok time as fractional minutes since
            midnight (injected by the caller for testability).

    Returns:
        A GeoJSON Feature dict, or ``None`` if the train is not active.
    """
    if not schedules or len(schedules) < 2:
        return None

    now_unix_ms = int(_time.time() * 1000)
    _lookahead = settings.trajectory_lookahead_seconds
    _step = settings.trajectory_step_seconds
    step_count = _lookahead // _step + 1

    time_intervals: list[list[float]] = []
    fallback_coords: list[list[float]] = []

    bounds_min_lon = float("inf")
    bounds_min_lat = float("inf")
    bounds_max_lon = float("-inf")
    bounds_max_lat = float("-inf")

    prev_stop_name: str | None = None
    next_stop_name: str | None = None
    first_valid = True
    current_speed: float | None = None
    current_status = "moving"
    current_eta_next_station: str | None = None
    current_progress_pct: float | None = None
    current_route_progress: float | None = None
    current_segment_progress: float | None = None

    for step in range(step_count):
        step_unix_ms = now_unix_ms + step * _step * 1000
        step_minutes = current_minutes + step * _step / 60.0

        # Find the bounding stops for this moment in time.
        prev_stop: Schedule | None = None
        next_stop: Schedule | None = None

        for i, s in enumerate(schedules):
            dep_mins = schedule_utils.get_schedule_minutes(s, prefer_departure=True)
            if dep_mins is None:
                continue
            if dep_mins + delay > step_minutes:
                next_stop = s
                if i > 0:
                    prev_stop = schedules[i - 1]
                break
            prev_stop = s

        if prev_stop is None or next_stop is None:
            if step == 0:
                return None  # Train not active at this moment.
            break  # Service complete — stop adding intervals.

        if first_valid:
            prev_stop_name = (
                prev_stop.station.name if prev_stop.station else prev_stop.station_name
            )
            next_stop_name = (
                next_stop.station.name if next_stop.station else next_stop.station_name
            )
            first_valid = False

        prev_mins = schedule_utils.get_schedule_minutes(prev_stop, prefer_departure=True)
        next_mins = schedule_utils.get_schedule_minutes(next_stop, prefer_departure=False)
        if prev_mins is None or next_mins is None:
            break

        prev_mins += delay
        next_mins += delay
        segment_duration = next_mins - prev_mins
        progress = (
            1.0
            if segment_duration <= 0
            else max(0.0, min(1.0, (step_minutes - prev_mins) / segment_duration))
        )

        segment_length_km: float | None = None
        overall_progress = progress

        active_segment = None
        if route_segments:
            active_segment = _find_initial_route_segment(
                schedules,
                route_segments,
                step_minutes,
                delay,
            )

        if active_segment and active_segment.get("coords") and len(active_segment["coords"]) >= 2:
            segment_coords = active_segment["coords"]
            lon, lat = geo_utils.interpolate_position(segment_coords, progress)
            head_frac = min(1.0, progress + 0.01)
            nlon, nlat = geo_utils.interpolate_position(segment_coords, head_frac)
            rotation = geo_utils.great_circle_bearing((lon, lat), (nlon, nlat))
            segment_length_km = float(active_segment.get("length_km") or 0.0)
            if route_distance_km and route_distance_km > 0:
                overall_progress = (
                    float(active_segment.get("start_km") or 0.0)
                    + segment_length_km * progress
                ) / route_distance_km
            else:
                overall_progress = progress
            geom_frac = max(0.0, min(1.0, overall_progress))
        elif route_coords and len(route_coords) >= 2:
            total_stops = len(schedules)
            prev_index = next(
                (idx for idx, s in enumerate(schedules) if s is prev_stop), 0
            )
            next_index = next(
                (idx for idx, s in enumerate(schedules) if s is next_stop),
                prev_index + 1,
            )
            start_p = schedule_utils.get_stop_progress(
                prev_stop, prev_index, total_stops, route_distance_km
            )
            end_p = schedule_utils.get_stop_progress(
                next_stop, next_index, total_stops, route_distance_km
            )
            geom_frac = start_p + (end_p - start_p) * progress
            overall_progress = geom_frac

            lon, lat = geo_utils.interpolate_position(route_coords, geom_frac)
            head_frac = min(1.0, max(geom_frac + 0.005, end_p))
            nlon, nlat = geo_utils.interpolate_position(route_coords, head_frac)
            rotation = geo_utils.great_circle_bearing((lon, lat), (nlon, nlat))

            if segment_duration > 0:
                dist_km = geo_utils.segment_distance_km(route_coords, start_p, end_p)
                if dist_km > 0:
                    segment_length_km = dist_km
        else:
            # Fallback: straight-line interpolation between station points.
            if prev_stop.station is None or next_stop.station is None:
                break
            prev_pt = to_shape(prev_stop.station.location)
            next_pt = to_shape(next_stop.station.location)
            lon = float(prev_pt.x) + (float(next_pt.x) - float(prev_pt.x)) * progress
            lat = float(prev_pt.y) + (float(next_pt.y) - float(prev_pt.y)) * progress
            rotation = geo_utils.great_circle_bearing(
                (float(prev_pt.x), float(prev_pt.y)),
                (float(next_pt.x), float(next_pt.y)),
            )
            geom_frac = len(fallback_coords) / max(step_count - 1, 1)
            fallback_coords.append([lon, lat])

        if step == 0:
            if segment_length_km is not None and segment_duration > 0:
                current_speed = round(segment_length_km / (segment_duration / 60), 1)
            current_status = "at_station" if progress < 0.05 or progress > 0.95 else "moving"
            current_eta_next_station = _minutes_to_hhmm(next_mins)
            current_progress_pct = round(progress * 100, 1)
            current_route_progress = round(max(0.0, min(1.0, overall_progress)), 6)
            current_segment_progress = round(progress, 6)

        bounds_min_lon = min(bounds_min_lon, lon)
        bounds_min_lat = min(bounds_min_lat, lat)
        bounds_max_lon = max(bounds_max_lon, lon)
        bounds_max_lat = max(bounds_max_lat, lat)

        time_intervals.append([step_unix_ms, round(geom_frac, 6), round(rotation, 1)])

    if not time_intervals:
        return None

    # Build GeoJSON geometry.
    if route_coords and len(route_coords) >= 2:
        geometry: dict[str, Any] = {"type": "LineString", "coordinates": route_coords}
    elif len(fallback_coords) >= 2:
        geometry = {"type": "LineString", "coordinates": fallback_coords}
    elif len(fallback_coords) == 1:
        geometry = {"type": "Point", "coordinates": fallback_coords[0]}
    else:
        return None

    color = _TRAIN_TYPE_COLORS.get(train.train_type or "", "#2196F3")
    first_frac = time_intervals[0][1]
    last_frac = time_intervals[-1][1]
    state = "BOARDING" if first_frac < 0.05 or last_frac > 0.95 else "DRIVING"
    initial_segment = _find_initial_route_segment(
        schedules,
        route_segments,
        current_minutes,
        delay,
    )

    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            # Core identification
            "train_id": train.id,
            "train_number": train.train_number,
            "train_type": train.train_type,
            "route_id": train.current_route_id,
            "route_identifier": train.train_number,
            # Temporal position data (geops TrackerTrajectory pattern)
            # time_intervals: [[unix_ms, geom_frac, rotation_deg], ...]
            "time_intervals": time_intervals,
            "bounds": [
                bounds_min_lon,
                bounds_min_lat,
                bounds_max_lon,
                bounds_max_lat,
            ],
            # Context
            "next_station": next_stop_name,
            "prev_station": prev_stop_name,
            "speed": current_speed,
            "status": current_status,
            "eta_next_station": current_eta_next_station,
            "progress": current_progress_pct,
            "route_progress": current_route_progress,
            "segment_progress": current_segment_progress,
            "current_edge_id": (
                int(initial_segment["edge_id"]) if initial_segment is not None else None
            ),
            "graph_from_station_id": (
                int(initial_segment["from_station_id"])
                if initial_segment is not None
                else None
            ),
            "graph_to_station_id": (
                int(initial_segment["to_station_id"])
                if initial_segment is not None
                else None
            ),
            "route_distance_km": route_distance_km,
            # Delay — both units for compatibility
            "delay_minutes": delay,  # legacy / display
            "delay": delay * 60,  # geops standard (seconds)
            # Line info — extended for geops compatibility
            "line": {
                "name": train.train_number,
                "color": color,
                "id": train.id,
                "stroke": color,
                "text_color": "#FFFFFF",
                "tags": ["rail"],
            },
            # geops TrackerTrajectoryProperties required fields
            "state": state,
            "type": "rail",
            "tenant": settings.position_tenant,
            "timestamp": now_unix_ms,
            "has_journey": True,
            "has_realtime": True,
            "has_realtime_journey": True,
            "gen_level": 0,
            "gen_range": [],
            "graph": "thailand_railway",
            "operator_provides_realtime_journey": "yes",
        },
    }


def build_stop_sequence(
    schedules: list[Schedule],
    *,
    delay: int,
    current_minutes: float,
) -> list[dict[str, Any]]:
    """Generate an ordered stop-sequence list for a train.

    Similar to the geops *StopSequence* channel — lets the frontend display
    an upcoming-stops panel without extra queries.

    Args:
        schedules: Schedule entries ordered by sequence.
        delay: Current delay in minutes (sourced from TTS).
        current_minutes: Current Bangkok time as fractional minutes since
            midnight (injected by the caller for testability).

    Returns:
        List of stop dicts, each with state ``PASSED`` / ``BOARDING`` / ``PENDING``.
    """
    result: list[dict[str, Any]] = []
    for s in schedules:
        dep_mins = schedule_utils.get_schedule_minutes(s, prefer_departure=True)
        arr_mins = schedule_utils.get_schedule_minutes(s, prefer_departure=False)
        stop_mins = dep_mins if dep_mins is not None else arr_mins
        if stop_mins is None:
            continue
        delayed_stop = stop_mins + delay
        if delayed_stop + 1 < current_minutes:
            state = "PASSED"
        elif abs(delayed_stop - current_minutes) <= 2:
            state = "BOARDING"
        else:
            state = "PENDING"
        result.append(
            {
                "station_name": (
                    (s.station.name if s.station else None) or s.station_name or ""
                ),
                "sequence": s.sequence,
                "aimed_departure_minutes": (
                    dep_mins % (24 * 60) if dep_mins is not None else None
                ),
                "departure_day_offset": s.departure_day_offset,
                "delay_minutes": delay,
                "state": state,
            }
        )
    return result
