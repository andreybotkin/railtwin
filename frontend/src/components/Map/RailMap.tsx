/**
 * Root Leaflet map for the RailTwin UI.
 *
 *  - Loads topology once from /api/v1/map/topology (stations + network edges).
 *  - Subscribes to the trajectory WebSocket via useTrajectoryStream.
 *  - Renders thick route polylines coloured by route type.
 *  - Renders stations as white circles with black borders.
 *  - Renders trains as rounded-rectangle (pill) markers with a headlight dot
 *    on the locomotive side; wagons are the same shape without the dot.
 *  - Shows delay/advance label at zoom >= 10.
 *  - Reports viewport bbox to the store for server-side trajectory filtering.
 */

'use client';

import 'leaflet/dist/leaflet.css';

import { useCallback, useEffect, useMemo } from 'react';
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

import { useMapTopology, useTheme, useTrajectoryStream } from '@/lib/hooks';
import { useRailwayStore } from '@/lib/stores/railway-store';
import { getRouteColor } from '@/lib/utils';

import LeafletStationMarker from './LeafletStationMarker';
import LeafletTrainMarker from './LeafletTrainMarker';

// Fix Leaflet's default icon broken in Next.js / webpack
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

// Thailand geographic centre
const THAILAND_CENTER: [number, number] = [15.87, 100.9925];
const INITIAL_ZOOM = 6;

// ─── Tile URL helpers ─────────────────────────────────────────────────────────

type AppTheme = 'light' | 'dark' | 'satellite';

function getTileUrl(theme: AppTheme): string {
  if (theme === 'dark')
    return 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
  if (theme === 'satellite')
    return 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
  return 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
}

function getTileAttribution(theme: AppTheme): string {
  if (theme === 'satellite')
    return 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community';
  return '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';
}

// ─── Inner map component (has access to useMap / useMapEvents) ────────────────

function MapCore() {
  const map = useMap();
  const { data: topology } = useMapTopology();
  const { theme } = useTheme();

  const setTopology = useRailwayStore((s) => s.setTopology);
  const setViewportBbox = useRailwayStore((s) => s.setViewportBbox);
  const selectTrain = useRailwayStore((s) => s.selectTrain);
  const trajectories = useRailwayStore((s) => s.trajectories);
  const selectedTrainId = useRailwayStore((s) => s.selectedTrainId);
  const flyTo = useRailwayStore((s) => s.flyTo);
  const requestFlyTo = useRailwayStore((s) => s.requestFlyTo);

  useTrajectoryStream();

  // Sync topology into store
  useEffect(() => {
    setTopology(topology ?? null);
  }, [topology, setTopology]);

  // flyTo: pan/zoom to a requested location
  useEffect(() => {
    if (!flyTo) return;
    map.flyTo(
      [flyTo.lat, flyTo.lon],
      flyTo.zoom ?? Math.max(map.getZoom(), 11),
      { duration: 0.9 },
    );
    requestFlyTo(null);
  }, [flyTo, map, requestFlyTo]);

  // Report viewport bbox on every moveend
  const publishViewport = useCallback(() => {
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
  }, [map, setViewportBbox]);

  // Send initial bbox on mount
  useEffect(() => {
    publishViewport();
  }, [publishViewport]);

  useMapEvents({ moveend: publishViewport });

  // ── Derived data ──────────────────────────────────────────────────────────

  const stations = topology?.stations ?? [];
  const networkEdges = topology?.network_edges?.features ?? [];

  // Deduplicate edges (same segment may appear from both directions)
  const displayEdges = useMemo(() => {
    const seen = new Set<string>();
    return networkEdges.filter((edge) => {
      const a = edge.properties.from_node_id;
      const b = edge.properties.to_node_id;
      const key = `${Math.min(a, b)}:${Math.max(a, b)}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [networkEdges]);

  // Trajectory list for rendering
  const trajectoryList = useMemo(
    () => Array.from(trajectories.values()),
    [trajectories],
  );

  // Selected train trajectory for highlight polyline
  const selectedRouteCoords = useMemo(() => {
    if (selectedTrainId === null) return null;
    return trajectories.get(selectedTrainId)?.route_coords ?? null;
  }, [trajectories, selectedTrainId]);

  // ── Tile URL (theme-driven) ───────────────────────────────────────────────
  const tileUrl = getTileUrl(theme as AppTheme);
  const tileAttribution = getTileAttribution(theme as AppTheme);

  return (
    <>
      {/* Base tile layer */}
      <TileLayer
        key={theme}
        url={tileUrl}
        attribution={tileAttribution}
        maxZoom={19}
      />

      {/* Scale bar */}
      <ScaleControl position="bottomright" imperial={false} />

      {/* Route network — thick coloured polylines */}
      {displayEdges.map((edge, idx) => {
        const positions = edge.geometry.coordinates.map(
          ([lon, lat]) => [lat, lon] as [number, number],
        );
        const routeType = edge.properties.route_type ?? '';
        return (
          <Polyline
            key={`edge-${idx}`}
            positions={positions}
            color={getRouteColor(routeType)}
            weight={4}
            opacity={0.8}
            interactive={false}
          />
        );
      })}

      {/* Selected train full route highlight */}
      {selectedRouteCoords && selectedRouteCoords.length >= 2 && (
        <>
          <Polyline
            positions={selectedRouteCoords.map(([lon, lat]) => [lat, lon] as [number, number])}
            color="#FFFFFF"
            weight={9}
            opacity={0.85}
            interactive={false}
          />
          <Polyline
            positions={selectedRouteCoords.map(([lon, lat]) => [lat, lon] as [number, number])}
            color="#F59E0B"
            weight={5}
            opacity={0.95}
            interactive={false}
          />
        </>
      )}

      {/* Stations — clustered at low zoom, individual markers above zoom 10 */}
      <MarkerClusterGroup
        chunkedLoading
        maxClusterRadius={40}
        disableClusteringAtZoom={10}
        spiderfyOnMaxZoom
        showCoverageOnHover={false}
      >
        {stations.map((station) => (
          <LeafletStationMarker key={station.id} station={station} />
        ))}
      </MarkerClusterGroup>

      {/* Trains */}
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

// ─── Public component ─────────────────────────────────────────────────────────

export default function RailMap() {
  return (
    <div className="h-full w-full">
      <MapContainer
        center={THAILAND_CENTER}
        zoom={INITIAL_ZOOM}
        className="h-full w-full"
        attributionControl={false}
        zoomControl
        scrollWheelZoom
      >
        <MapCore />
      </MapContainer>
    </div>
  );
}
