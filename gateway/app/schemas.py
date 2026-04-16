from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TrajectoryStatus(str, Enum):
    moving = "moving"
    dwelling = "dwelling"
    arrived = "arrived"


class ConsistSpec(BaseModel):
    locomotive_length_m: float
    car_count: int
    car_length_m: float
    total_length_m: float | None = None


class TrajectoryFrame(BaseModel):
    t_ms: int
    lon: float
    lat: float
    geom_fraction: float = Field(ge=0, le=1)
    rotation_deg: float
    speed_kmh: float
    status: TrajectoryStatus


class TrajectoryMeta(BaseModel):
    train_id: int
    train_number: str
    train_type: str | None = None
    color: str
    from_station: str | None = None
    to_station: str | None = None
    next_station: str | None = None
    prev_station: str | None = None
    eta_next_ms: int | None = None
    delay_minutes: int = 0
    route_progress_pct: float = 0
    topology_version: str | None = None


class Trajectory(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    train_id: int
    generated_at_ms: int
    valid_until_ms: int
    route_coords: list[list[float]]
    route_length_m: float
    frames: list[TrajectoryFrame]
    anchors: list[dict] = Field(default_factory=list)
    consist: ConsistSpec
    meta: TrajectoryMeta
