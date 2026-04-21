/**
 * TypeScript types mirroring the gateway schemas.
 *
 * The authoritative declarations live in `simulation/app/domain/trajectory.py`
 * and `gateway/app/schemas.py`; whenever those change, regenerate the
 * OpenAPI-derived types (`npm run generate:types`) and keep this file in sync
 * with the hand-written aliases used by the UI.
 */

// Re-export map topic types
export type { MapLayer, MapTopic, LayerCategory, ZoomGeneralization } from './map-topics';

// --------------------------------------------------------------------------- //
// GeoJSON + domain primitives                                                  //
// --------------------------------------------------------------------------- //

export interface GeoJSONPoint {
  type: 'Point';
  coordinates: [number, number];
}

export interface GeoJSONLineString {
  type: 'LineString';
  coordinates: [number, number][];
}

export interface StationFacilities {
  parking: boolean;
  restaurant: boolean;
  atm: boolean;
  toilet: boolean;
  wifi: boolean;
}

export interface Station {
  id: number;
  name: string;
  name_th: string | null;
  code: string;
  location: GeoJSONPoint;
  city: string | null;
  province: string | null;
  facilities: StationFacilities | null;
  has_schedule?: boolean;
  created_at: string;
  updated_at: string;
}

export interface StationSummary {
  id: number;
  name: string;
  code: string;
}

// --------------------------------------------------------------------------- //
// Routes + trains                                                              //
// --------------------------------------------------------------------------- //

export type RouteType = 'northern' | 'northeastern' | 'southern' | 'eastern';

export interface RouteStationInfo {
  id: number;
  name: string;
  code: string;
  sequence: number;
  distance_from_start: number | null;
}

export interface Route {
  id: number;
  name: string;
  name_th: string | null;
  route_type: RouteType;
  distance_km: number | null;
  color: string | null;
  line_geometry: GeoJSONLineString | null;
  stations: RouteStationInfo[];
  created_at: string;
}

export interface RouteSummary {
  id: number;
  name: string;
  route_type: RouteType;
  color: string | null;
}

export type TrainType =
  | 'special_express'
  | 'express'
  | 'rapid'
  | 'ordinary'
  | 'commuter'
  | (string & {});

export interface Train {
  id: number;
  train_number: string;
  train_type: TrainType;
  name: string | null;
  capacity: number | null;
  operator: string;
  current_route_id: number | null;
  current_route: RouteSummary | null;
  created_at: string;
}

export interface TrainSummary {
  id: number;
  train_number: string;
  train_type: TrainType;
  name: string | null;
}

// --------------------------------------------------------------------------- //
// Trajectory domain (mirrors simulation/app/domain/trajectory.py)              //
// --------------------------------------------------------------------------- //

export type TrajectoryStatus = 'moving' | 'dwelling' | 'arrived' | 'boarding';

export interface ConsistSpec {
  locomotive_length_m: number;
  car_count: number;
  car_length_m: number;
  total_length_m: number;
}

export interface TrajectoryFrame {
  t_ms: number;
  lon: number;
  lat: number;
  geom_fraction: number;
  head_distance_m: number;
  rotation_deg: number;
  speed_kmh: number;
  status: TrajectoryStatus;
}

export interface TrajectoryAnchor {
  t_ms: number;
  station_id: number | null;
  station_name: string;
  event: 'arrival' | 'departure';
  geom_fraction: number;
  scheduled_minutes: number;
  adjusted_minutes: number;
  delay_minutes: number;
}

export interface TrajectoryMeta {
  train_id: number;
  train_number: string;
  train_type: TrainType;
  train_name: string | null;
  color: string;
  operator: string;
  origin_station: string | null;
  destination_station: string | null;
  prev_station: string | null;
  next_station: string | null;
  eta_next_ms: number | null;
  delay_minutes: number;
  route_id: number | null;
  route_progress_pct: number;
  segment_progress_pct: number;
  current_edge_id: number | null;
  graph_from_station_id: number | null;
  graph_to_station_id: number | null;
  topology_version: string | null;
}

export interface Trajectory {
  train_id: number;
  generated_at_ms: number;
  valid_until_ms: number;
  /** Authoritative polyline the train rides — [lon, lat] pairs. */
  route_coords: [number, number][];
  route_length_m: number;
  frames: TrajectoryFrame[];
  anchors: TrajectoryAnchor[];
  consist: ConsistSpec;
  meta: TrajectoryMeta;
  bounds: [number, number, number, number];
}

// --------------------------------------------------------------------------- //
// Stop sequence                                                                //
// --------------------------------------------------------------------------- //

export type StopState = 'PASSED' | 'BOARDING' | 'PENDING';

export interface StopSequenceItem {
  station_name: string;
  sequence: number;
  aimed_arrival_minutes: number | null;
  aimed_departure_minutes: number | null;
  arrival_day_offset: number;
  departure_day_offset: number;
  delay_minutes: number;
  state: StopState;
}

export type TrainStopSequence = StopSequenceItem[];

// --------------------------------------------------------------------------- //
// Schedule domain                                                              //
// --------------------------------------------------------------------------- //

export interface Schedule {
  id: number;
  train_id: number;
  station_id: number;
  arrival_time: string | null;
  departure_time: string | null;
  sequence: number;
  day_of_week: number[] | null;
  platform: string | null;
  station?: StationSummary | null;
  train?: TrainSummary | null;
}

export interface TrainSchedule {
  train: TrainSummary;
  stops: Schedule[];
}

export interface StationSchedule {
  station: StationSummary;
  schedules: Schedule[];
}

// --------------------------------------------------------------------------- //
// Map topology                                                                 //
// --------------------------------------------------------------------------- //

export interface NetworkEdgeProperties {
  from_node_id: number;
  to_node_id: number;
  from_station_id: number;
  to_station_id: number;
  length_m: number;
  edge_kind?: string | null;
  component_id?: number | null;
  route_type: RouteType | null;
  line_name: string | null;
}

export interface NetworkEdgeFeature {
  type: 'Feature';
  geometry: GeoJSONLineString;
  properties: NetworkEdgeProperties;
}

export interface NetworkEdgeCollection {
  type: 'FeatureCollection';
  features: NetworkEdgeFeature[];
}

export interface TopologyMetadata {
  topology_version: string;
  physical_nodes_count: number;
  physical_edges_count: number;
  station_nodes_count: number;
  physical_components_count: number;
  station_components_count: number;
  operational_links_count: number;
  main_component_station_count: number;
  disconnected_station_count: number;
  unsnapped_station_count: number;
  max_snap_distance_m: number | null;
  built_at: string;
}

export interface MapSnapshot {
  topology: TopologyMetadata | null;
  stations: Station[];
  network_edges: NetworkEdgeCollection;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

// --------------------------------------------------------------------------- //
// WebSocket protocol                                                           //
// --------------------------------------------------------------------------- //

export type TrajectoryWSMessage =
  | { source: 'trajectory'; content: Trajectory; timestamp: number }
  | { source: 'deleted_vehicles'; content: number; timestamp: number }
  | { source: 'keepalive'; timestamp: number };

export interface StopSequenceWSMessage {
  type: 'stopsequence' | 'keepalive';
  train_id?: number;
  data?: TrainStopSequence | null;
  timestamp: number;
}

// --------------------------------------------------------------------------- //
// UI state                                                                     //
// --------------------------------------------------------------------------- //

export interface MapViewState {
  center: [number, number];
  zoom: number;
}

export interface FilterState {
  routeTypes: RouteType[];
  trainTypes: TrainType[];
  searchQuery: string;
}
