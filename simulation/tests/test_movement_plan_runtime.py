"""Unit tests for app.services.movement_plan_runtime.

All tests are pure (no DB, no Redis, no network) and deterministic via the
``now_unix_ms``, ``lookahead_seconds``, and ``step_seconds`` overrides.

Route: two points — Bangkok ≈ [100.5, 13.75] → Ayutthaya ≈ [100.6, 14.35]
Route length ≈ 70 km → 70_000 m used throughout.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.domain.movement_plan import PlannedMovementSegment, PlannedTrainRun
from app.services.movement_plan_runtime import (
    _compute_geom_fraction,
    _effective_minutes,
    resolve_trajectory,
)

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

_ROUTE = [[100.5, 13.75], [100.6, 14.35]]
_ROUTE_LEN_M = 70_000.0
_NOW_MS = 1_700_000_000_000  # fixed epoch ms for determinism

# A minimal train namespace that resolve_trajectory will accept.
_TRAIN = SimpleNamespace(
    id=1,
    train_number="101",
    train_type="express",
    name="Bangkok Express",
    operator="SRT",
    current_route_id=10,
)

# A minimal schedule namespace (used for meta station name extraction).
_SCHEDULE_A = SimpleNamespace(
    id=1,
    train_id=1,
    station_id=101,
    station_name="Bangkok",
    station_name_th="กรุงเทพ",
    arrival_time_minutes=0,
    departure_time_minutes=600,
    day_offset=0,
    sequence=1,
    station=None,
    arrival_time=None,
    departure_time=None,
    arrival_day_offset=0,
    departure_day_offset=0,
)
_SCHEDULE_B = SimpleNamespace(
    id=2,
    train_id=1,
    station_id=102,
    station_name="Ayutthaya",
    station_name_th="อยุธยา",
    arrival_time_minutes=720,
    departure_time_minutes=720,
    day_offset=0,
    sequence=2,
    station=None,
    arrival_time=None,
    departure_time=None,
    arrival_day_offset=0,
    departure_day_offset=0,
)


def _move_segment(
    *,
    seq: int = 1,
    abs_start: float = 600.0,
    abs_end: float = 720.0,
    start_frac: float = 0.0,
    end_frac: float = 1.0,
    speed_kmh: float = 60.0,
    from_sched_id: int = 1,
    to_sched_id: int = 2,
    planned_run_id: int = 99,
) -> PlannedMovementSegment:
    """Build a move segment spanning the full route fraction."""
    # abs_start = start_time_minutes + start_day_offset * 1440
    # We encode: start_time_minutes = abs_start, day_offset = 0
    return PlannedMovementSegment(
        id=seq,
        planned_run_id=planned_run_id,
        sequence=seq,
        segment_type="move",
        from_station_id=101,
        to_station_id=102,
        from_schedule_id=from_sched_id,
        to_schedule_id=to_sched_id,
        start_time_minutes=abs_start,
        end_time_minutes=abs_end,
        start_day_offset=0,
        end_day_offset=0,
        start_distance_m=0.0,
        end_distance_m=70_000.0,
        start_geom_fraction=start_frac,
        end_geom_fraction=end_frac,
        start_edge_id=None,
        end_edge_id=None,
        planned_speed_kmh=speed_kmh,
        quality_score=1.0,
        warnings=[],
    )


def _dwell_segment(
    *,
    seq: int = 1,
    abs_start: float = 600.0,
    abs_end: float = 610.0,
    frac: float = 0.0,
    from_sched_id: int = 1,
    to_sched_id: int = 1,
    planned_run_id: int = 99,
) -> PlannedMovementSegment:
    return PlannedMovementSegment(
        id=seq,
        planned_run_id=planned_run_id,
        sequence=seq,
        segment_type="dwell",
        from_station_id=101,
        to_station_id=101,
        from_schedule_id=from_sched_id,
        to_schedule_id=to_sched_id,
        start_time_minutes=abs_start,
        end_time_minutes=abs_end,
        start_day_offset=0,
        end_day_offset=0,
        start_distance_m=0.0,
        end_distance_m=0.0,
        start_geom_fraction=frac,
        end_geom_fraction=frac,
        start_edge_id=None,
        end_edge_id=None,
        planned_speed_kmh=None,
        quality_score=1.0,
        warnings=[],
    )


def _run(
    segments: list[PlannedMovementSegment], *, status: str = "ready"
) -> PlannedTrainRun:
    return PlannedTrainRun(
        id=99,
        train_id=1,
        route_id=10,
        service_date=None,
        service_pattern=None,
        plan_version="v1",
        topology_version="topo-1",
        quality_score=1.0,
        status=status,  # type: ignore[arg-type]
        warnings=[],
        segments=segments,
    )


# ---------------------------------------------------------------------------
# _effective_minutes
# ---------------------------------------------------------------------------


def test_effective_minutes_no_delay() -> None:
    assert _effective_minutes(720.0, 0) == 720.0


def test_effective_minutes_positive_delay_shifts_backward() -> None:
    # A 10-minute delay means the plan alignment shifts 10 minutes backward.
    assert _effective_minutes(730.0, 10) == 720.0


def test_effective_minutes_negative_delay() -> None:
    assert _effective_minutes(710.0, -5) == 715.0


# ---------------------------------------------------------------------------
# _compute_geom_fraction
# ---------------------------------------------------------------------------


def test_compute_geom_fraction_midpoint_of_move() -> None:
    seg = _move_segment(abs_start=600.0, abs_end=720.0, start_frac=0.0, end_frac=1.0)
    frac = _compute_geom_fraction(seg, 660.0)  # midpoint
    assert frac is not None
    assert abs(frac - 0.5) < 1e-9


def test_compute_geom_fraction_at_start() -> None:
    seg = _move_segment(abs_start=600.0, abs_end=720.0, start_frac=0.0, end_frac=1.0)
    frac = _compute_geom_fraction(seg, 600.0)
    assert frac is not None
    assert abs(frac - 0.0) < 1e-9


def test_compute_geom_fraction_at_end() -> None:
    seg = _move_segment(abs_start=600.0, abs_end=720.0, start_frac=0.0, end_frac=1.0)
    frac = _compute_geom_fraction(seg, 720.0)
    assert frac is not None
    assert abs(frac - 1.0) < 1e-9


def test_compute_geom_fraction_dwell_pinned_to_start_frac() -> None:
    seg = _dwell_segment(abs_start=720.0, abs_end=730.0, frac=0.75)
    frac = _compute_geom_fraction(seg, 725.0)  # middle of dwell
    assert frac is not None
    assert abs(frac - 0.75) < 1e-9


def test_compute_geom_fraction_reverse_direction() -> None:
    # end_frac < start_frac → descending route
    seg = _move_segment(abs_start=600.0, abs_end=720.0, start_frac=1.0, end_frac=0.0)
    frac = _compute_geom_fraction(seg, 660.0)  # midpoint
    assert frac is not None
    assert abs(frac - 0.5) < 1e-9


def test_compute_geom_fraction_none_when_start_frac_missing() -> None:
    seg = PlannedMovementSegment(
        id=1,
        planned_run_id=99,
        sequence=1,
        segment_type="move",
        from_station_id=None,
        to_station_id=None,
        from_schedule_id=None,
        to_schedule_id=None,
        start_time_minutes=600.0,
        end_time_minutes=720.0,
        start_day_offset=0,
        end_day_offset=0,
        start_distance_m=None,
        end_distance_m=None,
        start_geom_fraction=None,  # ← missing
        end_geom_fraction=0.5,
        start_edge_id=None,
        end_edge_id=None,
        planned_speed_kmh=60.0,
        quality_score=None,
        warnings=[],
    )
    assert _compute_geom_fraction(seg, 660.0) is None


# ---------------------------------------------------------------------------
# resolve_trajectory — happy path
# ---------------------------------------------------------------------------


def test_resolve_trajectory_returns_trajectory_for_move_segment() -> None:
    seg = _move_segment(abs_start=600.0, abs_end=720.0)
    planned = _run([seg])
    # current effective time = 660.0 (midpoint)
    result = resolve_trajectory(
        planned_run=planned,
        route_coords=_ROUTE,
        route_length_m=_ROUTE_LEN_M,
        current_minutes=660.0,  # no delay
        delay_minutes=0,
        train=_TRAIN,
        schedules=[_SCHEDULE_A, _SCHEDULE_B],
        now_unix_ms=_NOW_MS,
        lookahead_seconds=120,
        step_seconds=60,
    )
    assert result is not None
    assert result.train_id == 1
    assert len(result.frames) >= 1
    # First frame should be near midpoint
    head = result.frames[0]
    assert 0.4 < head.geom_fraction < 0.6


def test_resolve_trajectory_returns_trajectory_for_dwell_segment() -> None:
    seg = _dwell_segment(abs_start=720.0, abs_end=730.0, frac=1.0)
    planned = _run([seg])
    result = resolve_trajectory(
        planned_run=planned,
        route_coords=_ROUTE,
        route_length_m=_ROUTE_LEN_M,
        current_minutes=725.0,
        delay_minutes=0,
        train=_TRAIN,
        schedules=[_SCHEDULE_A, _SCHEDULE_B],
        now_unix_ms=_NOW_MS,
        lookahead_seconds=60,
        step_seconds=60,
    )
    assert result is not None
    # Dwell: all frames should be at fraction=1.0
    for frame in result.frames:
        assert frame.geom_fraction == pytest.approx(1.0, abs=1e-4)
        assert frame.status == "dwelling"
        assert frame.speed_kmh == 0.0


def test_resolve_trajectory_frames_have_correct_timestamps() -> None:
    seg = _move_segment(abs_start=600.0, abs_end=720.0)
    planned = _run([seg])
    result = resolve_trajectory(
        planned_run=planned,
        route_coords=_ROUTE,
        route_length_m=_ROUTE_LEN_M,
        current_minutes=600.0,
        delay_minutes=0,
        train=_TRAIN,
        schedules=[_SCHEDULE_A, _SCHEDULE_B],
        now_unix_ms=_NOW_MS,
        lookahead_seconds=120,
        step_seconds=60,
    )
    assert result is not None
    assert result.frames[0].t_ms == _NOW_MS
    assert result.frames[1].t_ms == _NOW_MS + 60 * 1000


def test_resolve_trajectory_meta_has_correct_train_id() -> None:
    seg = _move_segment(abs_start=600.0, abs_end=720.0)
    planned = _run([seg])
    result = resolve_trajectory(
        planned_run=planned,
        route_coords=_ROUTE,
        route_length_m=_ROUTE_LEN_M,
        current_minutes=660.0,
        delay_minutes=0,
        train=_TRAIN,
        schedules=[_SCHEDULE_A, _SCHEDULE_B],
        now_unix_ms=_NOW_MS,
        lookahead_seconds=60,
        step_seconds=60,
    )
    assert result is not None
    assert result.meta.train_id == 1
    assert result.meta.train_number == "101"
    assert result.meta.route_id == 10
    assert result.meta.delay_minutes == 0


def test_resolve_trajectory_frames_advance_along_route() -> None:
    seg = _move_segment(abs_start=600.0, abs_end=720.0)  # 120-minute journey
    planned = _run([seg])
    result = resolve_trajectory(
        planned_run=planned,
        route_coords=_ROUTE,
        route_length_m=_ROUTE_LEN_M,
        current_minutes=600.0,
        delay_minutes=0,
        train=_TRAIN,
        schedules=[_SCHEDULE_A, _SCHEDULE_B],
        now_unix_ms=_NOW_MS,
        lookahead_seconds=120,
        step_seconds=60,
    )
    assert result is not None
    fracs = [f.geom_fraction for f in result.frames]
    # Each frame should have a higher (or equal) fraction than the previous.
    assert fracs == sorted(fracs)


# ---------------------------------------------------------------------------
# resolve_trajectory — delay handling
# ---------------------------------------------------------------------------


def test_resolve_trajectory_delay_shifts_effective_time() -> None:
    """A 10-minute delay means effective = current - 10.

    If we are at wall-clock minute 670, effective = 660, which should be
    the same position as current=660 with no delay.
    """
    seg = _move_segment(abs_start=600.0, abs_end=720.0, start_frac=0.0, end_frac=1.0)
    planned = _run([seg])

    result_no_delay = resolve_trajectory(
        planned_run=planned,
        route_coords=_ROUTE,
        route_length_m=_ROUTE_LEN_M,
        current_minutes=660.0,
        delay_minutes=0,
        train=_TRAIN,
        schedules=[_SCHEDULE_A, _SCHEDULE_B],
        now_unix_ms=_NOW_MS,
        lookahead_seconds=60,
        step_seconds=60,
    )
    result_with_delay = resolve_trajectory(
        planned_run=planned,
        route_coords=_ROUTE,
        route_length_m=_ROUTE_LEN_M,
        current_minutes=670.0,
        delay_minutes=10,
        train=_TRAIN,
        schedules=[_SCHEDULE_A, _SCHEDULE_B],
        now_unix_ms=_NOW_MS,
        lookahead_seconds=60,
        step_seconds=60,
    )
    assert result_no_delay is not None
    assert result_with_delay is not None
    assert result_no_delay.frames[0].geom_fraction == pytest.approx(
        result_with_delay.frames[0].geom_fraction, abs=1e-4
    )


# ---------------------------------------------------------------------------
# resolve_trajectory — None / error cases
# ---------------------------------------------------------------------------


def test_resolve_trajectory_returns_none_for_invalid_status() -> None:
    seg = _move_segment(abs_start=600.0, abs_end=720.0)
    planned = _run([seg], status="invalid")
    result = resolve_trajectory(
        planned_run=planned,
        route_coords=_ROUTE,
        route_length_m=_ROUTE_LEN_M,
        current_minutes=660.0,
        delay_minutes=0,
        train=_TRAIN,
        schedules=[_SCHEDULE_A, _SCHEDULE_B],
        now_unix_ms=_NOW_MS,
        lookahead_seconds=60,
        step_seconds=60,
    )
    assert result is None


def test_resolve_trajectory_returns_none_for_empty_segments() -> None:
    planned = _run([])
    result = resolve_trajectory(
        planned_run=planned,
        route_coords=_ROUTE,
        route_length_m=_ROUTE_LEN_M,
        current_minutes=660.0,
        delay_minutes=0,
        train=_TRAIN,
        schedules=[_SCHEDULE_A, _SCHEDULE_B],
        now_unix_ms=_NOW_MS,
        lookahead_seconds=60,
        step_seconds=60,
    )
    assert result is None


def test_resolve_trajectory_returns_none_for_empty_route() -> None:
    seg = _move_segment(abs_start=600.0, abs_end=720.0)
    planned = _run([seg])
    result = resolve_trajectory(
        planned_run=planned,
        route_coords=[],
        route_length_m=_ROUTE_LEN_M,
        current_minutes=660.0,
        delay_minutes=0,
        train=_TRAIN,
        schedules=[_SCHEDULE_A, _SCHEDULE_B],
        now_unix_ms=_NOW_MS,
        lookahead_seconds=60,
        step_seconds=60,
    )
    assert result is None


def test_resolve_trajectory_returns_none_for_zero_route_length() -> None:
    seg = _move_segment(abs_start=600.0, abs_end=720.0)
    planned = _run([seg])
    result = resolve_trajectory(
        planned_run=planned,
        route_coords=_ROUTE,
        route_length_m=0.0,
        current_minutes=660.0,
        delay_minutes=0,
        train=_TRAIN,
        schedules=[_SCHEDULE_A, _SCHEDULE_B],
        now_unix_ms=_NOW_MS,
        lookahead_seconds=60,
        step_seconds=60,
    )
    assert result is None


def test_resolve_trajectory_returns_none_when_no_active_segment_at_time_zero() -> None:
    # Segment starts in the future.
    seg = _move_segment(abs_start=700.0, abs_end=720.0)
    planned = _run([seg])
    result = resolve_trajectory(
        planned_run=planned,
        route_coords=_ROUTE,
        route_length_m=_ROUTE_LEN_M,
        current_minutes=660.0,  # before segment start
        delay_minutes=0,
        train=_TRAIN,
        schedules=[_SCHEDULE_A, _SCHEDULE_B],
        now_unix_ms=_NOW_MS,
        lookahead_seconds=60,
        step_seconds=60,
    )
    assert result is None


def test_resolve_trajectory_returns_none_when_missing_geom_fraction() -> None:
    seg = PlannedMovementSegment(
        id=1,
        planned_run_id=99,
        sequence=1,
        segment_type="move",
        from_station_id=None,
        to_station_id=None,
        from_schedule_id=None,
        to_schedule_id=None,
        start_time_minutes=600.0,
        end_time_minutes=720.0,
        start_day_offset=0,
        end_day_offset=0,
        start_distance_m=None,
        end_distance_m=None,
        start_geom_fraction=None,  # ← missing
        end_geom_fraction=1.0,
        start_edge_id=None,
        end_edge_id=None,
        planned_speed_kmh=60.0,
        quality_score=None,
        warnings=[],
    )
    planned = _run([seg])
    result = resolve_trajectory(
        planned_run=planned,
        route_coords=_ROUTE,
        route_length_m=_ROUTE_LEN_M,
        current_minutes=660.0,
        delay_minutes=0,
        train=_TRAIN,
        schedules=[_SCHEDULE_A, _SCHEDULE_B],
        now_unix_ms=_NOW_MS,
        lookahead_seconds=60,
        step_seconds=60,
    )
    assert result is None


# ---------------------------------------------------------------------------
# resolve_trajectory — overnight
# ---------------------------------------------------------------------------


def test_resolve_trajectory_overnight_absolute_minutes() -> None:
    """Segments that cross midnight use absolute minutes > 1440."""
    seg = PlannedMovementSegment(
        id=1,
        planned_run_id=99,
        sequence=1,
        segment_type="move",
        from_station_id=None,
        to_station_id=None,
        from_schedule_id=None,
        to_schedule_id=None,
        # Day 1, 00:00 → Day 1, 02:00 → absolute 1440–1560
        start_time_minutes=0.0,
        end_time_minutes=120.0,
        start_day_offset=1,
        end_day_offset=1,
        start_distance_m=0.0,
        end_distance_m=70_000.0,
        start_geom_fraction=0.0,
        end_geom_fraction=1.0,
        start_edge_id=None,
        end_edge_id=None,
        planned_speed_kmh=60.0,
        quality_score=1.0,
        warnings=[],
    )
    planned = _run([seg])
    # current effective = 1500.0 → midpoint of [1440, 1560]
    result = resolve_trajectory(
        planned_run=planned,
        route_coords=_ROUTE,
        route_length_m=_ROUTE_LEN_M,
        current_minutes=1500.0,
        delay_minutes=0,
        train=_TRAIN,
        schedules=[_SCHEDULE_A, _SCHEDULE_B],
        now_unix_ms=_NOW_MS,
        lookahead_seconds=60,
        step_seconds=60,
    )
    assert result is not None
    assert 0.4 < result.frames[0].geom_fraction < 0.6


# ---------------------------------------------------------------------------
# resolve_trajectory — shape invariants
# ---------------------------------------------------------------------------


def test_resolve_trajectory_route_coords_preserved() -> None:
    seg = _move_segment(abs_start=600.0, abs_end=720.0)
    planned = _run([seg])
    result = resolve_trajectory(
        planned_run=planned,
        route_coords=_ROUTE,
        route_length_m=_ROUTE_LEN_M,
        current_minutes=660.0,
        delay_minutes=0,
        train=_TRAIN,
        schedules=[_SCHEDULE_A, _SCHEDULE_B],
        now_unix_ms=_NOW_MS,
        lookahead_seconds=60,
        step_seconds=60,
    )
    assert result is not None
    assert len(result.route_coords) == 2
    assert result.route_length_m == _ROUTE_LEN_M


def test_resolve_trajectory_bounds_contain_all_frames() -> None:
    seg = _move_segment(abs_start=600.0, abs_end=720.0)
    planned = _run([seg])
    result = resolve_trajectory(
        planned_run=planned,
        route_coords=_ROUTE,
        route_length_m=_ROUTE_LEN_M,
        current_minutes=600.0,
        delay_minutes=0,
        train=_TRAIN,
        schedules=[_SCHEDULE_A, _SCHEDULE_B],
        now_unix_ms=_NOW_MS,
        lookahead_seconds=120,
        step_seconds=60,
    )
    assert result is not None
    min_lon, min_lat, max_lon, max_lat = result.bounds
    for frame in result.frames:
        assert min_lon <= frame.lon <= max_lon
        assert min_lat <= frame.lat <= max_lat
