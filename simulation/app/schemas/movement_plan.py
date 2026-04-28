"""Pydantic response schemas for movement plan diagnostics API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Static warning metadata (code → severity, description)
# ---------------------------------------------------------------------------

_WARNING_META: dict[str, tuple[str, str]] = {
    "missing_route_station_id": (
        "warning",
        "Schedule stop lacks route_station_id link",
    ),
    "missing_station_id": ("warning", "Schedule stop lacks station_id"),
    "missing_route_distance": (
        "warning",
        "No distance data available; linear index fallback used",
    ),
    "projection_fallback_used": (
        "info",
        "Distance from schedule column or index, not route_station",
    ),
    "non_monotonic_distance": (
        "warning",
        "Segment distances are not monotonically ordered",
    ),
    "non_monotonic_time": (
        "warning",
        "Absolute times are not monotonically increasing",
    ),
    "zero_or_negative_duration": (
        "error",
        "Segment has ≤ 0-minute duration",
    ),
    "suspicious_speed": (
        "warning",
        "Computed speed is outside the 1–200 km/h range",
    ),
    "missing_route_geometry": (
        "warning",
        "Route has no distance_km; geometry fractions are estimates",
    ),
    "missing_topology_version": (
        "info",
        "No topology_metadata row was present at build time",
    ),
    "insufficient_usable_stops": (
        "error",
        "Fewer than 2 stops have time data; plan cannot be built",
    ),
}


def warning_severity(code: str) -> str:
    return _WARNING_META.get(code, ("warning", ""))[0]


def warning_description(code: str) -> str:
    return _WARNING_META.get(code, ("", f"Unknown warning code: {code!r}"))[1]


# ---------------------------------------------------------------------------
# Segment
# ---------------------------------------------------------------------------


class PlannedSegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sequence: int
    segment_type: str
    from_station_id: int | None = None
    to_station_id: int | None = None
    from_schedule_id: int | None = None
    to_schedule_id: int | None = None
    start_time_minutes: int
    end_time_minutes: int
    start_day_offset: int
    end_day_offset: int
    absolute_start_minutes: int
    absolute_end_minutes: int
    start_distance_m: float | None = None
    end_distance_m: float | None = None
    start_geom_fraction: float | None = None
    end_geom_fraction: float | None = None
    start_edge_id: int | None = None
    end_edge_id: int | None = None
    planned_speed_kmh: float | None = None
    quality_score: float | None = None
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Run (summary and detail)
# ---------------------------------------------------------------------------


class PlannedRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    train_id: int
    route_id: int
    service_date: str | None = None
    service_pattern: str | None = None
    plan_version: str
    topology_version: str | None = None
    status: str
    quality_score: float | None = None
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PlannedRunDetail(PlannedRunSummary):
    segments: list[PlannedSegmentOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Summary aggregate
# ---------------------------------------------------------------------------


class MovementPlanSummary(BaseModel):
    total_runs: int
    ready_runs: int
    degraded_runs: int
    invalid_runs: int
    total_segments: int
    move_segments: int
    dwell_segments: int
    average_quality_score: float | None = None
    top_warning_codes: list[str] = Field(default_factory=list)
    latest_plan_version: str | None = None
    latest_topology_version: str | None = None


# ---------------------------------------------------------------------------
# Warning code info
# ---------------------------------------------------------------------------

WarningSeverity = Literal["info", "warning", "error"]


class WarningCodeInfo(BaseModel):
    code: str
    count: int
    severity: WarningSeverity
    description: str


# ---------------------------------------------------------------------------
# Paginated list wrappers
# ---------------------------------------------------------------------------


class PlannedRunListResponse(BaseModel):
    items: list[PlannedRunSummary]
    total: int
    limit: int
    offset: int
