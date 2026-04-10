"""SQLAlchemy implementation of the schedule repository.

Uses raw SQL for upsert semantics against the shared PostgreSQL database.
Station lookup uses a multi-strategy approach:
  1. Exact case-insensitive match
  2. Substring containment (station name contains raw name OR vice-versa)
  3. NULL (stored as station_name only — still fully queryable)
"""

import json
from datetime import time as dt_time

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.schedule.entities import TrainData
from app.domain.schedule.repository import ScheduleRepository

logger = get_logger(__name__)

# Station id cache: lower(name) → db id.  Shared within a session for speed.
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

    # ------------------------------------------------------------------ #
    # Query methods                                                        #
    # ------------------------------------------------------------------ #

    async def count_trains(self) -> int:
        result = await self._s.execute(sa.text("SELECT COUNT(*) FROM trains"))
        return result.scalar() or 0

    # ------------------------------------------------------------------ #
    # Write methods                                                        #
    # ------------------------------------------------------------------ #

    async def upsert_train(self, train: TrainData) -> int:
        """Insert or update one train record.  Returns the database id."""
        row = await self._s.execute(
            sa.text("""
                INSERT INTO trains
                    (train_number, train_type, name, operator, source,
                     source_url, service_notes)
                VALUES (
                    :number, :type, :name, :operator, :source,
                    :source_url, cast(:notes AS jsonb)
                )
                ON CONFLICT (train_number) DO UPDATE SET
                    train_type    = EXCLUDED.train_type,
                    name          = EXCLUDED.name,
                    operator      = EXCLUDED.operator,
                    source        = EXCLUDED.source,
                    source_url    = EXCLUDED.source_url,
                    service_notes = EXCLUDED.service_notes
                RETURNING id
                """),
            {
                "number": train.train_number,
                "type": train.train_type,
                "name": train.name,
                "operator": train.operator,
                "source": train.source,
                "source_url": train.source_url,
                "notes": json.dumps(train.service_notes or {}),
            },
        )
        return row.scalar_one()

    async def replace_schedules(self, train_id: int, train: TrainData) -> int:
        """Delete existing schedule stops for train_id then insert fresh rows."""
        await self._s.execute(
            sa.text("DELETE FROM schedules WHERE train_id = :tid"),
            {"tid": train_id},
        )
        count = 0
        prev_station_id: int | None = None
        for stop in train.stops:
            station_id = await self._resolve_station_id(
                stop.station_name, prev_station_id=prev_station_id
            )
            await self._s.execute(
                sa.text("""
                    INSERT INTO schedules (
                        train_id, station_id, station_name,
                        arrival_time, departure_time,
                        arrival_day_offset, departure_day_offset,
                        day_of_week, platform, sequence,
                        distance_from_origin_km
                    ) VALUES (
                        :train_id, :station_id, :station_name,
                        :arrival_time,
                        :departure_time,
                        :arrival_offset, :departure_offset,
                        :dow,
                        :platform, :sequence, :distance
                    )
                    """),
                {
                    "train_id": train_id,
                    "station_id": station_id,
                    "station_name": stop.station_name,
                    "arrival_time": _parse_time(stop.arrival_time),
                    "departure_time": _parse_time(stop.departure_time),
                    "arrival_offset": stop.arrival_day_offset,
                    "departure_offset": stop.departure_day_offset,
                    "dow": stop.day_of_week,
                    "platform": stop.platform,
                    "sequence": stop.sequence,
                    "distance": stop.distance_from_origin_km,
                },
            )
            if station_id is not None:
                prev_station_id = station_id
            count += 1
        return count

    # ------------------------------------------------------------------ #
    # Station lookup helpers                                               #
    # ------------------------------------------------------------------ #

    async def _resolve_station_id(
        self,
        station_name: str,
        prev_station_id: int | None = None,
    ) -> int | None:
        """Resolve station_id for a raw timetable stop name.

        Strategy (in order):
          1. Cache hit (exact-match cache only — proximity results are not cached)
          2. Exact case-insensitive match on ``stations.name`` (single result)
          3. If multiple exact or fuzzy candidates exist, pick the one closest
             to the previous stop's location (graph-connectivity heuristic)
          4. Containment match with proximity tie-breaking
          5. Return None (schedule stop stored with station_name only)
        """
        key = station_name.lower()
        if key in self._station_cache:
            # Cache stores the single exact-match result; use it directly if
            # there was no ambiguity (value may be None meaning "not found").
            cached = self._station_cache[key]
            # If we have a previous station, cached exact matches are still valid
            # because exact name means unambiguous.
            return cached

        # ── 1. Exact case-insensitive match ──────────────────────────────
        rows = await self._s.execute(
            sa.text("SELECT id FROM stations WHERE LOWER(name) = LOWER(:n)"),
            {"n": station_name},
        )
        exact_ids = [r[0] for r in rows.fetchall()]

        if len(exact_ids) == 1:
            # Unambiguous exact match → cache and return
            self._station_cache[key] = exact_ids[0]
            return exact_ids[0]

        if len(exact_ids) > 1:
            # Multiple stations share the same name; use proximity to disambiguate
            station_id = await self._nearest_candidate(exact_ids, prev_station_id)
            # Don't cache ambiguous result
            return station_id

        # ── 2. Fuzzy containment match (no exact match found) ────────────
        rows = await self._s.execute(
            sa.text("""
                SELECT id FROM stations
                WHERE LOWER(name) LIKE '%' || LOWER(:n) || '%'
                   OR LOWER(:n) LIKE '%' || LOWER(name) || '%'
                ORDER BY length(name)
                """),
            {"n": station_name},
        )
        fuzzy_ids = [r[0] for r in rows.fetchall()]

        if not fuzzy_ids:
            logger.debug("Station not matched", station_name=station_name)
            self._station_cache[key] = None
            return None

        if len(fuzzy_ids) == 1:
            self._station_cache[key] = fuzzy_ids[0]
            return fuzzy_ids[0]

        # Multiple fuzzy candidates → proximity tie-break
        station_id = await self._nearest_candidate(fuzzy_ids, prev_station_id)
        return station_id

    async def _nearest_candidate(
        self,
        candidate_ids: list[int],
        prev_station_id: int | None,
    ) -> int:
        """Return the id from candidate_ids that is closest to prev_station_id.

        Falls back to the first candidate when no previous station is known or
        when prev_station_id has no geometry.
        """
        if prev_station_id is None or not candidate_ids:
            return candidate_ids[0]

        # Order candidates by distance to the previous station
        placeholders = ", ".join(f":id_{i}" for i in range(len(candidate_ids)))
        params: dict = {f"id_{i}": cid for i, cid in enumerate(candidate_ids)}
        params["prev"] = prev_station_id
        row = await self._s.execute(
            sa.text(f"""
                SELECT c.id
                FROM stations c
                WHERE c.id IN ({placeholders})
                ORDER BY
                    ST_Distance(
                        c.location::geography,
                        (SELECT location::geography FROM stations WHERE id = :prev)
                    ) ASC
                LIMIT 1
                """),
            params,
        )
        result = row.fetchone()
        return result[0] if result else candidate_ids[0]

    async def assign_routes_by_station_match(self, min_matches: int = 2) -> int:
        """Assign current_route_id to trains based on station overlap.

        For each train without a route, finds the route that shares the most
        stations with the train's schedule (station_id must be non-null).
        Updates trains.current_route_id in bulk.

        Args:
            min_matches: Minimum number of matching stations required.

        Returns:
            Number of trains updated.
        """
        result = await self._s.execute(
            sa.text("""
                WITH ranked_routes AS (
                  SELECT
                    t.id                                                             AS train_id,
                    rs.route_id,
                    COUNT(*)                                                         AS matches,
                    ROW_NUMBER() OVER (
                        PARTITION BY t.id
                        ORDER BY COUNT(*) DESC, rs.route_id ASC
                    )                                                                AS rn
                  FROM trains t
                  JOIN schedules sc ON sc.train_id = t.id AND sc.station_id IS NOT NULL
                  JOIN route_stations rs ON rs.station_id = sc.station_id
                  GROUP BY t.id, rs.route_id
                )
                UPDATE trains
                SET current_route_id = ranked_routes.route_id
                FROM ranked_routes
                WHERE trains.id = ranked_routes.train_id
                  AND ranked_routes.rn = 1
                  AND ranked_routes.matches >= :min_matches
                  AND trains.current_route_id IS NULL
                """),
            {"min_matches": min_matches},
        )
        updated = result.rowcount or 0  # type: ignore[attr-defined]
        logger.info(
            "Route assignment complete", trains_updated=updated, min_matches=min_matches
        )
        return updated
