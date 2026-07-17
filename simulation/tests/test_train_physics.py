from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.train_physics import (
    InfeasibleLegError,
    build_track_profile,
    integrate_dem_elevations,
    resolve_train_physics,
    simulate_leg,
)


def _train(**overrides):  # noqa: ANN003, ANN202
    values = {
        "train_type": "ordinary",
        "capacity": 400,
        "passenger_load": 200,
        "locomotive_mass_t": 80,
        "rolling_stock_mass_t": 300,
        "horsepower": 2500,
        "max_tractive_effort_kn": 250,
        "max_brake_deceleration_mps2": 0.7,
        "max_speed_kmh": 120,
        "passenger_mass_kg": 75,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_passenger_load_contributes_to_total_mass() -> None:
    empty = resolve_train_physics(_train(passenger_load=0))
    loaded = resolve_train_physics(_train(passenger_load=200))
    assert loaded.mass_kg - empty.mass_kg == pytest.approx(15_000)


def test_dem_sampling_fills_voids_and_preserves_existing_z() -> None:
    coords = [[100.0, 13.0, 8.0], [100.1, 13.1], [100.2, 13.2]]

    def sample(lon: float, _lat: float) -> float | None:
        return None if lon < 100.15 else 28.0

    enriched = integrate_dem_elevations(coords, sample)
    assert enriched[0][2] == 8.0
    assert enriched[1][2] == pytest.approx(18.0)
    assert enriched[2][2] == 28.0


def test_profile_exposes_grade_and_nested_speed_zone() -> None:
    track = build_track_profile(
        [[100.0, 13.0, 0.0], [100.1, 13.0, 100.0]],
        10_000.0,
        [
            {
                "start_km": 0,
                "end_km": 10,
                "max_speed_kmh": 100,
                "speed_limit_zones": [
                    {"start_m": 4000, "end_m": 6000, "max_speed_kmh": 40}
                ],
            }
        ],
    )
    assert track.grade_at(5000) == pytest.approx(0.01, rel=0.05)
    assert track.speed_limit_at(5000) == 40
    assert track.speed_limit_at(2000) == 100


def test_simulation_accelerates_and_brakes_to_stop() -> None:
    spec = resolve_train_physics(_train())
    track = build_track_profile(
        [[100.0, 13.0], [100.1, 13.0]],
        10_000.0,
        [{"start_km": 0, "end_km": 10, "max_speed_kmh": 90}],
    )
    states = simulate_leg(0.0, 10_000.0, 900.0, spec, track)
    assert max(state.speed_mps for state in states) > 5.0
    assert max(state.speed_mps for state in states) <= 90 / 3.6 + 1e-6
    assert states[-1].distance_m == pytest.approx(10_000.0, abs=0.1)
    assert states[-1].speed_mps == 0.0


def test_rejects_physically_impossible_schedule() -> None:
    spec = resolve_train_physics(_train(max_speed_kmh=60))
    track = build_track_profile([[100.0, 13.0], [100.1, 13.0]], 10_000.0, None)
    with pytest.raises(InfeasibleLegError):
        simulate_leg(0.0, 10_000.0, 60.0, spec, track)
