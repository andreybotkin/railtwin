"""Domain types — pure data structures shared across services and API layers."""

from app.domain.trajectory import (
    ConsistSpec,
    Trajectory,
    TrajectoryFrame,
    TrajectoryMeta,
    TrajectoryStatus,
    resolve_consist,
)

__all__ = [
    "ConsistSpec",
    "Trajectory",
    "TrajectoryFrame",
    "TrajectoryMeta",
    "TrajectoryStatus",
    "resolve_consist",
]
