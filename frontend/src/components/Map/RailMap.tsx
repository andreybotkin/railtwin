'use client';

import 'maplibre-gl/dist/maplibre-gl.css';

import type { Map as MaplibreMap } from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';
import Map, { AttributionControl, NavigationControl, ScaleControl } from 'react-map-gl/maplibre';

import { useRafVehicleTicker } from '@/lib/hooks/useRafVehicleTicker';
import type { Trajectory } from '@/lib/trajectory-interpolation';
import { useRailwayStore } from '@/lib/stores/useRailwayStore';

import StationsLayer from './StationsLayer';
import TracksLayer from './TracksLayer';
import VehiclesLayer from './VehiclesLayer';

const STYLE_URL = process.env.NEXT_PUBLIC_MAP_STYLE_URL || 'https://tiles.openfreemap.org/styles/liberty';

export default function RailMap() {
  const mapRef = useRef<MaplibreMap | null>(null);
  const [ready, setReady] = useState(false);
  const topology = useRailwayStore((s) => s.topology);
  const setTopology = useRailwayStore((s) => s.setTopology);
  const setTrajectories = useRailwayStore((s) => s.setTrajectories);
  const setSelectedTrainId = useRailwayStore((s) => s.setSelectedTrainId);

  useEffect(() => {
    (async () => {
      const res = await fetch('/api/v1/map/topology');
      if (!res.ok) return;
      const payload = await res.json();
      setTopology(payload);

      const trajectoriesRes = await fetch('/api/v1/trains/trajectories');
      if (!trajectoriesRes.ok) return;
      const trajectoryPayload = await trajectoriesRes.json();
      setTrajectories(trajectoryPayload as Trajectory[]);
    })();

    const trajectoryMap = new Map<number, Trajectory>();
    const ws = new WebSocket(`${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/trajectory`);
    ws.onmessage = (event) => {
      const parsed = JSON.parse(event.data);
      if (parsed?.type === 'trajectory_delta') {
        for (const trajectory of parsed.upserts ?? []) {
          trajectoryMap.set(trajectory.train_id, trajectory as Trajectory);
        }
        for (const removedId of parsed.removed_ids ?? []) {
          trajectoryMap.delete(Number(removedId));
        }
        setTrajectories(Array.from(trajectoryMap.values()));
      }
    };
    return () => ws.close();
  }, [setTopology, setTrajectories]);

  useRafVehicleTicker(mapRef.current);

  return (
    <Map
      reuseMaps
      mapStyle={STYLE_URL}
      initialViewState={{ longitude: 100.5018, latitude: 13.7563, zoom: 6 }}
      interactiveLayerIds={['vehicles-symbol']}
      onLoad={(ev) => {
        mapRef.current = ev.target as MaplibreMap;
        setReady(true);
        ev.target.on('click', 'vehicles-symbol', (event) => {
          const feature = event.features?.[0];
          const trainId = Number(feature?.properties?.train_id);
          setSelectedTrainId(Number.isFinite(trainId) ? trainId : null);
        });
      }}
      attributionControl={false}
      style={{ width: '100%', height: '100%' }}
    >
      <AttributionControl compact customAttribution="© OpenStreetMap contributors" />
      <NavigationControl position="top-left" />
      <ScaleControl position="bottom-right" />

      {ready && topology && (
        <>
          <TracksLayer edges={topology.edges} />
          <StationsLayer stations={topology.stations} />
          <VehiclesLayer />
        </>
      )}
    </Map>
  );
}
