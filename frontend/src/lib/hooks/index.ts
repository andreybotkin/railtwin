/**
 * Custom React hooks for the application.
 */

import { startTransition, useEffect, useState, useCallback, useRef } from 'react';
import { useQuery, UseQueryResult } from '@tanstack/react-query';
import {
  mapApi,
  stationApi,
  routeApi,
  trainApi,
  scheduleApi,
} from '@/lib/api/client';
import { getWebSocketClient, TrainWebSocketClient, getTrajectoryClient } from '@/lib/websocket';
import type {
  Station,
  Route,
  Train,
  Schedule,
  TrainSchedule,
  StationSchedule,
  TrainPositionUpdate,
  TrainTrajectory,
  PaginatedResponse,
  NetworkEdgeCollection,
} from '@/types';

/**
 * Hook for fetching all stations.
 */
export function useStations(): UseQueryResult<PaginatedResponse<Station>> {
  return useQuery({
    queryKey: ['stations'],
    queryFn: () => stationApi.getAll(1, 100),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Hook for fetching all routes.
 */
export function useRoutes(): UseQueryResult<PaginatedResponse<Route>> {
  return useQuery({
    queryKey: ['routes'],
    queryFn: () => routeApi.getAll(1, 100),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Hook for fetching all trains.
 */
export function useTrains(): UseQueryResult<PaginatedResponse<Train>> {
  return useQuery({
    queryKey: ['trains'],
    queryFn: () => trainApi.getAll(1, 100),
    staleTime: 1 * 60 * 1000, // 1 minute
  });
}

/**
 * Hook for fetching train schedule.
 */
export function useTrainSchedule(
  trainId: number | null
): UseQueryResult<TrainSchedule | null> {
  return useQuery({
    queryKey: ['train-schedule', trainId],
    queryFn: () => (trainId ? scheduleApi.getTrainSchedule(trainId) : null),
    enabled: !!trainId,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook for fetching station schedule.
 */
export function useStationSchedule(
  stationId: number | null
): UseQueryResult<StationSchedule | null> {
  return useQuery({
    queryKey: ['station-schedule', stationId],
    queryFn: () => (stationId ? scheduleApi.getStationSchedule(stationId) : null),
    enabled: !!stationId,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook for real-time train positions via WebSocket.
 */
export function useTrainPositions(
  bbox?: string | null,
): {
  positions: TrainPositionUpdate[];
  isConnected: boolean;
  error: string | null;
} {
  const [positions, setPositions] = useState<TrainPositionUpdate[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsClientRef = useRef<TrainWebSocketClient | null>(null);

  useEffect(() => {
    // Only run on client
    if (typeof window === 'undefined') return;

    const client = getWebSocketClient();
    wsClientRef.current = client;

    const unsubscribeConnect = client.onConnect(() => {
      setIsConnected(true);
      setError(null);
    });

    const unsubscribeDisconnect = client.onDisconnect(() => {
      setIsConnected(false);
    });

    const unsubscribeMessage = client.onMessage((newPositions) => {
      setPositions(newPositions);
    });

    const unsubscribeError = client.onError(() => {
      setError('Connection error');
    });

    client.connect();

    return () => {
      unsubscribeConnect();
      unsubscribeDisconnect();
      unsubscribeMessage();
      unsubscribeError();
      client.disconnect();
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || !bbox) return;
    const client = wsClientRef.current ?? getWebSocketClient();
    client.sendBBox(bbox);
  }, [bbox]);

  return { positions, isConnected, error };
}

/**
 * Hook for initial train positions (REST API fallback).
 */
export function useInitialPositions(
  bbox?: string | null,
): UseQueryResult<TrainPositionUpdate[]> {
  return useQuery({
    queryKey: ['train-positions', bbox ?? 'no-bbox'],
    queryFn: () => trainApi.getAllPositions(bbox!),
    enabled: Boolean(bbox),
    refetchInterval: 30000, // Refetch every 30 seconds as fallback
    staleTime: 10000,
  });
}

/**
 * Hook for geops-compatible train trajectories via WebSocket.
 *
 * Connects to /ws/trajectory and maintains a Map<trainId, TrainTrajectory>.
 * Trajectories contain time_intervals so the caller can interpolate position at
 * any moment with getVehiclePosition() — no additional round-trips needed.
 *
 * Pattern: geops/mobility-toolbox-js RealtimeEngine trajectory management.
 */
export function useTrainTrajectories(): {
  trajectories: Map<number, TrainTrajectory>;
  isConnected: boolean;
} {
  const [trajectories, setTrajectories] = useState<Map<number, TrainTrajectory>>(new Map());
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const client = getTrajectoryClient();

    const unsub = client.onUpdate((updated) => {
      startTransition(() => {
        setTrajectories(new Map(updated));
      });
      if (!isConnected) setIsConnected(true);
    });

    client.connect();

    return () => {
      unsub();
      client.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { trajectories, isConnected };
}

/**
 * Hook for loading static map infrastructure data once per page load.
 */
export function useStaticMapData(): UseQueryResult<{
  stations: Station[];
  network_edges: NetworkEdgeCollection;
}> {
  return useQuery({
    queryKey: ['map-static-data'],
    queryFn: () => mapApi.getStaticData(),
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

/**
 * Hook for searching stations.
 */
export function useStationSearch(query: string): UseQueryResult<Station[]> {
  return useQuery({
    queryKey: ['station-search', query],
    queryFn: () => stationApi.search(query),
    enabled: query.length >= 2,
    staleTime: 60 * 1000,
  });
}

/**
 * Hook for managing selected train.
 */
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

/**
 * Hook for managing selected station.
 */
export function useSelectedStation(): {
  selectedStationId: number | null;
  selectStation: (id: number | null) => void;
} {
  const [selectedStationId, setSelectedStationId] = useState<number | null>(null);

  const selectStation = useCallback((id: number | null) => {
    setSelectedStationId(id);
  }, []);

  return { selectedStationId, selectStation };
}

/**
 * Hook for dark mode.
 */
export function useDarkMode(): {
  isDark: boolean;
  toggle: () => void;
} {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    // Check initial preference
    const stored = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const shouldBeDark = stored === 'dark' || (!stored && prefersDark);

    setIsDark(shouldBeDark);
    document.documentElement.classList.toggle('dark', shouldBeDark);
  }, []);

  const toggle = useCallback(() => {
    setIsDark((prev) => {
      const newValue = !prev;
      localStorage.setItem('theme', newValue ? 'dark' : 'light');
      document.documentElement.classList.toggle('dark', newValue);
      return newValue;
    });
  }, []);

  return { isDark, toggle };
}
