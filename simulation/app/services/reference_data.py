"""Redis-backed reference data store for simulation read paths."""

from __future__ import annotations

import json
import re
from datetime import datetime, time
from types import SimpleNamespace
from typing import Any

from geoalchemy2.elements import WKTElement
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.repositories.movement_plan import MovementPlanRepository
from app.repositories.network import NetworkRepository
from app.repositories.route import RouteRepository
from app.repositories.schedule import ScheduleRepository
from app.repositories.station import StationRepository
from app.repositories.train import TrainRepository

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_SEARCH_PREFIX = "sim:ref:search:"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), default=str)


def _json_loads(value: str | bytes | None, default: Any) -> Any:
    if not value:
        return default
    if isinstance(value, bytes):
        value = value.decode()
    return json.loads(value)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _time_to_str(value: time | None) -> str | None:
    return value.isoformat() if value is not None else None


def _time_from_str(value: str | None) -> time | None:
    return time.fromisoformat(value) if value else None


def _normalise_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(_TOKEN_RE.findall(value.lower()))


def _station_search_tokens(payload: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for field in ("name", "name_th", "code", "city", "province"):
        tokens.update(_TOKEN_RE.findall(str(payload.get(field, "")).lower()))
    return {token for token in tokens if token}


class ReferenceDataKeys:
    """Key builder for Redis reference-data namespace."""

    def __init__(self, namespace: str | None = None) -> None:
        self.ns = namespace or settings.reference_data_namespace

    @property
    def meta(self) -> str:
        return f"{self.ns}:meta"

    @property
    def stations_by_id(self) -> str:
        return f"{self.ns}:stations:by_id"

    @property
    def stations_by_code(self) -> str:
        return f"{self.ns}:stations:by_code"

    @property
    def station_ids(self) -> str:
        return f"{self.ns}:stations:ids"

    def station_search(self, token: str) -> str:
        return f"{self.ns}:stations:search:{token}"

    @property
    def routes_by_id(self) -> str:
        return f"{self.ns}:routes:by_id"

    @property
    def route_ids(self) -> str:
        return f"{self.ns}:routes:ids"

    def routes_by_type(self, route_type: str) -> str:
        return f"{self.ns}:routes:by_type:{route_type}"

    def route_geometry(self, route_id: int) -> str:
        return f"{self.ns}:route_geometry:by_route:{route_id}"

    def route_edges(self, route_id: int) -> str:
        return f"{self.ns}:route_edges:by_route:{route_id}"

    @property
    def trains_by_id(self) -> str:
        return f"{self.ns}:trains:by_id"

    @property
    def train_ids(self) -> str:
        return f"{self.ns}:trains:ids"

    @property
    def trains_by_number(self) -> str:
        return f"{self.ns}:trains:by_number"

    def trains_by_type(self, train_type: str) -> str:
        return f"{self.ns}:trains:by_type:{train_type}"

    def trains_by_route(self, route_id: int) -> str:
        return f"{self.ns}:trains:by_route:{route_id}"

    @property
    def schedules_by_id(self) -> str:
        return f"{self.ns}:schedules:by_id"

    @property
    def schedule_ids(self) -> str:
        return f"{self.ns}:schedules:ids"

    def schedules_by_train(self, train_id: int) -> str:
        return f"{self.ns}:schedules:by_train:{train_id}"

    def schedules_by_station(self, station_id: int) -> str:
        return f"{self.ns}:schedules:by_station:{station_id}"

    @property
    def network_edges(self) -> str:
        return f"{self.ns}:network:edges"

    @property
    def network_nodes(self) -> str:
        return f"{self.ns}:network:nodes"

    @property
    def topology(self) -> str:
        return f"{self.ns}:network:topology"

    @property
    def adjacency(self) -> str:
        return f"{self.ns}:network:adjacency"

    @property
    def physical_adjacency(self) -> str:
        return f"{self.ns}:network:physical_adjacency"

    def movement_plan_by_train(self, train_id: int) -> str:
        return f"{self.ns}:movement_plans:by_train:{train_id}"

    @property
    def movement_plan_ids(self) -> str:
        return f"{self.ns}:movement_plans:ids"


def _serialize_movement_plan(run: Any) -> dict[str, Any]:
    """Serialise a :class:`PlannedTrainRun` ORM instance for Redis storage."""
    segments = []
    for seg in sorted(
        run.segments or [],
        key=lambda s: s.sequence,
    ):
        segments.append(
            {
                "id": int(seg.id),
                "sequence": int(seg.sequence),
                "segment_type": seg.segment_type,
                "from_station_id": (
                    int(seg.from_station_id)
                    if seg.from_station_id is not None
                    else None
                ),
                "to_station_id": (
                    int(seg.to_station_id) if seg.to_station_id is not None else None
                ),
                "from_schedule_id": (
                    int(seg.from_schedule_id)
                    if seg.from_schedule_id is not None
                    else None
                ),
                "to_schedule_id": (
                    int(seg.to_schedule_id) if seg.to_schedule_id is not None else None
                ),
                "start_time_minutes": int(seg.start_time_minutes),
                "end_time_minutes": int(seg.end_time_minutes),
                "start_day_offset": int(seg.start_day_offset),
                "end_day_offset": int(seg.end_day_offset),
                "absolute_start_minutes": int(seg.absolute_start_minutes),
                "absolute_end_minutes": int(seg.absolute_end_minutes),
                "start_distance_m": (
                    float(seg.start_distance_m)
                    if seg.start_distance_m is not None
                    else None
                ),
                "end_distance_m": (
                    float(seg.end_distance_m)
                    if seg.end_distance_m is not None
                    else None
                ),
                "start_geom_fraction": (
                    float(seg.start_geom_fraction)
                    if seg.start_geom_fraction is not None
                    else None
                ),
                "end_geom_fraction": (
                    float(seg.end_geom_fraction)
                    if seg.end_geom_fraction is not None
                    else None
                ),
                "start_edge_id": (
                    int(seg.start_edge_id) if seg.start_edge_id is not None else None
                ),
                "end_edge_id": (
                    int(seg.end_edge_id) if seg.end_edge_id is not None else None
                ),
                "planned_speed_kmh": (
                    float(seg.planned_speed_kmh)
                    if seg.planned_speed_kmh is not None
                    else None
                ),
                "quality_score": (
                    float(seg.quality_score) if seg.quality_score is not None else None
                ),
                "warnings": seg.warnings or [],
            }
        )
    return {
        "id": int(run.id),
        "train_id": int(run.train_id),
        "route_id": int(run.route_id),
        "service_date": str(run.service_date) if run.service_date else None,
        "service_pattern": run.service_pattern,
        "plan_version": run.plan_version,
        "topology_version": run.topology_version,
        "quality_score": (
            float(run.quality_score) if run.quality_score is not None else None
        ),
        "status": run.status,
        "warnings": run.warnings or [],
        "segments": segments,
    }


def _movement_plan_to_domain(payload: dict[str, Any]) -> Any:
    """Reconstruct a :class:`PlannedTrainRun` domain object from a Redis payload."""
    from app.domain.movement_plan import PlannedMovementSegment, PlannedTrainRun

    segments = []
    for seg in payload.get("segments", []):
        segments.append(
            PlannedMovementSegment(
                id=seg.get("id"),
                planned_run_id=payload["id"],
                sequence=int(seg["sequence"]),
                segment_type=seg["segment_type"],
                from_station_id=seg.get("from_station_id"),
                to_station_id=seg.get("to_station_id"),
                from_schedule_id=seg.get("from_schedule_id"),
                to_schedule_id=seg.get("to_schedule_id"),
                start_time_minutes=float(seg["start_time_minutes"]),
                end_time_minutes=float(seg["end_time_minutes"]),
                start_day_offset=int(seg["start_day_offset"]),
                end_day_offset=int(seg["end_day_offset"]),
                start_distance_m=seg.get("start_distance_m"),
                end_distance_m=seg.get("end_distance_m"),
                start_geom_fraction=seg.get("start_geom_fraction"),
                end_geom_fraction=seg.get("end_geom_fraction"),
                start_edge_id=seg.get("start_edge_id"),
                end_edge_id=seg.get("end_edge_id"),
                planned_speed_kmh=seg.get("planned_speed_kmh"),
                quality_score=seg.get("quality_score"),
                warnings=seg.get("warnings") or [],
            )
        )
    return PlannedTrainRun(
        id=payload.get("id"),
        train_id=int(payload["train_id"]),
        route_id=int(payload["route_id"]),
        service_date=payload.get("service_date"),
        plan_version=int(payload.get("plan_version") or 0),
        topology_version=payload.get("topology_version") or "",
        quality_score=payload.get("quality_score"),
        status=payload.get("status", "invalid"),
        warnings=payload.get("warnings") or [],
        segments=segments,
    )


def _serialize_station(station: Any) -> dict[str, Any]:
    geojson = _json_loads(getattr(station, "_geojson", None), {})
    return {
        "id": int(station.id),
        "name": station.name,
        "name_th": station.name_th,
        "code": station.code,
        "city": station.city,
        "province": station.province,
        "facilities": station.facilities,
        "location": {
            "type": "Point",
            "coordinates": geojson.get("coordinates", [0, 0]),
        },
        "created_at": station.created_at.isoformat(),
        "updated_at": station.updated_at.isoformat(),
    }


def _serialize_route(route: Any) -> dict[str, Any]:
    line_geometry = _json_loads(getattr(route, "_geojson", None), None)
    stations = []
    for route_station in sorted(
        route.route_stations or [], key=lambda item: item.sequence
    ):
        station = route_station.station
        if station is None:
            continue
        stations.append(
            {
                "id": int(station.id),
                "name": station.name,
                "code": station.code,
                "sequence": int(route_station.sequence),
                "distance_from_start": _to_float(route_station.distance_from_start),
                "route_station_id": int(route_station.id),
            }
        )
    return {
        "id": int(route.id),
        "name": route.name,
        "name_th": route.name_th,
        "route_type": route.route_type,
        "distance_km": _to_float(route.distance_km),
        "color": route.color,
        "line_geometry": line_geometry,
        "stations": stations,
        "created_at": route.created_at.isoformat(),
    }


def _serialize_train(train: Any) -> dict[str, Any]:
    current_route = None
    if train.current_route is not None:
        current_route = {
            "id": int(train.current_route.id),
            "name": train.current_route.name,
            "route_type": train.current_route.route_type,
            "color": train.current_route.color,
        }
    return {
        "id": int(train.id),
        "train_number": train.train_number,
        "train_type": train.train_type,
        "name": train.name,
        "capacity": train.capacity,
        "operator": train.operator,
        "source": train.source,
        "source_url": train.source_url,
        "service_notes": train.service_notes,
        "current_route_id": train.current_route_id,
        "current_route": current_route,
        "created_at": train.created_at.isoformat(),
    }


def _serialize_schedule(
    schedule: Any,
    *,
    route_station_distances: dict[int, float | None],
) -> dict[str, Any]:
    train_summary = None
    if schedule.train is not None:
        train_summary = {
            "id": int(schedule.train.id),
            "train_number": schedule.train.train_number,
            "train_type": schedule.train.train_type,
            "name": schedule.train.name,
        }
    station_summary = None
    if schedule.station is not None:
        station_summary = {
            "id": int(schedule.station.id),
            "name": schedule.station.name,
            "name_th": getattr(schedule.station, "name_th", None),
            "code": schedule.station.code,
            "location": getattr(schedule.station, "_geojson", None),
        }
    route_station_distance = None
    if schedule.route_station_id is not None:
        route_station_distance = route_station_distances.get(
            int(schedule.route_station_id)
        )
    return {
        "id": int(schedule.id),
        "train_id": int(schedule.train_id),
        "station_id": (
            int(schedule.station_id) if schedule.station_id is not None else None
        ),
        "station_name": schedule.station_name,
        "arrival_time": _time_to_str(schedule.arrival_time),
        "departure_time": _time_to_str(schedule.departure_time),
        "arrival_day_offset": int(schedule.arrival_day_offset),
        "departure_day_offset": int(schedule.departure_day_offset),
        "day_of_week": schedule.day_of_week,
        "platform": schedule.platform,
        "sequence": int(schedule.sequence),
        "route_station_id": (
            int(schedule.route_station_id)
            if schedule.route_station_id is not None
            else None
        ),
        "route_station_distance_from_start": route_station_distance,
        "distance_from_origin_km": _to_float(schedule.distance_from_origin_km),
        "route_progress": _to_float(schedule.route_progress),
        "train": train_summary,
        "station": station_summary,
    }


def _schedule_sort_key(payload: dict[str, Any]) -> tuple[int, int, int]:
    departure = _time_from_str(payload.get("departure_time"))
    arrival = _time_from_str(payload.get("arrival_time"))
    preferred = departure or arrival or time(0, 0)
    offset = (
        int(payload.get("departure_day_offset") or 0)
        if departure is not None
        else int(payload.get("arrival_day_offset") or 0)
    )
    return (
        offset,
        preferred.hour * 60 + preferred.minute,
        int(payload.get("sequence") or 0),
    )


class RedisReferenceDataLoader:
    """Load and refresh reference data from Postgres into Redis."""

    def __init__(
        self,
        session: AsyncSession,
        redis_client: Redis,
        *,
        batch_size: int | None = None,
        namespace: str | None = None,
    ) -> None:
        self._session = session
        self._redis = redis_client
        self._batch_size = batch_size or settings.reference_data_batch_size
        self._keys = ReferenceDataKeys(namespace)

    async def load(self) -> dict[str, Any]:
        await self._clear_namespace()
        loading_meta = {
            "schema_version": 1,
            "load_status": "loading",
            "loaded_at": None,
        }
        await self._redis.set(self._keys.meta, _json_dumps(loading_meta))

        station_repo = StationRepository(self._session)
        route_repo = RouteRepository(self._session)
        train_repo = TrainRepository(self._session)
        schedule_repo = ScheduleRepository(self._session)
        network_repo = NetworkRepository(self._session)
        movement_plan_repo = MovementPlanRepository(self._session)

        stations: list[dict[str, Any]] = []
        routes: list[dict[str, Any]] = []
        trains: list[dict[str, Any]] = []
        schedules: list[dict[str, Any]] = []
        route_station_distances: dict[int, float | None] = {}
        batch: list[Any]

        offset = 0
        while True:
            batch = await station_repo.get_all_with_location(
                skip=offset,
                limit=self._batch_size,
            )
            if not batch:
                break
            stations.extend(_serialize_station(station) for station in batch)
            if len(batch) < self._batch_size:
                break
            offset += self._batch_size

        offset = 0
        while True:
            batch = await route_repo.get_all_with_geometry(
                skip=offset,
                limit=self._batch_size,
            )
            if not batch:
                break
            for route in batch:
                route_payload = _serialize_route(route)
                routes.append(route_payload)
                for station in route_payload["stations"]:
                    route_station_id = station.get("route_station_id")
                    if route_station_id is not None:
                        route_station_distances[int(route_station_id)] = station.get(
                            "distance_from_start"
                        )
            if len(batch) < self._batch_size:
                break
            offset += self._batch_size

        offset = 0
        while True:
            batch = await train_repo.get_all_with_route(
                skip=offset,
                limit=self._batch_size,
            )
            if not batch:
                break
            trains.extend(_serialize_train(train) for train in batch)
            if len(batch) < self._batch_size:
                break
            offset += self._batch_size

        offset = 0
        while True:
            batch = await schedule_repo.get_all_with_relations(
                skip=offset,
                limit=self._batch_size,
            )
            if not batch:
                break
            schedules.extend(
                _serialize_schedule(
                    schedule,
                    route_station_distances=route_station_distances,
                )
                for schedule in batch
            )
            if len(batch) < self._batch_size:
                break
            offset += self._batch_size

        route_ids = [int(route["id"]) for route in routes]
        route_geometry_by_route = await route_repo.get_graph_geometry_bulk(route_ids)

        topology = await network_repo.get_topology_metadata()
        network_edges = await network_repo.get_all_edges(include_synthetic=True)
        network_nodes = await network_repo.get_all_nodes()
        adjacency = await network_repo.get_adjacency_list()
        physical_adjacency = await network_repo.get_adjacency_list(
            include_synthetic=False
        )

        schedules_by_train: dict[int, list[dict[str, Any]]] = {}
        schedules_by_station: dict[int, list[dict[str, Any]]] = {}
        for schedule in schedules:
            schedules_by_train.setdefault(int(schedule["train_id"]), []).append(
                schedule
            )
            station_id = schedule.get("station_id")
            if station_id is not None:
                schedules_by_station.setdefault(int(station_id), []).append(schedule)

        for grouped in schedules_by_train.values():
            grouped.sort(key=lambda item: int(item.get("sequence") or 0))
        for grouped in schedules_by_station.values():
            grouped.sort(key=_schedule_sort_key)

        pipe = self._redis.pipeline()
        for station in stations:
            station_id = str(station["id"])
            pipe.hset(self._keys.stations_by_id, station_id, _json_dumps(station))
            pipe.hset(self._keys.stations_by_code, station["code"], station_id)
            for token in _station_search_tokens(station):
                pipe.sadd(self._keys.station_search(token), station_id)

        for route_data in routes:
            route_id = int(route_data["id"])
            pipe.hset(self._keys.routes_by_id, str(route_id), _json_dumps(route_data))
            pipe.sadd(self._keys.routes_by_type(route_data["route_type"]), route_id)
            geometry_payload = route_geometry_by_route.get(route_id, {})
            pipe.set(self._keys.route_geometry(route_id), _json_dumps(geometry_payload))
            pipe.set(
                self._keys.route_edges(route_id),
                _json_dumps(await network_repo.get_route_edge_sequence(route_id)),
            )

        for train in trains:
            train_id = str(train["id"])
            pipe.hset(self._keys.trains_by_id, train_id, _json_dumps(train))
            pipe.hset(self._keys.trains_by_number, train["train_number"], train_id)
            pipe.sadd(self._keys.trains_by_type(train["train_type"]), train_id)
            if train.get("current_route_id") is not None:
                pipe.sadd(
                    self._keys.trains_by_route(int(train["current_route_id"])), train_id
                )

        for schedule in schedules:
            pipe.hset(
                self._keys.schedules_by_id,
                str(schedule["id"]),
                _json_dumps(schedule),
            )

        for sched_train_id, grouped in schedules_by_train.items():
            pipe.set(
                self._keys.schedules_by_train(sched_train_id), _json_dumps(grouped)
            )
        for sched_station_id, grouped in schedules_by_station.items():
            pipe.set(
                self._keys.schedules_by_station(sched_station_id), _json_dumps(grouped)
            )

        pipe.set(
            self._keys.station_ids, _json_dumps([station["id"] for station in stations])
        )
        pipe.set(self._keys.route_ids, _json_dumps([route["id"] for route in routes]))
        pipe.set(self._keys.train_ids, _json_dumps([train["id"] for train in trains]))
        pipe.set(
            self._keys.schedule_ids,
            _json_dumps([schedule["id"] for schedule in schedules]),
        )
        pipe.set(self._keys.network_edges, _json_dumps(network_edges))
        pipe.set(self._keys.network_nodes, _json_dumps(network_nodes))
        pipe.set(self._keys.topology, _json_dumps(topology or {}))
        pipe.set(self._keys.adjacency, _json_dumps(adjacency))
        pipe.set(self._keys.physical_adjacency, _json_dumps(physical_adjacency))

        # Movement plan snapshot (best usable run per train).
        movement_plan_train_ids: list[int] = []
        try:
            mp_runs = await movement_plan_repo.get_best_runs_for_all_trains()
            for mp_run in mp_runs:
                mp_train_id = int(mp_run.train_id)
                movement_plan_train_ids.append(mp_train_id)
                pipe.set(
                    self._keys.movement_plan_by_train(mp_train_id),
                    _json_dumps(_serialize_movement_plan(mp_run)),
                )
            pipe.set(
                self._keys.movement_plan_ids,
                _json_dumps(movement_plan_train_ids),
            )
        except Exception as exc:  # noqa: BLE001
            # Non-fatal: movement plans may not be built yet.
            logger.warning("Could not load movement plans into Redis", error=str(exc))
            movement_plan_train_ids = []

        meta = {
            "schema_version": 1,
            "load_status": "ready",
            "loaded_at": datetime.utcnow().isoformat(),
            "source_topology_version": (topology or {}).get("topology_version"),
            "stations_count": len(stations),
            "routes_count": len(routes),
            "trains_count": len(trains),
            "schedules_count": len(schedules),
            "route_stations_count": sum(len(route["stations"]) for route in routes),
            "movement_plans_count": len(movement_plan_train_ids),
        }
        pipe.set(self._keys.meta, _json_dumps(meta))
        await pipe.execute()
        logger.info("Reference data loaded into Redis", **meta)
        return meta

    async def _clear_namespace(self) -> None:
        pattern = f"{self._keys.ns}:*"
        keys = [key async for key in self._redis.scan_iter(match=pattern)]
        if keys:
            await self._redis.delete(*keys)


class RedisReferenceReader:
    """Read reference data from Redis."""

    def __init__(
        self,
        redis_client: Redis,
        *,
        namespace: str | None = None,
    ) -> None:
        self._redis = redis_client
        self._keys = ReferenceDataKeys(namespace)

    async def is_ready(self) -> bool:
        meta = await self.get_meta()
        return meta.get("load_status") == "ready"

    async def get_meta(self) -> dict[str, Any]:
        return _json_loads(await self._redis.get(self._keys.meta), {})

    async def get_station(self, station_id: int) -> dict[str, Any] | None:
        raw = await self._redis.hget(self._keys.stations_by_id, str(station_id))
        return _json_loads(raw, None)

    async def get_station_by_code(self, code: str) -> dict[str, Any] | None:
        station_id = await self._redis.hget(self._keys.stations_by_code, code)
        if station_id is None:
            return None
        return await self.get_station(int(station_id))

    async def list_stations(
        self, page: int, size: int
    ) -> tuple[list[dict[str, Any]], int]:
        ids = await self._get_ids(self._keys.station_ids)
        total = len(ids)
        page_ids = ids[(page - 1) * size : (page - 1) * size + size]
        return await self._get_hash_payloads(self._keys.stations_by_id, page_ids), total

    async def search_stations(self, query: str, limit: int) -> list[dict[str, Any]]:
        tokens = list(dict.fromkeys(_TOKEN_RE.findall(query.lower())))
        if not tokens:
            return []
        station_ids: set[str] | None = None
        for token in tokens:
            members = {
                member.decode() if isinstance(member, bytes) else str(member)
                for member in await self._redis.smembers(
                    self._keys.station_search(token)
                )
            }
            station_ids = members if station_ids is None else station_ids & members
        if not station_ids:
            return []
        payloads = await self._get_hash_payloads(
            self._keys.stations_by_id,
            sorted(int(station_id) for station_id in station_ids),
        )
        normalised_query = _normalise_text(query)
        payloads.sort(
            key=lambda payload: (
                0 if payload["code"].lower() == query.lower() else 1,
                (
                    0
                    if _normalise_text(payload["name"]).startswith(normalised_query)
                    else 1
                ),
                payload["name"],
            )
        )
        return payloads[:limit]

    async def get_route(self, route_id: int) -> dict[str, Any] | None:
        raw = await self._redis.hget(self._keys.routes_by_id, str(route_id))
        return _json_loads(raw, None)

    async def list_routes(
        self,
        page: int,
        size: int,
        route_type: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        if route_type:
            ids = await self._get_set_ids(self._keys.routes_by_type(route_type))
        else:
            ids = await self._get_ids(self._keys.route_ids)
        total = len(ids)
        page_ids = ids[(page - 1) * size : (page - 1) * size + size]
        return await self._get_hash_payloads(self._keys.routes_by_id, page_ids), total

    async def get_train(self, train_id: int) -> dict[str, Any] | None:
        raw = await self._redis.hget(self._keys.trains_by_id, str(train_id))
        return _json_loads(raw, None)

    async def get_train_by_number(self, train_number: str) -> dict[str, Any] | None:
        train_id = await self._redis.hget(self._keys.trains_by_number, train_number)
        if train_id is None:
            return None
        return await self.get_train(int(train_id))

    async def list_trains(
        self,
        page: int,
        size: int,
        train_type: str | None = None,
        route_id: int | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        if train_type:
            ids = await self._get_set_ids(self._keys.trains_by_type(train_type))
        elif route_id is not None:
            ids = await self._get_set_ids(self._keys.trains_by_route(route_id))
        else:
            ids = await self._get_ids(self._keys.train_ids)
        total = len(ids)
        page_ids = ids[(page - 1) * size : (page - 1) * size + size]
        return await self._get_hash_payloads(self._keys.trains_by_id, page_ids), total

    async def get_schedule(self, schedule_id: int) -> dict[str, Any] | None:
        raw = await self._redis.hget(self._keys.schedules_by_id, str(schedule_id))
        return _json_loads(raw, None)

    async def list_schedules(
        self,
        page: int,
        size: int,
        train_id: int | None = None,
        station_id: int | None = None,
        day_of_week: int | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        if train_id is not None:
            payloads = _json_loads(
                await self._redis.get(self._keys.schedules_by_train(train_id)),
                [],
            )
        elif station_id is not None:
            payloads = _json_loads(
                await self._redis.get(self._keys.schedules_by_station(station_id)),
                [],
            )
        else:
            ids = await self._get_ids(self._keys.schedule_ids)
            payloads = await self._get_hash_payloads(self._keys.schedules_by_id, ids)
        if day_of_week is not None:
            payloads = [
                payload
                for payload in payloads
                if payload.get("day_of_week") is None
                or day_of_week in payload["day_of_week"]
            ]
        payloads.sort(key=_schedule_sort_key)
        total = len(payloads)
        return payloads[(page - 1) * size : (page - 1) * size + size], total

    async def get_train_schedule(
        self,
        train_id: int,
        day_of_week: int | None = None,
    ) -> list[dict[str, Any]]:
        payloads = _json_loads(
            await self._redis.get(self._keys.schedules_by_train(train_id)), []
        )
        if day_of_week is not None:
            payloads = [
                payload
                for payload in payloads
                if payload.get("day_of_week") is None
                or day_of_week in payload["day_of_week"]
            ]
        payloads.sort(key=lambda item: int(item.get("sequence") or 0))
        return payloads

    async def get_station_schedule(
        self,
        station_id: int,
        day_of_week: int | None = None,
    ) -> list[dict[str, Any]]:
        payloads = _json_loads(
            await self._redis.get(self._keys.schedules_by_station(station_id)),
            [],
        )
        if day_of_week is not None:
            payloads = [
                payload
                for payload in payloads
                if payload.get("day_of_week") is None
                or day_of_week in payload["day_of_week"]
            ]
        payloads.sort(key=_schedule_sort_key)
        return payloads

    async def get_station_ids_with_schedules(self) -> set[int]:
        ids = await self._get_ids(self._keys.schedule_ids)
        if not ids:
            return set()
        payloads = await self._get_hash_payloads(self._keys.schedules_by_id, ids)
        station_ids: set[int] = set()
        for payload in payloads:
            station_id = payload.get("station_id")
            if isinstance(station_id, int):
                station_ids.add(station_id)
        return station_ids

    async def get_upcoming_departures(
        self,
        station_id: int,
        current_time: time,
        day_of_week: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        payloads = await self.get_station_schedule(station_id, day_of_week)
        current_minutes = current_time.hour * 60 + current_time.minute
        result = []
        for payload in payloads:
            departure = _time_from_str(payload.get("departure_time"))
            if departure is None:
                continue
            departure_minutes = departure.hour * 60 + departure.minute
            if departure_minutes >= current_minutes:
                result.append(payload)
        return result[:limit]

    async def get_schedules_by_trains(
        self,
        train_ids: list[int],
    ) -> dict[int, list[dict[str, Any]]]:
        grouped: dict[int, list[dict[str, Any]]] = {}
        if not train_ids:
            return grouped
        pipe = self._redis.pipeline()
        for train_id in train_ids:
            pipe.get(self._keys.schedules_by_train(train_id))
        raw_payloads = await pipe.execute()
        for train_id, raw in zip(train_ids, raw_payloads, strict=False):
            grouped[train_id] = _json_loads(raw, [])
        return grouped

    async def get_route_geometry_bulk(
        self,
        route_ids: list[int],
    ) -> dict[int, dict[str, Any]]:
        if not route_ids:
            return {}
        pipe = self._redis.pipeline()
        for route_id in route_ids:
            pipe.get(self._keys.route_geometry(route_id))
        raw_payloads = await pipe.execute()
        result: dict[int, dict[str, Any]] = {}
        for route_id, raw in zip(route_ids, raw_payloads, strict=False):
            result[route_id] = _json_loads(raw, {})
        return result

    async def get_network_edges(self) -> list[dict[str, Any]]:
        return _json_loads(await self._redis.get(self._keys.network_edges), [])

    async def get_network_nodes(self) -> list[dict[str, Any]]:
        return _json_loads(await self._redis.get(self._keys.network_nodes), [])

    async def get_topology(self) -> dict[str, Any]:
        return _json_loads(await self._redis.get(self._keys.topology), {})

    async def get_adjacency(
        self, *, include_synthetic: bool = True
    ) -> dict[str, list[int]]:
        key = (
            self._keys.adjacency if include_synthetic else self._keys.physical_adjacency
        )
        return _json_loads(await self._redis.get(key), {})

    async def get_route_edges(self, route_id: int) -> list[dict[str, Any]]:
        return _json_loads(await self._redis.get(self._keys.route_edges(route_id)), [])

    async def get_all_trains_for_simulation(
        self,
        *,
        skip: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        ids = await self._get_ids(self._keys.train_ids)
        return await self._get_hash_payloads(
            self._keys.trains_by_id,
            ids[skip : skip + limit],
        )

    async def _get_ids(self, key: str) -> list[int]:
        return [int(value) for value in _json_loads(await self._redis.get(key), [])]

    async def _get_set_ids(self, key: str) -> list[int]:
        members = await self._redis.smembers(key)
        values = [
            int(member.decode() if isinstance(member, bytes) else member)
            for member in members
        ]
        values.sort()
        return values

    async def _get_hash_payloads(
        self, key: str, ids: list[int]
    ) -> list[dict[str, Any]]:
        if not ids:
            return []
        raw_values = await self._redis.hmget(key, [str(item) for item in ids])
        return [_json_loads(raw, {}) for raw in raw_values if raw is not None]

    # ------------------------------------------------------------------ #
    # Movement plan reader methods                                         #
    # ------------------------------------------------------------------ #

    async def get_movement_plan_for_train(self, train_id: int) -> Any | None:
        """Return the best :class:`PlannedTrainRun` for *train_id*, or ``None``."""
        raw = await self._redis.get(self._keys.movement_plan_by_train(train_id))
        payload = _json_loads(raw, None)
        if not payload:
            return None
        try:
            return _movement_plan_to_domain(payload)
        except Exception:  # noqa: BLE001
            return None

    async def get_movement_plans_bulk(
        self, train_ids: list[int]
    ) -> dict[int, Any | None]:
        """Return best :class:`PlannedTrainRun` for each train ID (pipeline, no N+1).

        Values are ``None`` for trains without a usable plan.
        """
        if not train_ids:
            return {}
        pipe = self._redis.pipeline()
        for train_id in train_ids:
            pipe.get(self._keys.movement_plan_by_train(train_id))
        raw_values = await pipe.execute()
        result: dict[int, Any | None] = {}
        for train_id, raw in zip(train_ids, raw_values, strict=False):
            payload = _json_loads(raw, None)
            if payload:
                try:
                    result[train_id] = _movement_plan_to_domain(payload)
                except Exception:  # noqa: BLE001
                    result[train_id] = None
            else:
                result[train_id] = None
        return result


async def refresh_reference_data(
    session: AsyncSession,
    redis_client: Redis,
) -> dict[str, Any]:
    """Refresh the full Redis reference snapshot after a write."""
    loader = RedisReferenceDataLoader(session, redis_client)
    return await loader.load()


def train_payload_to_domain(payload: dict[str, Any]) -> Any:
    """Adapt a Redis train payload into the attribute-based object shape used by simulation."""
    return SimpleNamespace(
        id=int(payload["id"]),
        train_number=payload["train_number"],
        train_type=payload["train_type"],
        current_route_id=payload.get("current_route_id"),
        name=payload.get("name"),
        operator=payload.get("operator"),
    )


def schedule_payloads_to_domain(payloads: list[dict[str, Any]]) -> list[Any]:
    """Adapt Redis schedule payloads into lightweight objects for pure simulation functions."""
    schedules: list[Any] = []
    for payload in payloads:
        station_payload = payload.get("station")
        station = None
        if station_payload is not None:
            location_geojson = _json_loads(station_payload.get("location"), {})
            lon, lat = location_geojson.get("coordinates", [0, 0])
            station = SimpleNamespace(
                id=int(station_payload["id"]),
                name=station_payload["name"],
                name_th=station_payload.get("name_th"),
                code=station_payload["code"],
                location=WKTElement(f"POINT({lon} {lat})", srid=4326),
            )
        route_station = None
        if payload.get("route_station_distance_from_start") is not None:
            route_station = SimpleNamespace(
                distance_from_start=float(payload["route_station_distance_from_start"])
            )
        schedules.append(
            SimpleNamespace(
                id=int(payload["id"]),
                train_id=int(payload["train_id"]),
                station_id=payload.get("station_id"),
                station_name=payload["station_name"],
                arrival_time=_time_from_str(payload.get("arrival_time")),
                departure_time=_time_from_str(payload.get("departure_time")),
                arrival_day_offset=int(payload.get("arrival_day_offset") or 0),
                departure_day_offset=int(payload.get("departure_day_offset") or 0),
                day_of_week=payload.get("day_of_week"),
                platform=payload.get("platform"),
                sequence=int(payload.get("sequence") or 0),
                route_station_id=payload.get("route_station_id"),
                distance_from_origin_km=_to_float(
                    payload.get("distance_from_origin_km")
                ),
                route_progress=_to_float(payload.get("route_progress")),
                station=station,
                route_station=route_station,
            )
        )
    schedules.sort(key=lambda item: item.sequence)
    return schedules
