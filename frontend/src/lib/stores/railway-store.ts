/**
 * Zustand store for the live railway scene.
 *
 * Holds the map topology snapshot, the current trajectory dictionary (keyed
 * by train id), the selected train, and the viewport bbox. Everything the
 * MapLibre layers and info sheet need, so they can subscribe to narrow
 * slices of state rather than ping-ponging props.
 */

import { create } from 'zustand';

import type { MapSnapshot, Trajectory } from '@/types';

/**
 * One-shot request to the map to fly to a location. `RailMap` consumes the
 * target and immediately sets it back to `null`, so the same coords can be
 * re-sent later. `nonce` lets repeated fly-tos to the same coords trigger a
 * subscription update.
 */
export interface FlyToTarget {
  lon: number;
  lat: number;
  zoom?: number;
  nonce: number;
}

interface RailwayState {
  topology: MapSnapshot | null;
  trajectories: Map<number, Trajectory>;
  selectedTrainId: number | null;
  selectedStationId: number | null;
  viewportBbox: string | null;
  wsConnected: boolean;
  flyTo: FlyToTarget | null;

  setTopology: (snapshot: MapSnapshot | null) => void;
  setTrajectories: (next: Map<number, Trajectory>) => void;
  upsertTrajectory: (trajectory: Trajectory) => void;
  removeTrajectory: (trainId: number) => void;
  selectTrain: (trainId: number | null) => void;
  selectStation: (stationId: number | null) => void;
  setViewportBbox: (bbox: string | null) => void;
  setWsConnected: (connected: boolean) => void;
  requestFlyTo: (target: Omit<FlyToTarget, 'nonce'> | null) => void;
}

export const useRailwayStore = create<RailwayState>((set) => ({
  topology: null,
  trajectories: new Map(),
  selectedTrainId: null,
  selectedStationId: null,
  viewportBbox: null,
  wsConnected: false,
  flyTo: null,

  setTopology: (snapshot) => set({ topology: snapshot }),
  setTrajectories: (next) => set({ trajectories: new Map(next) }),
  upsertTrajectory: (trajectory) =>
    set((state) => {
      const next = new Map(state.trajectories);
      next.set(trajectory.train_id, trajectory);
      return { trajectories: next };
    }),
  removeTrajectory: (trainId) =>
    set((state) => {
      if (!state.trajectories.has(trainId)) return state;
      const next = new Map(state.trajectories);
      next.delete(trainId);
      return { trajectories: next };
    }),
  selectTrain: (trainId) =>
    set({ selectedTrainId: trainId, selectedStationId: null }),
  selectStation: (stationId) =>
    set({ selectedStationId: stationId, selectedTrainId: null }),
  setViewportBbox: (bbox) => set({ viewportBbox: bbox }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
  requestFlyTo: (target) =>
    set((state) =>
      target === null
        ? { flyTo: null }
        : {
            flyTo: {
              lon: target.lon,
              lat: target.lat,
              zoom: target.zoom,
              nonce: (state.flyTo?.nonce ?? 0) + 1,
            },
          }
    ),
}));
