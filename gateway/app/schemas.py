"""Pydantic schemas mirroring :mod:`simulation.app.domain.trajectory`.

The gateway re-declares these models (instead of importing them from the
simulation package) so it remains standalone and can be deployed without the
simulation code on the Python path.  The wire format must match exactly —
when the simulation domain changes, bump both sides in the same PR.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TrajectoryStatus = Literal["moving", "dwelling", "arrived", "boarding"]


class ConsistSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    locomotive_length_m: float = Field(..., gt=0)
    car_count: int = Field(..., ge=0)
    car_length_m: float = Field(..., gt=0)
    total_length_m: float = Field(..., ge=0)


class TrajectoryFrame(BaseModel):
    model_config = ConfigDict(frozen=True)

    t_ms: int
    lon: float = Field(..., ge=-180.0, le=180.0)
    lat: float = Field(..., ge=-90.0, le=90.0)
    geom_fraction: float = Field(..., ge=0.0, le=1.0)
    head_distance_m: float = Field(..., ge=0.0)
    rotation_deg: float = Field(..., ge=0.0, lt=360.0)
    speed_kmh: float = Field(..., ge=0.0, le=400.0)
    status: TrajectoryStatus = "moving"


class TrajectoryAnchor(BaseModel):
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
    model_config = ConfigDict(frozen=True)

    train_id: int
    train_number: str
    train_type: str
    train_name: str | None = None
    color: str
    operator: str = "State Railway of Thailand"
    origin_station: str | None = None
    destination_station: str | None = None
    prev_station: str | None = None
    next_station: str | None = None
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
    bounds: tuple[float, float, float, float]


class TopologyMetadata(BaseModel):
    topology_version: str
    physical_nodes_count: int
    physical_edges_count: int
    station_nodes_count: int
    physical_components_count: int
    station_components_count: int
    operational_links_count: int
    main_component_station_count: int
    disconnected_station_count: int
    unsnapped_station_count: int
    max_snap_distance_m: float | None = None
    built_at: str


class MapSnapshot(BaseModel):
    """Full network geometry + station catalogue — fetched once on page load."""

    topology: TopologyMetadata | None = None
    stations: list[dict] = Field(default_factory=list)
    network_edges: dict = Field(
        default_factory=lambda: {"type": "FeatureCollection", "features": []}
    )


class StopSequenceItem(BaseModel):
    station_name: str
    sequence: int
    aimed_arrival_minutes: int | None = None
    aimed_departure_minutes: int | None = None
    arrival_day_offset: int = 0
    departure_day_offset: int = 0
    delay_minutes: int = 0
    state: Literal["PASSED", "BOARDING", "PENDING"]


__all__ = [
    "ConsistSpec",
    "MapSnapshot",
    "StopSequenceItem",
    "TopologyMetadata",
    "Trajectory",
    "TrajectoryAnchor",
    "TrajectoryFrame",
    "TrajectoryMeta",
    "TrajectoryStatus",
]
