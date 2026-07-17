"""SQLAlchemy Core repository for precomputed movement plans.

Responsible for:
  - reading the current topology version
  - loading train / schedule / route_station data for the builder
  - deleting and re-inserting planned_train_runs + planned_movement_segments

All business logic lives in app.domain.railroad.movement_plan_service.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select

from app.core.logging import get_logger
from app.domain.railroad.movement_plan_service import (
    BuiltRun,
    StopInput,
    TrainBuildInput,
)
from app.infrastructure.database.tables import (
    t_planned_movement_segments,
    t_planned_train_runs,
    t_network_edges,
    t_route_stations,
    t_routes,
    t_schedules,
    t_topology_metadata,
    t_trains,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _GraphArc:
    to_station_id: int
    edge_id: int
    length_m: float


def _shortest_path(
    graph: dict[int, list[_GraphArc]], start: int, end: int
) -> list[_GraphArc] | None:
    """Return the shortest directed station-edge path."""
    if start == end:
        return []
    queue: list[tuple[float, int]] = [(0.0, start)]
    distances = {start: 0.0}
    previous: dict[int, tuple[int, _GraphArc]] = {}
    while queue:
        distance, station_id = heapq.heappop(queue)
        if distance != distances.get(station_id):
            continue
        if station_id == end:
            break
        for arc in graph.get(station_id, []):
            candidate = distance + arc.length_m
            if candidate < distances.get(arc.to_station_id, float("inf")):
                distances[arc.to_station_id] = candidate
                previous[arc.to_station_id] = (station_id, arc)
                heapq.heappush(queue, (candidate, arc.to_station_id))
    if end not in previous:
        return None
    result: list[_GraphArc] = []
    cursor = end
    while cursor != start:
        parent, arc = previous[cursor]
        result.append(arc)
        cursor = parent
    result.reverse()
    return result


class SqlMovementPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_topology_version(self) -> str | None:
        """Return the most recent topology_version string, or None."""
        stmt = (
            select(t_topology_metadata.c.topology_version)
            .order_by(t_topology_metadata.c.id.desc())
            .limit(1)
        )
        result = await self._s.execute(stmt)
        return result.scalar_one_or_none()

    async def load_trains_with_schedules(self) -> list[TrainBuildInput]:
        """Load all trains that have current_route_id set, with their schedule stops.

        Each stop is joined to route_stations so the builder can use
        distance_from_start and edge_id when available.
        """
        stmt = (
            select(
                t_trains.c.id.label("train_id"),
                t_trains.c.current_route_id.label("route_id"),
                t_routes.c.distance_km,
                t_schedules.c.id.label("schedule_id"),
                t_schedules.c.sequence,
                t_schedules.c.station_id,
                t_schedules.c.route_station_id,
                t_schedules.c.arrival_time,
                t_schedules.c.departure_time,
                t_schedules.c.arrival_day_offset,
                t_schedules.c.departure_day_offset,
                t_schedules.c.distance_from_origin_km,
                t_schedules.c.route_progress,
                t_route_stations.c.distance_from_start.label("rs_distance_from_start"),
                t_route_stations.c.edge_id.label("rs_edge_id"),
            )
            .select_from(t_trains)
            .join(t_routes, t_routes.c.id == t_trains.c.current_route_id)
            .join(t_schedules, t_schedules.c.train_id == t_trains.c.id)
            .outerjoin(
                t_route_stations,
                t_route_stations.c.id == t_schedules.c.route_station_id,
            )
            .where(t_trains.c.current_route_id.isnot(None))
            .order_by(t_trains.c.id, t_schedules.c.sequence)
        )

        rows = (await self._s.execute(stmt)).fetchall()

        edge_rows = (
            await self._s.execute(
                select(
                    t_network_edges.c.id,
                    t_network_edges.c.from_station_id,
                    t_network_edges.c.to_station_id,
                    t_network_edges.c.length_m,
                ).where(t_network_edges.c.length_m > 0)
            )
        ).fetchall()
        graph: dict[int, list[_GraphArc]] = {}
        for edge in edge_rows:
            graph.setdefault(int(edge.from_station_id), []).append(
                _GraphArc(
                    to_station_id=int(edge.to_station_id),
                    edge_id=int(edge.id),
                    length_m=float(edge.length_m),
                )
            )

        trains: dict[int, TrainBuildInput] = {}
        for row in rows:
            train_id = row.train_id
            if train_id not in trains:
                trains[train_id] = TrainBuildInput(
                    train_id=train_id,
                    route_id=row.route_id,
                    route_distance_km=(
                        float(row.distance_km) if row.distance_km is not None else None
                    ),
                    stops=[],
                )

            arr_min: int | None = None
            if row.arrival_time is not None:
                arr_min = row.arrival_time.hour * 60 + row.arrival_time.minute

            dep_min: int | None = None
            if row.departure_time is not None:
                dep_min = row.departure_time.hour * 60 + row.departure_time.minute

            trains[train_id].stops.append(
                StopInput(
                    schedule_id=row.schedule_id,
                    sequence=row.sequence,
                    station_id=row.station_id,
                    route_station_id=row.route_station_id,
                    arrival_time_minutes=arr_min,
                    departure_time_minutes=dep_min,
                    arrival_day_offset=int(row.arrival_day_offset),
                    departure_day_offset=int(row.departure_day_offset),
                    route_station_distance_from_start_km=(
                        float(row.rs_distance_from_start)
                        if row.rs_distance_from_start is not None
                        else None
                    ),
                    route_station_edge_id=row.rs_edge_id,
                    schedule_distance_from_origin_km=(
                        float(row.distance_from_origin_km)
                        if row.distance_from_origin_km is not None
                        else None
                    ),
                    schedule_route_progress=(
                        float(row.route_progress)
                        if row.route_progress is not None
                        else None
                    ),
                )
            )

        # Resolve every timetable on the same directed station graph used by
        # runtime train geometry.  A single route_station sequence cannot
        # represent branch-crossing services and was the source of false
        # 200–2000 km/h plans.
        for train in trains.values():
            cumulative_m = 0.0
            path_cache: dict[tuple[int, int], list[_GraphArc] | None] = {}
            if train.stops:
                train.stops[0].graph_distance_from_start_m = 0.0
            for left, right in zip(train.stops, train.stops[1:], strict=False):
                if left.station_id is None or right.station_id is None:
                    continue
                start, end = int(left.station_id), int(right.station_id)
                key = (start, end)
                if key not in path_cache:
                    path_cache[key] = _shortest_path(graph, start, end)
                path = path_cache[key]
                if path is None:
                    continue
                if path and left.graph_edge_id is None:
                    left.graph_edge_id = path[0].edge_id
                cumulative_m += sum(arc.length_m for arc in path)
                right.graph_distance_from_start_m = cumulative_m
                if path:
                    right.graph_edge_id = path[-1].edge_id
            if cumulative_m > 0:
                train.route_distance_km = cumulative_m / 1000.0

        return list(trains.values())

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def delete_all_plans(self) -> int:
        """Delete all planned_movement_segments then planned_train_runs.

        Segments must be deleted first to satisfy the FK constraint.
        """
        r1 = await self._s.execute(delete(t_planned_movement_segments))
        r2 = await self._s.execute(delete(t_planned_train_runs))
        deleted = (r1.rowcount or 0) + (r2.rowcount or 0)  # type: ignore[attr-defined]
        if deleted:
            logger.info("Cleared existing movement plans", rows_deleted=deleted)
        return deleted

    async def save_run(self, run: BuiltRun) -> int:
        """Insert one planned_train_run and all its segments. Returns the new run ID."""
        now = datetime.now(UTC)

        run_stmt = (
            t_planned_train_runs.insert()
            .values(
                train_id=run.train_id,
                route_id=run.route_id,
                service_date=run.service_date,
                service_pattern=run.service_pattern,
                plan_version=run.plan_version,
                topology_version=run.topology_version,
                quality_score=run.quality_score,
                status=run.status,
                warnings=run.warnings if run.warnings else None,
                created_at=now,
                updated_at=now,
            )
            .returning(t_planned_train_runs.c.id)
        )
        result = await self._s.execute(run_stmt)
        run_id: int = result.scalar_one()

        if run.segments:
            seg_rows = [
                {
                    "planned_run_id": run_id,
                    "sequence": seg.sequence,
                    "segment_type": seg.segment_type,
                    "from_station_id": seg.from_station_id,
                    "to_station_id": seg.to_station_id,
                    "from_schedule_id": seg.from_schedule_id,
                    "to_schedule_id": seg.to_schedule_id,
                    "start_time_minutes": seg.start_time_minutes,
                    "end_time_minutes": seg.end_time_minutes,
                    "start_day_offset": seg.start_day_offset,
                    "end_day_offset": seg.end_day_offset,
                    "absolute_start_minutes": seg.absolute_start_minutes,
                    "absolute_end_minutes": seg.absolute_end_minutes,
                    "start_distance_m": (
                        round(seg.start_distance_m, 2)
                        if seg.start_distance_m is not None
                        else None
                    ),
                    "end_distance_m": (
                        round(seg.end_distance_m, 2)
                        if seg.end_distance_m is not None
                        else None
                    ),
                    "start_geom_fraction": (
                        round(seg.start_geom_fraction, 8)
                        if seg.start_geom_fraction is not None
                        else None
                    ),
                    "end_geom_fraction": (
                        round(seg.end_geom_fraction, 8)
                        if seg.end_geom_fraction is not None
                        else None
                    ),
                    "start_edge_id": seg.start_edge_id,
                    "end_edge_id": seg.end_edge_id,
                    "planned_speed_kmh": seg.planned_speed_kmh,
                    "quality_score": seg.quality_score,
                    "warnings": seg.warnings if seg.warnings else None,
                    "created_at": now,
                }
                for seg in run.segments
            ]
            await self._s.execute(t_planned_movement_segments.insert(), seg_rows)

        return run_id

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    async def count_runs(self) -> int:
        result = await self._s.execute(
            select(func.count()).select_from(t_planned_train_runs)
        )
        return result.scalar_one() or 0

    async def count_segments(self) -> int:
        result = await self._s.execute(
            select(func.count()).select_from(t_planned_movement_segments)
        )
        return result.scalar_one() or 0
