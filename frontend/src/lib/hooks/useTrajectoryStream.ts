/**
 * Bootstrap the visible trajectories with a bbox-filtered REST snapshot, then
 * keep the store synchronized through the gateway WebSocket delta stream.
 */

import { useEffect } from 'react';

import { gatewayApi } from '@/lib/api/client';
import { useRailwayStore } from '@/lib/stores/railway-store';
import { getTrajectoryClient } from '@/lib/websocket';
import type { Trajectory } from '@/types';

function toTrajectoryMap(items: Trajectory[]): Map<number, Trajectory> {
  return new Map(items.map((trajectory) => [trajectory.train_id, trajectory]));
}

export function useTrajectoryStream(): void {
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const client = getTrajectoryClient();
    const setTrajectories = useRailwayStore.getState().setTrajectories;
    const setWsConnected = useRailwayStore.getState().setWsConnected;

    let disposed = false;
    let started = false;
    let wsDeliveredData = false;
    let initialBBox: string | null = null;
    let unsubscribeUpdates: (() => void) | null = null;

    const preserveSelectedTrain = (
      snapshot: Map<number, Trajectory>
    ): Map<number, Trajectory> => {
      const state = useRailwayStore.getState();
      const selectedId = state.selectedTrainId;
      if (selectedId === null || snapshot.has(selectedId)) return snapshot;

      const selectedTrajectory = state.trajectories.get(selectedId);
      if (!selectedTrajectory) return snapshot;

      const next = new Map(snapshot);
      next.set(selectedId, selectedTrajectory);
      return next;
    };

    const start = (bbox: string) => {
      if (started || disposed) return;
      started = true;
      initialBBox = bbox;
      client.sendBBox(bbox);

      unsubscribeUpdates = client.onUpdate((snapshot) => {
        wsDeliveredData = true;
        setTrajectories(preserveSelectedTrain(snapshot));
        setWsConnected(client.isConnected());
      });

      client.connect();
      setWsConnected(client.isConnected());

      void gatewayApi
        .getTrajectories(bbox)
        .then((items) => {
          if (
            disposed ||
            wsDeliveredData ||
            useRailwayStore.getState().viewportBbox !== initialBBox
          )
            return;
          setTrajectories(preserveSelectedTrain(toTrajectoryMap(items)));
        })
        .catch(() => {
          // The WebSocket remains the authoritative fallback.
        });
    };

    const currentBBox = useRailwayStore.getState().viewportBbox;
    if (currentBBox) start(currentBBox);

    const unsubscribeStore = useRailwayStore.subscribe((state, previous) => {
      if (!started && state.viewportBbox) {
        start(state.viewportBbox);
        return;
      }
      if (
        started &&
        state.viewportBbox &&
        state.viewportBbox !== previous.viewportBbox
      ) {
        client.sendBBox(state.viewportBbox);
      }
    });

    return () => {
      disposed = true;
      unsubscribeStore();
      unsubscribeUpdates?.();
      client.disconnect();
      setWsConnected(false);
    };
  }, []);
}
