/**
 * TypeScript type definitions for the Thailand Railway Digital Twin application.
 */

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
  type: 'positions' | 'position';
  data: TrainPositionUpdate[] | TrainPositionUpdate | null;
  train_id?: number;
  timestamp: number;
}

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
