"""Tests for movement plan builder — pure logic, no database required.

All tests operate on the domain service only:
    app.domain.railroad.movement_plan_service

No SQLAlchemy, no async, no fixtures beyond simple helper functions.
"""

from __future__ import annotations

import pytest

from app.domain.railroad.movement_plan_service import (
    WARN_MISSING_ROUTE_STATION_ID,
    WARN_NON_MONOTONIC_DISTANCE,
    WARN_SUSPICIOUS_SPEED,
    WARN_ZERO_OR_NEGATIVE_DURATION,
    StopInput,
    TrainBuildInput,
    build_movement_plan,
)

_PLAN_VERSION = "20260429T000000"
_TOPO_VERSION = "v1"


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _stop(
    *,
    schedule_id: int,
    sequence: int,
    station_id: int | None = 1,
    route_station_id: int | None = 1,
    arrival_min: int | None = None,
    departure_min: int | None = None,
    arrival_offset: int = 0,
    departure_offset: int = 0,
    rs_dist_km: float | None = None,
    sched_dist_km: float | None = None,
    route_progress: float | None = None,
) -> StopInput:
    return StopInput(
        schedule_id=schedule_id,
        sequence=sequence,
        station_id=station_id,
        route_station_id=route_station_id,
        arrival_time_minutes=arrival_min,
        departure_time_minutes=departure_min,
        arrival_day_offset=arrival_offset,
        departure_day_offset=departure_offset,
        route_station_distance_from_start_km=rs_dist_km,
        route_station_edge_id=None,
        schedule_distance_from_origin_km=sched_dist_km,
        schedule_route_progress=route_progress,
    )


def _train(stops: list[StopInput], route_dist_km: float = 100.0) -> TrainBuildInput:
    return TrainBuildInput(
        train_id=1, route_id=1, route_distance_km=route_dist_km, stops=stops
    )


# ---------------------------------------------------------------------------
# Absolute-minutes computation
# ---------------------------------------------------------------------------


class TestAbsoluteMinutes:
    def test_same_day(self) -> None:
        stops = [
            _stop(schedule_id=1, sequence=0, departure_min=600, rs_dist_km=0.0),
            _stop(schedule_id=2, sequence=1, arrival_min=700, rs_dist_km=50.0),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        moves = [s for s in run.segments if s.segment_type == "move"]
        assert len(moves) == 1
        assert moves[0].absolute_start_minutes == 600  # 600 + 0*1440
        assert moves[0].absolute_end_minutes == 700

    def test_overnight_day_offset(self) -> None:
        # Train departs 23:00 day 0, arrives 02:00 day 1
        stops = [
            _stop(
                schedule_id=1,
                sequence=0,
                departure_min=1380,
                departure_offset=0,
                rs_dist_km=0.0,
            ),
            _stop(
                schedule_id=2,
                sequence=1,
                arrival_min=120,
                arrival_offset=1,
                rs_dist_km=50.0,
            ),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        moves = [s for s in run.segments if s.segment_type == "move"]
        assert len(moves) == 1
        # 1380 + 0*1440 = 1380; 120 + 1*1440 = 1560
        assert moves[0].absolute_start_minutes == 1380
        assert moves[0].absolute_end_minutes == 1560


# ---------------------------------------------------------------------------
# Dwell segment generation
# ---------------------------------------------------------------------------


class TestDwellSegments:
    def test_dwell_created_when_arr_lt_dep(self) -> None:
        stops = [
            _stop(schedule_id=1, sequence=0, departure_min=600, rs_dist_km=0.0),
            _stop(
                schedule_id=2,
                sequence=1,
                arrival_min=700,
                departure_min=710,
                rs_dist_km=50.0,
            ),
            _stop(schedule_id=3, sequence=2, arrival_min=800, rs_dist_km=100.0),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        dwells = [s for s in run.segments if s.segment_type == "dwell"]
        assert len(dwells) == 1
        d = dwells[0]
        assert d.from_station_id == d.to_station_id
        assert d.absolute_start_minutes == 700
        assert d.absolute_end_minutes == 710
        assert d.planned_speed_kmh == 0.0

    def test_no_dwell_when_only_departure_set(self) -> None:
        stops = [
            _stop(schedule_id=1, sequence=0, departure_min=600, rs_dist_km=0.0),
            _stop(schedule_id=2, sequence=1, departure_min=700, rs_dist_km=100.0),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        assert not [s for s in run.segments if s.segment_type == "dwell"]

    def test_no_dwell_when_dep_equals_arr(self) -> None:
        stops = [
            _stop(schedule_id=1, sequence=0, departure_min=600, rs_dist_km=0.0),
            _stop(
                schedule_id=2,
                sequence=1,
                arrival_min=700,
                departure_min=700,  # equal — no dwell
                rs_dist_km=50.0,
            ),
            _stop(schedule_id=3, sequence=2, arrival_min=800, rs_dist_km=100.0),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        assert not [s for s in run.segments if s.segment_type == "dwell"]


# ---------------------------------------------------------------------------
# Movement segment generation
# ---------------------------------------------------------------------------


class TestMovementSegments:
    def test_basic_two_stop_segment(self) -> None:
        stops = [
            _stop(schedule_id=1, sequence=0, departure_min=600, rs_dist_km=0.0),
            _stop(schedule_id=2, sequence=1, arrival_min=660, rs_dist_km=50.0),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        assert run.status == "ready"
        moves = [s for s in run.segments if s.segment_type == "move"]
        assert len(moves) == 1
        mv = moves[0]
        assert mv.from_schedule_id == 1
        assert mv.to_schedule_id == 2
        assert mv.absolute_start_minutes == 600
        assert mv.absolute_end_minutes == 660
        # 50 km / 1 h = 50 km/h
        assert mv.planned_speed_kmh == pytest.approx(50.0, rel=1e-2)

    def test_geom_fractions_from_route_stations(self) -> None:
        stops = [
            _stop(schedule_id=1, sequence=0, departure_min=600, rs_dist_km=0.0),
            _stop(schedule_id=2, sequence=1, arrival_min=660, rs_dist_km=100.0),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        moves = [s for s in run.segments if s.segment_type == "move"]
        assert moves[0].start_geom_fraction == pytest.approx(0.0)
        assert moves[0].end_geom_fraction == pytest.approx(1.0)

    def test_move_uses_departure_as_start_when_available(self) -> None:
        # The move from stop 1 should start at departure (605), not arrival (600).
        stops = [
            _stop(
                schedule_id=1,
                sequence=0,
                arrival_min=600,
                departure_min=605,
                rs_dist_km=0.0,
            ),
            _stop(schedule_id=2, sequence=1, arrival_min=660, rs_dist_km=50.0),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        moves = [s for s in run.segments if s.segment_type == "move"]
        assert moves[0].absolute_start_minutes == 605

    def test_move_uses_arrival_as_end_when_available(self) -> None:
        # The move into stop 2 should end at arrival (660), not departure (665).
        stops = [
            _stop(schedule_id=1, sequence=0, departure_min=600, rs_dist_km=0.0),
            _stop(
                schedule_id=2,
                sequence=1,
                arrival_min=660,
                departure_min=665,
                rs_dist_km=50.0,
            ),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        moves = [s for s in run.segments if s.segment_type == "move"]
        assert moves[0].absolute_end_minutes == 660


# ---------------------------------------------------------------------------
# Reverse-direction trains
# ---------------------------------------------------------------------------


class TestReverseDirection:
    def test_descending_distance_not_flagged(self) -> None:
        """A train running in the descending direction has decreasing distances.
        This is valid and must NOT produce WARN_NON_MONOTONIC_DISTANCE.
        """
        stops = [
            _stop(schedule_id=1, sequence=0, departure_min=600, rs_dist_km=100.0),
            _stop(schedule_id=2, sequence=1, arrival_min=700, rs_dist_km=0.0),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        assert run.status in {"ready", "degraded"}
        assert WARN_NON_MONOTONIC_DISTANCE not in run.warnings

    def test_direction_reversal_within_run_is_flagged(self) -> None:
        """Distances going up, then down, then up → non-monotonic → warning."""
        stops = [
            _stop(schedule_id=1, sequence=0, departure_min=600, rs_dist_km=0.0),
            _stop(
                schedule_id=2,
                sequence=1,
                arrival_min=640,
                departure_min=645,
                rs_dist_km=50.0,
            ),
            _stop(
                schedule_id=3, sequence=2, arrival_min=700, rs_dist_km=30.0
            ),  # goes back
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        assert WARN_NON_MONOTONIC_DISTANCE in run.warnings


# ---------------------------------------------------------------------------
# Speed warnings
# ---------------------------------------------------------------------------


class TestSuspiciousSpeed:
    def test_high_speed_flagged(self) -> None:
        # 90 km in 1 minute = 5400 km/h → suspicious (> 200 km/h)
        stops = [
            _stop(schedule_id=1, sequence=0, departure_min=600, rs_dist_km=0.0),
            _stop(schedule_id=2, sequence=1, arrival_min=601, rs_dist_km=90.0),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        assert WARN_SUSPICIOUS_SPEED in run.warnings

    def test_normal_speed_not_flagged(self) -> None:
        # 100 km in 120 minutes ≈ 50 km/h — realistic
        stops = [
            _stop(schedule_id=1, sequence=0, departure_min=600, rs_dist_km=0.0),
            _stop(schedule_id=2, sequence=1, arrival_min=720, rs_dist_km=100.0),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        assert WARN_SUSPICIOUS_SPEED not in run.warnings


# ---------------------------------------------------------------------------
# Degraded plans — missing route_station_id
# ---------------------------------------------------------------------------


class TestDegradedQuality:
    def test_missing_route_station_id_appears_in_warnings(self) -> None:
        """When stops have no route_station_id, the run warns about it."""
        stops = [
            _stop(
                schedule_id=1,
                sequence=0,
                route_station_id=None,
                departure_min=600,
                sched_dist_km=0.0,
            ),
            _stop(
                schedule_id=2,
                sequence=1,
                route_station_id=None,
                arrival_min=660,
                sched_dist_km=50.0,
            ),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        all_warnings = run.warnings + [w for seg in run.segments for w in seg.warnings]
        assert any(WARN_MISSING_ROUTE_STATION_ID in w for w in all_warnings)

    def test_all_missing_route_station_produces_degraded_not_invalid(self) -> None:
        stops = [
            _stop(
                schedule_id=1,
                sequence=0,
                route_station_id=None,
                departure_min=600,
                sched_dist_km=0.0,
            ),
            _stop(
                schedule_id=2,
                sequence=1,
                route_station_id=None,
                arrival_min=660,
                sched_dist_km=50.0,
            ),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        # Should produce at least one move segment — not invalid
        assert any(s.segment_type == "move" for s in run.segments)
        assert run.status in {"ready", "degraded"}


# ---------------------------------------------------------------------------
# Invalid plans
# ---------------------------------------------------------------------------


class TestInvalidPlan:
    def test_fewer_than_2_usable_stops(self) -> None:
        stops = [_stop(schedule_id=1, sequence=0, arrival_min=600, rs_dist_km=0.0)]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        assert run.status == "invalid"

    def test_stops_with_no_time_data(self) -> None:
        stops = [
            _stop(schedule_id=1, sequence=0),  # no arrival/departure times
            _stop(schedule_id=2, sequence=1),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        assert run.status == "invalid"

    def test_zero_duration_move_produces_warning(self) -> None:
        stops = [
            _stop(schedule_id=1, sequence=0, departure_min=700, rs_dist_km=0.0),
            _stop(
                schedule_id=2, sequence=1, arrival_min=700, rs_dist_km=50.0
            ),  # same time
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        assert WARN_ZERO_OR_NEGATIVE_DURATION in run.warnings


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_identical_inputs_identical_outputs(self) -> None:
        stops = [
            _stop(schedule_id=1, sequence=0, departure_min=600, rs_dist_km=0.0),
            _stop(schedule_id=2, sequence=1, arrival_min=660, rs_dist_km=50.0),
        ]
        train = _train(stops)
        run1 = build_movement_plan(train, _PLAN_VERSION, _TOPO_VERSION)
        run2 = build_movement_plan(train, _PLAN_VERSION, _TOPO_VERSION)

        assert run1.status == run2.status
        assert run1.quality_score == run2.quality_score
        assert len(run1.segments) == len(run2.segments)
        for s1, s2 in zip(run1.segments, run2.segments):
            assert s1.segment_type == s2.segment_type
            assert s1.absolute_start_minutes == s2.absolute_start_minutes
            assert s1.absolute_end_minutes == s2.absolute_end_minutes
            assert s1.planned_speed_kmh == s2.planned_speed_kmh


# ---------------------------------------------------------------------------
# Fallback position resolution
# ---------------------------------------------------------------------------


class TestPositionResolution:
    def test_uses_schedule_distance_when_no_route_station(self) -> None:
        stops = [
            _stop(
                schedule_id=1,
                sequence=0,
                route_station_id=None,
                departure_min=600,
                sched_dist_km=0.0,
            ),
            _stop(
                schedule_id=2,
                sequence=1,
                route_station_id=None,
                arrival_min=660,
                sched_dist_km=50.0,
            ),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        moves = [s for s in run.segments if s.segment_type == "move"]
        assert len(moves) == 1
        assert moves[0].start_geom_fraction == pytest.approx(0.0)
        assert moves[0].end_geom_fraction == pytest.approx(0.5)

    def test_uses_route_progress_when_no_distance(self) -> None:
        stops = [
            _stop(
                schedule_id=1,
                sequence=0,
                route_station_id=None,
                departure_min=600,
                route_progress=0.0,
            ),
            _stop(
                schedule_id=2,
                sequence=1,
                route_station_id=None,
                arrival_min=660,
                route_progress=0.75,
            ),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        moves = [s for s in run.segments if s.segment_type == "move"]
        assert len(moves) == 1
        assert moves[0].start_geom_fraction == pytest.approx(0.0)
        assert moves[0].end_geom_fraction == pytest.approx(0.75)

    def test_linear_index_fallback_when_all_absent(self) -> None:
        # route_station_id=None, no distances, no route_progress → linear index
        stops = [
            _stop(
                schedule_id=1,
                sequence=0,
                route_station_id=None,
                departure_min=600,
            ),
            _stop(
                schedule_id=2,
                sequence=1,
                route_station_id=None,
                arrival_min=660,
            ),
        ]
        run = build_movement_plan(_train(stops), _PLAN_VERSION, _TOPO_VERSION)
        moves = [s for s in run.segments if s.segment_type == "move"]
        assert len(moves) == 1
        # With 2 stops: index 0 → 0.0, index 1 → 1.0
        assert moves[0].start_geom_fraction == pytest.approx(0.0)
        assert moves[0].end_geom_fraction == pytest.approx(1.0)
