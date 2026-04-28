"""Domain types for the precomputed movement plan.

These are **data-only** classes used as the shared vocabulary between:
- the plan builder  (raildbsetup, Phase 3)
- the Redis serialiser (simulation/reference_data, Phase 4)
- the runtime resolver (simulation/movement_plan_resolver, Phase 4)

No runtime behaviour is implemented here; importing this module has no
side effects and changes no existing code paths.

See docs/precomputed-movement-plan.md for the full design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Segment type aliases
# ---------------------------------------------------------------------------

SegmentType = Literal["move", "dwell"]
PlanStatus = Literal["ready", "degraded", "invalid"]


# ---------------------------------------------------------------------------
# PlannedMovementSegment
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlannedMovementSegment:
    """A single contiguous period of movement or dwell in a train's journey.

    All time values are in minutes-since-midnight on their respective calendar
    day (mirroring ``schedule.arrival/departure_day_offset``).

    Geometry is referenced only via ``route_id`` (on the parent run) and
    optional ``edge_id`` pointers — no coordinate data is duplicated here.
    """

    id: int | None
    planned_run_id: int
    sequence: int

    segment_type: SegmentType

    from_station_id: int | None
    to_station_id: int | None
    from_schedule_id: int | None
    to_schedule_id: int | None

    # Time bounds
    start_time_minutes: float
    end_time_minutes: float
    start_day_offset: int
    end_day_offset: int

    # Route distance bounds in metres
    start_distance_m: float
    end_distance_m: float

    # Precomputed polyline fractions [0, 1]
    start_geom_fraction: float
    end_geom_fraction: float

    # Optional edge references for edge-aligned queries
    start_edge_id: int | None
    end_edge_id: int | None

    # Planned average speed (None for dwell segments)
    planned_speed_kmh: float | None

    quality_score: float | None
    warnings: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience helpers (no I/O, no side effects)
    # ------------------------------------------------------------------

    @property
    def absolute_start_minutes(self) -> float:
        """Start time in absolute minutes (midnight of day 0 = 0)."""
        return self.start_time_minutes + self.start_day_offset * 24 * 60

    @property
    def absolute_end_minutes(self) -> float:
        """End time in absolute minutes (midnight of day 0 = 0)."""
        return self.end_time_minutes + self.end_day_offset * 24 * 60

    def contains_time(self, absolute_minutes: float) -> bool:
        """Return True when *absolute_minutes* falls within this segment."""
        return (
            self.absolute_start_minutes <= absolute_minutes <= self.absolute_end_minutes
        )

    def interpolate_fraction(self, absolute_minutes: float) -> float:
        """Linearly interpolate geom_fraction for the given time.

        Clamps to [start_geom_fraction, end_geom_fraction] (or the reverse
        range for trains running in the descending direction).
        """
        duration = self.absolute_end_minutes - self.absolute_start_minutes
        if duration <= 0:
            return self.end_geom_fraction
        progress = max(
            0.0, min(1.0, (absolute_minutes - self.absolute_start_minutes) / duration)
        )
        return (
            self.start_geom_fraction
            + (self.end_geom_fraction - self.start_geom_fraction) * progress
        )


# ---------------------------------------------------------------------------
# PlannedTrainRun
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlannedTrainRun:
    """Header for a precomputed movement plan covering one train+route pair.

    ``segments`` is an ordered list (by ``sequence``) of movement and dwell
    segments that together span the full operating day for this train.
    """

    id: int | None
    train_id: int
    route_id: int

    # NULL means the plan applies to every operating day (typical).
    service_date: str | None  # ISO-8601 date string

    plan_version: int
    topology_version: str

    quality_score: float | None
    status: PlanStatus

    warnings: list[str] = field(default_factory=list)
    segments: list[PlannedMovementSegment] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def find_segment(self, absolute_minutes: float) -> PlannedMovementSegment | None:
        """Return the segment that covers *absolute_minutes*, or None.

        Performs a linear scan; the segment list is short (< 200 entries for
        any realistic Thai railway train), so a binary search is unnecessary
        in Phase 4.  Replace with ``bisect`` if profiling shows a need.
        """
        for seg in self.segments:
            if seg.contains_time(absolute_minutes):
                return seg
        return None

    def is_usable(self) -> bool:
        """Return True when this plan can be used by the resolver."""
        return self.status in ("ready", "degraded") and bool(self.segments)
