# Precomputed Movement Plan — Phase 1 Design

**Status:** design / pre-implementation  
**Author:** automated analysis, April 2026  
**Scope:** analysis of current codebase + concrete proposal for Phase 1

---

## 1. Motivation

Every 5 s `PositionCacheUpdater` calls `TrainSimulationService.get_all_active_train_data()`,
which for every active train:

1. Fetches schedule payloads from Redis (fast).
2. Fetches route geometry from Redis (fast, bulk).
3. Calls `build_trajectory()` → `_stop_fractions()`:
   - iterates all schedule stops (30–80 per train),
   - projects each station coordinate onto the polyline (haversine math),
   - applies corridor check and monotonicity sweep.
4. Then generates `lookahead_seconds / step_seconds` frames (~12 at default settings).

Steps 3–4 repeat with the **same static inputs** (same schedule, same route
geometry, same station coordinates) every tick.  The only dynamic input is
`current_time + delay`.

**Goal:** precompute the movement plan once after topology build so that the
hot path can do:

```
current_time + delay
  → binary-search planned_movement_segments
  → linear interpolation of geom_fraction
  → emit Trajectory frames
```

No schedule iteration, no projection, no monotonicity sweep per tick.

---

## 2. Current Data Model — Key Observations

### 2.1 Train → Route → Schedule linkage

```
trains.current_route_id ──► routes.id
                               │
                         route_stations (route_id, station_id, sequence,
                                         distance_from_start [m],
                                         edge_id, node_id,
                                         snap_distance_m, snapped_location)
                               │
                         schedules (train_id, station_id,
                                    route_station_id  ← nullable FK,
                                    route_progress    ← nullable fraction [0,1],
                                    distance_from_origin_km,
                                    arrival_time, departure_time,
                                    arrival_day_offset, departure_day_offset,
                                    sequence)
```

`route_station_id` is populated by `InitSchedulesUseCase` when a schedule stop
can be matched to a `route_stations` row.  It is **nullable** — unmatched stops
fall back to fuzzy name matching.

`route_progress` stores the resolved fraction `[0, 1]` for each schedule stop;
it is the "reference sequence" used inside `_stop_fractions()` before
projection correction.

### 2.2 Route geometry

`route_edges` (route_id, edge_id, sequence, direction="forward") joined to
`network_edges` (from_station_id, to_station_id, length_m, geometry, edge_kind)
gives the full ordered, directed polyline for a route.

`RouteRepository._get_graph_payloads()` already builds:
```python
{
  route_id: {
    "coords": [...],          # merged [lon, lat] from edge geometries
    "distance_km": ...,
    "segments": [             # per edge
      {"edge_id", "sequence", "direction",
       "from_station_id", "to_station_id",
       "length_km", "start_km", "end_km", "coords"}
    ]
  }
}
```
This payload is cached 5 min in-process and serialised to Redis by
`RedisReferenceDataLoader`.

### 2.3 Station matching quality — what exists today

| Source | Column | Meaning |
|---|---|---|
| `stations` | `snap_distance_m` | distance from station point to nearest KML segment |
| `route_stations` | `snap_distance_m` | distance after route-aware snapping |
| `route_stations` | `snapped_location` | snapped point geometry |
| `schedules` | `route_station_id` | NULL if stop could not be matched to topology |
| `schedules` | `route_progress` | NULL if not resolvable |

There is **no existing per-stop matching quality score** that captures whether
the `_stop_fractions()` projection agreed with the reference.

### 2.4 Are `route_stations.distance_from_start` and `schedule.route_progress` reliable?

- `route_stations.distance_from_start` is computed from real route geometry
  during topology build → **reliable for ordering and km bounding**.
- `schedule.route_progress` is derived from the same value divided by
  `route.distance_km` → **reliable when `route_station_id` is resolved**.
- When `route_station_id` is NULL the fallback is linear interpolation by
  sequence index → **coarse but monotonic**.

Conclusion: they are reliable enough to be the primary source for segment
distance bounds in the precomputed plan.  The projection step in
`_stop_fractions()` can refine them at plan-build time (not at runtime).

### 2.5 Do `route_edges` contain enough for movement segments?

Yes.  `route_edges` + `network_edges` provide:
- ordered edge sequence with start/end station IDs,
- cumulative `start_km` / `end_km` per edge,
- geometry per edge (not duplicated — referenced by `edge_id`).

This is sufficient to determine which edge each schedule stop falls on, and
therefore which `edge_id` bounds a movement segment.

### 2.6 Redis keys and API contracts that must remain backward-compatible

| Key / Endpoint | Consumer | Must not change |
|---|---|---|
| `train:trajectories:latest` | gateway `read_trajectories()` | shape of `Trajectory` list |
| `train:trajectory:{train_id}` | gateway `read_individual_trajectory()` | same |
| `train:stopsequence:{train_id}` | gateway stop-sequence WS | `StopSequenceItem` list |
| `map:stations:all` | gateway map snapshot | station list |
| `map:network_edges:all` | gateway map snapshot | GeoJSON FeatureCollection |
| `system:topology:metadata` | gateway `/api/v1/system/topology` | topology dict |
| `GET /api/v1/trains/trajectories` | frontend | `Trajectory[]` |
| `GET /api/v1/trains/{id}/trajectory` | frontend | `Trajectory` |
| `WS /ws/trajectory` | frontend `TrajectoryWebSocketClient` | geops trajectory/deleted_vehicles protocol |
| `Trajectory` Pydantic schema | gateway schemas.py | all fields |
| `Trajectory` TypeScript interface | frontend types/index.ts | all fields |

**No existing key or endpoint shape may change.**

---

## 3. Proposed New Tables

### 3.1 `planned_train_runs`

```sql
CREATE TABLE planned_train_runs (
    id                SERIAL PRIMARY KEY,
    train_id          INTEGER NOT NULL REFERENCES trains(id) ON DELETE CASCADE,
    route_id          INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    -- Identifies which service pattern/day this plan covers.
    -- NULL means "all operating days" (typical for fixed daily service).
    service_date      DATE,
    -- Incremented whenever the plan is rebuilt for the same train+route+date.
    plan_version      INTEGER NOT NULL DEFAULT 1,
    -- topology_version string from topology_metadata at build time.
    -- Used to detect stale plans when topology changes.
    topology_version  VARCHAR(64) NOT NULL,
    -- 0.0–1.0 aggregate quality across all segments.
    quality_score     NUMERIC(5, 4),
    -- ready | degraded | invalid
    status            VARCHAR(16) NOT NULL DEFAULT 'ready',
    -- Structured warnings captured during plan build.
    warnings          JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (train_id, route_id, service_date, plan_version)
);

CREATE INDEX ix_planned_runs_train   ON planned_train_runs(train_id);
CREATE INDEX ix_planned_runs_route   ON planned_train_runs(route_id);
CREATE INDEX ix_planned_runs_status  ON planned_train_runs(status);
CREATE INDEX ix_planned_runs_topo    ON planned_train_runs(topology_version);
```

### 3.2 `planned_movement_segments`

```sql
CREATE TABLE planned_movement_segments (
    id                    SERIAL PRIMARY KEY,
    planned_run_id        INTEGER NOT NULL
                              REFERENCES planned_train_runs(id) ON DELETE CASCADE,
    sequence              INTEGER NOT NULL,

    -- 'move' = train is running between two stations
    -- 'dwell' = train is stationary at a station
    segment_type          VARCHAR(8) NOT NULL CHECK (segment_type IN ('move','dwell')),

    -- Nullable: only set for dwell or when segment starts/ends at a station.
    from_station_id       INTEGER REFERENCES stations(id) ON DELETE SET NULL,
    to_station_id         INTEGER REFERENCES stations(id) ON DELETE SET NULL,

    -- Nullable: FK to the schedule row for the bounding stops.
    -- Allows plan builder to trace back to source timing.
    from_schedule_id      INTEGER REFERENCES schedules(id) ON DELETE SET NULL,
    to_schedule_id        INTEGER REFERENCES schedules(id) ON DELETE SET NULL,

    -- Time bounds in minutes-since-midnight, with day offsets for overnight trains.
    -- Mirrors the convention in schedules.arrival/departure_day_offset.
    start_time_minutes    NUMERIC(8, 3) NOT NULL,
    end_time_minutes      NUMERIC(8, 3) NOT NULL,
    start_day_offset      SMALLINT NOT NULL DEFAULT 0,
    end_day_offset        SMALLINT NOT NULL DEFAULT 0,

    -- Route distance bounds in metres.
    -- Derived from route_stations.distance_from_start at build time.
    -- Does NOT duplicate geometry — references the route.
    start_distance_m      NUMERIC(12, 2) NOT NULL,
    end_distance_m        NUMERIC(12, 2) NOT NULL,

    -- Precomputed fraction along the route polyline [0, 1].
    -- Stored here so runtime never touches PostGIS.
    start_geom_fraction   NUMERIC(9, 8) NOT NULL,
    end_geom_fraction     NUMERIC(9, 8) NOT NULL,

    -- Optional edge references.  Useful for edge-aligned queries.
    -- NULL for dwell segments that sit entirely within one station.
    start_edge_id         INTEGER REFERENCES network_edges(id) ON DELETE SET NULL,
    end_edge_id           INTEGER REFERENCES network_edges(id) ON DELETE SET NULL,

    -- Planned average speed for the move segment, NULL for dwell.
    planned_speed_kmh     NUMERIC(6, 2),

    -- Per-segment matching quality.
    quality_score         NUMERIC(5, 4),
    warnings              JSONB,

    UNIQUE (planned_run_id, sequence)
);

CREATE INDEX ix_pms_run     ON planned_movement_segments(planned_run_id);
CREATE INDEX ix_pms_time    ON planned_movement_segments(planned_run_id, start_time_minutes, end_time_minutes);
CREATE INDEX ix_pms_dist    ON planned_movement_segments(planned_run_id, start_distance_m, end_distance_m);
```

**Design invariant:** Neither table stores coordinates or copies route geometry.
Geometry is accessed only by looking up `route_id` or `edge_id` in the existing
tables.

---

## 4. Runtime Resolution Concept

```
runtime resolver(train_id, current_time_minutes, delay_minutes):

  1. Load planned_run for train (from Redis cache, not DB).
     If no valid plan → fall back to existing build_trajectory().

  2. effective_minutes = current_time_minutes + delay_minutes

  3. Binary-search planned_movement_segments by
     start_time_minutes + start_day_offset*1440
     ≤ effective_minutes
     ≤ end_time_minutes + end_day_offset*1440

  4. If no segment found → fallback.

  5. Interpolate geom_fraction:
     progress = (effective_minutes - seg.start_time_minutes) /
                (seg.end_time_minutes - seg.start_time_minutes)
     geom_fraction = seg.start_geom_fraction +
                     (seg.end_geom_fraction - seg.start_geom_fraction) * progress

  6. Use existing geo_utils.interpolate_position(route_coords, geom_fraction)
     to get (lon, lat).  route_coords still comes from Redis reference data
     (no change to how geometry is served).

  7. Build Trajectory with same schema as today.
     frames/anchors/meta/bounds are constructed the same way — only the
     input stop fractions are precomputed instead of projected on-the-fly.
```

The `Trajectory` object produced is **structurally identical** to what
`build_trajectory()` produces today, so all downstream consumers
(gateway, Redis, frontend) require no changes.

---

## 5. Phased Implementation Plan

### Phase 1 — Diagnostics and schema design *(this document)*

**Goal:** understand the current system thoroughly; produce the design doc;
add no code that changes runtime behaviour.

Deliverables:
- `docs/precomputed-movement-plan.md` (this file)
- Placeholder dataclass/type stubs in `simulation/app/domain/movement_plan.py`
  (types only, no runtime effect)

Files changed:
- `docs/precomputed-movement-plan.md` ← new
- `simulation/app/domain/movement_plan.py` ← new (types only)

---

### Phase 2 — Database tables

**Goal:** add `planned_train_runs` and `planned_movement_segments` to the schema.

Steps:
1. New Alembic migration `010_planned_movement_plan.py` in `raildbsetup/alembic/versions/`.
2. Add `t_planned_train_runs` and `t_planned_movement_segments` Core Table objects
   to `raildbsetup/app/infrastructure/database/tables.py`.
3. Add `PlannedTrainRun` and `PlannedMovementSegment` ORM models to
   `simulation/app/models/database/models.py`.

Files changed:
- `raildbsetup/alembic/versions/010_planned_movement_plan.py` ← new
- `raildbsetup/app/infrastructure/database/tables.py`
- `simulation/app/models/database/models.py`

---

### Phase 3 — Movement plan builder

**Goal:** build movement plans from existing topology data after
`BuildNetworkTopologyUseCase` completes.

Algorithm (per train):
1. Load train's schedules (ordered by sequence).
2. For each consecutive stop pair `(S_i, S_{i+1})`:
   a. Resolve `from_schedule_id` and `to_schedule_id`.
   b. Resolve `start_distance_m` / `end_distance_m` from
      `route_stations.distance_from_start` (preferred) or
      `schedule.distance_from_origin_km`.
   c. Resolve `start_geom_fraction` = `start_distance_m / route.distance_km`.
      If a projected fraction (from `_stop_fractions` logic) deviates < 0.10,
      prefer the projected value.
   d. Compute `quality_score`:
      - 1.0 if both stops have a resolved `route_station_id` and
        `snap_distance_m < 200 m`.
      - 0.7 if `route_station_id` is set but `snap_distance_m ≥ 200 m`.
      - 0.4 if `route_station_id` is NULL (name-matched fallback).
      - 0.0 if neither stop has geometry.
   e. Emit a **dwell** segment if `departure_time > arrival_time` at `S_i`.
   f. Emit a **move** segment from `S_i` departure to `S_{i+1}` arrival.
3. Persist `planned_train_run` with aggregate `quality_score = mean(segments)`.
4. Write warnings for: unresolved stops, non-monotonic distances,
   implausible speeds (> 180 km/h or < 0), overnight crossings.
5. Set `status = 'degraded'` if `quality_score < 0.5`, `'invalid'` if < 0.2.

Files changed:
- `raildbsetup/app/domain/railroad/movement_plan_entities.py` ← new (domain types)
- `raildbsetup/app/infrastructure/database/repositories/movement_plan.py` ← new
- `raildbsetup/app/application/use_cases/build_movement_plan.py` ← new
- `raildbsetup/app/main.py` — call `BuildMovementPlanUseCase` after topology build
- `raildbsetup/app/api/` — add `/api/v1/movement-plan/status` (admin only)

---

### Phase 4 — Runtime resolver

**Goal:** add a resolver that converts `(train_id, now_minutes, delay)` into
a `Trajectory` using precomputed segments; does NOT replace `build_trajectory()`
yet.

Steps:
1. `simulation/app/services/movement_plan_resolver.py`:
   - `MovementPlanResolver.resolve(train, segments, route_coords, now_minutes, delay)`
   - Returns a `Trajectory | None` (same type as today).
   - Falls back to `None` on any error so callers can fall back to current path.
2. `simulation/app/repositories/movement_plan.py`:
   - `get_segments_for_train(train_id, route_id)` — DB query.
3. Add movement plan Redis keys to `ReferenceDataKeys` in
   `simulation/app/services/reference_data.py`:
   ```
   sim:ref:movement_plan:by_train:{train_id}
   ```
4. `RedisReferenceDataLoader.load()`: after loading schedules, serialise
   movement plan segments per train into the new keys.

Files changed:
- `simulation/app/services/movement_plan_resolver.py` ← new
- `simulation/app/repositories/movement_plan.py` ← new
- `simulation/app/services/reference_data.py`

---

### Phase 5 — Admin matching/quality endpoints

**Goal:** expose plan quality for operator inspection without exposing
runtime-critical endpoints.

Endpoints (simulation service, admin prefix):
- `GET /api/v1/admin/movement-plans` — list runs with quality_score, status, warnings.
- `GET /api/v1/admin/movement-plans/{run_id}/segments` — segment detail.
- `POST /api/v1/admin/movement-plans/rebuild` — trigger full rebuild (async).

Files changed:
- `simulation/app/api/v1/endpoints/admin_movement_plan.py` ← new
- `simulation/app/api/v1/router.py`

---

### Phase 6 — Switch trajectory generation to resolver with fallback

**Goal:** `TrainSimulationService.get_train_trajectory()` tries the resolver
first; falls back to `build_trajectory()` if resolver returns `None`.

```python
# simulation/app/services/simulation.py

async def get_train_trajectory(self, train, schedules, route_coords, ...):
    segments = await self._get_movement_segments(train)
    if segments:
        traj = self._resolver.resolve(train, segments, route_coords, ...)
        if traj is not None:
            return traj
    # existing fallback
    return build_trajectory(train, schedules, route_coords, ...)
```

`position_cache.py` and `PositionCacheUpdater` require **no changes**:
they call `get_all_active_train_data()` which returns the same `Trajectory`
list regardless of which path produced it.

Files changed:
- `simulation/app/services/simulation.py`
- `simulation/app/services/position_cache.py` — no change required

---

## 6. Complete List of Files That Need to Change

| Phase | File | Change type |
|---|---|---|
| 1 | `docs/precomputed-movement-plan.md` | new |
| 1 | `simulation/app/domain/movement_plan.py` | new (types) |
| 2 | `raildbsetup/alembic/versions/010_planned_movement_plan.py` | new |
| 2 | `raildbsetup/app/infrastructure/database/tables.py` | add tables |
| 2 | `simulation/app/models/database/models.py` | add ORM models |
| 3 | `raildbsetup/app/domain/railroad/movement_plan_entities.py` | new |
| 3 | `raildbsetup/app/infrastructure/database/repositories/movement_plan.py` | new |
| 3 | `raildbsetup/app/application/use_cases/build_movement_plan.py` | new |
| 3 | `raildbsetup/app/main.py` | call new use-case |
| 3 | `raildbsetup/app/api/` | new admin endpoint |
| 4 | `simulation/app/services/movement_plan_resolver.py` | new |
| 4 | `simulation/app/repositories/movement_plan.py` | new |
| 4 | `simulation/app/services/reference_data.py` | add plan keys |
| 5 | `simulation/app/api/v1/endpoints/admin_movement_plan.py` | new |
| 5 | `simulation/app/api/v1/router.py` | register endpoint |
| 6 | `simulation/app/services/simulation.py` | add resolver path |

**Files that must NOT change in any phase:**
- `gateway/app/main.py`
- `gateway/app/schemas.py`
- `gateway/app/redis_payloads.py`
- `simulation/app/services/position_cache.py` (Phase 6 leaves it untouched)
- `simulation/app/services/trajectory_service.py` (kept as fallback indefinitely)
- `frontend/src/types/index.ts`
- All existing Alembic migrations

---

## 7. Risks and Invariants

### Must-hold invariants

| # | Invariant |
|---|---|
| I-1 | `Trajectory` schema is not modified in any phase. |
| I-2 | All existing Redis keys keep the same names and value shapes. |
| I-3 | `trajectory_service.build_trajectory()` is never removed; it remains the fallback path. |
| I-4 | Route geometry is never copied into movement plan tables; only `route_id`, `edge_id`, distances, and fractions are stored. |
| I-5 | `PositionCacheUpdater` writes to the same Redis keys regardless of which internal path produced the `Trajectory`. |
| I-6 | No PostGIS function is called per train per simulation tick. |
| I-7 | Plans with `status = 'invalid'` are never used by the resolver; fallback is automatic. |

### Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `route_stations.distance_from_start` is NULL for some stations | Medium | Use `schedule.distance_from_origin_km` as fallback; if both NULL, set quality_score = 0.4 and emit warning |
| `schedules.route_station_id` NULL for a subset of stops | Medium | Accept degraded quality_score; resolver falls back to `build_trajectory()` when score < threshold |
| Reverse-direction trains | Low (currently all forward) | `start_geom_fraction > end_geom_fraction` is valid; resolver handles descending fractions. Flagged by `direction = 'reverse'` in `route_edges` |
| Overnight trains crossing midnight | Present | `start_day_offset` / `end_day_offset` mirror the existing `schedule.arrival/departure_day_offset` convention; resolver converts to absolute minutes before comparison |
| Topology rebuild invalidates all plans | Certain on topology change | `planned_train_runs.topology_version` checked against `system:topology:metadata`; stale plans trigger fallback and async rebuild |
| Multiple plan versions in DB | Certain over time | Keep only `plan_version = max` per (train_id, route_id, service_date); old rows cleaned by builder before inserting new |
| Plan build is slow (hundreds of trains) | Low | Plan builder runs once after topology, not on the hot path; is OK to take 10–30 s |
| `_stop_fractions()` projection improves on `distance_from_start` | Possible | Phase 3 builder runs the same projection logic to pick the best fraction at build time |

### Backward compatibility guarantee

The existing `build_trajectory()` path in `trajectory_service.py` is always
available.  During Phases 1–5 it is the **only** path used at runtime.
Phase 6 introduces the resolver as the **primary** path with explicit fallback.
A feature flag environment variable (`USE_MOVEMENT_PLAN_RESOLVER=false` default)
will gate Phase 6 activation so rollback is instant.

---

## 8. Open Questions (for later phases)

1. **Service date vs all-days:** Thai railway timetables are largely fixed
   across all weekdays.  Should `service_date` default to NULL (meaning
   "applies every operating day") or should we materialise per-date plans
   for special services?  → Start with NULL, add per-date support only if
   needed.

2. **Partial route trains:** Some trains only cover a sub-sequence of the
   route's stations.  The builder must not assume first schedule stop =
   `distance_from_start = 0`.

3. **Shared stations between routes:** A station can appear in `route_stations`
   for multiple routes.  `schedules.route_station_id` picks the correct one
   when it is set; otherwise the builder must use `train.current_route_id` to
   filter `route_stations`.

4. **Resolver warm-up:** On service start, movement plan segments may not yet
   be in Redis.  The resolver must handle a cold cache gracefully by falling
   back to `build_trajectory()` until the reference data loader runs.

5. **Speed plausibility check:** The builder should flag `planned_speed_kmh`
   outside the range `[0, 180]` as a warning (mirrors the 200 km/h clamp
   already in `_compute_frame()`).
