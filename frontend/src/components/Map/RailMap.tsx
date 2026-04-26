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

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AttributionControl,
  MapContainer,
  Polyline,
  ScaleControl,
  TileLayer,
  useMap,
  useMapEvents,
} from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import L from 'leaflet';

import type { Trajectory } from '@/types';
import { getTrajectoryFrameAt } from '@/lib/trajectory-interpolation';
import { useMapTopology, useTheme, useTrajectoryStream } from '@/lib/hooks';
import { useRailwayStore } from '@/lib/stores/railway-store';
import { getRouteColor, getTrainTypeColor } from '@/lib/utils';

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

interface RailMapProps {
  onLocateReady?: (locateFn: (() => void) | null) => void;
}

// ─── Viewport persistence ─────────────────────────────────────────────────────

const VIEW_STORAGE_KEY = 'rt-map-view';

interface SavedView { lat: number; lng: number; zoom: number; }

function loadSavedView(): { center: [number, number]; zoom: number } {
  try {
    const raw = localStorage.getItem(VIEW_STORAGE_KEY);
    if (raw) {
      const v = JSON.parse(raw) as SavedView;
      if (
        typeof v.lat === 'number' && isFinite(v.lat) &&
        typeof v.lng === 'number' && isFinite(v.lng) &&
        typeof v.zoom === 'number' && v.zoom >= 1 && v.zoom <= 20
      ) {
        return { center: [v.lat, v.lng], zoom: v.zoom };
      }
    }
  } catch { /* ignore */ }
  return { center: THAILAND_CENTER, zoom: INITIAL_ZOOM };
}

function saveView(lat: number, lng: number, zoom: number): void {
  try {
    localStorage.setItem(VIEW_STORAGE_KEY, JSON.stringify({ lat, lng, zoom }));
  } catch { /* ignore */ }
}

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

// ─── Selected route highlight with RAF-animated wave ─────────────────────────

interface SelectedRouteHighlightProps {
  /** [lon, lat] pairs from trajectory.route_coords */
  routeCoords: [number, number][];
  color: string;
  travelForward: boolean;
}

/**
 * Renders three imperatively-created Leaflet polylines for the selected train
 * route and drives the wave animation via requestAnimationFrame so that it
 * reliably works on SVG <path> elements regardless of CSS scoping.
 */
function SelectedRouteHighlight({
  routeCoords,
  color,
  travelForward,
}: SelectedRouteHighlightProps) {
  const map = useMap();
  // Keep a stable ref to travelForward so the RAF closure always sees the
  // current direction without restarting the loop.
  const travelForwardRef = useRef(travelForward);
  useEffect(() => { travelForwardRef.current = travelForward; }, [travelForward]);

  useEffect(() => {
    const latLngs = routeCoords.map(([lon, lat]) => L.latLng(lat, lon));

    const casingLine = L.polyline(latLngs, {
      pane: 'selected-route-pane',
      color: '#FFFFFF',
      weight: 12,
      opacity: 0.9,
      interactive: false,
    }).addTo(map);

    const fillLine = L.polyline(latLngs, {
      pane: 'selected-route-pane',
      color,
      weight: 8,
      opacity: 0.95,
      interactive: false,
    }).addTo(map);

    const waveLine = L.polyline(latLngs, {
      pane: 'selected-route-pane',
      color: 'rgba(255,255,255,0.85)',
      weight: 5,
      opacity: 1,
      dashArray: '18 14',
      lineCap: 'round',
      lineJoin: 'round',
      interactive: false,
    }).addTo(map);

    // Drive stroke-dashoffset directly so the animation is frame-accurate and
    // never fights with CSS resets from react-leaflet re-renders.
    const PERIOD = 32; // dashArray sum: 18+14
    const SPEED = 30;  // px/s
    let offset = 0;
    let last: number | null = null;
    let rafId: number;

    const step = (t: number) => {
      if (last !== null) {
        const dt = (t - last) / 1000;
        offset += (travelForwardRef.current ? SPEED : -SPEED) * dt;
        // keep offset in [0, PERIOD) to avoid float growth
        offset = ((offset % PERIOD) + PERIOD) % PERIOD;
      }
      last = t;
      const path = (waveLine as unknown as { _path: SVGElement | null })._path;
      if (path) {
        (path as SVGElement & { style: CSSStyleDeclaration }).style.strokeDashoffset =
          String(-offset);
      }
      rafId = requestAnimationFrame(step);
    };
    rafId = requestAnimationFrame(step);

    return () => {
      cancelAnimationFrame(rafId);
      map.removeLayer(casingLine);
      map.removeLayer(fillLine);
      map.removeLayer(waveLine);
    };
  // Re-create layers only when the route itself or base color changes.
  // travelForward changes are handled via ref.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, routeCoords, color]);

  return null;
}

// ─── Route stop markers ──────────────────────────────────────────────────────

/**
 * Interpolate a point along a [lon, lat][] polyline at the given fraction [0, 1].
 * Returns a Leaflet-order [lat, lon] pair.
 */
function interpolateRoutePoint(
  routeCoords: [number, number][],
  fraction: number,
): [number, number] | null {
  const n = routeCoords.length;
  if (n === 0) return null;
  if (n === 1) return [routeCoords[0][1], routeCoords[0][0]];
  const f = Math.max(0, Math.min(1, fraction));
  if (f <= 0) return [routeCoords[0][1], routeCoords[0][0]];
  if (f >= 1) return [routeCoords[n - 1][1], routeCoords[n - 1][0]];

  // Cumulative distances in degree-space (sufficient for visual placement)
  const cumDist: number[] = [0];
  for (let i = 1; i < n; i++) {
    const dx = routeCoords[i][0] - routeCoords[i - 1][0];
    const dy = routeCoords[i][1] - routeCoords[i - 1][1];
    cumDist.push(cumDist[i - 1] + Math.sqrt(dx * dx + dy * dy));
  }
  const total = cumDist[n - 1];
  const target = f * total;
  for (let i = 1; i < n; i++) {
    if (cumDist[i] >= target) {
      const t = (target - cumDist[i - 1]) / (cumDist[i] - cumDist[i - 1]);
      const lon = routeCoords[i - 1][0] + (routeCoords[i][0] - routeCoords[i - 1][0]) * t;
      const lat = routeCoords[i - 1][1] + (routeCoords[i][1] - routeCoords[i - 1][1]) * t;
      return [lat, lon];
    }
  }
  return [routeCoords[n - 1][1], routeCoords[n - 1][0]];
}

/** Format minutes-since-midnight → "HH:MM". */
function formatMins(minutes: number): string {
  const h = Math.floor((minutes % 1440) / 60);
  const m = Math.round(minutes % 60);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

/**
 * Renders halo markers at every scheduled stop along the selected train's route.
 *
 *  - Passed stops  → gray halo
 *  - Next stop     → bright green halo (larger)
 *  - Pending stops → pale green halo
 *
 * Tooltips show scheduled and adjusted (delay-aware) arrival times.
 *
 * Uses two concentric `L.circleMarker` instances per stop (outer halo ring +
 * inner fill dot) created imperatively to avoid React reconciliation overhead.
 */
function RouteStopMarkers({ trajectory }: { trajectory: Trajectory }) {
  const map = useMap();

  useEffect(() => {
    const { anchors, route_coords } = trajectory;
    if (!anchors.length || route_coords.length < 2) return;

    // Deduplicate: one entry per station.
    // Track both arrival anchor (for time display) and departure anchor (for
    // geom_fraction placement — train is at the station on departure).
    const stationMap = new Map<
      string,
      { pos: typeof anchors[number]; time: typeof anchors[number] }
    >();
    for (const anchor of anchors) {
      const key =
        anchor.station_id !== null ? String(anchor.station_id) : anchor.station_name;
      const entry = stationMap.get(key);
      if (!entry) {
        stationMap.set(key, { pos: anchor, time: anchor });
      } else {
        // Use departure for geom_fraction (train is at station then)
        if (anchor.event === 'departure') entry.pos = anchor;
        // Use arrival for displaying arrival time
        if (anchor.event === 'arrival') entry.time = anchor;
      }
    }

    const stops = Array.from(stationMap.values());

    // Current position fraction
    const frame = getTrajectoryFrameAt(Date.now(), trajectory);
    const currentFraction = frame?.geomFraction ?? trajectory.meta.route_progress_pct / 100;
    const travelForward = frame?.travelForward ?? true;

    // Sort stops in travel direction
    stops.sort((a, b) =>
      travelForward
        ? a.pos.geom_fraction - b.pos.geom_fraction
        : b.pos.geom_fraction - a.pos.geom_fraction,
    );

    const layers: L.CircleMarker[] = [];
    let nextFound = false;

    for (const { pos: stop, time: timeAnchor } of stops) {
      const isPassed = travelForward
        ? stop.geom_fraction < currentFraction
        : stop.geom_fraction > currentFraction;

      let isNext = false;
      if (!isPassed && !nextFound) {
        isNext = true;
        nextFound = true;
      }

      const pos = interpolateRoutePoint(route_coords, stop.geom_fraction);
      if (!pos) continue;

      // Style by state
      const fillColor = isPassed ? '#9CA3AF' : isNext ? '#22C55E' : '#86EFAC';
      const haloRadius = isNext ? 10 : 7;
      const dotRadius = isNext ? 5 : 3.5;
      const haloOpacity = isPassed ? 0.3 : isNext ? 0.35 : 0.3;
      const dotOpacity = isPassed ? 0.55 : isNext ? 1 : 0.8;
      const strokeColor = isPassed ? '#6B7280' : isNext ? '#16A34A' : '#4ADE80';

      // Outer halo ring
      const halo = L.circleMarker(pos, {
        radius: haloRadius,
        color: strokeColor,
        weight: isNext ? 2 : 1.5,
        fill: true,
        fillColor,
        fillOpacity: haloOpacity,
        opacity: isPassed ? 0.45 : 0.7,
        // interactive:true lets hover work for passed/pending; next uses permanent tooltip
        interactive: !isNext,
      }).addTo(map);

      // Inner dot (decorative, no interaction)
      const dot = L.circleMarker(pos, {
        radius: dotRadius,
        color: strokeColor,
        weight: 1,
        fillColor,
        fillOpacity: dotOpacity,
        opacity: 0,
        interactive: false,
      }).addTo(map);

      // Build tooltip HTML — only time(s), no station name, no delay amount
      const scheduledStr = formatMins(timeAnchor.scheduled_minutes);
      const delayMin = timeAnchor.delay_minutes;
      let tipClass: string;
      let tooltipHtml: string;
      if (isPassed) {
        tipClass = 'stop-tip-passed';
        tooltipHtml = scheduledStr;
      } else if (delayMin <= 0) {
        tipClass = 'stop-tip-ontime';
        tooltipHtml = scheduledStr;
      } else {
        tipClass = delayMin < 15 ? 'stop-tip-warn' : 'stop-tip-late';
        const adjustedStr = formatMins(timeAnchor.adjusted_minutes);
        tooltipHtml = `<s style="opacity:0.6">${scheduledStr}</s> <b>${adjustedStr}</b>`;
      }

      halo.bindTooltip(tooltipHtml, {
        permanent: isNext,
        direction: 'top',
        offset: [0, -haloRadius - 2],
        interactive: false,
        className: tipClass,
      });

      layers.push(halo, dot);
    }

    return () => {
      layers.forEach((l) => map.removeLayer(l));
    };
  }, [map, trajectory]);

  return null;
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

  useEffect(() => {
    if (!map) return;
    if (!map.getPane('selected-route-pane')) {
      map.createPane('selected-route-pane');
      const pane = map.getPane('selected-route-pane');
      // 201 = just above tile pane (200), always below overlayPane (400) and markerPane (600)
      if (pane) pane.style.zIndex = '201';
    }
  }, [map]);

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

  // Report viewport bbox and persist center+zoom on every moveend
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
    const c = map.getCenter();
    saveView(c.lat, c.lng, map.getZoom());
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
  const selectedTrajectory = useMemo(
    () => (selectedTrainId === null ? null : trajectories.get(selectedTrainId) ?? null),
    [trajectories, selectedTrainId],
  );

  const selectedRouteCoords = useMemo(() => {
    return selectedTrajectory?.route_coords ?? null;
  }, [selectedTrajectory]);

  const selectedRouteColor = useMemo(() => {
    if (!selectedTrajectory) return '#2196F3';
    return getTrainTypeColor(selectedTrajectory.meta.train_type);
  }, [selectedTrajectory]);

  const selectedRouteTravelForward = useMemo(() => {
    if (!selectedTrajectory) return true;
    const frame = getTrajectoryFrameAt(Date.now(), selectedTrajectory);
    return frame?.travelForward ?? true;
  }, [selectedTrajectory]);

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

      {/* Selected train full route highlight — animated wave, always below station/train overlays */}
      {selectedRouteCoords && selectedRouteCoords.length >= 2 && (
        <SelectedRouteHighlight
          routeCoords={selectedRouteCoords}
          color={selectedRouteColor}
          travelForward={selectedRouteTravelForward}
        />
      )}

      {/* Stop halos — passed (gray) / next (bright green) / pending (pale green) */}
      {selectedTrajectory && (
        <RouteStopMarkers trajectory={selectedTrajectory} />
      )}

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

// ─── Locate-me control ───────────────────────────────────────────────────────

function LocateMeControl({ onLocateReady }: { onLocateReady?: (locateFn: (() => void) | null) => void }) {
  const map = useMap();
  const locatingRef = useRef(false);

  // One-shot location request: move the map once on click, do not track continuously.
  const handleClick = useCallback(() => {
    if (!navigator.geolocation || locatingRef.current) return;
    locatingRef.current = true;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        locatingRef.current = false;
        map.flyTo(
          [pos.coords.latitude, pos.coords.longitude],
          Math.max(map.getZoom(), 13),
          { duration: 0.8 },
        );
      },
      () => {
        locatingRef.current = false;
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }, [map]);

  useEffect(() => {
    onLocateReady?.(handleClick);
  }, [handleClick, onLocateReady]);

  return null;
}

// ─── Public component ─────────────────────────────────────────────────────────

export default function RailMap({ onLocateReady }: RailMapProps) {
  // Read once — MapContainer treats center/zoom as initial-only values.
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
      >
        <MapCore />
        <LocateMeControl onLocateReady={onLocateReady} />
      </MapContainer>
    </div>
  );
}
