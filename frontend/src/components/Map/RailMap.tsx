/**
 * Root Leaflet map for the RailTwin UI.
 *
 * Static railway geometry is rendered through one Canvas-backed GeoJSON layer
 * instead of thousands of React SVG paths. Live trains are bootstrapped with a
 * viewport-filtered REST snapshot and then updated through WebSocket deltas.
 */

'use client';

import 'leaflet/dist/leaflet.css';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  MapContainer,
  Polyline,
  ScaleControl,
  TileLayer,
  useMap,
  useMapEvents,
} from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import L from 'leaflet';

import type { NetworkEdgeCollection } from '@/types';
import { useMapTopology, useTheme, useTrajectoryStream } from '@/lib/hooks';
import { useRailwayStore } from '@/lib/stores/railway-store';
import { getRouteColor, getTrainTypeColor } from '@/lib/utils';

import LeafletStationMarker from './LeafletStationMarker';
import LeafletTrainMarker from './LeafletTrainMarker';

const THAILAND_CENTER: [number, number] = [15.87, 100.9925];
const INITIAL_ZOOM = 6;
const VIEW_STORAGE_KEY = 'rt-map-view';
const EMPTY_EDGES: NetworkEdgeCollection = {
  type: 'FeatureCollection',
  features: [],
};

type AppTheme = 'light' | 'dark' | 'satellite';

interface RailMapProps {
  onLocateReady?: (locateFn: (() => void) | null) => void;
}

interface SavedView {
  lat: number;
  lng: number;
  zoom: number;
}

function loadSavedView(): { center: [number, number]; zoom: number } {
  try {
    const raw = localStorage.getItem(VIEW_STORAGE_KEY);
    if (raw) {
      const view = JSON.parse(raw) as SavedView;
      if (
        Number.isFinite(view.lat) &&
        Number.isFinite(view.lng) &&
        Number.isFinite(view.zoom) &&
        view.zoom >= 1 &&
        view.zoom <= 20
      ) {
        return { center: [view.lat, view.lng], zoom: view.zoom };
      }
    }
  } catch {
    // Use the Thailand-wide default view.
  }
  return { center: THAILAND_CENTER, zoom: INITIAL_ZOOM };
}

function saveView(lat: number, lng: number, zoom: number): void {
  try {
    localStorage.setItem(VIEW_STORAGE_KEY, JSON.stringify({ lat, lng, zoom }));
  } catch {
    // Storage is an optional optimization.
  }
}

function getTileUrl(theme: AppTheme): string {
  if (theme === 'dark') {
    return 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
  }
  if (theme === 'satellite') {
    return 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
  }
  return 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
}

function getTileAttribution(theme: AppTheme): string {
  if (theme === 'satellite') {
    return 'Tiles &copy; Esri and the GIS User Community';
  }
  return '&copy; OpenStreetMap contributors &copy; CARTO';
}

function TracksCanvasLayer({ edges }: { edges?: NetworkEdgeCollection | null }) {
  const map = useMap();
  const renderer = useMemo(() => L.canvas({ padding: 0.5 }), []);

  const collection = useMemo<NetworkEdgeCollection>(() => {
    const source = edges ?? EMPTY_EDGES;
    const seen = new Set<string>();
    return {
      type: 'FeatureCollection',
      features: source.features.filter((edge) => {
        const a = edge.properties.from_node_id;
        const b = edge.properties.to_node_id;
        const key = `${Math.min(a, b)}:${Math.max(a, b)}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      }),
    };
  }, [edges]);

  useEffect(() => {
    if (collection.features.length === 0) return;

    const casing = L.geoJSON(collection as never, {
      renderer,
      interactive: false,
      style: {
        color: '#ffffff',
        weight: 6,
        opacity: 0.62,
        lineCap: 'round',
        lineJoin: 'round',
      },
    });
    const routes = L.geoJSON(collection as never, {
      renderer,
      interactive: false,
      style: (feature) => ({
        color: getRouteColor(String(feature?.properties?.route_type ?? '')),
        weight: 4,
        opacity: 0.82,
        lineCap: 'round',
        lineJoin: 'round',
      }),
    });
    const group = L.layerGroup([casing, routes]).addTo(map);
    return () => {
      map.removeLayer(group);
    };
  }, [collection, map, renderer]);

  return null;
}

function MapCore() {
  const map = useMap();
  const { data: topology } = useMapTopology();
  const { theme } = useTheme();

  const setTopology = useRailwayStore((state) => state.setTopology);
  const setViewportBbox = useRailwayStore((state) => state.setViewportBbox);
  const selectTrain = useRailwayStore((state) => state.selectTrain);
  const trajectories = useRailwayStore((state) => state.trajectories);
  const selectedTrainId = useRailwayStore((state) => state.selectedTrainId);
  const flyTo = useRailwayStore((state) => state.flyTo);
  const requestFlyTo = useRailwayStore((state) => state.requestFlyTo);

  useTrajectoryStream();

  useEffect(() => setTopology(topology ?? null), [setTopology, topology]);

  useEffect(() => {
    if (!flyTo) return;
    map.flyTo([flyTo.lat, flyTo.lon], flyTo.zoom ?? Math.max(map.getZoom(), 11), {
      duration: 0.9,
    });
    requestFlyTo(null);
  }, [flyTo, map, requestFlyTo]);

  const publishViewport = useCallback(() => {
    const bounds = map.getBounds();
    const bbox = [
      bounds.getWest(),
      bounds.getSouth(),
      bounds.getEast(),
      bounds.getNorth(),
    ]
      .map((value) => value.toFixed(4))
      .join(',');
    setViewportBbox(bbox);
    const center = map.getCenter();
    saveView(center.lat, center.lng, map.getZoom());
  }, [map, setViewportBbox]);

  useEffect(() => publishViewport(), [publishViewport]);
  useMapEvents({ moveend: publishViewport });

  const trajectoryList = useMemo(
    () => Array.from(trajectories.values()),
    [trajectories]
  );
  const selectedTrajectory =
    selectedTrainId === null ? null : trajectories.get(selectedTrainId) ?? null;
  const selectedPositions = selectedTrajectory?.route_coords.map(
    ([lon, lat]) => [lat, lon] as [number, number]
  );

  return (
    <>
      <TileLayer
        key={theme}
        url={getTileUrl(theme as AppTheme)}
        attribution={getTileAttribution(theme as AppTheme)}
        maxZoom={19}
      />
      <ScaleControl position="bottomright" imperial={false} />
      <TracksCanvasLayer edges={topology?.network_edges} />

      {selectedPositions && selectedPositions.length >= 2 && (
        <Polyline
          positions={selectedPositions}
          color={
            selectedTrajectory
              ? getTrainTypeColor(selectedTrajectory.meta.train_type)
              : '#2196F3'
          }
          weight={8}
          opacity={0.9}
          interactive={false}
        />
      )}

      <MarkerClusterGroup
        chunkedLoading
        maxClusterRadius={40}
        disableClusteringAtZoom={10}
        spiderfyOnMaxZoom
        showCoverageOnHover={false}
      >
        {(topology?.stations ?? []).map((station) => (
          <LeafletStationMarker key={station.id} station={station} />
        ))}
      </MarkerClusterGroup>

      {trajectoryList.map((trajectory) => (
        <LeafletTrainMarker
          key={trajectory.train_id}
          trajectory={trajectory}
          isSelected={trajectory.train_id === selectedTrainId}
          onSelect={selectTrain}
        />
      ))}
    </>
  );
}

function LocateMeControl({
  onLocateReady,
}: {
  onLocateReady?: (locateFn: (() => void) | null) => void;
}) {
  const map = useMap();
  const locate = useCallback(() => {
    navigator.geolocation?.getCurrentPosition(
      (position) => {
        map.flyTo(
          [position.coords.latitude, position.coords.longitude],
          Math.max(map.getZoom(), 13),
          { duration: 0.8 }
        );
      },
      () => undefined,
      { enableHighAccuracy: true, timeout: 10_000 }
    );
  }, [map]);

  useEffect(() => {
    onLocateReady?.(locate);
    return () => onLocateReady?.(null);
  }, [locate, onLocateReady]);

  return null;
}

export default function RailMap({ onLocateReady }: RailMapProps) {
  const [initialView] = useState(loadSavedView);

  return (
    <div className="h-full w-full">
      <MapContainer
        center={initialView.center}
        zoom={initialView.zoom}
        className="h-full w-full"
        attributionControl={false}
        zoomControl={false}
        scrollWheelZoom
        preferCanvas
      >
        <MapCore />
        <LocateMeControl onLocateReady={onLocateReady} />
      </MapContainer>
    </div>
  );
}
