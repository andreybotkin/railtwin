import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import time as dt_time
from difflib import SequenceMatcher
from math import atan2, cos, radians, sin, sqrt

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.schedule.entities import TrainData
from app.domain.schedule.repository import ScheduleRepository
from app.infrastructure.database.tables import (
    t_route_stations,
    t_routes,
    t_schedules,
    t_station_aliases,
    t_stations,
    t_trains,
)

logger = get_logger(__name__)

SOURCE_NAME = "raildbsetup_raw"
ALIAS_SOURCE = "schedule_raw"
# Aliases sourced from the curated JSON file (schedule_aliases block +
# per-station schedule_name). Loaded by ``_ensure_station_catalog`` with
# higher priority than runtime-learned ``schedule_raw`` aliases.
JSON_ALIAS_SOURCE = "json_aliases"
LEGACY_SOURCE_NAMES = {"raw_file", "seed_file", "local_cache", SOURCE_NAME}
_TIME_RE = re.compile(r"\([^)]*\)")

MANUAL_ALIAS_KEYS = {
    "bangkok": "bangkokhualamphong",
    "bangkokkrungthepaphiwat": "krungthepaphiwatcentralterminal",
}

_StationCache = dict[tuple[str, str | None, int | None], int | None]


@dataclass(slots=True)
class StationCandidate:
    id: int
    name: str
    route_type: str | None
    match_key: str
    lon: float
    lat: float


def _parse_time(t: str | dt_time | None) -> dt_time | None:
    if t is None or isinstance(t, dt_time):
        return t
    try:
        parts = t.split(":")
        return dt_time(int(parts[0]) % 24, int(parts[1]))
    except (AttributeError, ValueError, IndexError):
        return None


def _strip_parenthetical(value: str) -> str:
    return _TIME_RE.sub(" ", value)


def _normalize_station_name(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value)
    ascii_value = ascii_value.encode("ascii", "ignore").decode("ascii")
    ascii_value = ascii_value.lower().replace("&", " and ")
    ascii_value = ascii_value.replace("jct", "junction")
    ascii_value = re.sub(r"\bsta(?:tion)?\b", " ", ascii_value)
    ascii_value = re.sub(r"\bhalt\b", " ", ascii_value)
    ascii_value = re.sub(r"[^a-z0-9]+", " ", ascii_value)
    return " ".join(ascii_value.split())


def _station_match_key(value: str) -> str:
    normalized = _normalize_station_name(_strip_parenthetical(value))
    return normalized.replace(" ", "")


def _station_match_variants(value: str) -> set[str]:
    variants = {
        _station_match_key(value),
        _normalize_station_name(value).replace(" ", ""),
    }
    for parenthetical in re.findall(r"\(([^)]*)\)", value):
        key = _station_match_key(parenthetical)
        if key:
            variants.add(key)
    return {variant for variant in variants if variant}


def _similarity_score(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def _haversine_km(
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    earth_radius_km = 6371.0
    lon1, lat1 = first
    lon2, lat2 = second
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return earth_radius_km * 2 * atan2(sqrt(a), sqrt(1 - a))


class SqlScheduleRepository(ScheduleRepository):
    def __init__(
        self,
        session: AsyncSession,
        *,
        issues: list[dict[str, str | None]] | None = None,
    ) -> None:
        self._s = session
        self._station_cache: _StationCache = {}
        self._station_candidates: list[StationCandidate] | None = None
        self._stations_by_key: dict[str, list[StationCandidate]] | None = None
        self._stations_by_exact_name: dict[str, StationCandidate] = {}
        self._station_aliases: dict[str, int] | None = None
        self._candidate_by_id: dict[int, StationCandidate] = {}
        self._issues = issues
        self._current_train_number: str | None = None

    def set_current_train(self, train_number: str | None) -> None:
        """Tag unresolved-station issues with the train currently being processed."""
        self._current_train_number = train_number

    async def count_trains(self) -> int:
        result = await self._s.execute(select(func.count()).select_from(t_trains))
        return result.scalar_one() or 0

    async def reset_source_timetable(self) -> None:
        await self._s.execute(
            delete(t_station_aliases).where(t_station_aliases.c.source == ALIAS_SOURCE)
        )
        await self._s.execute(
            delete(t_trains).where(t_trains.c.source.in_(LEGACY_SOURCE_NAMES))
        )
        self._station_cache.clear()
        if self._station_aliases is not None:
            self._station_aliases.clear()

    async def upsert_train(self, train: TrainData) -> int:
        stmt = (
            pg_insert(t_trains)
            .values(
                train_number=train.train_number,
                train_type=train.train_type,
                name=train.name,
                capacity=None,
                operator=train.operator,
                source=SOURCE_NAME,
                source_url=train.source_url,
                service_notes=train.service_notes or {"route_type": train.route_type},
                current_route_id=None,
            )
            .on_conflict_do_update(
                index_elements=["train_number"],
                set_={
                    "train_type": train.train_type,
                    "name": train.name,
                    "capacity": None,
                    "operator": train.operator,
                    "source": SOURCE_NAME,
                    "source_url": train.source_url,
                    "service_notes": train.service_notes
                    or {"route_type": train.route_type},
                    "current_route_id": None,
                },
            )
            .returning(t_trains.c.id)
        )
        return (await self._s.execute(stmt)).scalar_one()

    async def replace_schedules(self, train_id: int, train: TrainData) -> int:
        await self._s.execute(
            delete(t_schedules).where(t_schedules.c.train_id == train_id)
        )
        count = 0
        prev_station_id: int | None = None
        for stop in train.stops:
            station_id = await self._resolve_station_id(
                stop.station_name,
                route_type_hint=train.route_type,
                prev_station_id=prev_station_id,
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

    async def assign_routes_by_station_match(self, min_matches: int = 2) -> int:
        await self._s.execute(
            update(t_trains)
            .where(t_trains.c.source == SOURCE_NAME)
            .values(current_route_id=None)
        )
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
            .where(
                t_trains.c.source == SOURCE_NAME,
                t_schedules.c.station_id.isnot(None),
            )
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
            )
        )
        result = await self._s.execute(stmt)
        updated = result.rowcount or 0  # type: ignore[attr-defined]
        logger.info("Route assignment complete", trains_updated=updated)
        return updated

    async def bind_route_stations_for_assigned_trains(self) -> int:
        trains = (
            await self._s.execute(
                select(t_trains.c.id, t_trains.c.current_route_id)
                .where(
                    t_trains.c.source == SOURCE_NAME,
                    t_trains.c.current_route_id.isnot(None),
                )
                .order_by(t_trains.c.id)
            )
        ).fetchall()

        updates = 0
        for train in trains:
            train_id = int(train.id)
            route_id = int(train.current_route_id)

            route_distance = (
                await self._s.execute(
                    select(t_routes.c.distance_km).where(t_routes.c.id == route_id)
                )
            ).scalar_one_or_none()
            route_distance_km = (
                float(route_distance) if route_distance is not None else None
            )

            route_stations = (
                await self._s.execute(
                    select(
                        t_route_stations.c.id,
                        t_route_stations.c.station_id,
                        t_route_stations.c.sequence,
                        t_route_stations.c.distance_from_start,
                    )
                    .where(t_route_stations.c.route_id == route_id)
                    .order_by(t_route_stations.c.sequence)
                )
            ).fetchall()
            if not route_stations:
                continue

            schedules = (
                await self._s.execute(
                    select(
                        t_schedules.c.id,
                        t_schedules.c.station_id,
                        t_schedules.c.sequence,
                        t_schedules.c.distance_from_origin_km,
                    )
                    .where(t_schedules.c.train_id == train_id)
                    .order_by(t_schedules.c.sequence)
                )
            ).fetchall()
            if not schedules:
                continue

            next_route_index = 0
            for schedule in schedules:
                if schedule.station_id is None:
                    continue

                matched_index: int | None = None
                for idx in range(next_route_index, len(route_stations)):
                    if int(route_stations[idx].station_id) == int(schedule.station_id):
                        matched_index = idx
                        break

                if matched_index is None:
                    for idx, route_station in enumerate(route_stations):
                        if int(route_station.station_id) == int(schedule.station_id):
                            matched_index = idx
                            break

                if matched_index is None:
                    continue

                route_station = route_stations[matched_index]
                next_route_index = matched_index + 1
                distance_from_start = (
                    float(route_station.distance_from_start)
                    if route_station.distance_from_start is not None
                    else None
                )
                route_progress = None
                if (
                    distance_from_start is not None
                    and route_distance_km
                    and route_distance_km > 0
                ):
                    route_progress = max(
                        0.0, min(1.0, distance_from_start / route_distance_km)
                    )

                values: dict[str, object] = {"route_station_id": int(route_station.id)}
                if (
                    schedule.distance_from_origin_km is None
                    and distance_from_start is not None
                ):
                    values["distance_from_origin_km"] = distance_from_start
                if route_progress is not None:
                    values["route_progress"] = route_progress

                await self._s.execute(
                    update(t_schedules)
                    .where(t_schedules.c.id == int(schedule.id))
                    .values(**values)
                )
                updates += 1

        logger.info("Route station binding complete", schedule_rows_updated=updates)
        return updates

    async def _ensure_station_catalog(self) -> None:
        if self._station_candidates is not None:
            return

        station_rows = (
            await self._s.execute(
                select(
                    t_stations.c.id,
                    t_stations.c.name,
                    t_stations.c.source_route_type,
                    func.ST_X(t_stations.c.location).label("lon"),
                    func.ST_Y(t_stations.c.location).label("lat"),
                )
            )
        ).fetchall()

        self._station_candidates = []
        self._stations_by_key = {}
        for row in station_rows:
            candidate = StationCandidate(
                id=int(row.id),
                name=str(row.name),
                route_type=(
                    str(row.source_route_type) if row.source_route_type else None
                ),
                match_key=_station_match_key(str(row.name)),
                lon=float(row.lon),
                lat=float(row.lat),
            )
            self._station_candidates.append(candidate)
            self._candidate_by_id[candidate.id] = candidate
            self._stations_by_exact_name[candidate.name.casefold().strip()] = candidate
            self._stations_by_key.setdefault(candidate.match_key, []).append(candidate)

        alias_rows = (
            await self._s.execute(
                select(
                    t_station_aliases.c.normalized_alias,
                    t_station_aliases.c.station_id,
                    t_station_aliases.c.source,
                ).where(
                    t_station_aliases.c.source.in_([ALIAS_SOURCE, JSON_ALIAS_SOURCE])
                )
            )
        ).fetchall()
        # Curated JSON aliases override any runtime-learned fuzzy mapping.
        self._station_aliases = {}
        for row in alias_rows:
            key = str(row.normalized_alias)
            if row.source == JSON_ALIAS_SOURCE or key not in self._station_aliases:
                self._station_aliases[key] = int(row.station_id)

    async def _resolve_station_id(
        self,
        station_name: str,
        route_type_hint: str | None,
        prev_station_id: int | None,
    ) -> int | None:
        await self._ensure_station_catalog()
        exact_name_key = station_name.casefold().strip()
        cache_key = (exact_name_key, route_type_hint, prev_station_id)
        if cache_key in self._station_cache:
            return self._station_cache[cache_key]

        # Exact canonical names must win before the parenthetical-insensitive
        # matching used for aliases.  Otherwise distinct stops such as
        # "Padang Besar" and "Padang Besar (Thai)" collapse to one station.
        exact_match = self._stations_by_exact_name.get(exact_name_key)
        if exact_match is not None:
            self._station_cache[cache_key] = exact_match.id
            return exact_match.id

        variants = _station_match_variants(station_name)
        manual_target = next(
            (
                MANUAL_ALIAS_KEYS[variant]
                for variant in variants
                if variant in MANUAL_ALIAS_KEYS
            ),
            None,
        )
        if manual_target:
            variants.add(manual_target)

        assert self._stations_by_key is not None
        assert self._station_aliases is not None
        direct_matches = self._find_direct_matches(variants)
        if direct_matches:
            station_id = self._choose_candidate(
                direct_matches, route_type_hint, prev_station_id
            )
            await self._persist_alias(station_name, station_id)
            self._station_cache[cache_key] = station_id
            return station_id

        candidate_pool = self._filter_candidates_by_route_type(route_type_hint)
        best_station_id = self._find_best_fuzzy_match(
            variants,
            candidate_pool,
            route_type_hint,
            prev_station_id,
        )
        if best_station_id is not None:
            await self._persist_alias(station_name, best_station_id)
        else:
            logger.warning(
                "Station not matched from raw schedule", station_name=station_name
            )
            if self._issues is not None:
                self._issues.append(
                    {
                        "train_number": self._current_train_number,
                        "station_name": station_name,
                        "route_type": route_type_hint,
                        "reason": "not_matched",
                    }
                )
        self._station_cache[cache_key] = best_station_id
        return best_station_id

    def _find_direct_matches(self, variants: set[str]) -> list[StationCandidate]:
        assert self._stations_by_key is not None
        assert self._station_aliases is not None
        candidates: dict[int, StationCandidate] = {}
        for variant in variants:
            alias_station_id = self._station_aliases.get(variant)
            if (
                alias_station_id is not None
                and alias_station_id in self._candidate_by_id
            ):
                candidate = self._candidate_by_id[alias_station_id]
                candidates[candidate.id] = candidate
            for candidate in self._stations_by_key.get(variant, []):
                candidates[candidate.id] = candidate
        return list(candidates.values())

    def _filter_candidates_by_route_type(
        self,
        route_type_hint: str | None,
    ) -> Iterable[StationCandidate]:
        assert self._station_candidates is not None
        normalized_hint = (route_type_hint or "").strip().lower()
        if not normalized_hint or normalized_hint == "other":
            return self._station_candidates
        matching = [
            candidate
            for candidate in self._station_candidates
            if candidate.route_type == normalized_hint
        ]
        return matching or self._station_candidates

    def _find_best_fuzzy_match(
        self,
        variants: set[str],
        candidate_pool: Iterable[StationCandidate],
        route_type_hint: str | None,
        prev_station_id: int | None,
    ) -> int | None:
        scored: list[tuple[float, StationCandidate]] = []
        normalized_hint = (route_type_hint or "").strip().lower()
        for candidate in candidate_pool:
            score = max(
                _similarity_score(variant, candidate.match_key) for variant in variants
            )
            if normalized_hint and candidate.route_type == normalized_hint:
                score += 0.03
            if score >= 0.74:
                scored.append((score, candidate))

        if not scored:
            return None

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score = scored[0][0]
        contenders = [
            candidate for score, candidate in scored if score >= best_score - 0.03
        ]
        chosen = self._choose_candidate(contenders, route_type_hint, prev_station_id)
        if best_score < 0.84 and prev_station_id is None:
            return None
        return chosen

    def _choose_candidate(
        self,
        candidates: list[StationCandidate],
        route_type_hint: str | None,
        prev_station_id: int | None,
    ) -> int:
        normalized_hint = (route_type_hint or "").strip().lower()
        preferred = [
            candidate
            for candidate in candidates
            if candidate.route_type == normalized_hint
        ]
        filtered = preferred or candidates
        if prev_station_id is None or prev_station_id not in self._candidate_by_id:
            return sorted(
                filtered, key=lambda candidate: (len(candidate.match_key), candidate.id)
            )[0].id

        previous = self._candidate_by_id[prev_station_id]
        return min(
            filtered,
            key=lambda candidate: (
                _haversine_km(
                    (previous.lon, previous.lat), (candidate.lon, candidate.lat)
                ),
                len(candidate.match_key),
                candidate.id,
            ),
        ).id

    async def _persist_alias(self, station_name: str, station_id: int) -> None:
        normalized_alias = _station_match_key(station_name)
        if not normalized_alias:
            return
        await self._s.execute(
            pg_insert(t_station_aliases)
            .values(
                station_id=station_id,
                source=ALIAS_SOURCE,
                alias=station_name,
                normalized_alias=normalized_alias,
            )
            .on_conflict_do_nothing(
                constraint="uq_station_aliases_source_normalized_alias"
            )
        )
        if self._station_aliases is not None:
            self._station_aliases[normalized_alias] = station_id
