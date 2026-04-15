"""SQLAlchemy 2 + GeoAlchemy2 implementation of the schedule repository.

Station lookup uses a multi-strategy approach:
  1. Exact case-insensitive match
  2. Substring containment (station name contains raw name OR vice-versa)
  3. NULL (stored as station_name only — still fully queryable)
"""

from datetime import time as dt_time

from geoalchemy2.functions import ST_Distance
from geoalchemy2.types import Geography
from sqlalchemy import cast, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.schedule.entities import TrainData
from app.domain.schedule.repository import ScheduleRepository
from app.infrastructure.database.tables import (
    t_route_stations,
    t_schedules,
    t_stations,
    t_trains,
)

logger = get_logger(__name__)

_StationCache = dict[str, int | None]


def _parse_time(t: str | dt_time | None) -> dt_time | None:
    """Convert a HH:MM string (or existing time object) to datetime.time."""
    if t is None or isinstance(t, dt_time):
        return t
    try:
        parts = t.split(":")
        return dt_time(int(parts[0]) % 24, int(parts[1]))
    except (AttributeError, ValueError, IndexError):
        return None


class SqlScheduleRepository(ScheduleRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._station_cache: _StationCache = {}

    async def count_trains(self) -> int:
        result = await self._s.execute(select(func.count()).select_from(t_trains))
        return result.scalar_one() or 0

    async def upsert_train(self, train: TrainData) -> int:
        """Insert or update one train record. Returns the database id."""
        stmt = (
            pg_insert(t_trains)
            .values(
                train_number=train.train_number,
                train_type=train.train_type,
                name=train.name,
                operator=train.operator,
                source=train.source,
                source_url=train.source_url,
                service_notes=train.service_notes or {},
            )
            .on_conflict_do_update(
                index_elements=["train_number"],
                set_={
                    "train_type": train.train_type,
                    "name": train.name,
                    "operator": train.operator,
                    "source": train.source,
                    "source_url": train.source_url,
                    "service_notes": train.service_notes or {},
                },
            )
            .returning(t_trains.c.id)
        )
        return (await self._s.execute(stmt)).scalar_one()

    async def replace_schedules(self, train_id: int, train: TrainData) -> int:
        """Delete existing schedule stops for train_id then insert fresh rows."""
        await self._s.execute(
            delete(t_schedules).where(t_schedules.c.train_id == train_id)
        )
        count = 0
        prev_station_id: int | None = None
        for stop in train.stops:
            station_id = await self._resolve_station_id(
                stop.station_name, prev_station_id=prev_station_id
            )
            await self._s.execute(
                pg_insert(t_schedules).values(
                    train_id=train_id,
                    station_id=station_id,
                    station_name=stop.station_name,
                    arrival_time=_parse_time(stop.arrival_time),
                    departure_time=_parse_time(stop.departure_time),
                    arrival_day_offset=stop.arrival_day_offset,
                    departure_day_offset=stop.departure_day_offset,
                    day_of_week=stop.day_of_week,
                    platform=stop.platform,
                    sequence=stop.sequence,
                    distance_from_origin_km=stop.distance_from_origin_km,
                )
            )
            if station_id is not None:
                prev_station_id = station_id
            count += 1
        return count

    async def _resolve_station_id(
        self,
        station_name: str,
        prev_station_id: int | None = None,
    ) -> int | None:
        key = station_name.lower()
        if key in self._station_cache:
            return self._station_cache[key]

        # ── 1. Exact case-insensitive match ───────────────────────────────────
        exact_stmt = select(t_stations.c.id).where(
            func.lower(t_stations.c.name) == func.lower(station_name)
        )
        exact_ids = [r[0] for r in (await self._s.execute(exact_stmt)).fetchall()]

        if len(exact_ids) == 1:
            self._station_cache[key] = exact_ids[0]
            return exact_ids[0]

        if len(exact_ids) > 1:
            station_id = await self._nearest_candidate(exact_ids, prev_station_id)
            # Don't cache ambiguous result
            return station_id

        # ── 2. Fuzzy substring containment ────────────────────────────────────
        name_lower = station_name.lower()
        fuzzy_stmt = (
            select(t_stations.c.id)
            .where(
                or_(
                    func.lower(t_stations.c.name).like(f"%{name_lower}%"),
                    func.lower(station_name).like(
                        func.concat("%", func.lower(t_stations.c.name), "%")
                    ),
                )
            )
            .order_by(func.length(t_stations.c.name))
        )
        fuzzy_ids = [r[0] for r in (await self._s.execute(fuzzy_stmt)).fetchall()]

        if not fuzzy_ids:
            logger.debug("Station not matched", station_name=station_name)
            self._station_cache[key] = None
            return None

        if len(fuzzy_ids) == 1:
            self._station_cache[key] = fuzzy_ids[0]
            return fuzzy_ids[0]

        return await self._nearest_candidate(fuzzy_ids, prev_station_id)

    async def _nearest_candidate(
        self,
        candidate_ids: list[int],
        prev_station_id: int | None,
    ) -> int:
        """Return the id from candidate_ids closest to prev_station_id."""
        if prev_station_id is None or not candidate_ids:
            return candidate_ids[0]

        prev_loc = (
            select(t_stations.c.location)
            .where(t_stations.c.id == prev_station_id)
            .scalar_subquery()
        )
        stmt = (
            select(t_stations.c.id)
            .where(t_stations.c.id.in_(candidate_ids))
            .order_by(
                ST_Distance(
                    cast(t_stations.c.location, Geography()),
                    cast(prev_loc, Geography()),
                )
            )
            .limit(1)
        )
        result = (await self._s.execute(stmt)).fetchone()
        return result[0] if result else candidate_ids[0]

    async def assign_routes_by_station_match(self, min_matches: int = 2) -> int:
        """Assign current_route_id to trains based on station overlap."""
        ranked = (
            select(
                t_trains.c.id.label("train_id"),
                t_route_stations.c.route_id,
                func.count().label("matches"),
                func.row_number()
                .over(
                    partition_by=t_trains.c.id,
                    order_by=[
                        func.count().desc(),
                        t_route_stations.c.route_id.asc(),
                    ],
                )
                .label("rn"),
            )
            .select_from(t_trains)
            .join(t_schedules, t_schedules.c.train_id == t_trains.c.id)
            .join(
                t_route_stations,
                t_route_stations.c.station_id == t_schedules.c.station_id,
            )
            .where(t_schedules.c.station_id.isnot(None))
            .group_by(t_trains.c.id, t_route_stations.c.route_id)
            .cte("ranked_routes")
        )
        stmt = (
            update(t_trains)
            .values(current_route_id=ranked.c.route_id)
            .where(
                t_trains.c.id == ranked.c.train_id,
                ranked.c.rn == 1,
                ranked.c.matches >= min_matches,
                t_trains.c.current_route_id.is_(None),
            )
        )
        result = await self._s.execute(stmt)
        updated = result.rowcount or 0  # type: ignore[attr-defined]
        logger.info(
            "Route assignment complete", trains_updated=updated, min_matches=min_matches
        )
        return updated
