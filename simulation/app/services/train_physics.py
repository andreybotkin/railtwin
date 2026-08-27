"""Pure physics primitives used by trajectory generation.

The module deliberately has no database or clock dependencies.  Route data can
come from a DEM-enriched 3D polyline or from per-edge elevation profiles.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from app.services import geo_utils

_G = 9.80665


@dataclass(frozen=True)
class TrainPhysicsSpec:
    mass_kg: float
    power_w: float
    max_tractive_force_n: float
    max_brake_deceleration_mps2: float
    max_speed_kmh: float
    passenger_load: int


@dataclass(frozen=True)
class ProfilePoint:
    distance_m: float
    elevation_m: float


@dataclass(frozen=True)
class SpeedZone:
    start_m: float
    end_m: float
    limit_kmh: float


@dataclass(frozen=True)
class MotionState:
    elapsed_s: float
    distance_m: float
    speed_mps: float


class InfeasibleLegError(ValueError):
    """The train cannot cover a scheduled leg within its physical limits."""


_DEFAULTS: dict[str, tuple[float, float, float, float, float]] = {
    # locomotive tonnes, trailing-stock tonnes, horsepower, tractive kN, max km/h
    "special_express": (84.0, 480.0, 2900.0, 270.0, 160.0),
    "express": (84.0, 440.0, 2900.0, 270.0, 140.0),
    "rapid": (84.0, 400.0, 2500.0, 250.0, 120.0),
    "ordinary": (84.0, 320.0, 2500.0, 250.0, 100.0),
    "commuter": (84.0, 240.0, 2500.0, 250.0, 100.0),
}


def resolve_train_physics(train: Any) -> TrainPhysicsSpec:
    """Resolve an explicit train specification, with type-based fallbacks."""

    key = str(getattr(train, "train_type", "ordinary") or "ordinary").lower()
    loco_t, stock_t, hp, effort_kn, max_speed = _DEFAULTS.get(
        key, _DEFAULTS["ordinary"]
    )
    capacity = int(getattr(train, "capacity", 0) or 0)
    load = getattr(train, "passenger_load", None)
    passenger_load = max(0, int(load if load is not None else capacity * 0.65))
    passenger_mass_kg = float(getattr(train, "passenger_mass_kg", 75.0) or 75.0)
    locomotive_mass_t = float(getattr(train, "locomotive_mass_t", loco_t) or loco_t)
    rolling_stock_mass_t = float(
        getattr(train, "rolling_stock_mass_t", stock_t) or stock_t
    )
    return TrainPhysicsSpec(
        mass_kg=(locomotive_mass_t + rolling_stock_mass_t) * 1000.0
        + passenger_load * passenger_mass_kg,
        power_w=float(getattr(train, "horsepower", hp) or hp) * 745.699872,
        max_tractive_force_n=float(
            getattr(train, "max_tractive_effort_kn", effort_kn) or effort_kn
        )
        * 1000.0,
        max_brake_deceleration_mps2=float(
            getattr(train, "max_brake_deceleration_mps2", 0.75) or 0.75
        ),
        max_speed_kmh=float(getattr(train, "max_speed_kmh", max_speed) or max_speed),
        passenger_load=passenger_load,
    )


def integrate_dem_elevations(
    coords: Sequence[Sequence[float]],
    sampler: Callable[[float, float], float | None],
) -> list[list[float]]:
    """Return ``[lon, lat, elevation]`` coordinates sampled from a DEM.

    Existing finite Z values are retained.  Missing DEM cells are interpolated
    between their nearest valid neighbours (or filled from the nearest end).
    """

    enriched: list[list[float]] = []
    elevations: list[float | None] = []
    for coord in coords:
        lon, lat = float(coord[0]), float(coord[1])
        existing = float(coord[2]) if len(coord) > 2 else None
        value = (
            existing
            if existing is not None and math.isfinite(existing)
            else sampler(lon, lat)
        )
        elevations.append(
            float(value) if value is not None and math.isfinite(value) else None
        )
        enriched.append([lon, lat, 0.0])
    valid = [i for i, value in enumerate(elevations) if value is not None]
    if not valid:
        return enriched
    for i, value in enumerate(elevations):
        if value is not None:
            enriched[i][2] = value
            continue
        left = max((j for j in valid if j < i), default=valid[0])
        right = min((j for j in valid if j > i), default=valid[-1])
        if left == right:
            enriched[i][2] = float(elevations[left] or 0.0)
        else:
            left_elevation = elevations[left]
            right_elevation = elevations[right]
            # ``valid`` only contains indices whose elevation is present.
            assert left_elevation is not None
            assert right_elevation is not None
            ratio = (i - left) / (right - left)
            enriched[i][2] = left_elevation + (right_elevation - left_elevation) * ratio
    return enriched


class TrackProfile:
    def __init__(
        self,
        *,
        length_m: float,
        elevations: Sequence[ProfilePoint],
        speed_zones: Sequence[SpeedZone],
        default_speed_kmh: float = 120.0,
    ) -> None:
        self.length_m = length_m
        self.elevations = sorted(elevations, key=lambda point: point.distance_m)
        self.speed_zones = sorted(speed_zones, key=lambda zone: zone.start_m)
        self.default_speed_kmh = default_speed_kmh

    def elevation_at(self, distance_m: float) -> float:
        if not self.elevations:
            return 0.0
        d = max(0.0, min(self.length_m, distance_m))
        if d <= self.elevations[0].distance_m:
            return self.elevations[0].elevation_m
        for left, right in zip(self.elevations, self.elevations[1:], strict=False):
            if d <= right.distance_m:
                span = right.distance_m - left.distance_m
                ratio = 0.0 if span <= 0 else (d - left.distance_m) / span
                return left.elevation_m + (right.elevation_m - left.elevation_m) * ratio
        return self.elevations[-1].elevation_m

    def grade_at(self, distance_m: float, direction: float = 1.0) -> float:
        window = min(50.0, max(5.0, self.length_m / 1000.0))
        low = max(0.0, distance_m - window)
        high = min(self.length_m, distance_m + window)
        if high <= low:
            return 0.0
        return (
            direction
            * (self.elevation_at(high) - self.elevation_at(low))
            / (high - low)
        )

    def speed_limit_at(self, distance_m: float) -> float:
        limits = [
            zone.limit_kmh
            for zone in self.speed_zones
            if zone.start_m <= distance_m <= zone.end_m
        ]
        return min(limits, default=self.default_speed_kmh)

    def permitted_speed_mps(
        self,
        distance_m: float,
        destination_m: float,
        direction: float,
        brake_mps2: float,
    ) -> float:
        remaining = abs(destination_m - distance_m)
        permitted = math.sqrt(max(0.0, 2.0 * brake_mps2 * remaining))
        permitted = min(permitted, self.speed_limit_at(distance_m) / 3.6)
        # Start braking before a lower limit, rather than only after entering it.
        for zone in self.speed_zones:
            boundary = zone.start_m if direction > 0 else zone.end_m
            ahead = direction * (boundary - distance_m)
            if 0.0 < ahead < remaining:
                approach = math.sqrt(
                    (zone.limit_kmh / 3.6) ** 2 + 2.0 * brake_mps2 * ahead
                )
                permitted = min(permitted, approach)
        return permitted


def build_track_profile(
    coords: Sequence[Sequence[float]],
    route_length_m: float,
    route_segments: Sequence[dict[str, Any]] | None,
) -> TrackProfile:
    """Build a continuous grade and speed profile from cached route data."""

    elevations: list[ProfilePoint] = []
    if len(coords) >= 2 and any(len(coord) > 2 for coord in coords):
        cumulative = [0.0]
        for left, right in pairwise(coords):
            cumulative.append(
                cumulative[-1]
                + geo_utils.haversine_km(left[0], left[1], right[0], right[1]) * 1000.0
            )
        geometric_length = cumulative[-1] or route_length_m
        elevations = [
            ProfilePoint(
                distance_m=(distance / geometric_length) * route_length_m,
                elevation_m=float(coord[2]) if len(coord) > 2 else 0.0,
            )
            for distance, coord in zip(cumulative, coords, strict=False)
        ]

    zones: list[SpeedZone] = []
    for segment in route_segments or []:
        start_m = float(segment.get("start_km") or 0.0) * 1000.0
        end_m = float(segment.get("end_km") or segment.get("start_km") or 0.0) * 1000.0
        limit = segment.get("max_speed_kmh")
        if limit is not None and float(limit) > 0:
            zones.append(SpeedZone(start_m, end_m, float(limit)))
        local_profile = segment.get("elevation_profile") or []
        for point in local_profile:
            if isinstance(point, dict):
                offset = float(point.get("distance_m") or 0.0)
                elevation = point.get("elevation_m")
            else:
                offset, elevation = float(point[0]), point[1]
            if elevation is not None:
                elevations.append(ProfilePoint(start_m + offset, float(elevation)))
        for zone in segment.get("speed_limit_zones") or []:
            local_start = float(zone.get("start_m") or 0.0)
            local_end = float(zone.get("end_m") or (end_m - start_m))
            zone_limit = float(zone.get("max_speed_kmh") or 0.0)
            if zone_limit > 0:
                zones.append(
                    SpeedZone(start_m + local_start, start_m + local_end, zone_limit)
                )
    if not elevations:
        elevations = [ProfilePoint(0.0, 0.0), ProfilePoint(route_length_m, 0.0)]
    return TrackProfile(
        length_m=route_length_m,
        elevations=elevations,
        speed_zones=zones,
    )


def _run_leg(
    start_m: float,
    end_m: float,
    duration_s: float,
    spec: TrainPhysicsSpec,
    track: TrackProfile,
    cruise_cap_mps: float,
    *,
    record: bool,
) -> list[MotionState]:
    direction = 1.0 if end_m >= start_m else -1.0
    distance = start_m
    speed = 0.0
    elapsed = 0.0
    states = [MotionState(0.0, distance, speed)]
    dt_base = min(2.0, max(0.25, duration_s / 1200.0))
    while elapsed < duration_s - 1e-9:
        dt = min(dt_base, duration_s - elapsed)
        remaining = direction * (end_m - distance)
        if remaining <= 0.05:
            distance, speed = end_m, 0.0
        else:
            permitted = min(
                cruise_cap_mps,
                spec.max_speed_kmh / 3.6,
                track.permitted_speed_mps(
                    distance,
                    end_m,
                    direction,
                    spec.max_brake_deceleration_mps2,
                ),
            )
            if speed > permitted + 0.05:
                acceleration = -spec.max_brake_deceleration_mps2
            else:
                traction = min(
                    spec.max_tractive_force_n,
                    spec.power_w / max(speed, 2.0),
                )
                rolling = 0.0018 * spec.mass_kg * _G
                grade_force = spec.mass_kg * _G * track.grade_at(distance, direction)
                acceleration = max(
                    -0.15,
                    min(0.65, (traction - rolling - grade_force) / spec.mass_kg),
                )
                if speed >= permitted:
                    acceleration = min(acceleration, 0.0)
            new_speed = max(0.0, min(permitted, speed + acceleration * dt))
            advance = (speed + new_speed) * 0.5 * dt
            distance += direction * min(remaining, advance)
            speed = 0.0 if abs(end_m - distance) <= 0.05 else new_speed
        elapsed += dt
        if record:
            states.append(MotionState(elapsed, distance, speed))
    return states if record else [MotionState(elapsed, distance, speed)]


def simulate_leg(
    start_m: float,
    end_m: float,
    duration_s: float,
    spec: TrainPhysicsSpec,
    track: TrackProfile,
) -> list[MotionState]:
    """Plan a schedule-aligned leg under traction, grade, limits and braking."""

    if duration_s <= 0 or abs(end_m - start_m) <= 0.05:
        return [MotionState(0.0, end_m, 0.0)]
    max_cap = spec.max_speed_kmh / 3.6
    maximum = _run_leg(start_m, end_m, duration_s, spec, track, max_cap, record=False)[
        0
    ]
    shortfall_m = abs(end_m - maximum.distance_m)
    if shortfall_m > 0.1:
        raise InfeasibleLegError(
            f"scheduled leg is physically infeasible; shortfall={shortfall_m:.1f}m"
        )
    low, high = 0.1, max_cap
    # Pick the lowest cruise cap that can cover the leg in the available time.
    for _ in range(11):
        cap = (low + high) * 0.5
        final = _run_leg(start_m, end_m, duration_s, spec, track, cap, record=False)[0]
        covered = abs(final.distance_m - start_m)
        if covered >= abs(end_m - start_m) - 0.1:
            high = cap
        else:
            low = cap
    return _run_leg(start_m, end_m, duration_s, spec, track, high, record=True)


def state_at(states: Sequence[MotionState], elapsed_s: float) -> MotionState:
    if elapsed_s <= 0 or len(states) == 1:
        return states[0]
    if elapsed_s >= states[-1].elapsed_s:
        return states[-1]
    for left, right in pairwise(states):
        if elapsed_s <= right.elapsed_s:
            span = right.elapsed_s - left.elapsed_s
            ratio = 0.0 if span <= 0 else (elapsed_s - left.elapsed_s) / span
            return MotionState(
                elapsed_s,
                left.distance_m + (right.distance_m - left.distance_m) * ratio,
                left.speed_mps + (right.speed_mps - left.speed_mps) * ratio,
            )
    return states[-1]
