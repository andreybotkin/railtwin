/**
 * High-performance canvas train layer with geops-style trajectory interpolation.
 *
 * Inspired by geops/mobility-toolbox-js renderTrajectories / TrackerLayer:
 * - Single HTML Canvas element over the map (no DOM per train — scales to 1000+)
 * - If trajectory data available: uses `getVehiclePosition(Date.now(), trajectory)` for
 *   truly smooth 60fps animation — position computable at any moment without polling.
 * - Heading arrow drawn with ctx.save()/rotate()/restore() just like geops renderTrajectories.
 * - Graceful fallback to prev→target interpolation when only positions are available.
 * - Visibility API: skips drawing when the tab is hidden.
 * - Click detection on canvas-drawn trains via map click event (pointer-events: none on canvas).
 *
 * @see https://github.com/geops/mobility-toolbox-js/blob/master/src/common/utils/renderTrajectories.ts
 */

'use client';

import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import type { TrainPositionUpdate, TrainTrajectory, TrainType } from '@/types';
import { getVehiclePosition } from '@/lib/trajectory-interpolation';

// ---------------------------------------------------------------------------
// Color helpers
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Fallback animation state for trains without trajectories
// ---------------------------------------------------------------------------

interface AnimState {
  prevLat: number;
  prevLon: number;
  targetLat: number;
  targetLon: number;
  startTime: number;
  delayMinutes: number;
  trainType: TrainType;
}

/** Matches WS poll interval so fallback animation fills the gap between updates. */
const ANIM_DURATION = 1900;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface CanvasTrainLayerProps {
  positions: TrainPositionUpdate[];
  /** geops-style trajectory map from TrajectoryWebSocketClient. */
  trajectories?: Map<number, TrainTrajectory>;
  selectedTrainId?: number | null;
  onTrainSelect?: (id: number | null) => void;
  /** Minimum zoom level at which train markers are shown. */
  minZoom?: number;
}

/**
 * Canvas-based train layer rendering all non-selected trains.
 *
 * Draws directly to a single HTMLCanvasElement at 60fps using `getVehiclePosition()`
 * when trajectory data is available, or interpolates prev→target position as fallback.
 * Each train gets a circle + directional arrowhead when heading is known.
 */
export default function CanvasTrainLayer({
  positions,
  trajectories,
  selectedTrainId,
  onTrainSelect,
  minZoom = 5,
}: CanvasTrainLayerProps) {
  const map = useMap();

  // Mutable refs so the rAF loop always reads current values
  const positionsRef = useRef<TrainPositionUpdate[]>(positions);
  const trajectoriesRef = useRef<Map<number, TrainTrajectory>>(trajectories ?? new Map());
  const selectedIdRef = useRef<number | null>(selectedTrainId ?? null);
  const onSelectRef = useRef<((id: number | null) => void) | undefined>(onTrainSelect);
  const animStatesRef = useRef<Map<number, AnimState>>(new Map());
  const rafIdRef = useRef<number>(0);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Keep refs in sync with props
  useEffect(() => { positionsRef.current = positions; }, [positions]);
  useEffect(() => { trajectoriesRef.current = trajectories ?? new Map(); }, [trajectories]);
  useEffect(() => { selectedIdRef.current = selectedTrainId ?? null; }, [selectedTrainId]);
  useEffect(() => { onSelectRef.current = onTrainSelect; }, [onTrainSelect]);

  // Update fallback animation states when positions change
  useEffect(() => {
    const states = animStatesRef.current;
    const activeIds = new Set<number>();

    for (const pos of positions) {
      if (pos.train_id === selectedTrainId) continue;
      activeIds.add(pos.train_id);

      const lat = pos.location.coordinates[1];
      const lon = pos.location.coordinates[0];
      const existing = states.get(pos.train_id);

      if (existing) {
        existing.prevLat = existing.targetLat;
        existing.prevLon = existing.targetLon;
        existing.targetLat = lat;
        existing.targetLon = lon;
        existing.startTime = performance.now();
        existing.delayMinutes = pos.delay_minutes;
        existing.trainType = pos.train_type;
      } else {
        states.set(pos.train_id, {
          prevLat: lat, prevLon: lon,
          targetLat: lat, targetLon: lon,
          startTime: performance.now(),
          delayMinutes: pos.delay_minutes,
          trainType: pos.train_type,
        });
      }
    }

    for (const id of states.keys()) {
      if (!activeIds.has(id)) states.delete(id);
    }
  }, [positions, selectedTrainId]);

  // Mount: create canvas, rAF loop, click handler
  useEffect(() => {
    const container = map.getContainer();

    // Canvas floating above the map, pointer-events:none so map interactions still work
    const canvas = document.createElement('canvas');
    canvas.style.cssText =
      'position:absolute;top:0;left:0;pointer-events:none;z-index:450;';
    canvas.setAttribute('aria-hidden', 'true');
    container.appendChild(canvas);
    canvasRef.current = canvas;

    const resizeCanvas = () => {
      const size = map.getSize();
      canvas.width = size.x;
      canvas.height = size.y;
    };
    resizeCanvas();
    map.on('resize', resizeCanvas);

    // Click detection: find train closest to click point within HIT_RADIUS pixels
    const HIT_RADIUS_PX = 12;
    const onMapClick = (e: L.LeafletMouseEvent) => {
      const point = e.containerPoint;
      const trajs = trajectoriesRef.current;
      const pos = positionsRef.current;
      const selId = selectedIdRef.current;
      const nowMs = Date.now();
      const nowPerf = performance.now();

      let closest: number | null = null;
      let closestDist = HIT_RADIUS_PX;

      for (const p of pos) {
        if (p.train_id === selId) continue;
        let lat: number, lon: number;
        const traj = trajs.get(p.train_id);
        if (traj) {
          const vp = getVehiclePosition(nowMs, traj);
          if (!vp) continue;
          lat = vp.lat; lon = vp.lon;
        } else {
          const state = animStatesRef.current.get(p.train_id);
          if (!state) continue;
          const t = Math.min((nowPerf - state.startTime) / ANIM_DURATION, 1);
          lat = state.prevLat + (state.targetLat - state.prevLat) * t;
          lon = state.prevLon + (state.targetLon - state.prevLon) * t;
        }
        const pixel = map.latLngToContainerPoint([lat, lon]);
        const dx = pixel.x - point.x;
        const dy = pixel.y - point.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < closestDist) { closestDist = dist; closest = p.train_id; }
      }

      if (closest !== null) {
        onSelectRef.current?.(closest === selId ? null : closest);
      }
    };
    map.on('click', onMapClick);

    // rAF draw loop: runs at 60fps, reads current refs each frame
    const draw = () => {
      rafIdRef.current = requestAnimationFrame(draw);

      // Skip drawing when tab is hidden (Visibility API — geops RealtimeEngine pattern)
      if (document.hidden) return;

      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const zoom = map.getZoom();
      if (zoom < minZoom) return;

      const trajs = trajectoriesRef.current;
      const positions = positionsRef.current;
      const selId = selectedIdRef.current;
      const animStates = animStatesRef.current;
      const nowMs = Date.now();
      const nowPerf = performance.now();

      // Radius scales with zoom for zoom-adaptive detail (generalization)
      const radius = zoom >= 11 ? 7 : zoom >= 9 ? 6 : zoom >= 7 ? 5 : 4;
      const showArrow = zoom >= 8;

      for (const pos of positions) {
        if (pos.train_id === selId) continue;

        let lat: number;
        let lon: number;
        let rotation: number | null = null;
        const traj = trajs.get(pos.train_id);

        if (traj) {
          // geops time-based interpolation — position from time_intervals at current clock
          const vp = getVehiclePosition(nowMs, traj);
          if (!vp) continue;
          lat = vp.lat;
          lon = vp.lon;
          rotation = vp.rotation;
        } else {
          // Fallback: prev→target linear interpolation (old snapshot approach)
          const state = animStates.get(pos.train_id);
          if (!state) continue;
          const t = Math.min((nowPerf - state.startTime) / ANIM_DURATION, 1);
          lat = state.prevLat + (state.targetLat - state.prevLat) * t;
          lon = state.prevLon + (state.targetLon - state.prevLon) * t;
        }

        // Project to screen coordinates (containerPoint)
        const pixel = map.latLngToContainerPoint([lat, lon]);
        const px = pixel.x;
        const py = pixel.y;

        // Skip trains outside the visible canvas (quick cull)
        if (px < -radius - 10 || px > canvas.width + radius + 10) continue;
        if (py < -radius - 10 || py > canvas.height + radius + 10) continue;

        const fillColor = getDelayColor(pos.delay_minutes);
        const strokeColor = TYPE_COLORS[pos.train_type as TrainType] ?? '#2196F3';

        ctx.save();
        ctx.translate(px, py);

        // Heading arrowhead (geops renderTrajectories pattern)
        // Convert heading (0=N, clockwise) to canvas angle (0=E, clockwise)
        if (showArrow && rotation !== null) {
          const canvasAngle = (rotation - 90) * (Math.PI / 180);
          ctx.rotate(canvasAngle);
          ctx.beginPath();
          // Triangle pointing in +x direction (after rotation)
          ctx.moveTo(radius + 7, 0);
          ctx.lineTo(radius + 1, -3.5);
          ctx.lineTo(radius + 1, 3.5);
          ctx.closePath();
          ctx.fillStyle = strokeColor;
          ctx.fill();
          ctx.rotate(-canvasAngle);
        }

        // Circle body
        ctx.beginPath();
        ctx.arc(0, 0, radius, 0, Math.PI * 2);
        ctx.fillStyle = fillColor;
        ctx.fill();
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.restore();
      }
    };

    rafIdRef.current = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(rafIdRef.current);
      map.off('resize', resizeCanvas);
      map.off('click', onMapClick);
      canvas.remove();
      canvasRef.current = null;
    };
  }, [map, minZoom]);

  return null;
}

