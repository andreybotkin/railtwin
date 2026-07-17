# Physics-based movement

Trajectory generation integrates velocity instead of interpolating a constant
fraction between timetable stops. The integrator accounts for power-limited
traction, maximum tractive effort, rolling and grade resistance, service
braking, train/rolling-stock/passenger mass, train maximum speed, and track
speed limits. It still uses timetable arrival/departure times as the target for
each leg and emits an exact zero-speed dwell at stations.

## Input data

Migration `011_physics_profiles` adds optional physical fields to `trains`.
Missing values are resolved from conservative defaults for the train type;
`passenger_load` defaults to 65% of capacity and passenger mass to 75 kg.

Each `network_edges.elevation_profile` is a JSON array of local samples:

```json
[
  {"distance_m": 0, "elevation_m": 18.2},
  {"distance_m": 500, "elevation_m": 23.7}
]
```

Samples should be produced by projecting edge coordinates into the DEM CRS and
sampling its elevation band. `integrate_dem_elevations(coords, sampler)` in
`simulation/app/services/train_physics.py` is the reusable adapter: it produces
3D `[lon, lat, elevation]` coordinates, retains existing Z values, and fills DEM
voids by interpolation. The runtime accepts either these 3D route coordinates
or the per-edge JSON profiles above.

An edge-wide limit uses `network_edges.max_speed_kmh`. More precise restrictions
(curves, bridges, mountain passes, temporary restrictions) use local zones:

```json
[
  {"start_m": 1200, "end_m": 2600, "max_speed_kmh": 45}
]
```

Offsets are measured from the start of the directed edge. The route cache
converts them to global distances. The simulator follows a braking curve before
the zone boundary, so velocity is already compliant on entry.

## Connected train routes

A train is no longer placed on the single KML line with the largest number of
matching stops. During reference-data refresh, every consecutive timetable pair
is resolved through the directed station graph. The shortest physical edge path
is concatenated into a train-specific polyline, so services can cross a trunk
and one or more branches without collapsing stops onto a junction.

The generated payload records an authoritative distance for every schedule row.
Trajectory generation uses these distances directly; it does not re-project a
station onto an ambiguous looping or branching polyline.

The route is rejected and not published when it contains any of the following:

- an unresolved station;
- two differently named consecutive stops resolved to one station;
- no graph path between consecutive stops;
- non-positive inter-station travel time;
- non-monotonic or duplicate stop positions;
- a leg that cannot be completed within train and track physical limits.

Redis reference metadata exposes `valid_train_geometries_count` and
`invalid_train_geometries_count`. A single-train trajectory request returns HTTP
422 with structured route issues when its graph path is invalid.

Topology metadata now contains actual undirected component counts. Unsnapped
stations remain visible as isolated components instead of being reported as
members of the main component. The station-to-route matching corridor is 500 m;
the former 2 km corridor admitted stations from nearby branches.

## Output and rollout

Every trajectory frame includes `elevation_m`, signed `grade_permille`, and
`speed_limit_kmh` in addition to velocity. Existing clients remain compatible
because the gateway supplies defaults for older cached frames.

After deploying the migration and loading DEM/limit data, refresh the simulation
reference-data snapshot so Redis receives the new edge and train attributes.
Re-run the railroad and schedule initialization as well: timetable validation
now quarantines source files with backwards travel times, and movement plans
with non-monotonic geometry/time or suspicious speed are marked `invalid`.

The current canonical snapshot contains backwards inter-station times in trains
279, 416, 418, 420, and 430. They are intentionally skipped during schedule
initialization until their upstream TTS values can be verified; the simulator
must not invent corrected times.
