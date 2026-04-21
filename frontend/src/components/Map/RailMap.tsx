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
import type { MapLayerMouseEvent, Map as MapLibreMap, MapStyleImageMissingEvent } from 'maplibre-gl';
import { Map, NavigationControl, ScaleControl, type MapRef } from 'react-map-gl/maplibre';

import {
  useMapTopology,
  useRafVehicleTicker,
  useTrajectoryStream,
} from '@/lib/hooks';
import { useRailwayStore } from '@/lib/stores/railway-store';
import {
  HALO_ICON_ID,
  LIFT_GATE_ICON_ID,
  TRAIN_TYPE_IDS,
  carriageIconId,
  carriageIconIdLeft,
  registerLiftGateFallback,
  registerVehicleIcons,
  locoIconId,
  locoIconIdLeft,
} from '@/lib/vehicle-icons';

import { useTheme } from '@/lib/hooks';

import SelectedRouteLayer from './SelectedRouteLayer';
import StationsLayer, { STATIONS_INTERACTIVE_LAYERS } from './StationsLayer';
import TracksLayer from './TracksLayer';
import VehiclesLayer from './VehiclesLayer';
import { THAILAND_VIEW, getMapStyleForTheme } from './map-style';

const VEHICLE_INTERACTIVE_LAYERS = ['vehicles-locomotive', 'vehicles-carriage'];
const INTERACTIVE_LAYERS = [
  ...VEHICLE_INTERACTIVE_LAYERS,
  ...STATIONS_INTERACTIVE_LAYERS,
];

function ensureMapIcons(map: MapLibreMap | null): void {
  if (!map) return;
  registerVehicleIcons(map);
  registerLiftGateFallback(map);
}

function areMapIconsReady(map: MapLibreMap): boolean {
  if (!map.hasImage(LIFT_GATE_ICON_ID)) return false;
  if (!map.hasImage(HALO_ICON_ID)) return false;
  return TRAIN_TYPE_IDS.every(
    (type) =>
      map.hasImage(locoIconId(type)) &&
      map.hasImage(carriageIconId(type)) &&
      map.hasImage(locoIconIdLeft(type)) &&
      map.hasImage(carriageIconIdLeft(type)),
  );
}

export default function RailMap() {
  const mapRef = useRef<MapRef | null>(null);
  const iconMapRef = useRef<MapLibreMap | null>(null);
  const { data: topology } = useMapTopology();
  const { theme } = useTheme();

  const setTopology = useRailwayStore((s) => s.setTopology);
  const setViewportBbox = useRailwayStore((s) => s.setViewportBbox);
  const selectTrain = useRailwayStore((s) => s.selectTrain);
  const selectStation = useRailwayStore((s) => s.selectStation);
  const requestFlyTo = useRailwayStore((s) => s.requestFlyTo);
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
    const isMobile = typeof window !== 'undefined' && window.innerWidth < 640;
    let padding: { top: number; bottom: number; left: number; right: number } | undefined;
    if (isMobile) {
      const panel = document.querySelector<HTMLElement>('.info-sheet');
      const bottom = panel?.offsetHeight ?? Math.round(window.innerHeight * 0.48);
      padding = { top: 0, bottom, left: 16, right: 16 };
    }
    map.flyTo({
      center: [flyTo.lon, flyTo.lat],
      zoom: flyTo.zoom ?? Math.max(map.getZoom() ?? 0, 11),
      duration: 900,
      essential: true,
      ...(padding ? { padding } : {}),
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
    ensureMapIcons(map ?? null);
    publishViewport();
  }, [publishViewport]);

  const handleClick = useCallback(
    (event: MapLayerMouseEvent) => {
      const features = event.features ?? [];
      const isMobile = typeof window !== 'undefined' && window.innerWidth < 640;

      const vehicle = features.find((f) =>
        VEHICLE_INTERACTIVE_LAYERS.includes(f.layer?.id ?? ''),
      );
      if (vehicle) {
        const trainId = vehicle.properties?.train_id;
        if (typeof trainId === 'number') {
          const isNew = trainId !== selectedTrainId;
          selectTrain(isNew ? trainId : null);
          if (isNew && isMobile) {
            requestFlyTo({ lon: event.lngLat.lng, lat: event.lngLat.lat });
          }
        }
        return;
      }

      const station = features.find((f) =>
        (f.layer?.id ?? '').startsWith('stations-'),
      );
      if (station) {
        const stationId = station.properties?.station_id;
        if (typeof stationId === 'number') {
          const isNew = stationId !== selectedStationId;
          selectStation(isNew ? stationId : null);
          if (isNew && isMobile) {
            requestFlyTo({ lon: event.lngLat.lng, lat: event.lngLat.lat });
          }
        }
        return;
      }

      // Empty space: clear both selections.
      selectTrain(null);
      selectStation(null);
    },
    [selectTrain, selectStation, requestFlyTo, selectedTrainId, selectedStationId],
  );

  const hasSelection = selectedTrainId !== null || selectedStationId !== null;

  useEffect(() => {
    let frameId: number | null = null;
    let detach = () => {};

    const bindMapEvents = () => {
      const map = mapRef.current?.getMap() ?? null;
      if (!map) {
        frameId = window.requestAnimationFrame(bindMapEvents);
        return;
      }

      if (iconMapRef.current === map) {
        ensureMapIcons(map);
        return;
      }

      const handleStyleData = () => {
        ensureMapIcons(map);
      };
      const handleStyleImageMissing = (event: MapStyleImageMissingEvent) => {
        if (event.id.startsWith('railtwin-') || event.id === LIFT_GATE_ICON_ID) {
          ensureMapIcons(map);
        }
      };

      map.on('styledata', handleStyleData);
      map.on('styleimagemissing', handleStyleImageMissing);
      iconMapRef.current = map;
      ensureMapIcons(map);

      detach = () => {
        map.off('styledata', handleStyleData);
        map.off('styleimagemissing', handleStyleImageMissing);
        if (iconMapRef.current === map) {
          iconMapRef.current = null;
        }
      };
    };

    bindMapEvents();

    return () => {
      if (frameId !== null) window.cancelAnimationFrame(frameId);
      detach();
    };
  }, []);

  useEffect(() => {
    let frameId: number | null = null;
    let cancelled = false;

    const retryIcons = () => {
      if (cancelled) return;
      const map = mapRef.current?.getMap() ?? null;
      if (map) {
        ensureMapIcons(map);
        if (areMapIconsReady(map)) return;
      }
      frameId = window.requestAnimationFrame(retryIcons);
    };

    retryIcons();

    return () => {
      cancelled = true;
      if (frameId !== null) window.cancelAnimationFrame(frameId);
    };
  }, []);

  return (
    <Map
      ref={mapRef}
      initialViewState={THAILAND_VIEW}
      mapStyle={getMapStyleForTheme(theme)}
      interactiveLayerIds={INTERACTIVE_LAYERS}
      onLoad={handleLoad}
      onStyleData={() => ensureMapIcons(mapRef.current?.getMap() ?? null)}
      onMoveEnd={publishViewport}
      onClick={handleClick}
      cursor={hasSelection ? 'pointer' : 'grab'}
      reuseMaps
      attributionControl={{ compact: true }}
    >
      <NavigationControl position="top-right" showCompass={false} />
      <ScaleControl position="bottom-right" maxWidth={120} unit="metric" />
      <TracksLayer edges={topology?.network_edges ?? null} />
      <StationsLayer
        stations={topology?.stations ?? null}
        selectedStationId={selectedStationId}
      />
      <SelectedRouteLayer />
      <VehiclesLayer />
    </Map>
  );
}
