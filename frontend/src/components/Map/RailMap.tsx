/**
 * Root MapLibre map for the RailTwin UI.
 *
 *  - loads `/api/v1/map/topology` once (ETag-cached on the gateway),
 *  - subscribes to the trajectory WebSocket,
 *  - streams vehicle positions into a GeoJSON source on every rAF tick,
 *  - reports the current viewport bbox back to the store so the server can
 *    pre-filter trajectories.
 */

'use client';

import 'maplibre-gl/dist/maplibre-gl.css';

import { useCallback, useEffect, useRef } from 'react';
import type { MapLayerMouseEvent } from 'maplibre-gl';
import { Map, NavigationControl, ScaleControl, type MapRef } from 'react-map-gl/maplibre';

import {
  useMapTopology,
  useRafVehicleTicker,
  useTrajectoryStream,
} from '@/lib/hooks';
import { useRailwayStore } from '@/lib/stores/railway-store';

import StationsLayer from './StationsLayer';
import TracksLayer from './TracksLayer';
import VehiclesLayer from './VehiclesLayer';
import { THAILAND_VIEW, getMapStyleUrl } from './map-style';

const VEHICLE_INTERACTIVE_LAYERS = ['vehicles-locomotive', 'vehicles-carriage'];

export default function RailMap() {
  const mapRef = useRef<MapRef | null>(null);
  const { data: topology } = useMapTopology();

  const setTopology = useRailwayStore((s) => s.setTopology);
  const setViewportBbox = useRailwayStore((s) => s.setViewportBbox);
  const selectTrain = useRailwayStore((s) => s.selectTrain);
  const selectedTrainId = useRailwayStore((s) => s.selectedTrainId);

  useTrajectoryStream();
  useRafVehicleTicker(mapRef);

  useEffect(() => {
    setTopology(topology ?? null);
  }, [topology, setTopology]);

  const publishViewport = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (!map) return;
    const bounds = map.getBounds();
    const bbox = [
      bounds.getWest(),
      bounds.getSouth(),
      bounds.getEast(),
      bounds.getNorth(),
    ]
      .map((n) => n.toFixed(4))
      .join(',');
    setViewportBbox(bbox);
  }, [setViewportBbox]);

  const handleClick = useCallback(
    (event: MapLayerMouseEvent) => {
      const feature = event.features?.find((f) =>
        VEHICLE_INTERACTIVE_LAYERS.includes(f.layer?.id ?? ''),
      );
      if (!feature) {
        selectTrain(null);
        return;
      }
      const trainId = feature.properties?.train_id;
      if (typeof trainId === 'number') {
        selectTrain(trainId === selectedTrainId ? null : trainId);
      }
    },
    [selectTrain, selectedTrainId],
  );

  return (
    <Map
      ref={mapRef}
      initialViewState={THAILAND_VIEW}
      mapStyle={getMapStyleUrl()}
      interactiveLayerIds={VEHICLE_INTERACTIVE_LAYERS}
      onLoad={publishViewport}
      onMoveEnd={publishViewport}
      onClick={handleClick}
      cursor={selectedTrainId !== null ? 'pointer' : 'grab'}
      reuseMaps
      attributionControl={{ compact: true }}
    >
      <NavigationControl position="top-right" showCompass={false} />
      <ScaleControl position="bottom-right" maxWidth={120} unit="metric" />
      {topology?.network_edges ? <TracksLayer edges={topology.network_edges} /> : null}
      {topology?.stations ? <StationsLayer stations={topology.stations} /> : null}
      <VehiclesLayer />
    </Map>
  );
}
