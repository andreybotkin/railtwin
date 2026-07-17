"""Runtime movement plan resolver.

Converts a precomputed :class:`~app.domain.movement_plan.PlannedTrainRun`
into a :class:`~app.domain.trajectory.Trajectory` without any I/O.

Design principles
-----------------
* **Pure function** — no database, no Redis, no clock access outside of the
  ``now_unix_ms`` keyword (which tests can inject).
* **Returns None on any error** — the caller falls back to
  ``build_trajectory()`` silently.
* **Delay handling** — delays shift the *effective time* backwards relative to
  the planned schedule: ``effective_minutes = current_minutes - delay_minutes``.
  A delayed train is "earlier" against its plan even though its wall-clock time
  is later.
* **Reverse direction** — supported naturally: ``end_geom_fraction`` may be
  less than ``start_geom_fraction``.
* **Overnight trains** — handled through ``absolute_start/end_minutes`` which
  span midnight by adding ``day_offset * 1440``.
* **Meta fields** — station names and ETA are derived from *schedules* (the
  same objects already loaded in the simulation hot path) so the
  :class:`~app.domain.trajectory.TrajectoryMeta` is identical to the one
  produced by ``build_trajectory()``.
"""

from __future__ import annotations

import time as _time
from collections.abc import Iterable
from typing import Any

from app.core.config import settings as _settings
from app.core.logging import get_logger
from app.domain.movement_plan import PlannedTrainRun
from app.domain.trajectory import (
    Trajectory,
    TrajectoryAnchor,
    TrajectoryFrame,
    TrajectoryMeta,
    TrajectoryStatus,
    resolve_consist,
)
from app.services import geo_utils
from app.services.trajectory_service import (
    _bearing_at_fraction,  # noqa: PLC2701 — shared internal geometry helper
    _station_name,
    _station_name_th,
    train_type_color,
)

logger = get_logger(__name__)

__all__ = ["resolve_trajectory"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _effective_minutes(current_minutes: float, delay_minutes: int) -> float:
    """Shift current wall-clock minutes to the plan timeline.

    Adding a delay means the train departs *later* in wall-clock time, so to
    find the matching planned segment we shift the query *earlier*:
    ``effective = current - delay``.
    """
    return current_minutes - delay_minutes


def _frame_status(segment_type: str) -> TrajectoryStatus:
    return "dwelling" if segment_type == "dwell" else "moving"


def _compute_geom_fraction(
    segment: Any,
    effective: float,
) -> float | None:
    """Return the geom_fraction for *effective* within *segment*.

    Returns ``None`` when either bounding fraction is missing — the caller
    must fall back to ``build_trajectory()``.
    """
    start_frac = (
        float(segment.start_geom_fraction)
        if segment.start_geom_fraction is not None
        else None
    )
    end_frac = (
        float(segment.end_geom_fraction)
        if segment.end_geom_fraction is not None
        else None
    )
    if start_frac is None or end_frac is None:
        return None

    abs_start = float(segment.absolute_start_minutes)
    abs_end = float(segment.absolute_end_minutes)

    if segment.segment_type == "dwell":
        # Position is pinned to the arrival (start) fraction for dwell.
        return max(0.0, min(1.0, start_frac))

    duration = abs_end - abs_start
    if duration <= 0:
        return max(0.0, min(1.0, end_frac))

    progress = max(0.0, min(1.0, (effective - abs_start) / duration))
    fraction = start_frac + (end_frac - start_frac) * progress
    # Clamp to the range [min, max] of the two fractions (handles reverse direction).
    lo = min(start_frac, end_frac)
    hi = max(start_frac, end_frac)
    return max(lo, min(hi, fraction))


def _speed_kmh(segment: Any, route_length_m: float) -> float:
    """Derive speed for a move segment."""
    if segment.segment_type == "dwell":
        return 0.0
    if segment.planned_speed_kmh is not None:
        return max(0.0, min(400.0, float(segment.planned_speed_kmh)))
    # Fall back to distance/time if available.
    start_dist = (
        float(segment.start_distance_m)
        if segment.start_distance_m is not None
        else None
    )
    end_dist = (
        float(segment.end_distance_m) if segment.end_distance_m is not None else None
    )
    abs_start = float(segment.absolute_start_minutes)
    abs_end = float(segment.absolute_end_minutes)
    duration_h = (abs_end - abs_start) / 60.0
    if duration_h > 0 and start_dist is not None and end_dist is not None:
        return max(0.0, min(400.0, abs(end_dist - start_dist) / 1000.0 / duration_h))
    return 0.0


# ---------------------------------------------------------------------------
# Anchors from movement plan segments
# ---------------------------------------------------------------------------


def _build_plan_anchors(
    *,
    segments: list[Any],
    schedules: list[Any],
    delay: int,
    current_minutes: float,
    now_unix_ms: int,
) -> list[TrajectoryAnchor]:
    """Build :class:`TrajectoryAnchor` from planned segment boundaries.

    Station names come from *schedules* matched by ``from_schedule_id`` /
    ``to_schedule_id``.  Segments without a name match are skipped.
    """
    # Build fast lookup: schedule.id → (station_name, station_id)
    sched_lookup: dict[int, tuple[str, int | None]] = {}
    for sched in schedules:
        sid = getattr(sched, "id", None)
        if sid is None:
            continue
        name = _station_name(sched)
        station_id = getattr(sched, "station_id", None)
        if station_id is not None:
            station_id = int(station_id)
        sched_lookup[int(sid)] = (name, station_id)

    anchors: list[TrajectoryAnchor] = []
    for seg in segments:
        abs_start = float(seg.absolute_start_minutes)
        abs_end = float(seg.absolute_end_minutes)

        frac_start = (
            float(seg.start_geom_fraction)
            if seg.start_geom_fraction is not None
            else None
        )
        frac_end = (
            float(seg.end_geom_fraction) if seg.end_geom_fraction is not None else None
        )
        if frac_start is None or frac_end is None:
            continue

        def _emit(
            abs_minutes: float,
            frac: float,
            event: str,
            schedule_id: int | None,
        ) -> None:
            if schedule_id is None:
                return
            entry = sched_lookup.get(int(schedule_id))
            if entry is None:
                return
            station_name, station_id = entry
            if not station_name:
                return
            adjusted = abs_minutes + delay
            offset_s = (adjusted - current_minutes) * 60
            anchors.append(
                TrajectoryAnchor(
                    t_ms=now_unix_ms + int(round(offset_s * 1000)),
                    station_id=station_id,
                    station_name=station_name,
                    event=event,  # type: ignore[arg-type]
                    geom_fraction=round(frac, 6),
                    scheduled_minutes=int(abs_minutes),
                    adjusted_minutes=int(adjusted),
                    delay_minutes=delay,
                )
            )

        if seg.segment_type == "dwell":
            _emit(abs_start, frac_start, "arrival", seg.from_schedule_id)
            _emit(abs_end, frac_end, "departure", seg.to_schedule_id)
        else:
            _emit(abs_start, frac_start, "departure", seg.from_schedule_id)
            _emit(abs_end, frac_end, "arrival", seg.to_schedule_id)

    anchors.sort(key=lambda a: a.t_ms)
    # Deduplicate by (station_name, event) keeping the first occurrence.
    seen: set[tuple[str, str]] = set()
    unique: list[TrajectoryAnchor] = []
    for anchor in anchors:
        key = (anchor.station_name, anchor.event)
        if key not in seen:
            seen.add(key)
            unique.append(anchor)
    return unique


# ---------------------------------------------------------------------------
# Meta helpers (mirror trajectory_service.py)
# ---------------------------------------------------------------------------


def _meta_station_names(
    schedules: list[Any],
    *,
    current_minutes: float,
    delay: int,
) -> tuple[str | None, str | None, str | None, str | None, str | None, str | None]:
    """Return (origin, dest, origin_th, dest_th, prev, next) station names."""
    from app.services.trajectory_service import _find_bounding_stops

    origin = _station_name(schedules[0]) if schedules else None
    dest = _station_name(schedules[-1]) if schedules else None
    origin_th = _station_name_th(schedules[0]) if schedules else None
    dest_th = _station_name_th(schedules[-1]) if schedules else None

    prev_idx, next_idx = _find_bounding_stops(
        schedules, step_minutes=current_minutes, delay=delay
    )
    prev_name = _station_name(schedules[prev_idx]) if prev_idx is not None else None
    next_name = _station_name(schedules[next_idx]) if next_idx is not None else None
    return origin, dest, origin_th, dest_th, prev_name, next_name


# ---------------------------------------------------------------------------
# Bounds helper
# ---------------------------------------------------------------------------


def _compute_bounds(
    frames: Iterable[TrajectoryFrame],
) -> tuple[float, float, float, float]:
    lons = [f.lon for f in frames]
    lats = [f.lat for f in frames]
    if not lons:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(lons), min(lats), max(lons), max(lats))


# ---------------------------------------------------------------------------
# Edge / segment progress helpers
# ---------------------------------------------------------------------------


def _resolve_edge_info(
    geom_fraction: float,
    route_length_m: float,
    route_segments: list[dict[str, Any]] | None,
) -> tuple[int | None, int | None, int | None]:
    """Return (edge_id, from_station_id, to_station_id) for *geom_fraction*."""
    if not route_segments:
        return None, None, None
    target_km = geom_fraction * route_length_m / 1000.0
    for segment in route_segments:
        start_km = float(segment.get("start_km") or 0.0)
        end_km = float(segment.get("end_km") or start_km)
        if start_km - 1e-6 <= target_km <= end_km + 1e-6:
            edge_id = int(segment.get("edge_id") or 0) or None
            from_id = segment.get("from_station_id")
            to_id = segment.get("to_station_id")
            return (
                edge_id,
                int(from_id) if from_id is not None else None,
                int(to_id) if to_id is not None else None,
            )
    return None, None, None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def resolve_trajectory(
    *,
    planned_run: PlannedTrainRun,
    route_coords: list[list[float]],
    route_length_m: float,
    current_minutes: float,
    delay_minutes: int,
    train: Any,
    schedules: list[Any],
    route_segments: list[dict[str, Any]] | None = None,
    topology_version: str | None = None,
    now_unix_ms: int | None = None,
    lookahead_seconds: int | None = None,
    step_seconds: int | None = None,
) -> Trajectory | None:
    """Return a :class:`Trajectory` from a precomputed movement plan, or ``None``.

    Returns ``None`` whenever the plan is unusable, geometry data is
    missing, or no active segment can be found — in all cases the caller
    should fall back to ``build_trajectory()``.

    Parameters
    ----------
    planned_run:
        The precomputed run (domain dataclass with ``.segments``).
    route_coords:
        ``[[lon, lat], ...]`` polyline for the route (already loaded from Redis).
    route_length_m:
        Pre-computed polyline length in metres.
    current_minutes:
        Wall-clock Bangkok time in absolute minutes (output of
        ``candidate_current_minutes``).
    delay_minutes:
        TTS delay in minutes.
    train:
        SimpleNamespace (or ORM instance) with ``id``, ``train_number``,
        ``train_type``, ``name``, ``operator``.
    schedules:
        Schedule entries in sequence order — used only for meta extraction
        (origin/destination/prev/next station names, ETA).
    route_segments:
        Optional edge-aligned segments for ``current_edge_id`` lookup.
    topology_version:
        Topology version string for ``TrajectoryMeta``.
    now_unix_ms:
        Override for ``time.time()`` in milliseconds (useful in tests).
    lookahead_seconds:
        Override for ``settings.trajectory_lookahead_seconds``.
    step_seconds:
        Override for ``settings.trajectory_step_seconds``.
    """
    if not planned_run.is_usable():
        return None

    if not route_coords or len(route_coords) < 2:
        return None

    if route_length_m <= 0:
        return None

    lookahead = (
        lookahead_seconds
        if lookahead_seconds is not None
        else _settings.trajectory_lookahead_seconds
    )
    step = (
        step_seconds if step_seconds is not None else _settings.trajectory_step_seconds
    )

    now_ms = now_unix_ms if now_unix_ms is not None else int(_time.time() * 1000)
    effective = _effective_minutes(current_minutes, delay_minutes)

    segments = planned_run.segments

    # ------------------------------------------------------------------ #
    # Build frames                                                         #
    # ------------------------------------------------------------------ #
    frames: list[TrajectoryFrame] = []
    step_count = lookahead // step + 1

    for i in range(step_count):
        step_effective = effective + i * step / 60.0
        step_unix_ms = now_ms + i * step * 1000

        seg = planned_run.find_segment(step_effective)
        if seg is None:
            if (
                planned_run.segments
                and step_effective < planned_run.segments[0].absolute_start_minutes
            ):
                seg = planned_run.segments[0]
            elif (
                planned_run.segments
                and step_effective > planned_run.segments[-1].absolute_end_minutes
            ):
                seg = planned_run.segments[-1]
            else:
                if i == 0:
                    return None
                break

        geom_fraction = _compute_geom_fraction(seg, step_effective)
        if geom_fraction is None:
            # Missing fraction data — cannot resolve; fall back.
            return None

        geom_fraction = max(0.0, min(1.0, geom_fraction))
        lon, lat = geo_utils.interpolate_position(route_coords, geom_fraction)
        rotation = _bearing_at_fraction(route_coords, geom_fraction)
        speed = _speed_kmh(seg, route_length_m) if seg.segment_type == "move" else 0.0
        status: TrajectoryStatus = _frame_status(seg.segment_type)

        frames.append(
            TrajectoryFrame(
                t_ms=step_unix_ms,
                lon=round(lon, 6),
                lat=round(lat, 6),
                geom_fraction=round(geom_fraction, 6),
                head_distance_m=round(geom_fraction * route_length_m, 3),
                rotation_deg=geo_utils.normalize_bearing(rotation),
                speed_kmh=round(speed, 2),
                status=status,
            )
        )

    if not frames:
        return None

    # ------------------------------------------------------------------ #
    # Anchors                                                              #
    # ------------------------------------------------------------------ #
    anchors = _build_plan_anchors(
        segments=segments,
        schedules=schedules,
        delay=delay_minutes,
        current_minutes=current_minutes,
        now_unix_ms=now_ms,
    )

    # ------------------------------------------------------------------ #
    # Meta                                                                 #
    # ------------------------------------------------------------------ #
    head = frames[0]
    edge_id, from_station_id, to_station_id = _resolve_edge_info(
        head.geom_fraction, route_length_m, route_segments
    )

    origin, dest, origin_th, dest_th, prev_name, next_name = (
        _meta_station_names(
            schedules, current_minutes=current_minutes, delay=delay_minutes
        )
        if schedules
        else (None, None, None, None, None, None)
    )

    next_name_th: str | None = None
    if schedules:
        from app.services.trajectory_service import _find_bounding_stops

        _, next_idx = _find_bounding_stops(
            schedules, step_minutes=current_minutes, delay=delay_minutes
        )
        if next_idx is not None:
            next_name_th = _station_name_th(schedules[next_idx])

    # ETA for next station — first matching anchor
    eta_next_ms: int | None = None
    if next_name:
        for anchor in anchors:
            if anchor.event == "arrival" and anchor.station_name == next_name:
                eta_next_ms = anchor.t_ms
                break

    # Segment progress: fraction within current active leg
    active_seg = planned_run.find_segment(effective)
    if active_seg is not None:
        frac_start = (
            float(active_seg.start_geom_fraction)
            if active_seg.start_geom_fraction is not None
            else head.geom_fraction
        )
        frac_end = (
            float(active_seg.end_geom_fraction)
            if active_seg.end_geom_fraction is not None
            else head.geom_fraction
        )
        span = abs(frac_end - frac_start)
        if span > 1e-9:
            segment_progress = max(
                0.0,
                min(1.0, (head.geom_fraction - frac_start) / (frac_end - frac_start)),
            )
        else:
            segment_progress = 1.0
    else:
        segment_progress = 0.0

    consist = resolve_consist(getattr(train, "train_type", None))
    color = train_type_color(getattr(train, "train_type", None))

    meta = TrajectoryMeta(
        train_id=int(train.id),
        train_number=str(train.train_number),
        train_type=str(getattr(train, "train_type", "") or ""),
        train_name=getattr(train, "name", None),
        color=color,
        operator=getattr(train, "operator", "State Railway of Thailand")
        or "State Railway of Thailand",
        origin_station=origin,
        destination_station=dest,
        origin_station_th=origin_th,
        destination_station_th=dest_th,
        prev_station=prev_name,
        next_station=next_name,
        next_station_th=next_name_th,
        eta_next_ms=eta_next_ms,
        delay_minutes=delay_minutes,
        route_id=planned_run.route_id,
        route_progress_pct=round(head.geom_fraction * 100.0, 2),
        segment_progress_pct=round(segment_progress * 100.0, 2),
        current_edge_id=edge_id,
        graph_from_station_id=from_station_id,
        graph_to_station_id=to_station_id,
        topology_version=topology_version,
    )

    bounds = _compute_bounds(frames)

    valid_until_ms = now_ms + lookahead * 1000

    return Trajectory(
        train_id=int(train.id),
        generated_at_ms=now_ms,
        valid_until_ms=valid_until_ms,
        route_coords=[[float(p[0]), float(p[1])] for p in route_coords],
        route_length_m=route_length_m,
        frames=frames,
        anchors=anchors,
        consist=consist,
        meta=meta,
        bounds=bounds,
    )
