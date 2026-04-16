import { useQuery, UseQueryResult } from '@tanstack/react-query';

import { mapApi, routeApi, scheduleApi, stationApi, trainApi } from '@/lib/api/client';
import type {
  PaginatedResponse,
  Route,
  Schedule,
  Station,
  StationSchedule,
  Train,
  TrainSchedule,
} from '@/types';

export function useStations(): UseQueryResult<PaginatedResponse<Station>> {
  return useQuery({ queryKey: ['stations'], queryFn: () => stationApi.getAll(1, 100), staleTime: 300000 });
}

export function useRoutes(): UseQueryResult<PaginatedResponse<Route>> {
  return useQuery({ queryKey: ['routes'], queryFn: () => routeApi.getAll(1, 100), staleTime: 300000 });
}

export function useTrains(): UseQueryResult<PaginatedResponse<Train>> {
  return useQuery({ queryKey: ['trains'], queryFn: () => trainApi.getAll(1, 100), staleTime: 60000 });
}

export function useTrainSchedule(trainId: number | null): UseQueryResult<TrainSchedule | null> {
  return useQuery({ queryKey: ['train-schedule', trainId], queryFn: () => (trainId ? scheduleApi.getTrainSchedule(trainId) : null), enabled: !!trainId });
}

export function useStationSchedule(stationId: number | null): UseQueryResult<StationSchedule | null> {
  return useQuery({ queryKey: ['station-schedule', stationId], queryFn: () => (stationId ? scheduleApi.getStationSchedule(stationId) : null), enabled: !!stationId });
}

export function useStationSearch(query: string): UseQueryResult<Station[]> {
  return useQuery({ queryKey: ['station-search', query], queryFn: () => stationApi.search(query), enabled: query.length >= 2 });
}

export function useMapTopology(): UseQueryResult<{ stations: Station[]; network_edges: Schedule[] }> {
  return useQuery({ queryKey: ['map-static-data'], queryFn: () => mapApi.getStaticData() as never });
}
