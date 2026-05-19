/**
 * API client for the RailTwin gateway.
 *
 * The gateway is the only surface the frontend talks to; everything that
 * isn't a trajectory / stop-sequence stream goes through its catch-all proxy
 * to the simulation service.
 */

import axios, { AxiosInstance, AxiosError } from 'axios';
import type {
  MapSnapshot,
  PaginatedResponse,
  Route,
  Schedule,
  Station,
  StationSchedule,
  TopologyMetadata,
  Train,
  TrainSchedule,
  TrainStopSequence,
  Trajectory,
} from '@/types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8002';

const createApiClient = (): AxiosInstance => {
  const client = axios.create({
    baseURL: `${API_BASE_URL}/api/v1`,
    timeout: 10_000,
    headers: { 'Content-Type': 'application/json' },
  });

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

export const stationApi = {
  getAll: async (page = 1, size = 100): Promise<PaginatedResponse<Station>> => {
    const response = await api.get<PaginatedResponse<Station>>('/stations', {
      params: { page, size },
    });
    return response.data;
  },
  getById: async (id: number): Promise<Station> => {
    const response = await api.get<Station>(`/stations/${id}`);
    return response.data;
  },
  search: async (query: string, limit = 10): Promise<Station[]> => {
    const response = await api.get<Station[]>('/stations/search', {
      params: { q: query, limit },
    });
    return response.data;
  },
};

export const routeApi = {
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
  getById: async (id: number): Promise<Route> => {
    const response = await api.get<Route>(`/routes/${id}`);
    return response.data;
  },
};

export const trainApi = {
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
  getAllPages: async (
    trainType?: string,
    routeId?: number,
    pageSize = 100
  ): Promise<Train[]> => {
    const firstPage = await trainApi.getAll(1, pageSize, trainType, routeId);
    const items = [...firstPage.items];
    for (let page = 2; page <= firstPage.pages; page += 1) {
      const response = await trainApi.getAll(
        page,
        pageSize,
        trainType,
        routeId
      );
      items.push(...response.items);
    }
    return items;
  },
  getById: async (id: number): Promise<Train> => {
    const response = await api.get<Train>(`/trains/${id}`);
    return response.data;
  },
};

export const scheduleApi = {
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

export const mapApi = {
  /** Fetch the full stations + network-edges snapshot in one request. */
  getTopology: async (): Promise<MapSnapshot> => {
    const response = await api.get<MapSnapshot>('/map/topology');
    return response.data;
  },
};

export const gatewayApi = {
  getSystemTopology: async (): Promise<TopologyMetadata> => {
    const response = await api.get<TopologyMetadata>('/system/topology');
    return response.data;
  },
  getTrajectories: async (bbox?: string): Promise<Trajectory[]> => {
    const response = await api.get<Trajectory[]>('/trains/trajectories', {
      params: bbox ? { bbox } : undefined,
    });
    return response.data;
  },
  getTrainTrajectory: async (trainId: number): Promise<Trajectory> => {
    const response = await api.get<Trajectory>(`/trains/${trainId}/trajectory`);
    return response.data;
  },
  getStopSequence: async (trainId: number): Promise<TrainStopSequence> => {
    const response = await api.get<TrainStopSequence>(
      `/trains/${trainId}/stopsequence`
    );
    return response.data;
  },
};

export const healthApi = {
  check: async (): Promise<{ status: string }> => {
    const response = await axios.get<{ status: string }>(
      `${API_BASE_URL}/health`
    );
    return response.data;
  },
};

export default api;
