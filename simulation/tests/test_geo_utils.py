"""Tests for :mod:`app.services.geo_utils`.

These guard the invariant the trajectory builder depends on: given a polyline
with Haversine-measured cumulative length ``L``, for any fraction ``f`` the
point returned by :func:`interpolate_position` sits at exactly ``f * L``
kilometres from the start along the geodesic. :func:`project_onto_polyline` is
the inverse: given a point, it returns the fraction that would reproduce it.
"""

from __future__ import annotations

import math

import pytest

from app.services import geo_utils


# Bangkok → Ayutthaya → Lopburi, ascending roughly NE.
_POLYLINE: list[list[float]] = [
    [100.5172, 13.7395],
    [100.5675, 14.3551],
    [100.6200, 14.7995],
]


def test_cumulative_haversine_is_monotonic_and_ends_at_total() -> None:
    cum = geo_utils.cumulative_haversine_km(_POLYLINE)
    assert cum[0] == 0.0
    for a, b in zip(cum, cum[1:]):
        assert b >= a
    # Total route is ~118 km (≈13.7°N → 14.8°N ≈ 1.1° of lat).
    assert cum[-1] > 100.0
    assert cum[-1] < 150.0


@pytest.mark.parametrize("fraction", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_interpolate_position_round_trips_through_project(fraction: float) -> None:
    lon, lat = geo_utils.interpolate_position(_POLYLINE, fraction)
    dist_km, projected_fraction = geo_utils.project_onto_polyline(
        _POLYLINE, lon, lat
    )
    assert projected_fraction == pytest.approx(fraction, abs=1e-3)
    total_km = geo_utils.cumulative_haversine_km(_POLYLINE)[-1]
    assert dist_km == pytest.approx(fraction * total_km, abs=total_km * 1e-3)


def test_project_off_polyline_snaps_to_nearest_vertex() -> None:
    # A point far to the west of Bangkok should project to ~fraction 0.
    _, frac_west = geo_utils.project_onto_polyline(_POLYLINE, 99.0, 13.7395)
    assert frac_west == pytest.approx(0.0, abs=1e-3)
    # A point east/north of Lopburi should project to ~fraction 1.
    _, frac_east = geo_utils.project_onto_polyline(_POLYLINE, 101.5, 14.9)
    assert frac_east == pytest.approx(1.0, abs=1e-3)


def test_interpolate_position_respects_haversine_midpoint() -> None:
    # The 0.5-fraction point must be at 0.5 * total-km from the start.
    total_km = geo_utils.cumulative_haversine_km(_POLYLINE)[-1]
    lon, lat = geo_utils.interpolate_position(_POLYLINE, 0.5)
    dist_from_start = geo_utils.haversine_km(
        _POLYLINE[0][0], _POLYLINE[0][1], lon, lat
    )
    # Haversine on a near-straight polyline approximates the cumulative
    # distance within ~1%, so allow a tolerance of 1 km over the ~120 km route.
    assert dist_from_start == pytest.approx(total_km * 0.5, abs=1.0)


def test_segment_distance_km_uses_absolute_delta() -> None:
    total_km = geo_utils.cumulative_haversine_km(_POLYLINE)[-1]
    # Distances are absolute so reversing start/end doesn't flip the sign.
    assert geo_utils.segment_distance_km(_POLYLINE, 0.2, 0.8) == pytest.approx(
        0.6 * total_km, abs=1e-9
    )
    assert geo_utils.segment_distance_km(_POLYLINE, 0.8, 0.2) == pytest.approx(
        0.6 * total_km, abs=1e-9
    )


def test_great_circle_bearing_points_north_for_northbound_polyline() -> None:
    bearing = geo_utils.great_circle_bearing(
        (_POLYLINE[0][0], _POLYLINE[0][1]),
        (_POLYLINE[-1][0], _POLYLINE[-1][1]),
    )
    # The polyline moves slightly east but mostly north, so bearing ≈ 0–30°.
    assert 0.0 <= bearing <= 30.0 or 330.0 <= bearing <= 360.0


def test_project_degenerate_inputs_return_zero() -> None:
    assert geo_utils.project_onto_polyline([], 0.0, 0.0) == (0.0, 0.0)
    assert geo_utils.project_onto_polyline([[0, 0]], 1.0, 1.0) == (0.0, 0.0)


def test_interpolate_position_handles_edge_cases() -> None:
    assert geo_utils.interpolate_position([], 0.5) == (0.0, 0.0)
    assert geo_utils.interpolate_position([[1, 2]], 0.5) == (1.0, 2.0)
    assert geo_utils.interpolate_position(_POLYLINE, -0.1) == (
        _POLYLINE[0][0],
        _POLYLINE[0][1],
    )
    assert geo_utils.interpolate_position(_POLYLINE, 1.5) == (
        _POLYLINE[-1][0],
        _POLYLINE[-1][1],
    )


def test_haversine_km_symmetric_and_zero_for_equal_points() -> None:
    assert geo_utils.haversine_km(100.0, 13.0, 100.0, 13.0) == 0.0
    forward = geo_utils.haversine_km(100.0, 13.0, 101.0, 14.0)
    reverse = geo_utils.haversine_km(101.0, 14.0, 100.0, 13.0)
    assert forward == pytest.approx(reverse)
    # 1° lon × 1° lat at ~13°N ≈ 152 km.
    assert forward == pytest.approx(152.0, abs=5.0)
    assert not math.isnan(forward)
