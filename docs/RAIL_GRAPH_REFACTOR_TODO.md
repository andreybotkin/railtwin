# Rail Graph Refactor Notes

## Implemented

- Graph-first topology build in raildbsetup: the railway graph is now derived from KML geometry first, not from station ordering.
- Atomic graph segmentation: route geometries are merged, noded, and split into real map-backed segments before route reconstruction.
- Physical vs operational graph split: `network_edges` now stores only KML-backed physical track edges, while detached station-bearing components are connected separately through `network_links`.
- Explicit source-route membership: `network_edge_routes` maps each physical graph edge back to one or more source routes, so route reconstruction no longer depends on lossy heuristics stored directly on edges.
- Connected-component diagnostics: `network_nodes.component_id` and `network_edges.component_id` persist the physical connected component for QA, debugging, and map/API consumers.
- Station-to-network binding: every imported station is snapped to the nearest graph edge and assigned a graph node.
- Route-aware station snapping: station import now persists `stations.source_route_type`, and topology build first anchors the station to the nearest KML route of that family before selecting the physical graph edge.
- Station-induced edge splitting: when a station falls inside a segment, the segment is split so the station becomes part of the graph.
- Route reconstruction from graph: route edge sequences are rebuilt from the final graph and now prefer contiguous edge chaining instead of a pure fraction sort.
- Route station reconstruction from graph: `route_stations` are rebuilt from graph node order, now also storing `node_id` alongside `edge_id`.
- Backend route geometry now prefers route_edges/network_edges, with fallback to legacy routes.line_geometry only when graph geometry is unavailable.
- Backend network API now exposes physical graph metadata through `/api/v1/network/metadata`, while operational bridges are only included when explicitly requested.
- Schedule binding: schedules now populate route_station_id and route_progress from rebuilt route_stations even when timetable seeding is skipped.
- KML parsing now normalizes repeated coordinates and strips closed duplicate endpoints before topology build, reducing false loops from source geometry noise.
- Topology build now persists a `topology_version` plus connectivity/snap metrics in `topology_metadata`.
- Backend position cache now publishes topology metadata to Redis (`system:topology:metadata`) and tags position/trajectory payloads with `topology_version`.
- Gateway now exposes topology metadata directly from Redis at `/api/v1/system/topology`.
- Local verification completed: docker-compose stack starts locally and serves backend, gateway, frontend, raildbsetup, and raildatacollector.

## Remaining TODO

- Replace generated `network_links` with surveyed or source-backed geometry where disconnected components are caused by missing KML links instead of real network separation.
- Add an explicit `link_source` / `confidence` model for `network_links` so hand-curated bridges can be distinguished from automatically generated ones.
- Add topology integration tests that assert:
  - 366/366 stations receive node_id
  - the physical `track` subgraph component distribution is stable and explainable
  - the operational station-bearing graph is a single connected component when `network_links` are included
  - route_stations and route_edges are rebuilt for all routes
  - schedules receive route_station_id and route_progress after a repeat setup run
- Add graph QA metrics to raildbsetup status output: component count, connector count, max snap distance, 95th percentile snap distance, routes without route_edges.
- Extend graph versioning in Redis so frontend consumers can invalidate route and network caches explicitly, not just read the version.
- Add generalized graph variants for frontend zoom levels, similar to the graph / generalization split used by geOps routing and realtime stacks.
- Add stronger station alias normalization for timetable imports, inspired by routing/stops lookup patterns, so external names resolve more reliably before route binding.
- Add an optional API filter to expose only physical components or only operational links for QA views in the frontend/admin tooling.
- Add a dedicated raildatacollector graph sync smoke test to ensure its SQLAlchemy table metadata stays aligned with the shared schema.