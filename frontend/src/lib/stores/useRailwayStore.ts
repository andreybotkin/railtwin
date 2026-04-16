import { create } from 'zustand';

import type { Trajectory } from '@/lib/trajectory-interpolation';

interface TopologyPayload {
  stations: Array<Record<string, unknown>>;
  edges: { type: 'FeatureCollection'; features: Array<Record<string, unknown>> };
}

interface State {
  trajectories: Map<number, Trajectory>;
  topology: TopologyPayload | null;
  selectedTrainId: number | null;
  setTrajectories: (items: Trajectory[]) => void;
  setTopology: (payload: TopologyPayload) => void;
  setSelectedTrainId: (id: number | null) => void;
}

export const useRailwayStore = create<State>((set) => ({
  trajectories: new Map(),
  topology: null,
  selectedTrainId: null,
  setTrajectories: (items) => set({ trajectories: new Map(items.map((t) => [t.train_id, t])) }),
  setTopology: (payload) => set({ topology: payload }),
  setSelectedTrainId: (id) => set({ selectedTrainId: id }),
}));
