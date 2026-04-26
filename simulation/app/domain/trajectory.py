"""Trajectory domain model — authoritative shape of "where the train is now and next".

A :class:`Trajectory` is the single source of truth published by the simulation.
It contains:

* an authoritative **polyline** (the track geometry the train moves along) with
  its **length in metres** precomputed on the server;
* a dense list of :class:`TrajectoryFrame` s (one every N seconds, configured by
  :attr:`app.core.config.Settings.trajectory_step_seconds`) covering the next
  :attr:`app.core.config.Settings.trajectory_lookahead_seconds` of motion;
* schedule-aligned :attr:`Trajectory.anchors` (exact arrival/departure events);
* a :class:`ConsistSpec` describing the locomotive and carriages so the client
  can place every body precisely on the rail polyline.

The frontend consumes a :class:`Trajectory` and interpolates the head frame at
``now``; wagons are placed by walking the polyline backwards in metres using
``locomotive_length_m / 2 + index * car_length_m``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TrajectoryStatus = Literal["moving", "dwelling", "arrived", "boarding"]


class ConsistSpec(BaseModel):
    """Physical composition of a train (locomotive + carriages).

    ``total_length_m`` is derived server-side so the client never has to guess
    how far the tail of the train is from the head.
    """

    model_config = ConfigDict(frozen=True)

    locomotive_length_m: float = Field(..., gt=0)
    car_count: int = Field(..., ge=0)
    car_length_m: float = Field(..., gt=0)
    total_length_m: float = Field(..., ge=0)

    @classmethod
    def build(
        cls,
        *,
        locomotive_length_m: float,
        car_count: int,
        car_length_m: float,
    ) -> ConsistSpec:
        total = locomotive_length_m + car_count * car_length_m
        return cls(
            locomotive_length_m=locomotive_length_m,
            car_count=car_count,
            car_length_m=car_length_m,
            total_length_m=total,
        )


# Train-type consist specs.  Lengths based on Thai SRT rolling stock:
#   - Alsthom / GE diesel-electric locomotives ≈ 20 m
#   - Standard coach ≈ 24 m (AC/sleeper) or 20 m (3rd class)
# Values are deliberately conservative and validated by :func:`resolve_consist`.
_CONSIST_BY_TYPE: dict[str, ConsistSpec] = {
    "special_express": ConsistSpec.build(
        locomotive_length_m=20.0,
        car_count=12,
        car_length_m=24.0,
    ),
    "express": ConsistSpec.build(
        locomotive_length_m=20.0,
        car_count=11,
        car_length_m=24.0,
    ),
    "rapid": ConsistSpec.build(
        locomotive_length_m=20.0,
        car_count=10,
        car_length_m=24.0,
    ),
    "ordinary": ConsistSpec.build(
        locomotive_length_m=20.0,
        car_count=8,
        car_length_m=20.0,
    ),
    "commuter": ConsistSpec.build(
        locomotive_length_m=20.0,
        car_count=6,
        car_length_m=20.0,
    ),
}

_DEFAULT_CONSIST: ConsistSpec = _CONSIST_BY_TYPE["ordinary"]


def resolve_consist(train_type: str | None) -> ConsistSpec:
    """Return the :class:`ConsistSpec` matching a train-type key.

    Unknown types fall back to the "ordinary" consist rather than raising —
    timetable data is often noisy and we never want the simulation to crash
    over an unexpected classifier.
    """

    if train_type is None:
        return _DEFAULT_CONSIST
    return _CONSIST_BY_TYPE.get(train_type.strip().lower(), _DEFAULT_CONSIST)


class TrajectoryFrame(BaseModel):
    """One sampled instant of a train's future motion."""

    model_config = ConfigDict(frozen=True)

    t_ms: int = Field(..., description="Unix timestamp in milliseconds (UTC).")
    lon: float = Field(..., ge=-180.0, le=180.0)
    lat: float = Field(..., ge=-90.0, le=90.0)
    geom_fraction: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="0..1 fraction along the authoritative route polyline.",
    )
    head_distance_m: float = Field(
        ...,
        ge=0.0,
        description="Distance from the start of the polyline to the locomotive head.",
    )
    rotation_deg: float = Field(
        ...,
        ge=0.0,
        lt=360.0,
        description="Compass bearing of the locomotive (clockwise from North).",
    )
    speed_kmh: float = Field(..., ge=0.0, le=400.0)
    status: TrajectoryStatus = "moving"


class TrajectoryAnchor(BaseModel):
    """A station-level event overlaid on the frame timeline."""

    model_config = ConfigDict(frozen=True)

    t_ms: int
    station_id: int | None = None
    station_name: str
    event: Literal["arrival", "departure"]
    geom_fraction: float = Field(..., ge=0.0, le=1.0)
    scheduled_minutes: int
    adjusted_minutes: int
    delay_minutes: int


class TrajectoryMeta(BaseModel):
    """Train-level metadata shipped alongside the frames."""

    model_config = ConfigDict(frozen=True)

    train_id: int
    train_number: str
    train_type: str
    train_name: str | None = None
    color: str = Field(..., description="Hex colour matching the frontend palette.")
    operator: str = "State Railway of Thailand"
    origin_station: str | None = None
    destination_station: str | None = None
    origin_station_th: str | None = None
    destination_station_th: str | None = None
    prev_station: str | None = None
    next_station: str | None = None
    next_station_th: str | None = None
    eta_next_ms: int | None = None
    delay_minutes: int = 0
    route_id: int | None = None
    route_progress_pct: float = Field(..., ge=0.0, le=100.0)
    segment_progress_pct: float = Field(..., ge=0.0, le=100.0)
    current_edge_id: int | None = None
    graph_from_station_id: int | None = None
    graph_to_station_id: int | None = None
    topology_version: str | None = None


class Trajectory(BaseModel):
    """Full wire-level trajectory object.

    This is what the simulation writes to Redis, what the gateway forwards to
    the frontend, and what the frontend uses as the single source of truth for
    drawing the train + its wagons at any instant within its validity window.
    """

    model_config = ConfigDict(populate_by_name=True)

    train_id: int
    generated_at_ms: int
    valid_until_ms: int
    route_coords: list[tuple[float, float]] = Field(..., min_length=2)
    route_length_m: float = Field(..., ge=0.0)
    frames: list[TrajectoryFrame] = Field(..., min_length=1)
    anchors: list[TrajectoryAnchor] = Field(default_factory=list)
    consist: ConsistSpec
    meta: TrajectoryMeta
    bounds: tuple[float, float, float, float] = Field(
        ...,
        description="min_lon, min_lat, max_lon, max_lat — used for viewport filtering.",
    )

    @field_validator("valid_until_ms")
    @classmethod
    def _valid_until_after_generated(cls, v: int, info) -> int:  # noqa: ANN001
        generated = info.data.get("generated_at_ms")
        if generated is not None and v < generated:
            raise ValueError("valid_until_ms must not precede generated_at_ms")
        return v
