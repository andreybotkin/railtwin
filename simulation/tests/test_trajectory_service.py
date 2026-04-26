"""Pure-function tests for :mod:`app.services.trajectory_service`.

These cover the invariants the frontend relies on:

* monotonic ``geom_fraction`` along moving segments;
* dwell windows emit frames with ``speed_kmh == 0`` and constant position;
* ``ConsistSpec`` total length matches ``locomotive + car_count * car_length``;
* anchors align with the full schedule (arrival + departure events for every
    stop, including past and future events relative to ``current_minutes``);
* the trajectory terminates when the last schedule entry is reached.
"""

from __future__ import annotations

from datetime import time
from types import SimpleNamespace
from typing import Any

import pytest

from app.domain.trajectory import (
    ConsistSpec,
    Trajectory,
    resolve_consist,
)
from app.services.trajectory_service import (
    build_stop_sequence,
    build_trajectory,
    train_type_color,
)

# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #


def _make_train(
    *,
    train_id: int = 101,
    train_number: str = "10",
    train_type: str = "rapid",
    name: str | None = "Bangkok → Ayutthaya",
    current_route_id: int | None = 1,
) -> Any:
    """Build a minimal train-like object without hitting the DB."""

    return SimpleNamespace(
        id=train_id,
        train_number=train_number,
        train_type=train_type,
        name=name,
        capacity=None,
        operator="State Railway of Thailand",
        source="test",
        source_url=None,
        service_notes=None,
        current_route_id=current_route_id,
    )


def _make_schedule(
    *,
    train_id: int = 101,
    sequence: int,
    station_name: str,
    arrival: time | None,
    departure: time | None,
    station_id: int | None = None,
    day_of_week: list[int] | None = None,
    route_progress: float | None = None,
) -> Any:
    return SimpleNamespace(
        train_id=train_id,
        station_id=station_id,
        route_station_id=None,
        station_name=station_name,
        arrival_time=arrival,
        departure_time=departure,
        arrival_day_offset=0,
        departure_day_offset=0,
        day_of_week=day_of_week,
        platform=None,
        sequence=sequence,
        distance_from_origin_km=None,
        route_progress=route_progress,
        station=None,
        route_station=None,
    )


def _three_stop_schedule() -> list[Any]:
    """Bangkok (10:00) → Ayutthaya (11:00-11:05) → Lopburi (12:30)."""
    return [
        _make_schedule(
            sequence=0,
            station_name="Bangkok",
            arrival=None,
            departure=time(10, 0),
            route_progress=0.0,
        ),
        _make_schedule(
            sequence=1,
            station_name="Ayutthaya",
            arrival=time(11, 0),
            departure=time(11, 5),
            route_progress=0.5,
        ),
        _make_schedule(
            sequence=2,
            station_name="Lopburi",
            arrival=time(12, 30),
            departure=None,
            route_progress=1.0,
        ),
    ]


# A straight-ish polyline from Hua Lamphong → Ayutthaya → Lopburi (approx).
_POLYLINE: list[list[float]] = [
    [100.5172, 13.7395],  # Bangkok
    [100.5675, 14.3551],  # Ayutthaya
    [100.6200, 14.7995],  # Lopburi
]


# --------------------------------------------------------------------------- #
# Core tests                                                                   #
# --------------------------------------------------------------------------- #


def test_consist_total_length_matches_formula() -> None:
    consist = ConsistSpec.build(
        locomotive_length_m=20.0,
        car_count=10,
        car_length_m=24.0,
    )
    assert consist.total_length_m == pytest.approx(20.0 + 10 * 24.0)


def test_resolve_consist_falls_back_to_ordinary_for_unknown_types() -> None:
    unknown = resolve_consist("deluxe_extraordinary")
    ordinary = resolve_consist("ordinary")
    assert unknown == ordinary


def test_train_type_color_returns_palette_entry() -> None:
    assert train_type_color("rapid") == "#1E88E5"
    assert train_type_color(None) == "#2196F3"
    assert train_type_color("   RAPID  ") == "#1E88E5"


def test_build_trajectory_produces_monotonic_fractions_between_stops() -> None:
    train = _make_train(train_type="rapid")
    schedules = _three_stop_schedule()
    # Mid-morning, between Bangkok departure and Ayutthaya arrival.
    current_minutes = 10 * 60 + 30  # 10:30

    trajectory = build_trajectory(
        train,
        schedules,
        _POLYLINE,
        route_distance_km=130.0,
        delay=0,
        current_minutes=current_minutes,
        now_unix_ms=1_700_000_000_000,
    )

    assert isinstance(trajectory, Trajectory)
    assert trajectory.train_id == 101
    assert len(trajectory.frames) >= 2
    # Moving frames should be monotonic non-decreasing along the polyline.
    fractions = [f.geom_fraction for f in trajectory.frames]
    for a, b in zip(fractions, fractions[1:], strict=False):
        assert b + 1e-9 >= a, fractions

    # Head frame of a moving train has speed > 0 and status="moving".
    assert trajectory.frames[0].status == "moving"
    assert trajectory.frames[0].speed_kmh > 0.0

    # ConsistSpec for a rapid train matches the canonical spec.
    canonical = resolve_consist("rapid")
    assert trajectory.consist == canonical


def test_build_trajectory_dwell_frames_have_zero_speed_and_fixed_position() -> None:
    train = _make_train(train_type="rapid")
    schedules = _three_stop_schedule()
    # 11:02 — inside the Ayutthaya dwell window (11:00 – 11:05).
    current_minutes = 11 * 60 + 2

    trajectory = build_trajectory(
        train,
        schedules,
        _POLYLINE,
        route_distance_km=130.0,
        delay=0,
        current_minutes=current_minutes,
        now_unix_ms=1_700_000_000_000,
    )

    assert trajectory is not None
    head = trajectory.frames[0]
    assert head.status == "dwelling"
    assert head.speed_kmh == 0.0
    # Dwell clamps geom_fraction to the stop's fraction — here Ayutthaya @0.5.
    assert head.geom_fraction == pytest.approx(0.5, abs=1e-4)


def test_build_trajectory_returns_none_when_service_has_ended() -> None:
    train = _make_train()
    schedules = _three_stop_schedule()
    # 14:00 — well past the last arrival at 12:30.
    current_minutes = 14 * 60

    trajectory = build_trajectory(
        train,
        schedules,
        _POLYLINE,
        route_distance_km=130.0,
        delay=0,
        current_minutes=current_minutes,
        now_unix_ms=1_700_000_000_000,
    )
    assert trajectory is None


def test_build_trajectory_anchors_cover_full_route_schedule() -> None:
    train = _make_train()
    schedules = _three_stop_schedule()
    current_minutes = (
        10 * 60 + 53
    )  # 10:53 — Bangkok is past, Ayutthaya/Lopburi are ahead.

    trajectory = build_trajectory(
        train,
        schedules,
        _POLYLINE,
        route_distance_km=130.0,
        delay=0,
        current_minutes=current_minutes,
        now_unix_ms=1_700_000_000_000,
    )

    assert trajectory is not None

    offsets = [
        anchor.t_ms - trajectory.generated_at_ms for anchor in trajectory.anchors
    ]
    assert min(offsets) < 0
    assert max(offsets) > 0

    anchor_stations = {a.station_name for a in trajectory.anchors}
    assert anchor_stations == {"Bangkok", "Ayutthaya", "Lopburi"}

    anchor_events = {(a.station_name, a.event) for a in trajectory.anchors}
    assert anchor_events == {
        ("Bangkok", "departure"),
        ("Ayutthaya", "arrival"),
        ("Ayutthaya", "departure"),
        ("Lopburi", "arrival"),
    }


def test_build_trajectory_applies_delay_to_anchors_and_meta() -> None:
    train = _make_train()
    schedules = _three_stop_schedule()
    current_minutes = 10 * 60 + 30  # 10:30

    delayed = build_trajectory(
        train,
        schedules,
        _POLYLINE,
        route_distance_km=130.0,
        delay=15,
        current_minutes=current_minutes,
        now_unix_ms=1_700_000_000_000,
    )
    ontime = build_trajectory(
        train,
        schedules,
        _POLYLINE,
        route_distance_km=130.0,
        delay=0,
        current_minutes=current_minutes,
        now_unix_ms=1_700_000_000_000,
    )

    assert delayed is not None and ontime is not None
    assert delayed.meta.delay_minutes == 15

    def _ayutthaya_arrival(t: Trajectory) -> int | None:
        for a in t.anchors:
            if a.station_name == "Ayutthaya" and a.event == "arrival":
                return a.t_ms
        return None

    d_eta = _ayutthaya_arrival(delayed)
    o_eta = _ayutthaya_arrival(ontime)
    if d_eta is not None and o_eta is not None:
        # Delay pushes the arrival ~15 minutes later.
        assert d_eta - o_eta == pytest.approx(15 * 60 * 1000, abs=100)


def test_build_trajectory_uses_station_fallback_when_polyline_missing() -> None:
    train = _make_train()
    # Give schedules real station geometries so fallback can build a polyline.
    station_coords = [
        (100.5172, 13.7395),
        (100.5675, 14.3551),
        (100.6200, 14.7995),
    ]
    schedules = _three_stop_schedule()
    for schedule, (lon, lat) in zip(schedules, station_coords, strict=True):
        schedule.station = SimpleNamespace(
            id=schedule.sequence + 1,
            name=schedule.station_name,
            location=_FakeGeom(lon, lat),
        )

    trajectory = build_trajectory(
        train,
        schedules,
        route_coords=None,
        route_distance_km=None,
        delay=0,
        current_minutes=10 * 60 + 30,
        now_unix_ms=1_700_000_000_000,
    )
    assert trajectory is not None
    assert len(trajectory.route_coords) >= 2
    # The fallback uses station coordinates.
    first_lon, first_lat = trajectory.route_coords[0]
    assert first_lon == pytest.approx(station_coords[0][0], abs=1e-4)
    assert first_lat == pytest.approx(station_coords[0][1], abs=1e-4)


def test_build_trajectory_projects_stations_onto_polyline_when_available() -> None:
    """When schedule stations have real geometry, projection must override
    linear-by-index fractions.

    Hand-crafted scenario: three stops whose *stored* ``route_progress`` claims
    a uniform 0, 0.5, 1.0 split, but whose real coordinates place the middle
    station at ~70 % of the route. The builder should use the projected
    fraction (~0.7), not the falsy 0.5.
    """

    train = _make_train()
    # Polyline running ~west→east along the equator for easy math.
    polyline = [[100.0, 0.0], [101.0, 0.0]]

    # Middle station sits 70 % along the polyline.
    station_coords = [
        (100.0, 0.0),
        (100.7, 0.0),  # 70 %
        (101.0, 0.0),
    ]
    schedules = _three_stop_schedule()
    # Zero out route_progress so the projection path is the *only* source.
    for schedule in schedules:
        schedule.route_progress = None
    for schedule, (lon, lat) in zip(schedules, station_coords, strict=True):
        schedule.station = SimpleNamespace(
            id=schedule.sequence + 1,
            name=schedule.station_name,
            location=_FakeGeom(lon, lat),
        )

    trajectory = build_trajectory(
        train,
        schedules,
        polyline,
        route_distance_km=None,
        delay=0,
        current_minutes=10 * 60 + 30,  # 10:30 — between stop 0 and 1
        now_unix_ms=1_700_000_000_000,
    )

    assert trajectory is not None
    # Between stops 0 (10:00) and 1 (11:00) at 10:30 → halfway in time, so
    # geom_fraction should land at (0 + (0.7 - 0) * 0.5) = 0.35, NOT 0.25
    # (which is what linear-by-index would yield).
    head = trajectory.frames[0]
    assert head.geom_fraction == pytest.approx(0.35, abs=5e-3)


def test_stop_fractions_enforce_monotonicity() -> None:
    """A mid-sequence outlier must not push later fractions backwards."""

    from app.services.trajectory_service import _stop_fractions

    schedules = _three_stop_schedule()
    # Middle station projects ~east of the end-point (noise).
    station_coords = [
        (100.0, 0.0),
        (101.2, 0.0),  # noisy — would place middle *past* the end
        (101.0, 0.0),
    ]
    for schedule in schedules:
        schedule.route_progress = None
    for schedule, (lon, lat) in zip(schedules, station_coords, strict=True):
        schedule.station = SimpleNamespace(
            id=schedule.sequence + 1,
            name=schedule.station_name,
            location=_FakeGeom(lon, lat),
        )

    polyline = [[100.0, 0.0], [101.0, 0.0]]
    fractions = _stop_fractions(schedules, polyline, 111.0)
    # Must be non-decreasing.
    for a, b in zip(fractions, fractions[1:], strict=False):
        assert b >= a


def test_build_stop_sequence_marks_passed_boarding_pending_states() -> None:
    schedules = _three_stop_schedule()
    # 11:02 — Bangkok departed, Ayutthaya boarding, Lopburi pending.
    sequence = build_stop_sequence(schedules, delay=0, current_minutes=11 * 60 + 2)
    states = {item["station_name"]: item["state"] for item in sequence}
    assert states["Bangkok"] == "PASSED"
    assert states["Ayutthaya"] == "BOARDING"
    assert states["Lopburi"] == "PENDING"


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


class _FakeGeom:
    """Tiny stand-in for geoalchemy2 geometries used by the fallback path."""

    def __init__(self, lon: float, lat: float) -> None:
        self._lon = lon
        self._lat = lat

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - defensive
        raise AttributeError(name)


# Monkey-patch ``to_shape`` and ``Point`` behaviour for the fallback test: the
# real implementation expects a WKB geometry, so we intercept the import.
@pytest.fixture(autouse=True)
def _patch_to_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.trajectory_service as module

    def _to_shape(geom: _FakeGeom) -> Any:
        return SimpleNamespace(x=geom._lon, y=geom._lat)

    monkeypatch.setattr(module, "to_shape", _to_shape)
