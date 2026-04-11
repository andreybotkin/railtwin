/**
 * API client for Thailand Railway Digital Twin backend.
 */

import axios, { AxiosInstance, AxiosError } from 'axios';
import type {
  Station,
  Route,
  Train,
  Schedule,
  TrainPosition,
  TrainSchedule,
  StationSchedule,
  PaginatedResponse,
  TrainPositionUpdate,
} from '@/types';

// API base URL from environment
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8002';

/**
 * Create configured axios instance for API calls.
 */
const createApiClient = (): AxiosInstance => {
  const client = axios.create({
    baseURL: `${API_BASE_URL}/api/v1`,
    timeout: 10000,
    headers: {
      'Content-Type': 'application/json',
    },
  });

  // Response interceptor for error handling
  client.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
      console.error('API Error:', error.message);
      return Promise.reject(error);
    }
  );

  return client;
};

const api = createApiClient();

// Station API
export const stationApi = {
  /**
   * Get paginated list of stations.
   */
  getAll: async (page = 1, size = 100): Promise<PaginatedResponse<Station>> => {
    const response = await api.get<PaginatedResponse<Station>>('/stations', {
      params: { page, size },
    });
    return response.data;
  },

  /**
   * Get a single station by ID.
   */
  getById: async (id: number): Promise<Station> => {
    const response = await api.get<Station>(`/stations/${id}`);
    return response.data;
  },

  /**
   * Search stations by name or code.
   */
  search: async (query: string, limit = 10): Promise<Station[]> => {
    const response = await api.get<Station[]>('/stations/search', {
      params: { q: query, limit },
    });
    return response.data;
  },

  /**
   * Find stations near a location.
   */
  findNearby: async (
    longitude: number,
    latitude: number,
    radiusKm = 10,
    limit = 10
  ): Promise<Array<{ station: Station; distance_m: number }>> => {
    const response = await api.get('/stations/nearby', {
      params: {
        longitude,
        latitude,
        radius_km: radiusKm,
        limit,
      },
    });
    return response.data;
  },
};

// Route API
export const routeApi = {
  /**
   * Get paginated list of routes.
   */
  getAll: async (
    page = 1,
    size = 100,
    routeType?: string
  ): Promise<PaginatedResponse<Route>> => {
    const response = await api.get<PaginatedResponse<Route>>('/routes', {
      params: { page, size, route_type: routeType },
    });
    return response.data;
  },

  /**
   * Get a single route by ID with geometry.
   */
  getById: async (id: number): Promise<Route> => {
    const response = await api.get<Route>(`/routes/${id}`);
    return response.data;
  },
};

// Train API
export const trainApi = {
  /**
   * Get paginated list of trains.
   */
  getAll: async (
    page = 1,
    size = 100,
    trainType?: string,
    routeId?: number
  ): Promise<PaginatedResponse<Train>> => {
    const response = await api.get<PaginatedResponse<Train>>('/trains', {
      params: { page, size, train_type: trainType, route_id: routeId },
    });
    return response.data;
  },

  /**
   * Get a single train by ID.
   */
  getById: async (id: number): Promise<Train> => {
    const response = await api.get<Train>(`/trains/${id}`);
    return response.data;
  },

  /**
   * Get current position of a train.
   */
  getPosition: async (id: number): Promise<TrainPosition> => {
    const response = await api.get<TrainPosition>(`/trains/${id}/position`);
    return response.data;
  },

  /**
   * Get current positions of all active trains.
   */
  getAllPositions: async (): Promise<TrainPositionUpdate[]> => {
    const response = await api.get<TrainPositionUpdate[]>('/trains/positions');
    return response.data;
  },
};

// Schedule API
export const scheduleApi = {
  /**
   * Get paginated list of schedules.
   */
  getAll: async (
    page = 1,
    size = 100,
    trainId?: number,
    stationId?: number,
    dayOfWeek?: number
  ): Promise<PaginatedResponse<Schedule>> => {
    const response = await api.get<PaginatedResponse<Schedule>>('/schedules', {
      params: {
        page,
        size,
        train_id: trainId,
        station_id: stationId,
        day_of_week: dayOfWeek,
      },
    });
    return response.data;
  },

  /**
   * Get complete schedule for a train.
   */
  getTrainSchedule: async (
    trainId: number,
    dayOfWeek?: number
  ): Promise<TrainSchedule> => {
    const response = await api.get<TrainSchedule>(
      `/schedules/train/${trainId}`,
      { params: { day_of_week: dayOfWeek } }
    );
    return response.data;
  },

  /**
   * Get all arrivals/departures for a station.
   */
  getStationSchedule: async (
    stationId: number,
    dayOfWeek?: number
  ): Promise<StationSchedule> => {
    const response = await api.get<StationSchedule>(
      `/schedules/station/${stationId}`,
      { params: { day_of_week: dayOfWeek } }
    );
    return response.data;
  },

  /**
   * Get upcoming departures from a station.
   */
  getUpcomingDepartures: async (
    stationId: number,
    limit = 10
  ): Promise<Schedule[]> => {
    const response = await api.get<Schedule[]>(
      `/schedules/station/${stationId}/upcoming`,
      { params: { limit } }
    );
    return response.data;
  },
};

// Health check
export const healthApi = {
  /**
   * Check if API is healthy.
   */
  check: async (): Promise<{ status: string }> => {
    const response = await axios.get<{ status: string }>(
      `${API_BASE_URL}/health`
    );
    return response.data;
  },
};

export default api;
