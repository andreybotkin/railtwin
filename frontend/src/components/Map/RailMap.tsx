/**
 * Root MapLibre map for the RailTwin UI.
 *
 *  - loads `/api/v1/map/topology` once (ETag-cached on the gateway),
 *  - subscribes to the trajectory WebSocket,
 *  - streams vehicle positions into a GeoJSON source on every rAF tick,
 *  - reports the current viewport bbox back to the store so the server can
 *    pre-filter trajectories.
 *
 * All GeoJSON layers mount unconditionally (TracksLayer/StationsLayer accept
 * empty data while the topology is still loading) so MapLibre's layer stack
 * reflects the JSX order: tracks → stations → selected-route → vehicles.
 * Without this, VehiclesLayer would mount before the topology arrives and
 * end up *underneath* the tracks added later — which is how a circle could
 * end up "behind" a line in a typical WebGL renderer.
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
import { registerVehicleIcons } from '@/lib/vehicle-icons';

import SelectedRouteLayer from './SelectedRouteLayer';
import StationsLayer, { STATIONS_INTERACTIVE_LAYERS } from './StationsLayer';
import TracksLayer from './TracksLayer';
import VehiclesLayer from './VehiclesLayer';
import { THAILAND_VIEW, getMapStyleUrl } from './map-style';

const VEHICLE_INTERACTIVE_LAYERS = ['vehicles-locomotive', 'vehicles-carriage'];
const INTERACTIVE_LAYERS = [
  ...VEHICLE_INTERACTIVE_LAYERS,
  ...STATIONS_INTERACTIVE_LAYERS,
];

export default function RailMap() {
  const mapRef = useRef<MapRef | null>(null);
  const { data: topology } = useMapTopology();

  const setTopology = useRailwayStore((s) => s.setTopology);
  const setViewportBbox = useRailwayStore((s) => s.setViewportBbox);
  const selectTrain = useRailwayStore((s) => s.selectTrain);
  const selectStation = useRailwayStore((s) => s.selectStation);
  const selectedTrainId = useRailwayStore((s) => s.selectedTrainId);
  const selectedStationId = useRailwayStore((s) => s.selectedStationId);
  const flyTo = useRailwayStore((s) => s.flyTo);
  const clearFlyTo = useRailwayStore((s) => s.requestFlyTo);

  useTrajectoryStream();
  useRafVehicleTicker(mapRef);

  useEffect(() => {
    setTopology(topology ?? null);
  }, [topology, setTopology]);

  useEffect(() => {
    if (!flyTo) return;
    const map = mapRef.current?.getMap();
    if (!map) return;
    map.flyTo({
      center: [flyTo.lon, flyTo.lat],
      zoom: flyTo.zoom ?? Math.max(map.getZoom() ?? 0, 11),
      duration: 900,
      essential: true,
    });
    clearFlyTo(null);
  }, [flyTo, clearFlyTo]);

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

  const handleLoad = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (map) registerVehicleIcons(map);
    publishViewport();
  }, [publishViewport]);

  const handleClick = useCallback(
    (event: MapLayerMouseEvent) => {
      const features = event.features ?? [];

      const vehicle = features.find((f) =>
        VEHICLE_INTERACTIVE_LAYERS.includes(f.layer?.id ?? ''),
      );
      if (vehicle) {
        const trainId = vehicle.properties?.train_id;
        if (typeof trainId === 'number') {
          selectTrain(trainId === selectedTrainId ? null : trainId);
        }
        return;
      }

      const cluster = features.find(
        (f) => f.layer?.id === 'stations-clusters',
      );
      if (cluster && cluster.geometry.type === 'Point') {
        const map = mapRef.current?.getMap();
        const coords = cluster.geometry.coordinates as [number, number];
        if (map) {
          map.easeTo({
            center: coords,
            zoom: Math.min((map.getZoom() ?? 0) + 2, 14),
            duration: 400,
          });
        }
        return;
      }

      const station = features.find((f) => f.layer?.id === 'stations-unclustered');
      if (station) {
        const stationId = station.properties?.station_id;
        if (typeof stationId === 'number') {
          selectStation(stationId === selectedStationId ? null : stationId);
        }
        return;
      }

      // Empty space: clear both selections.
      selectTrain(null);
      selectStation(null);
    },
    [selectTrain, selectStation, selectedTrainId, selectedStationId],
  );

  const hasSelection = selectedTrainId !== null || selectedStationId !== null;

  return (
    <Map
      ref={mapRef}
      initialViewState={THAILAND_VIEW}
      mapStyle={getMapStyleUrl()}
      interactiveLayerIds={INTERACTIVE_LAYERS}
      onLoad={handleLoad}
      onMoveEnd={publishViewport}
      onClick={handleClick}
      cursor={hasSelection ? 'pointer' : 'grab'}
      reuseMaps
      attributionControl={{ compact: true }}
    >
      <NavigationControl position="top-right" showCompass={false} />
      <ScaleControl position="bottom-right" maxWidth={120} unit="metric" />
      <TracksLayer edges={topology?.network_edges ?? null} />
      <StationsLayer stations={topology?.stations ?? null} />
      <SelectedRouteLayer />
      <VehiclesLayer />
    </Map>
  );
}
