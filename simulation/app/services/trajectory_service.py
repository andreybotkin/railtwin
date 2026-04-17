"""Authoritative trajectory builder.

Given a train, its schedule and the underlying track geometry, this module
produces a :class:`app.domain.trajectory.Trajectory` covering the next
``settings.trajectory_lookahead_seconds`` of motion, sampled every
``settings.trajectory_step_seconds``.

Pure functions — no database, no Redis, no clock access outside of ``_now_ms``
(which is trivially injectable through the ``now_unix_ms`` keyword for tests).
"""

from __future__ import annotations

import time as _time
from typing import Any, Iterable, cast

from geoalchemy2.shape import to_shape
from shapely.geometry import Point

from app.core.config import settings
from app.domain.trajectory import (
    ConsistSpec,
    Trajectory,
    TrajectoryAnchor,
    TrajectoryFrame,
    TrajectoryMeta,
    resolve_consist,
)
from app.models.database.models import Schedule, Train
from app.services import geo_utils, schedule_utils

__all__ = [
    "build_trajectory",
    "build_stop_sequence",
    "train_type_color",
]

# Colour palette mirrors ``frontend/src/lib/utils.ts`` — keep in sync.
_TRAIN_TYPE_COLORS: dict[str, str] = {
    "special_express": "#E53935",
    "express": "#EF6C00",
    "rapid": "#1E88E5",
    "ordinary": "#43A047",
    "commuter": "#8E24AA",
}


def train_type_color(train_type: str | None) -> str:
    if not train_type:
        return "#2196F3"
    return _TRAIN_TYPE_COLORS.get(train_type.strip().lower(), "#2196F3")


# --------------------------------------------------------------------------- #
# Schedule helpers                                                             #
# --------------------------------------------------------------------------- #

def _station_name(schedule: Schedule) -> str:
    name = schedule.station.name if schedule.station else None
    return name or schedule.station_name or ""


def _is_dwell_window(
    schedule: Schedule,
    *,
    current_minutes: float,
    delay: int,
) -> bool:
    arrival, departure = schedule_utils.get_arrival_departure_minutes(schedule)
    if arrival is None or departure is None or departure <= arrival:
        return False
    return (arrival + delay) <= current_minutes <= (departure + delay)


def _absolute_event_minutes(schedule: Schedule, *, event: str) -> int | None:
    if event == "arrival":
        if schedule.arrival_time is None:
            return None
        return (
            schedule_utils.time_to_minutes(schedule.arrival_time)
            + int(schedule.arrival_day_offset) * 24 * 60
        )
    if schedule.departure_time is None:
        return None
    return (
        schedule_utils.time_to_minutes(schedule.departure_time)
        + int(schedule.departure_day_offset) * 24 * 60
    )


# --------------------------------------------------------------------------- #
# Geometry helpers                                                             #
# --------------------------------------------------------------------------- #

def _polyline_length_m(coords: list[list[float]]) -> float:
    total = 0.0
    for i in range(len(coords) - 1):
        total += geo_utils.haversine_km(
            coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1]
        )
    return total * 1000.0


def _cumulative_length_m(coords: list[list[float]]) -> list[float]:
    cum = [0.0]
    running = 0.0
    for i in range(len(coords) - 1):
        running += geo_utils.haversine_km(
            coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1]
        ) * 1000.0
        cum.append(running)
    return cum


def _bearing_at_fraction(coords: list[list[float]], fraction: float) -> float:
    if len(coords) < 2:
        return 0.0
    anchor = max(0.0, min(1.0, fraction))
    delta = 0.002
    if anchor >= 1.0 - delta:
        start = anchor - delta
        end = anchor
    else:
        start = anchor
        end = anchor + delta
    lon_a, lat_a = geo_utils.interpolate_position(coords, start)
    lon_b, lat_b = geo_utils.interpolate_position(coords, end)
    return geo_utils.great_circle_bearing((lon_a, lat_a), (lon_b, lat_b))


def _stop_fractions(
    schedules: list[Schedule],
    route_distance_km: float | None,
) -> list[float]:
    total_stops = len(schedules)
    return [
        max(
            0.0,
            min(
                1.0,
                schedule_utils.get_stop_progress(
                    schedule,
                    index,
                    total_stops,
                    route_distance_km,
                ),
            ),
        )
        for index, schedule in enumerate(schedules)
    ]


# --------------------------------------------------------------------------- #
# Core builder                                                                 #
# --------------------------------------------------------------------------- #

def _find_bounding_stops(
    schedules: list[Schedule],
    *,
    step_minutes: float,
    delay: int,
) -> tuple[int | None, int | None]:
    """Return ``(prev_index, next_index)`` for the segment enclosing ``step_minutes``."""

    prev_index: int | None = None
    next_index: int | None = None
    for i, schedule in enumerate(schedules):
        dep_mins = schedule_utils.get_schedule_minutes(schedule, prefer_departure=True)
        if dep_mins is None:
            continue
        if dep_mins + delay > step_minutes:
            next_index = i
            if i > 0:
                prev_index = i - 1
            break
        prev_index = i
    return prev_index, next_index


def _compute_frame(
    *,
    schedules: list[Schedule],
    stop_fractions: list[float],
    route_coords: list[list[float]],
    route_length_m: float,
    step_minutes: float,
    step_unix_ms: int,
    delay: int,
) -> TrajectoryFrame | None:
    """Return a single :class:`TrajectoryFrame` for ``step_minutes`` or ``None``."""

    prev_index, next_index = _find_bounding_stops(
        schedules, step_minutes=step_minutes, delay=delay
    )
    if prev_index is None or next_index is None:
        return None

    prev_stop = schedules[prev_index]
    next_stop = schedules[next_index]

    prev_mins = schedule_utils.get_schedule_minutes(prev_stop, prefer_departure=True)
    next_mins = schedule_utils.get_schedule_minutes(next_stop, prefer_departure=False)
    if prev_mins is None or next_mins is None:
        return None

    prev_mins += delay
    next_mins += delay
    duration = next_mins - prev_mins
    progress = (
        1.0
        if duration <= 0
        else max(0.0, min(1.0, (step_minutes - prev_mins) / duration))
    )

    start_frac = stop_fractions[prev_index]
    end_frac = stop_fractions[next_index]
    geom_fraction = start_frac + (end_frac - start_frac) * progress
    geom_fraction = max(0.0, min(1.0, geom_fraction))

    dwelling = _is_dwell_window(next_stop, current_minutes=step_minutes, delay=delay)

    if dwelling:
        geom_fraction = end_frac
        speed_kmh = 0.0
        status = "dwelling"
    else:
        if duration > 0:
            segment_length_m = (
                geo_utils.segment_distance_km(route_coords, start_frac, end_frac)
                * 1000.0
            )
            speed_kmh = (
                (segment_length_m / 1000.0) / (duration / 60.0)
                if segment_length_m > 0
                else 0.0
            )
        else:
            speed_kmh = 0.0
        status = "moving"

    lon, lat = geo_utils.interpolate_position(route_coords, geom_fraction)
    rotation = _bearing_at_fraction(route_coords, geom_fraction)

    return TrajectoryFrame(
        t_ms=step_unix_ms,
        lon=round(lon, 6),
        lat=round(lat, 6),
        geom_fraction=round(geom_fraction, 6),
        head_distance_m=round(geom_fraction * route_length_m, 3),
        rotation_deg=round(rotation % 360.0, 2),
        # Thai rolling stock tops out around 160 km/h, so clamping at 200 km/h
        # leaves a small safety margin while rejecting the ~400 km/h values that
        # used to surface when a schedule's timing was too tight for the route.
        speed_kmh=round(max(0.0, min(200.0, speed_kmh)), 2),
        status=status,
    )


def _build_anchors(
    *,
    schedules: list[Schedule],
    stop_fractions: list[float],
    current_minutes: float,
    delay: int,
    now_unix_ms: int,
    lookahead_seconds: int,
) -> list[TrajectoryAnchor]:
    anchors: list[TrajectoryAnchor] = []
    for index, schedule in enumerate(schedules):
        frac = stop_fractions[index]
        for event in ("arrival", "departure"):
            scheduled = _absolute_event_minutes(schedule, event=event)
            if scheduled is None:
                continue
            adjusted = scheduled + delay
            offset_seconds = (adjusted - current_minutes) * 60
            if offset_seconds < 0 or offset_seconds > lookahead_seconds:
                continue
            anchors.append(
                TrajectoryAnchor(
                    t_ms=now_unix_ms + int(round(offset_seconds * 1000)),
                    station_id=schedule.station.id if schedule.station else None,
                    station_name=_station_name(schedule),
                    event=event,
                    geom_fraction=round(frac, 6),
                    scheduled_minutes=int(scheduled),
                    adjusted_minutes=int(adjusted),
                    delay_minutes=delay,
                )
            )
    anchors.sort(key=lambda a: a.t_ms)
    return anchors


def _compute_bounds(
    frames: Iterable[TrajectoryFrame],
) -> tuple[float, float, float, float]:
    lons = [f.lon for f in frames]
    lats = [f.lat for f in frames]
    return (min(lons), min(lats), max(lons), max(lats))


def _fallback_route_from_stations(
    schedules: list[Schedule],
) -> tuple[list[list[float]], float] | None:
    coords: list[list[float]] = []
    for schedule in schedules:
        if schedule.station is None:
            return None
        point = cast(Point, to_shape(schedule.station.location))
        coords.append([float(point.x), float(point.y)])
    if len(coords) < 2:
        return None
    return coords, _polyline_length_m(coords)


def build_trajectory(
    train: Train,
    schedules: list[Schedule],
    route_coords: list[list[float]] | None,
    route_distance_km: float | None = None,
    *,
    delay: int,
    current_minutes: float,
    now_unix_ms: int | None = None,
    topology_version: str | None = None,
    route_segments: list[dict[str, Any]] | None = None,
) -> Trajectory | None:
    """Return a :class:`Trajectory` for ``train`` at ``current_minutes`` or ``None``.

    The function performs no I/O.  Callers provide pre-fetched domain objects
    and the server clock in ``now_unix_ms`` (defaults to ``time.time()``).
    """

    if not schedules or len(schedules) < 2:
        return None

    # Ensure a usable route polyline.
    polyline: list[list[float]]
    if route_coords and len(route_coords) >= 2:
        polyline = [[float(p[0]), float(p[1])] for p in route_coords]
    else:
        fallback = _fallback_route_from_stations(schedules)
        if fallback is None:
            return None
        polyline, _ = fallback

    route_length_m = (
        float(route_distance_km) * 1000.0
        if route_distance_km and route_distance_km > 0
        else _polyline_length_m(polyline)
    )
    if route_length_m <= 0:
        return None

    effective_distance_km = route_length_m / 1000.0
    stop_fractions = _stop_fractions(schedules, effective_distance_km)

    lookahead = settings.trajectory_lookahead_seconds
    step = settings.trajectory_step_seconds
    now_ms = now_unix_ms if now_unix_ms is not None else int(_time.time() * 1000)

    frames: list[TrajectoryFrame] = []
    step_count = lookahead // step + 1
    for i in range(step_count):
        step_minutes = current_minutes + i * step / 60.0
        step_unix_ms = now_ms + i * step * 1000
        frame = _compute_frame(
            schedules=schedules,
            stop_fractions=stop_fractions,
            route_coords=polyline,
            route_length_m=route_length_m,
            step_minutes=step_minutes,
            step_unix_ms=step_unix_ms,
            delay=delay,
        )
        if frame is None:
            if i == 0:
                return None
            break
        frames.append(frame)

    if not frames:
        return None

    anchors = _build_anchors(
        schedules=schedules,
        stop_fractions=stop_fractions,
        current_minutes=current_minutes,
        delay=delay,
        now_unix_ms=now_ms,
        lookahead_seconds=lookahead,
    )

    # Head frame drives the meta.
    head = frames[0]
    prev_index, next_index = _find_bounding_stops(
        schedules, step_minutes=current_minutes, delay=delay
    )
    prev_name = (
        _station_name(schedules[prev_index])
        if prev_index is not None
        else None
    )
    next_name = (
        _station_name(schedules[next_index])
        if next_index is not None
        else None
    )

    # ETA for next station = first matching anchor or next_stop adjusted minutes.
    eta_next_ms: int | None = None
    for anchor in anchors:
        if (
            next_index is not None
            and anchor.event == "arrival"
            and anchor.station_name == next_name
        ):
            eta_next_ms = anchor.t_ms
            break
    if eta_next_ms is None and next_index is not None:
        next_mins = schedule_utils.get_schedule_minutes(
            schedules[next_index], prefer_departure=False
        )
        if next_mins is not None:
            offset_seconds = (next_mins + delay - current_minutes) * 60
            if offset_seconds >= 0:
                eta_next_ms = now_ms + int(round(offset_seconds * 1000))

    # Segment progress expressed per-current-segment (0..1 inside active leg).
    # Using |end - start| covers the "backwards" case where the polyline was
    # stored in the opposite direction of travel: both numerator and
    # denominator flip sign so the ratio still lands between 0 and 1.
    if prev_index is not None and next_index is not None:
        start_frac = stop_fractions[prev_index]
        end_frac = stop_fractions[next_index]
        if abs(end_frac - start_frac) > 1e-9:
            segment_progress = max(
                0.0,
                min(
                    1.0,
                    (head.geom_fraction - start_frac) / (end_frac - start_frac),
                ),
            )
        else:
            segment_progress = 1.0
    else:
        segment_progress = 0.0

    origin_name = _station_name(schedules[0]) if schedules else None
    destination_name = _station_name(schedules[-1]) if schedules else None

    current_edge_id: int | None = None
    graph_from_station_id: int | None = None
    graph_to_station_id: int | None = None
    if route_segments:
        target_km = head.head_distance_m / 1000.0
        for segment in route_segments:
            start_km = float(segment.get("start_km") or 0.0)
            end_km = float(segment.get("end_km") or start_km)
            if start_km - 1e-6 <= target_km <= end_km + 1e-6:
                current_edge_id = int(segment.get("edge_id") or 0) or None
                graph_from_station_id = segment.get("from_station_id")
                graph_to_station_id = segment.get("to_station_id")
                graph_from_station_id = (
                    int(graph_from_station_id)
                    if graph_from_station_id is not None
                    else None
                )
                graph_to_station_id = (
                    int(graph_to_station_id)
                    if graph_to_station_id is not None
                    else None
                )
                break

    meta = TrajectoryMeta(
        train_id=int(train.id),
        train_number=train.train_number,
        train_type=train.train_type or "",
        train_name=train.name,
        color=train_type_color(train.train_type),
        operator=train.operator or "State Railway of Thailand",
        origin_station=origin_name,
        destination_station=destination_name,
        prev_station=prev_name,
        next_station=next_name,
        eta_next_ms=eta_next_ms,
        delay_minutes=delay,
        route_id=train.current_route_id,
        route_progress_pct=round(head.geom_fraction * 100.0, 2),
        segment_progress_pct=round(segment_progress * 100.0, 2),
        current_edge_id=current_edge_id,
        graph_from_station_id=graph_from_station_id,
        graph_to_station_id=graph_to_station_id,
        topology_version=topology_version,
    )

    consist: ConsistSpec = resolve_consist(train.train_type)
    bounds = _compute_bounds(frames)
    valid_until_ms = frames[-1].t_ms

    return Trajectory(
        train_id=int(train.id),
        generated_at_ms=now_ms,
        valid_until_ms=valid_until_ms,
        route_coords=[(round(p[0], 6), round(p[1], 6)) for p in polyline],
        route_length_m=round(route_length_m, 3),
        frames=frames,
        anchors=anchors,
        consist=consist,
        meta=meta,
        bounds=bounds,
    )


# --------------------------------------------------------------------------- #
# Stop sequence                                                                #
# --------------------------------------------------------------------------- #

def build_stop_sequence(
    schedules: list[Schedule],
    *,
    delay: int,
    current_minutes: float,
) -> list[dict[str, Any]]:
    """Return the list of upcoming stops with a ``state`` for each."""

    result: list[dict[str, Any]] = []
    for schedule in schedules:
        arrival, departure = schedule_utils.get_arrival_departure_minutes(schedule)
        stop_mins = departure if departure is not None else arrival
        if stop_mins is None:
            continue

        adjusted_arrival = arrival + delay if arrival is not None else None
        adjusted_departure = departure + delay if departure is not None else None
        adjusted_stop = stop_mins + delay
        adjusted_reference = (
            adjusted_departure if adjusted_departure is not None else adjusted_arrival
        )

        if (
            adjusted_arrival is not None
            and adjusted_departure is not None
            and adjusted_departure > adjusted_arrival
            and adjusted_arrival <= current_minutes <= adjusted_departure
        ):
            state = "BOARDING"
        elif adjusted_reference is not None and adjusted_reference + 1 < current_minutes:
            state = "PASSED"
        elif abs(adjusted_stop - current_minutes) <= 2:
            state = "BOARDING"
        else:
            state = "PENDING"

        result.append(
            {
                "station_name": _station_name(schedule),
                "sequence": schedule.sequence,
                "aimed_arrival_minutes": (
                    arrival % (24 * 60) if arrival is not None else None
                ),
                "aimed_departure_minutes": (
                    departure % (24 * 60) if departure is not None else None
                ),
                "arrival_day_offset": schedule.arrival_day_offset,
                "departure_day_offset": schedule.departure_day_offset,
                "delay_minutes": delay,
                "state": state,
            }
        )
    return result
