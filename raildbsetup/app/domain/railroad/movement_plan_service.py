"""Pure domain service for building precomputed movement plan segments.

Input:  flat stop-position data provided by the repository layer.
Output: BuiltRun with an ordered BuiltSegment list, ready for persistence.

No I/O, no SQLAlchemy imports, no clock access.  Tests can exercise this
module in isolation with no database or async infrastructure.

See docs/precomputed-movement-plan.md for the full design rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

# ---------------------------------------------------------------------------
# Warning-code string constants
# ---------------------------------------------------------------------------

WARN_MISSING_ROUTE_STATION_ID = "missing_route_station_id"
WARN_MISSING_STATION_ID = "missing_station_id"
WARN_MISSING_ROUTE_DISTANCE = "missing_route_distance"
WARN_PROJECTION_FALLBACK = "projection_fallback_used"
WARN_NON_MONOTONIC_DISTANCE = "non_monotonic_distance"
WARN_NON_MONOTONIC_TIME = "non_monotonic_time"
WARN_ZERO_OR_NEGATIVE_DURATION = "zero_or_negative_duration"
WARN_SUSPICIOUS_SPEED = "suspicious_speed"
WARN_MISSING_ROUTE_GEOMETRY = "missing_route_geometry"
WARN_MISSING_TOPOLOGY_VERSION = "missing_topology_version"

# Speed outside this range (km/h) triggers WARN_SUSPICIOUS_SPEED.
_SPEED_MIN_KMH = 1.0
_SPEED_MAX_KMH = 200.0

# ---------------------------------------------------------------------------
# Input dataclasses (populated by the repository layer)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class StopInput:
    """Flat stop record assembled by the repository from DB schedule + route_station rows."""

    schedule_id: int
    sequence: int
    station_id: int | None
    route_station_id: int | None
    # Minutes-since-midnight (H*60+M); None when the column is NULL.
    arrival_time_minutes: int | None
    departure_time_minutes: int | None
    arrival_day_offset: int
    departure_day_offset: int
    # From route_stations (resolved via schedule.route_station_id).
    route_station_distance_from_start_km: float | None
    route_station_edge_id: int | None
    # From schedule columns directly.
    schedule_distance_from_origin_km: float | None
    schedule_route_progress: float | None
    # Train-specific position resolved through the station graph.  Unlike a
    # route_station position this remains valid for services crossing branches
    # or more than one canonical KML route.
    graph_distance_from_start_m: float | None = None
    graph_edge_id: int | None = None


@dataclass(slots=True)
class TrainBuildInput:
    """All DB-layer data needed to build one planned_train_run row."""

    train_id: int
    route_id: int
    route_distance_km: float | None
    stops: list[StopInput]


# ---------------------------------------------------------------------------
# Output dataclasses (written by the repository layer)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BuiltSegment:
    """One planned_movement_segments row ready for INSERT."""

    sequence: int
    segment_type: str  # 'move' | 'dwell'

    from_station_id: int | None
    to_station_id: int | None
    from_schedule_id: int | None
    to_schedule_id: int | None

    start_time_minutes: int
    end_time_minutes: int
    start_day_offset: int
    end_day_offset: int
    absolute_start_minutes: int
    absolute_end_minutes: int

    start_distance_m: float | None
    end_distance_m: float | None
    start_geom_fraction: float | None
    end_geom_fraction: float | None

    start_edge_id: int | None
    end_edge_id: int | None

    planned_speed_kmh: float | None
    quality_score: float

    # warnings comes last so it can use a default_factory
    warnings: list[str] = field(default_factory=list)


@dataclass
class BuiltRun:
    """One planned_train_runs row + its ordered segments, ready for INSERT."""

    train_id: int
    route_id: int
    plan_version: str
    topology_version: str | None

    service_date: date | None = None  # always NULL in Phase 3
    service_pattern: str | None = "daily"
    quality_score: float = 1.0
    status: str = "ready"  # ready | degraded | invalid

    warnings: list[str] = field(default_factory=list)
    segments: list[BuiltSegment] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal resolved-stop type
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _ResolvedStop:
    schedule_id: int
    station_id: int | None
    # Absolute minutes (time_minutes + day_offset * 1440); None when not set.
    arrival_abs: int | None
    departure_abs: int | None
    # Raw per-day components for writing to segment columns.
    arrival_time_minutes: int | None
    departure_time_minutes: int | None
    arrival_day_offset: int
    departure_day_offset: int
    # Resolved geometry position.
    distance_m: float | None
    geom_fraction: float | None
    edge_id: int | None
    warnings: list[str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _abs_minutes(time_minutes: int, day_offset: int) -> int:
    return time_minutes + day_offset * 1440


def _resolve_stop(
    stop: StopInput,
    route_total_m: float | None,
    stop_index: int,
    total_stops: int,
) -> _ResolvedStop:
    """Resolve geometry position for one stop, emitting quality warnings."""
    warnings: list[str] = []

    if stop.station_id is None:
        warnings.append(WARN_MISSING_STATION_ID)
    if stop.route_station_id is None and stop.graph_distance_from_start_m is None:
        warnings.append(WARN_MISSING_ROUTE_STATION_ID)

    edge_id = stop.graph_edge_id or stop.route_station_edge_id

    arrival_abs = (
        _abs_minutes(stop.arrival_time_minutes, stop.arrival_day_offset)
        if stop.arrival_time_minutes is not None
        else None
    )
    departure_abs = (
        _abs_minutes(stop.departure_time_minutes, stop.departure_day_offset)
        if stop.departure_time_minutes is not None
        else None
    )

    # --- Resolve (distance_m, geom_fraction) via priority order ---
    dist_m: float | None = None
    frac: float | None = None

    # Priority 1: train-specific cumulative graph distance.  This is the only
    # reliable source for through trains spanning multiple canonical routes.
    if stop.graph_distance_from_start_m is not None and route_total_m:
        dist_m = float(stop.graph_distance_from_start_m)
        frac = max(0.0, min(1.0, dist_m / route_total_m))

    # Priority 2: route_station.distance_from_start
    elif stop.route_station_distance_from_start_km is not None and route_total_m:
        dist_m = float(stop.route_station_distance_from_start_km) * 1000.0
        frac = max(0.0, min(1.0, dist_m / route_total_m))

    # Priority 3: schedule.distance_from_origin_km
    elif stop.schedule_distance_from_origin_km is not None and route_total_m:
        dist_m = float(stop.schedule_distance_from_origin_km) * 1000.0
        frac = max(0.0, min(1.0, dist_m / route_total_m))
        warnings.append(WARN_PROJECTION_FALLBACK)

    # Priority 4: schedule.route_progress (direct fraction)
    elif stop.schedule_route_progress is not None:
        frac = max(0.0, min(1.0, float(stop.schedule_route_progress)))
        dist_m = frac * route_total_m if route_total_m else None
        warnings.append(WARN_PROJECTION_FALLBACK)

    else:
        # We will interpolate missing fractions later.
        frac = None
        dist_m = None
        warnings.append(WARN_MISSING_ROUTE_DISTANCE)
        warnings.append(WARN_PROJECTION_FALLBACK)

    if dist_m is None:
        warnings.append(WARN_MISSING_ROUTE_GEOMETRY)

    return _ResolvedStop(
        schedule_id=stop.schedule_id,
        station_id=stop.station_id,
        arrival_abs=arrival_abs,
        departure_abs=departure_abs,
        arrival_time_minutes=stop.arrival_time_minutes,
        departure_time_minutes=stop.departure_time_minutes,
        arrival_day_offset=stop.arrival_day_offset,
        departure_day_offset=stop.departure_day_offset,
        distance_m=dist_m,
        geom_fraction=frac,
        edge_id=edge_id,
        warnings=warnings,
    )


def _check_distance_monotonicity(resolved: list[_ResolvedStop]) -> str | None:
    """Return WARN_NON_MONOTONIC_DISTANCE when distances change direction more than once.

    A pure ascending or pure descending sequence is valid (reverse-direction train).
    Only a sequence that is both ascending and descending at different points is flagged.
    """
    dists = [r.distance_m for r in resolved if r.distance_m is not None]
    if len(dists) < 2:
        return None
    ascending = sum(1 for a, b in zip(dists, dists[1:], strict=False) if b > a)
    descending = sum(1 for a, b in zip(dists, dists[1:], strict=False) if b < a)
    if ascending > 0 and descending > 0:
        return WARN_NON_MONOTONIC_DISTANCE
    return None


def _stop_quality(stop: _ResolvedStop) -> float:
    """Per-stop quality contribution (0.0–1.0)."""
    score = 1.0
    if WARN_MISSING_STATION_ID in stop.warnings:
        score -= 0.2
    if WARN_MISSING_ROUTE_STATION_ID in stop.warnings:
        score -= 0.2
    if WARN_MISSING_ROUTE_DISTANCE in stop.warnings:
        score -= 0.3
    elif WARN_PROJECTION_FALLBACK in stop.warnings:
        score -= 0.15
    return max(0.0, score)


def _build_segments(
    resolved: list[_ResolvedStop],
    run_warnings: list[str],
) -> list[BuiltSegment]:
    """Emit dwell and move segments for a resolved stop sequence."""
    segments: list[BuiltSegment] = []
    seq = 0

    for i, stop in enumerate(resolved):

        # ---- Dwell segment ----
        # Emit when both arrival and departure are present and departure > arrival.
        if (
            stop.arrival_abs is not None
            and stop.departure_abs is not None
            and stop.arrival_time_minutes is not None
            and stop.departure_time_minutes is not None
        ):
            dwell_dur = stop.departure_abs - stop.arrival_abs
            if dwell_dur > 0:
                segments.append(
                    BuiltSegment(
                        sequence=seq,
                        segment_type="dwell",
                        from_station_id=stop.station_id,
                        to_station_id=stop.station_id,
                        from_schedule_id=stop.schedule_id,
                        to_schedule_id=stop.schedule_id,
                        start_time_minutes=stop.arrival_time_minutes,
                        end_time_minutes=stop.departure_time_minutes,
                        start_day_offset=stop.arrival_day_offset,
                        end_day_offset=stop.departure_day_offset,
                        absolute_start_minutes=stop.arrival_abs,
                        absolute_end_minutes=stop.departure_abs,
                        start_distance_m=stop.distance_m,
                        end_distance_m=stop.distance_m,
                        start_geom_fraction=stop.geom_fraction,
                        end_geom_fraction=stop.geom_fraction,
                        start_edge_id=stop.edge_id,
                        end_edge_id=stop.edge_id,
                        planned_speed_kmh=0.0,
                        quality_score=round(_stop_quality(stop), 4),
                        warnings=list(stop.warnings),
                    )
                )
                seq += 1
            elif dwell_dur < 0 and WARN_ZERO_OR_NEGATIVE_DURATION not in run_warnings:
                run_warnings.append(WARN_ZERO_OR_NEGATIVE_DURATION)

        # ---- Move segment to the next stop ----
        if i + 1 >= len(resolved):
            continue
        next_stop = resolved[i + 1]

        # Start time: prefer departure; fall back to arrival.
        if stop.departure_abs is not None and stop.departure_time_minutes is not None:
            start_abs = stop.departure_abs
            start_min = stop.departure_time_minutes
            start_off = stop.departure_day_offset
        elif stop.arrival_abs is not None and stop.arrival_time_minutes is not None:
            start_abs = stop.arrival_abs
            start_min = stop.arrival_time_minutes
            start_off = stop.arrival_day_offset
        else:
            continue  # No usable start time — skip this leg

        # End time: prefer arrival; fall back to departure.
        if (
            next_stop.arrival_abs is not None
            and next_stop.arrival_time_minutes is not None
        ):
            end_abs = next_stop.arrival_abs
            end_min = next_stop.arrival_time_minutes
            end_off = next_stop.arrival_day_offset
        elif (
            next_stop.departure_abs is not None
            and next_stop.departure_time_minutes is not None
        ):
            end_abs = next_stop.departure_abs
            end_min = next_stop.departure_time_minutes
            end_off = next_stop.departure_day_offset
        else:
            continue  # No usable end time — skip this leg

        move_dur = end_abs - start_abs

        # Accumulate segment warnings: stop quality issues + operational issues.
        seg_warnings: list[str] = []
        seen_sw: set[str] = set()
        for w in stop.warnings + next_stop.warnings:
            if w not in seen_sw:
                seen_sw.add(w)
                seg_warnings.append(w)

        if move_dur <= 0:
            seg_warnings.append(WARN_ZERO_OR_NEGATIVE_DURATION)
            if WARN_ZERO_OR_NEGATIVE_DURATION not in run_warnings:
                run_warnings.append(WARN_ZERO_OR_NEGATIVE_DURATION)

        # Compute planned speed.
        speed: float | None = None
        if (
            stop.distance_m is not None
            and next_stop.distance_m is not None
            and move_dur > 0
        ):
            dist_km = abs(next_stop.distance_m - stop.distance_m) / 1000.0
            speed = round(dist_km / (move_dur / 60.0), 2)
            if speed < _SPEED_MIN_KMH or speed > _SPEED_MAX_KMH:
                if WARN_SUSPICIOUS_SPEED not in seg_warnings:
                    seg_warnings.append(WARN_SUSPICIOUS_SPEED)
                if WARN_SUSPICIOUS_SPEED not in run_warnings:
                    run_warnings.append(WARN_SUSPICIOUS_SPEED)

        seg_q = min(_stop_quality(stop), _stop_quality(next_stop))
        if (
            WARN_ZERO_OR_NEGATIVE_DURATION in seg_warnings
            or WARN_SUSPICIOUS_SPEED in seg_warnings
        ):
            seg_q = max(0.0, seg_q - 0.3)

        segments.append(
            BuiltSegment(
                sequence=seq,
                segment_type="move",
                from_station_id=stop.station_id,
                to_station_id=next_stop.station_id,
                from_schedule_id=stop.schedule_id,
                to_schedule_id=next_stop.schedule_id,
                start_time_minutes=start_min,
                end_time_minutes=end_min,
                start_day_offset=start_off,
                end_day_offset=end_off,
                absolute_start_minutes=start_abs,
                absolute_end_minutes=end_abs,
                start_distance_m=stop.distance_m,
                end_distance_m=next_stop.distance_m,
                start_geom_fraction=stop.geom_fraction,
                end_geom_fraction=next_stop.geom_fraction,
                start_edge_id=stop.edge_id,
                end_edge_id=next_stop.edge_id,
                planned_speed_kmh=speed,
                quality_score=round(seg_q, 4),
                warnings=seg_warnings,
            )
        )
        seq += 1

    return segments


def _run_quality(
    segments: list[BuiltSegment],
    run_warnings: list[str],
) -> float:
    move_segs = [s for s in segments if s.segment_type == "move"]
    if not move_segs:
        return 0.0
    avg = sum(s.quality_score for s in move_segs) / len(move_segs)
    score = avg
    if WARN_NON_MONOTONIC_DISTANCE in run_warnings:
        score -= 0.2
    if WARN_NON_MONOTONIC_TIME in run_warnings:
        score -= 0.2
    if WARN_MISSING_TOPOLOGY_VERSION in run_warnings:
        score -= 0.05
    return max(0.0, min(1.0, round(score, 4)))


def _determine_status(quality: float, has_move: bool) -> str:
    if not has_move or quality < 0.2:
        return "invalid"
    if quality < 0.5:
        return "degraded"
    return "ready"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_movement_plan(
    train: TrainBuildInput,
    plan_version: str,
    topology_version: str | None,
) -> BuiltRun:
    """Build a single planned train run from flat stop data.

    Pure function: no I/O, no side effects, fully deterministic for identical
    inputs.  The caller is responsible for persisting the result.

    Args:
        train:            Stop data and route metadata loaded from the DB.
        plan_version:     Opaque version string (e.g. a timestamp).
        topology_version: topology_metadata.topology_version at build time;
                          None if not yet available.

    Returns:
        A :class:`BuiltRun` with status ``"ready"``, ``"degraded"``, or
        ``"invalid"``.  Invalid plans still carry diagnostic information.
    """
    run_warnings: list[str] = []

    if topology_version is None:
        run_warnings.append(WARN_MISSING_TOPOLOGY_VERSION)

    # Only stops with at least one time value are usable.
    usable = [
        s
        for s in train.stops
        if s.arrival_time_minutes is not None or s.departure_time_minutes is not None
    ]
    if len(usable) < 2:
        return BuiltRun(
            train_id=train.train_id,
            route_id=train.route_id,
            plan_version=plan_version,
            topology_version=topology_version,
            quality_score=0.0,
            status="invalid",
            warnings=["insufficient_usable_stops"],
        )

    route_total_m = (
        float(train.route_distance_km) * 1000.0 if train.route_distance_km else None
    )
    if route_total_m is None:
        run_warnings.append(WARN_MISSING_ROUTE_GEOMETRY)

    # Resolve position for every usable stop.
    resolved = [
        _resolve_stop(stop, route_total_m, i, len(usable))
        for i, stop in enumerate(usable)
    ]

    # Interpolate missing geom_fraction
    total_usable = len(usable)
    if all(r.geom_fraction is None for r in resolved):
        for i, r in enumerate(resolved):
            r.geom_fraction = float(i) / max(1, total_usable - 1)
            if route_total_m:
                r.distance_m = r.geom_fraction * route_total_m
    else:
        for i in range(total_usable):
            if resolved[i].geom_fraction is None:
                left_idx = i - 1
                while left_idx >= 0 and resolved[left_idx].geom_fraction is None:
                    left_idx -= 1
                right_idx = i + 1
                while (
                    right_idx < total_usable
                    and resolved[right_idx].geom_fraction is None
                ):
                    right_idx += 1

                left_val = resolved[left_idx].geom_fraction if left_idx >= 0 else None
                right_val = (
                    resolved[right_idx].geom_fraction
                    if right_idx < total_usable
                    else None
                )

                if left_val is not None and right_val is not None:
                    span = right_idx - left_idx
                    resolved[i].geom_fraction = left_val + (right_val - left_val) * (
                        (i - left_idx) / span
                    )
                elif left_val is not None:
                    resolved[i].geom_fraction = left_val
                elif right_val is not None:
                    resolved[i].geom_fraction = right_val

                gf = resolved[i].geom_fraction
                if route_total_m is not None and gf is not None:
                    resolved[i].distance_m = gf * route_total_m
    abs_times = [
        r.departure_abs if r.departure_abs is not None else r.arrival_abs
        for r in resolved
    ]
    known_times = [t for t in abs_times if t is not None]
    if len(known_times) >= 2 and not all(
        a <= b for a, b in zip(known_times, known_times[1:], strict=False)
    ):
        run_warnings.append(WARN_NON_MONOTONIC_TIME)

    # Check distance monotonicity.
    mono_warn = _check_distance_monotonicity(resolved)
    if mono_warn:
        run_warnings.append(mono_warn)

    # Aggregate stop-level quality warnings to run level for operator visibility.
    seen_stop_codes: set[str] = set()
    for r in resolved:
        seen_stop_codes.update(r.warnings)
    for code in (
        WARN_MISSING_ROUTE_STATION_ID,
        WARN_MISSING_STATION_ID,
        WARN_MISSING_ROUTE_DISTANCE,
        WARN_PROJECTION_FALLBACK,
        WARN_MISSING_ROUTE_GEOMETRY,
    ):
        if code in seen_stop_codes and code not in run_warnings:
            run_warnings.append(code)

    segments = _build_segments(resolved, run_warnings)

    has_move = any(s.segment_type == "move" for s in segments)
    quality = _run_quality(segments, run_warnings)
    status = _determine_status(quality, has_move)
    if any(
        warning in run_warnings
        for warning in (
            WARN_NON_MONOTONIC_DISTANCE,
            WARN_NON_MONOTONIC_TIME,
            WARN_ZERO_OR_NEGATIVE_DURATION,
            WARN_SUSPICIOUS_SPEED,
        )
    ):
        status = "invalid"

    # Deduplicate run-level warnings while preserving insertion order.
    seen: set[str] = set()
    deduped: list[str] = []
    for w in run_warnings:
        if w not in seen:
            seen.add(w)
            deduped.append(w)

    return BuiltRun(
        train_id=train.train_id,
        route_id=train.route_id,
        plan_version=plan_version,
        topology_version=topology_version,
        service_date=None,
        service_pattern="daily",
        quality_score=quality,
        status=status,
        warnings=deduped,
        segments=segments,
    )
