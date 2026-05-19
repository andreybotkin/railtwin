"""Read-only repository for planned movement plans.

Used by:
- diagnostics API endpoints (summary, warnings, problems)
- reference data loader (best run per train → Redis)
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.database.models import PlannedMovementSegment, PlannedTrainRun

logger = get_logger(__name__)

# Minimum quality_score for a run to be used at runtime.
RUNTIME_QUALITY_THRESHOLD = 0.5


class MovementPlanRepository:
    """Read-only queries for the planned movement plan tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ #
    # Diagnostics                                                          #
    # ------------------------------------------------------------------ #

    async def get_summary(self) -> dict[str, Any]:
        """Return aggregate counts and quality stats across all runs."""

        # Status breakdown
        status_rows = (
            await self._session.execute(
                select(
                    PlannedTrainRun.status,
                    func.count(PlannedTrainRun.id).label("cnt"),
                    func.avg(PlannedTrainRun.quality_score).label("avg_quality"),
                ).group_by(PlannedTrainRun.status)
            )
        ).all()

        counts: dict[str, int] = {}
        avg_qualities: list[float] = []
        for row in status_rows:
            counts[row.status] = int(row.cnt)
            if row.avg_quality is not None:
                avg_qualities.append(float(row.avg_quality))

        # Segment type breakdown
        seg_rows = (
            await self._session.execute(
                select(
                    PlannedMovementSegment.segment_type,
                    func.count(PlannedMovementSegment.id).label("cnt"),
                ).group_by(PlannedMovementSegment.segment_type)
            )
        ).all()

        seg_counts: dict[str, int] = {}
        for row in seg_rows:
            seg_counts[row.segment_type] = int(row.cnt)

        # Latest plan + topology version
        latest_row = (
            await self._session.execute(
                select(
                    PlannedTrainRun.plan_version,
                    PlannedTrainRun.topology_version,
                )
                .order_by(PlannedTrainRun.created_at.desc())
                .limit(1)
            )
        ).one_or_none()

        # Top warning codes (JSONB unnest — PostgreSQL only)
        try:
            warning_rows = (
                await self._session.execute(
                    text("""
                        SELECT elem AS code, count(*)::int AS cnt
                        FROM planned_train_runs,
                             jsonb_array_elements_text(warnings::jsonb) AS elem
                        WHERE warnings IS NOT NULL
                          AND warnings::text <> 'null'
                        GROUP BY elem
                        ORDER BY cnt DESC
                        LIMIT 10
                        """)
                )
            ).all()
            top_warning_codes = [row.code for row in warning_rows]
        except Exception:  # noqa: BLE001 — SQLite fallback in tests
            top_warning_codes = []

        avg_quality = (
            round(sum(avg_qualities) / len(avg_qualities), 4) if avg_qualities else None
        )

        return {
            "total_runs": sum(counts.values()),
            "ready_runs": counts.get("ready", 0),
            "degraded_runs": counts.get("degraded", 0),
            "invalid_runs": counts.get("invalid", 0),
            "total_segments": sum(seg_counts.values()),
            "move_segments": seg_counts.get("move", 0),
            "dwell_segments": seg_counts.get("dwell", 0),
            "average_quality_score": avg_quality,
            "top_warning_codes": top_warning_codes,
            "latest_plan_version": latest_row.plan_version if latest_row else None,
            "latest_topology_version": (
                latest_row.topology_version if latest_row else None
            ),
        }

    async def get_runs_for_train(self, train_id: int) -> list[PlannedTrainRun]:
        """All runs for a train, newest first."""
        result = await self._session.execute(
            select(PlannedTrainRun)
            .options(selectinload(PlannedTrainRun.segments))
            .where(PlannedTrainRun.train_id == train_id)
            .order_by(PlannedTrainRun.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_runs_for_route(
        self,
        route_id: int,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PlannedTrainRun], int]:
        """Runs for a route, paginated."""
        q = select(PlannedTrainRun).where(PlannedTrainRun.route_id == route_id)
        if status and status != "all":
            q = q.where(PlannedTrainRun.status == status)

        count_q = select(func.count()).select_from(q.subquery())
        total = int((await self._session.execute(count_q)).scalar_one())

        runs = (
            (
                await self._session.execute(
                    q.order_by(PlannedTrainRun.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return list(runs), total

    async def get_run_with_segments(self, run_id: int) -> PlannedTrainRun | None:
        """Single run with ordered segments."""
        result = await self._session.execute(
            select(PlannedTrainRun)
            .options(selectinload(PlannedTrainRun.segments))
            .where(PlannedTrainRun.id == run_id)
        )
        return result.scalar_one_or_none()

    async def get_warning_counts(self) -> list[dict[str, Any]]:
        """Warning code frequency across all runs (PostgreSQL only)."""
        try:
            rows = (
                await self._session.execute(
                    text("""
                        SELECT elem AS code, count(*)::int AS count
                        FROM planned_train_runs,
                             jsonb_array_elements_text(warnings::jsonb) AS elem
                        WHERE warnings IS NOT NULL
                          AND warnings::text <> 'null'
                        GROUP BY elem
                        ORDER BY count DESC
                        """)
                )
            ).all()
            return [{"code": row.code, "count": row.count} for row in rows]
        except Exception:
            logger.exception("Failed to query warning counts")
            return []

    async def get_problems(
        self,
        *,
        warning_code: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PlannedTrainRun], int]:
        """Degraded and invalid runs, optionally filtered by warning code."""
        q = select(PlannedTrainRun).where(
            PlannedTrainRun.status.in_(["degraded", "invalid"])
        )
        if warning_code:
            try:
                q = q.where(
                    text("warnings::jsonb @> to_jsonb(:code::text)").bindparams(
                        code=warning_code
                    )
                )
            except Exception:
                logger.exception(
                    "Failed to apply warning_code filter",
                    warning_code=warning_code,
                )

        count_q = select(func.count()).select_from(q.subquery())
        total = int((await self._session.execute(count_q)).scalar_one())

        runs = (
            (
                await self._session.execute(
                    q.order_by(PlannedTrainRun.quality_score.asc().nulls_last())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return list(runs), total

    # ------------------------------------------------------------------ #
    # Runtime loading                                                      #
    # ------------------------------------------------------------------ #

    async def get_best_runs_for_all_trains(self) -> list[PlannedTrainRun]:
        """Best usable run per train for the Redis reference snapshot.

        Selects runs with status in ('ready', 'degraded') and
        quality_score >= RUNTIME_QUALITY_THRESHOLD.  Since the builder
        always rebuilds from scratch (deletes all plans first), there is
        normally at most one run per train.
        """
        result = await self._session.execute(
            select(PlannedTrainRun)
            .options(selectinload(PlannedTrainRun.segments))
            .where(
                PlannedTrainRun.status.in_(["ready", "degraded"]),
                PlannedTrainRun.quality_score >= RUNTIME_QUALITY_THRESHOLD,
            )
        )
        return list(result.scalars().all())
