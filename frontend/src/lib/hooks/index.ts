/**
 * Custom React hooks.
 */

import { useCallback, useEffect, useState } from 'react';
import { useQuery, UseQueryResult } from '@tanstack/react-query';

import {
  gatewayApi,
  mapApi,
  routeApi,
  scheduleApi,
  stationApi,
  trainApi,
} from '@/lib/api/client';
import type {
  MapSnapshot,
  PaginatedResponse,
  Route,
  Schedule,
  Station,
  StationSchedule,
  Train,
  TrainSchedule,
  TrainStopSequence,
  Trajectory,
} from '@/types';

export { useRafVehicleTicker, VEHICLE_SOURCE_ID } from './useRafVehicleTicker';
export { useTrajectoryStream } from './useTrajectoryStream';
export { useBottomSheetDrag } from './useBottomSheetDrag';
export type { SheetType } from './useBottomSheetDrag';

export function useStations(): UseQueryResult<PaginatedResponse<Station>> {
  return useQuery({
    queryKey: ['stations'],
    queryFn: () => stationApi.getAll(1, 100),
    staleTime: 5 * 60 * 1000,
  });
}

export function useRoutes(): UseQueryResult<PaginatedResponse<Route>> {
  return useQuery({
    queryKey: ['routes'],
    queryFn: () => routeApi.getAll(1, 100),
    staleTime: 5 * 60 * 1000,
  });
}

export function useTrains(): UseQueryResult<PaginatedResponse<Train>> {
  return useQuery({
    queryKey: ['trains'],
    queryFn: () => trainApi.getAll(1, 100),
    staleTime: 1 * 60 * 1000,
  });
}

export function useTrainSchedule(
  trainId: number | null,
): UseQueryResult<TrainSchedule | null> {
  return useQuery({
    queryKey: ['train-schedule', trainId],
    queryFn: () => (trainId ? scheduleApi.getTrainSchedule(trainId) : null),
    enabled: !!trainId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useStationSchedule(
  stationId: number | null,
): UseQueryResult<StationSchedule | null> {
  return useQuery({
    queryKey: ['station-schedule', stationId],
    queryFn: () => (stationId ? scheduleApi.getStationSchedule(stationId) : null),
    enabled: !!stationId,
    staleTime: 5 * 60 * 1000,
  });
}

/** Cold-start trajectory snapshot — used before the WS delivers its first frame. */
export function useInitialTrajectories(
  bbox?: string | null,
): UseQueryResult<Trajectory[]> {
  return useQuery({
    queryKey: ['trajectories', bbox ?? 'all'],
    queryFn: () => gatewayApi.getTrajectories(bbox ?? undefined),
    staleTime: 10_000,
  });
}

export function useStopSequence(
  trainId: number | null,
): UseQueryResult<TrainStopSequence | null> {
  return useQuery({
    queryKey: ['stopsequence', trainId],
    queryFn: () => (trainId ? gatewayApi.getStopSequence(trainId) : null),
    enabled: !!trainId,
    refetchInterval: 30_000,
  });
}

export function useMapTopology(): UseQueryResult<MapSnapshot> {
  return useQuery({
    queryKey: ['map-topology'],
    queryFn: () => mapApi.getTopology(),
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

export function useStationSearch(query: string): UseQueryResult<Station[]> {
  return useQuery({
    queryKey: ['station-search', query],
    queryFn: () => stationApi.search(query),
    enabled: query.length >= 2,
    staleTime: 60 * 1000,
  });
}

export function useSelectedTrain(): {
  selectedTrainId: number | null;
  selectTrain: (id: number | null) => void;
} {
  const [selectedTrainId, setSelectedTrainId] = useState<number | null>(null);
  const selectTrain = useCallback((id: number | null) => {
    setSelectedTrainId(id);
  }, []);
  return { selectedTrainId, selectTrain };
}

function resolveInitialDark(): boolean {
  if (typeof window === 'undefined') return false;
  const stored = window.localStorage.getItem('theme');
  if (stored === 'dark') return true;
  if (stored === 'light' || stored === 'satellite') return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

export type AppTheme = 'light' | 'dark' | 'satellite';

function applyThemeClass(theme: AppTheme): void {
  document.documentElement.classList.remove('dark', 'satellite');
  if (theme === 'dark') document.documentElement.classList.add('dark');
  else if (theme === 'satellite') document.documentElement.classList.add('satellite');
}

function resolveInitialTheme(): AppTheme {
  if (typeof window === 'undefined') return 'light';
  const stored = window.localStorage.getItem('theme') as AppTheme | null;
  if (stored === 'dark' || stored === 'satellite') return stored;
  if (stored === 'light') return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function useTheme(): { theme: AppTheme; cycleTheme: () => void } {
  const [theme, setTheme] = useState<AppTheme>(() => resolveInitialTheme());

  useEffect(() => {
    applyThemeClass(theme);
  }, [theme]);

  const cycleTheme = useCallback(() => {
    setTheme((prev) => {
      const next: AppTheme =
        prev === 'light' ? 'dark' : prev === 'dark' ? 'satellite' : 'light';
      localStorage.setItem('theme', next);
      applyThemeClass(next);
      window.location.reload();
      return next;
    });
  }, []);

  return { theme, cycleTheme };
}

export function useDarkMode(): { isDark: boolean; toggle: () => void } {
  const [isDark, setIsDark] = useState<boolean>(() => resolveInitialDark());

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark);
  }, [isDark]);

  const toggle = useCallback(() => {
    setIsDark((prev) => {
      const next = !prev;
      localStorage.setItem('theme', next ? 'dark' : 'light');
      document.documentElement.classList.toggle('dark', next);
      return next;
    });
  }, []);

  return { isDark, toggle };
}

export type { Schedule };
