/**
 * Subscribe to the gateway trajectory WebSocket and keep the railway store in
 * sync. Also forwards the current viewport bbox to the server so it can
 * pre-filter trajectories before they hit the wire.
 */

import { useEffect } from 'react';

import { useRailwayStore } from '@/lib/stores/railway-store';
import { getTrajectoryClient } from '@/lib/websocket';

export function useTrajectoryStream(): void {
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const client = getTrajectoryClient();
    const setTrajectories = useRailwayStore.getState().setTrajectories;
    const setWsConnected = useRailwayStore.getState().setWsConnected;

    const unsubscribe = client.onUpdate((snapshot) => {
      setTrajectories(snapshot);
      setWsConnected(client.isConnected());
    });

    client.connect();
    setWsConnected(client.isConnected());

    return () => {
      unsubscribe();
      client.disconnect();
      setWsConnected(false);
    };
  }, []);

  useEffect(() => {
    return useRailwayStore.subscribe((state, prev) => {
      if (state.viewportBbox !== prev.viewportBbox && state.viewportBbox) {
        getTrajectoryClient().sendBBox(state.viewportBbox);
      }
    });
  }, []);
}
