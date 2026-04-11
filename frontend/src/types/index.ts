/**
 * TypeScript type definitions for the Thailand Railway Digital Twin application.
 */

// Re-export map topic types
export type { MapLayer, MapTopic, LayerCategory, ZoomGeneralization } from './map-topics';

// GeoJSON types
export interface GeoJSONPoint {
  type: 'Point';
  coordinates: [number, number]; // [longitude, latitude]
}

export interface GeoJSONLineString {
  type: 'LineString';
  coordinates: [number, number][]; // Array of [longitude, latitude]
}

// Station types
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
  created_at: string;
  updated_at: string;
}

export interface StationSummary {
  id: number;
  name: string;
  code: string;
}

// Route types
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

// Train types
export type TrainType = 'special_express' | 'rapid' | 'ordinary';
export type TrainStatus = 'moving' | 'stopped' | 'at_station' | 'delayed';

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

export interface TrainPosition {
  id: number;
  train_id: number;
  location: GeoJSONPoint;
  speed: number | null;
  heading: number | null;
  status: TrainStatus;
  delay_minutes: number;
  timestamp: string;
}

export interface TrainPositionUpdate {
  train_id: number;
  train_number: string;
  train_type: TrainType;
  location: GeoJSONPoint;
  speed: number | null;
  heading: number | null;
  status: TrainStatus;
  delay_minutes: number;
  next_station: string | null;
  prev_station: string | null;
  progress: number;
  route_id: number | null;
}

// Schedule types
export interface Schedule {
  id: number;
  train_id: number;
  station_id: number;
  arrival_time: string | null;
  departure_time: string | null;
  day_of_week: number[] | null;
  platform: string | null;
  sequence: number;
  train: TrainSummary | null;
  station: StationSummary | null;
}

export interface TrainSchedule {
  train: TrainSummary;
  stops: Schedule[];
}

export interface StationSchedule {
  station: StationSummary;
  schedules: Schedule[];
}

// API response types
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

// WebSocket message types
export interface WebSocketMessage {
  type: 'positions' | 'position' | 'keepalive';
  data: TrainPositionUpdate[] | TrainPositionUpdate | null;
  train_id?: number;
  timestamp: number;
}

// ---------------------------------------------------------------------------
// Trajectory types — geops mobility-toolbox-js pattern
// Backend generates time_intervals so clients can interpolate position at any
// moment without waiting for the next server update (smooth 60fps animation).
// @see https://github.com/geops/mobility-toolbox-js
// ---------------------------------------------------------------------------

/**
 * A single time-position-rotation sample inside a trajectory.
 * [unix_ms, geom_fraction, rotation_degrees]
 *   unix_ms        — Wall-clock time this sample was computed for
 *   geom_fraction  — Fraction (0..1) along the full route LineString
 *   rotation       — Heading in degrees (0 = North, clockwise)
 */
export type TimeInterval = [number, number, number];

export interface TrainTrajectoryLine {
  name: string;
  color: string;
  /** Internal route ID (geops compat). */
  id?: number;
  /** Stroke colour (alias for color, geops compat). */
  stroke?: string;
  text_color?: string;
  tags?: string[];
}

/** geops TrackerTrajectoryProperties — all mandatory fields included. */
export interface TrainTrajectoryProperties {
  // Core identification
  train_id: number;
  train_number: string;
  train_type: TrainType;
  route_identifier: string;
  // Delay
  /** Delay in minutes (legacy / display). */
  delay_minutes: number;
  /** Delay in seconds (geops standard). */
  delay: number;
  // Context
  next_station: string | null;
  prev_station: string | null;
  /** Geops-compatible time_intervals for temporal position interpolation. */
  time_intervals: TimeInterval[];
  line: TrainTrajectoryLine;
  /** BBOX of the visible trajectory segment: [minLon, minLat, maxLon, maxLat] */
  bounds: [number, number, number, number];
  // geops TrackerTrajectoryProperties required fields
  /** Vehicle movement state. */
  state: 'BOARDING' | 'DRIVING' | 'JOURNEY_CANCELLED';
  /** Vehicle type — always "rail" for trains. */
  type: 'rail';
  /** Tenant identifier for multi-operator deployments. */
  tenant: string;
  /** Server-side computation timestamp (Unix ms). */
  timestamp: number;
  has_journey: boolean;
  has_realtime: boolean;
  has_realtime_journey: boolean;
  gen_level: number;
  gen_range: number[];
  graph: string;
  operator_provides_realtime_journey: string;
}

/** geops-compatible GeoJSON Feature for a train trajectory. */
export interface TrainTrajectory {
  /** GeoJSON Feature discriminator. */
  type: 'Feature';
  /** Full GeoJSON LineString of the train's route. */
  geometry: GeoJSONLineString;
  properties: TrainTrajectoryProperties;
}

// ---------------------------------------------------------------------------
// Stop-sequence types
// ---------------------------------------------------------------------------

/** State of a single stop in the upcoming-stops panel. */
export type StopState = 'PASSED' | 'BOARDING' | 'PENDING' | 'JOURNEY_CANCELLED';

/** A single stop in a train's upcoming stop sequence. */
export interface StopSequenceItem {
  station_name: string;
  sequence: number;
  /** Scheduled departure minutes since midnight (local Bangkok time). */
  aimed_departure_minutes: number | null;
  departure_day_offset: number;
  delay_minutes: number;
  state: StopState;
}

/** Full stop-sequence payload from GET /api/v1/trains/{id}/stopsequence. */
export type TrainStopSequence = StopSequenceItem[];

/** Message from /ws/trajectory endpoint (gateway). */
export type TrajectoryWSMessage =
  | { source: 'trajectory'; content: TrainTrajectory; timestamp: number }
  | { source: 'deleted_vehicles'; content: number; timestamp: number }
  | { source: 'keepalive'; timestamp: number };



// UI state types
export interface MapViewState {
  center: [number, number];
  zoom: number;
}

export interface FilterState {
  routeTypes: RouteType[];
  trainTypes: TrainType[];
  searchQuery: string;
}
