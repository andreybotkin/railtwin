/**
 * Canvas-based train rendering layer for 1000+ trains.
 *
 * Pattern from geops/mobility-toolbox-js RealtimeEngine / TrackerLayer:
 * - Uses L.Canvas renderer for performant rendering of thousands of markers
 * - CircleMarker with Canvas renderer instead of DOM-based divIcon
 * - Only the selected train gets a full DOM-based interactive marker
 * - requestAnimationFrame interpolation for smooth movement
 * - Delay color coding applied to circle fill
 */

'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import type { TrainPositionUpdate, TrainType } from '@/types';

// --- Color helpers (same as TrainMarker but for canvas) ---

const DELAY_COLORS = {
  onTime: '#43A047',
  slight: '#FDD835',
  moderate: '#FB8C00',
  severe: '#E53935',
} as const;

const TYPE_COLORS: Record<TrainType, string> = {
  special_express: '#E53935',
  rapid: '#1E88E5',
  ordinary: '#43A047',
};

function getDelayColor(delayMinutes: number): string {
  if (delayMinutes <= 0) return DELAY_COLORS.onTime;
  if (delayMinutes <= 5) return DELAY_COLORS.slight;
  if (delayMinutes <= 15) return DELAY_COLORS.moderate;
  return DELAY_COLORS.severe;
}

// --- Animation state for each train ---
interface TrainAnimState {
  marker: L.CircleMarker;
  prevLat: number;
  prevLon: number;
  targetLat: number;
  targetLon: number;
  startTime: number;
}

const ANIM_DURATION = 1900; // ms, matches WS poll interval

interface CanvasTrainLayerProps {
  positions: TrainPositionUpdate[];
  selectedTrainId?: number | null;
  onTrainSelect?: (id: number | null) => void;
  /** Minimum zoom level at which individual train markers are shown */
  minZoom?: number;
}

/**
 * Canvas-rendered train layer component.
 * Renders all non-selected trains as lightweight L.CircleMarker on a shared Canvas renderer.
 * The selected train is excluded here and should be rendered separately as a richer TrainMarker.
 */
export default function CanvasTrainLayer({
  positions,
  selectedTrainId,
  onTrainSelect,
  minZoom = 5,
}: CanvasTrainLayerProps) {
  const map = useMap();
  const canvasRenderer = useRef<L.Canvas | null>(null);
  const layerGroup = useRef<L.LayerGroup | null>(null);
  const animStates = useRef<Map<number, TrainAnimState>>(new Map());
  const rafId = useRef<number>(0);

  // Initialize canvas renderer and layer group
  useEffect(() => {
    canvasRenderer.current = L.canvas({ padding: 0.5 });
    layerGroup.current = L.layerGroup().addTo(map);

    return () => {
      cancelAnimationFrame(rafId.current);
      layerGroup.current?.clearLayers();
      layerGroup.current?.remove();
      animStates.current.clear();
    };
  }, [map]);

  // Click handler factory
  const makeClickHandler = useCallback(
    (trainId: number) => () => {
      onTrainSelect?.(trainId === selectedTrainId ? null : trainId);
    },
    [onTrainSelect, selectedTrainId],
  );

  // Update markers when positions change
  useEffect(() => {
    if (!layerGroup.current || !canvasRenderer.current) return;

    const group = layerGroup.current;
    const renderer = canvasRenderer.current;
    const states = animStates.current;
    const currentZoom = map.getZoom();

    // Build set of active train IDs
    const activeIds = new Set<number>();

    for (const pos of positions) {
      // Skip selected train — it's rendered as a rich DOM marker elsewhere
      if (pos.train_id === selectedTrainId) continue;

      activeIds.add(pos.train_id);

      const lat = pos.location.coordinates[1];
      const lon = pos.location.coordinates[0];
      const existing = states.get(pos.train_id);

      // Determine radius by zoom-dependent generalization
      const radius = currentZoom >= 10 ? 6 : currentZoom >= 8 ? 5 : 4;

      if (existing) {
        // Update existing marker — set new animation target
        existing.prevLat = existing.targetLat;
        existing.prevLon = existing.targetLon;
        existing.targetLat = lat;
        existing.targetLon = lon;
        existing.startTime = performance.now();

        // Update style
        existing.marker.setStyle({
          fillColor: getDelayColor(pos.delay_minutes),
          color: TYPE_COLORS[pos.train_type] || '#666',
          radius,
        });

        // Re-bind click handler (selectedTrainId may have changed)
        existing.marker.off('click');
        existing.marker.on('click', makeClickHandler(pos.train_id));
      } else {
        // Create new canvas-rendered circle marker
        const marker = L.circleMarker([lat, lon], {
          renderer,
          radius,
          fillColor: getDelayColor(pos.delay_minutes),
          fillOpacity: 0.9,
          color: TYPE_COLORS[pos.train_type] || '#666',
          weight: 2,
          interactive: true,
          bubblingMouseEvents: false,
        });

        marker.on('click', makeClickHandler(pos.train_id));

        // Tooltip with train number
        marker.bindTooltip(pos.train_number, {
          permanent: false,
          direction: 'top',
          offset: [0, -8],
          className: 'train-canvas-tooltip',
        });

        group.addLayer(marker);

        states.set(pos.train_id, {
          marker,
          prevLat: lat,
          prevLon: lon,
          targetLat: lat,
          targetLon: lon,
          startTime: performance.now(),
        });
      }
    }

    // Remove markers for trains no longer present
    Array.from(states.entries()).forEach(([id, state]) => {
      if (!activeIds.has(id)) {
        group.removeLayer(state.marker);
        states.delete(id);
      }
    });
    // No cleanup needed; markers persist across renders
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positions, selectedTrainId, map, makeClickHandler]);

  // requestAnimationFrame loop for smooth interpolation
  useEffect(() => {
    const states = animStates.current;

    function animate() {
      const now = performance.now();
      states.forEach((state) => {
        const t = Math.min((now - state.startTime) / ANIM_DURATION, 1);
        if (t < 1) {
          const lat = state.prevLat + (state.targetLat - state.prevLat) * t;
          const lon = state.prevLon + (state.targetLon - state.prevLon) * t;
          state.marker.setLatLng([lat, lon]);
        }
      });
      rafId.current = requestAnimationFrame(animate);
    }

    rafId.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafId.current);
  }, []);

  return null;
}
