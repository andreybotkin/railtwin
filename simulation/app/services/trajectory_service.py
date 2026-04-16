from __future__ import annotations

import time as _time
from typing import Any, cast

from geoalchemy2.shape import to_shape
from shapely.geometry import Point

from app.core.config import settings
from app.domain.trajectory import ConsistSpec, Trajectory, TrajectoryFrame, TrajectoryMeta
from app.models.database.models import Schedule, Train
from app.services import geo_utils, schedule_utils

__all__ = [
    "attach_consist",
    "build_stop_sequence",
    "build_train_trajectory",
    "compute_frame",
    "interleave_anchors",
]

_TRAIN_TYPE_COLORS: dict[str, str] = {
    "special_express": "#E53935",
    "rapid": "#1E88E5",
    "ordinary": "#43A047",
}


def _station_name(schedule: Schedule | None) -> str | None:
    if schedule is None:
        return None
    return (schedule.station.name if schedule.station else None) or schedule.station_name


def _stop_progress(
    schedules: list[Schedule],
    stop: Schedule,
    route_distance_km: float | None,
) -> float:
    idx = next((i for i, item in enumerate(schedules) if item is stop), 0)
    return max(
        0.0,
        min(1.0, schedule_utils.get_stop_progress(stop, idx, len(schedules), route_distance_km)),
    )


def compute_frame(
    *,
    t_ms: int,
    step_minutes: float,
    schedules: list[Schedule],
    route_coords: list[list[float]] | None,
    route_distance_km: float | None,
    delay: int,
) -> tuple[TrajectoryFrame | None, Schedule | None, Schedule | None]:
    prev_stop: Schedule | None = None
    next_stop: Schedule | None = None

    for i, schedule in enumerate(schedules):
        dep_mins = schedule_utils.get_schedule_minutes(schedule, prefer_departure=True)
        if dep_mins is None:
            continue
        if dep_mins + delay > step_minutes:
            next_stop = schedule
            if i > 0:
                prev_stop = schedules[i - 1]
            break
        prev_stop = schedule

    if prev_stop is None or next_stop is None:
        return None, prev_stop, next_stop

    prev_mins = schedule_utils.get_schedule_minutes(prev_stop, prefer_departure=True)
    next_mins = schedule_utils.get_schedule_minutes(next_stop, prefer_departure=False)
    if prev_mins is None or next_mins is None:
        return None, prev_stop, next_stop

    prev_mins += delay
    next_mins += delay
    duration = max(1e-6, next_mins - prev_mins)
    segment_progress = max(0.0, min(1.0, (step_minutes - prev_mins) / duration))

    start_frac = _stop_progress(schedules, prev_stop, route_distance_km)
    end_frac = _stop_progress(schedules, next_stop, route_distance_km)

    dwell = (
        next_stop.arrival_time is not None
        and next_stop.departure_time is not None
        and schedule_utils.time_to_minutes(next_stop.arrival_time) + delay <= step_minutes
        <= schedule_utils.time_to_minutes(next_stop.departure_time) + delay
    )
    geom_fraction = start_frac + (end_frac - start_frac) * (0.0 if dwell else segment_progress)

    if route_coords and len(route_coords) >= 2:
        lon, lat = geo_utils.interpolate_position(route_coords, geom_fraction)
        head_lon, head_lat = geo_utils.interpolate_position(route_coords, min(1.0, geom_fraction + 0.0025))
    else:
        if prev_stop.station is None or next_stop.station is None:
            return None, prev_stop, next_stop
        prev_pt = cast(Point, to_shape(prev_stop.station.location))
        next_pt = cast(Point, to_shape(next_stop.station.location))
        lon = float(prev_pt.x) + (float(next_pt.x) - float(prev_pt.x)) * segment_progress
        lat = float(prev_pt.y) + (float(next_pt.y) - float(prev_pt.y)) * segment_progress
        head_lon, head_lat = float(next_pt.x), float(next_pt.y)

    rotation = geo_utils.great_circle_bearing((lon, lat), (head_lon, head_lat))
    seg_km = geo_utils.segment_distance_km(route_coords or [[lon, lat], [head_lon, head_lat]], start_frac, end_frac)
    speed_kmh = 0.0 if dwell else round(max(0.0, seg_km / (duration / 60.0)), 1)

    status = "dwelling" if dwell else "moving"
    return (
        TrajectoryFrame(
            t_ms=t_ms,
            lon=round(lon, 6),
            lat=round(lat, 6),
            geom_fraction=round(geom_fraction, 6),
            rotation_deg=round(rotation, 1),
            speed_kmh=speed_kmh,
            status=status,
        ),
        prev_stop,
        next_stop,
    )


def interleave_anchors(frames: list[TrajectoryFrame], anchors: list[dict[str, Any]]) -> list[TrajectoryFrame]:
    by_t = {frame.t_ms: frame for frame in frames}
    for anchor in anchors:
        t_ms = int(anchor["t_ms"])
        by_t[t_ms] = TrajectoryFrame.model_validate(anchor)
    return [by_t[t] for t in sorted(by_t.keys())]


def attach_consist(train_type: str | None) -> ConsistSpec:
    return ConsistSpec.from_train_type(train_type)


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
    del route_segments
    if not schedules or len(schedules) < 2:
        return None

    generated_at_ms = int(_time.time() * 1000)
    lookahead = settings.trajectory_lookahead_seconds
    step_s = settings.trajectory_step_seconds

    frames: list[TrajectoryFrame] = []
    prev_stop_name: str | None = None
    next_stop_name: str | None = None

    for step in range(lookahead // step_s + 1):
        t_ms = generated_at_ms + step * step_s * 1000
        step_minutes = current_minutes + step * step_s / 60.0
        frame, prev_stop, next_stop = compute_frame(
            t_ms=t_ms,
            step_minutes=step_minutes,
            schedules=schedules,
            route_coords=route_coords,
            route_distance_km=route_distance_km,
            delay=delay,
        )
        if frame is None:
            if step == 0:
                return None
            break
        if step == 0:
            prev_stop_name = _station_name(prev_stop)
            next_stop_name = _station_name(next_stop)
        frames.append(frame)

    if not frames:
        return None

    last = frames[-1]
    last_stop_minutes = schedule_utils.get_schedule_minutes(
        schedules[-1], prefer_departure=False
    )
    reaches_terminal = False
    if last_stop_minutes is not None:
        reaches_terminal = (current_minutes + lookahead / 60.0) >= (
            last_stop_minutes + delay
        )
    if last.geom_fraction >= 0.999 or reaches_terminal:
        last.geom_fraction = 1.0
        last.status = "arrived"

    consist = attach_consist(train.train_type)
    route_length_m = (route_distance_km or 0.0) * 1000.0
    meta = TrajectoryMeta(
        train_id=train.id,
        train_number=train.train_number,
        train_type=train.train_type,
        color=_TRAIN_TYPE_COLORS.get(train.train_type or "", "#2196F3"),
        from_station=_station_name(schedules[0]),
        to_station=_station_name(schedules[-1]),
        next_station=next_stop_name,
        prev_station=prev_stop_name,
        eta_next_ms=frames[0].t_ms,
        delay_minutes=delay,
        route_progress_pct=round(frames[0].geom_fraction * 100, 1),
    )

    trajectory = Trajectory(
        train_id=train.id,
        generated_at_ms=generated_at_ms,
        valid_until_ms=generated_at_ms + lookahead * 1000,
        route_coords=route_coords or [[f.lon, f.lat] for f in frames],
        route_length_m=route_length_m,
        frames=frames,
        anchors=[],
        consist=consist,
        meta=meta,
    )
    return trajectory.model_dump(mode="json")


def build_stop_sequence(
    schedules: list[Schedule],
    *,
    delay: int,
    current_minutes: float,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for s in schedules:
        arr_mins, dep_mins = schedule_utils.get_arrival_departure_minutes(s)
        stop_mins = dep_mins if dep_mins is not None else arr_mins
        if stop_mins is None:
            continue

        adjusted_arrival = arr_mins + delay if arr_mins is not None else None
        adjusted_departure = dep_mins + delay if dep_mins is not None else None
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
                "station_name": (_station_name(s) or ""),
                "sequence": s.sequence,
                "aimed_departure_minutes": dep_mins % (24 * 60) if dep_mins is not None else None,
                "departure_day_offset": s.departure_day_offset,
                "delay_minutes": delay,
                "state": state,
            }
        )
    return result
