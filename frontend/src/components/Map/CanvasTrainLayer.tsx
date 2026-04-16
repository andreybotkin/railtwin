/**
 * High-performance canvas train layer with articulated consist physics.
 *
 * Modern rendering approach:
 * - Single WebGL-friendly Canvas 2D pass for all trains at every zoom level.
 * - Each train is a connected articulated chain (locomotive + wagons).
 * - Wagons are solved via position-based dynamics (Verlet + constraints),
 *   creating natural "follow the locomotive" behaviour on curves.
 * - Geometry-aware targeting keeps the consist pinned to trajectory rails,
 *   while physics adds smooth inertial lag.
 */

'use client';

import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import type { TrainPositionUpdate, TrainTrajectory, TrainType } from '@/types';
import {
  getVehiclePosition,
  getVehicleTrajectoryState,
} from '@/lib/trajectory-interpolation';
import {
  buildConsistScreenPoints,
  solveConsistPhysics,
  type ConsistPhysicsNode,
} from '@/lib/train-consist';

const DELAY_COLORS = {
  onTime: '#43A047',
  slight: '#FDD835',
  moderate: '#FB8C00',
  severe: '#E53935',
} as const;

const TYPE_COLORS: Partial<Record<TrainType, string>> = {
  special_express: '#E53935',
  rapid: '#1E88E5',
  ordinary: '#43A047',
  local: '#6d4c41',
};

function drawRoundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number
) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + width - radius, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
  ctx.lineTo(x + width, y + height - radius);
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  ctx.lineTo(x + radius, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
}

function getDelayColor(delayMinutes: number): string {
  if (delayMinutes <= 0) return DELAY_COLORS.onTime;
  if (delayMinutes <= 5) return DELAY_COLORS.slight;
  if (delayMinutes <= 15) return DELAY_COLORS.moderate;
  return DELAY_COLORS.severe;
}

interface AnimState {
  prevLat: number;
  prevLon: number;
  targetLat: number;
  targetLon: number;
  startTime: number;
  delayMinutes: number;
  trainType: TrainType;
}

interface ConsistRenderState {
  wagons: ConsistPhysicsNode[];
  lastPerfMs: number;
  lastSpacingPx: number;
}

const ANIM_DURATION = 1900;
const TRAIN_CAR_COUNT = 10;
const DISPLAY_ROTATION_OFFSET_DEG = -90;

function zoomScale(zoom: number): number {
  return Math.min(2.2, Math.max(0.45, 0.52 * Math.pow(1.22, zoom - 8)));
}

function drawTrainCar(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  color: string,
  rotation: number,
  outlineColor: string,
  withHeadlight = false
) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate((rotation + DISPLAY_ROTATION_OFFSET_DEG) * (Math.PI / 180));
  drawRoundedRect(
    ctx,
    -width / 2,
    -height / 2,
    width,
    height,
    Math.min(6, height / 2)
  );
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = outlineColor;
  ctx.lineWidth = 1.5;
  ctx.stroke();

  if (withHeadlight) {
    ctx.beginPath();
    ctx.arc(width / 2 - 3, 0, 2, 0, Math.PI * 2);
    ctx.fillStyle = '#fff5bf';
    ctx.fill();
  }

  ctx.restore();
}

function projectPoint(
  x: number,
  y: number,
  canvasHeight: number,
  is3D: boolean
): { x: number; y: number; depth: number } {
  if (!is3D) return { x, y, depth: 0 };
  const horizon = canvasHeight * 0.18;
  const relY = Math.max(0, y - horizon);
  const pitchCos = Math.cos((55 * Math.PI) / 180);
  const pitchedY = horizon + relY * pitchCos;
  const skewX = x + relY * 0.035;
  const depth = Math.min(10, 2 + relY * 0.006);
  return { x: skewX, y: pitchedY, depth };
}

interface CanvasTrainLayerProps {
  positions: TrainPositionUpdate[];
  trajectories?: Map<number, TrainTrajectory>;
  selectedTrainId?: number | null;
  onTrainSelect?: (id: number | null) => void;
  minZoom?: number;
  is3D?: boolean;
}

export default function CanvasTrainLayer({
  positions,
  trajectories,
  selectedTrainId,
  onTrainSelect,
  minZoom = 5,
  is3D = false,
}: CanvasTrainLayerProps) {
  const map = useMap();

  const positionsRef = useRef<TrainPositionUpdate[]>(positions);
  const trajectoriesRef = useRef<Map<number, TrainTrajectory>>(
    trajectories ?? new Map()
  );
  const selectedIdRef = useRef<number | null>(selectedTrainId ?? null);
  const onSelectRef = useRef<((id: number | null) => void) | undefined>(
    onTrainSelect
  );
  const animStatesRef = useRef<Map<number, AnimState>>(new Map());
  const consistStateRef = useRef<Map<number, ConsistRenderState>>(new Map());
  const rafIdRef = useRef<number>(0);

  useEffect(() => {
    positionsRef.current = positions;
  }, [positions]);
  useEffect(() => {
    trajectoriesRef.current = trajectories ?? new Map();
  }, [trajectories]);
  useEffect(() => {
    selectedIdRef.current = selectedTrainId ?? null;
  }, [selectedTrainId]);
  useEffect(() => {
    onSelectRef.current = onTrainSelect;
  }, [onTrainSelect]);

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
          prevLat: lat,
          prevLon: lon,
          targetLat: lat,
          targetLon: lon,
          startTime: performance.now(),
          delayMinutes: pos.delay_minutes,
          trainType: pos.train_type,
        });
      }
    }

    for (const id of states.keys()) {
      if (!activeIds.has(id)) states.delete(id);
    }

    for (const id of consistStateRef.current.keys()) {
      if (!activeIds.has(id)) consistStateRef.current.delete(id);
    }
  }, [positions, selectedTrainId]);

  useEffect(() => {
    const container = map.getContainer();

    const canvas = document.createElement('canvas');
    canvas.style.cssText =
      'position:absolute;top:0;left:0;pointer-events:none;z-index:450;';
    canvas.setAttribute('aria-hidden', 'true');
    container.appendChild(canvas);

    const resizeCanvas = () => {
      const size = map.getSize();
      canvas.width = size.x;
      canvas.height = size.y;
    };

    resizeCanvas();
    map.on('resize', resizeCanvas);

    const HIT_RADIUS_PX = 16;
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
        let lat: number;
        let lon: number;
        const traj = trajs.get(p.train_id);

        if (traj) {
          const vp = getVehiclePosition(nowMs, traj);
          if (!vp) continue;
          lat = vp.lat;
          lon = vp.lon;
        } else {
          const state = animStatesRef.current.get(p.train_id);
          if (!state) continue;
          const t = Math.min((nowPerf - state.startTime) / ANIM_DURATION, 1);
          lat = state.prevLat + (state.targetLat - state.prevLat) * t;
          lon = state.prevLon + (state.targetLon - state.prevLon) * t;
        }

        const pixel = map.latLngToContainerPoint([lat, lon]);
        const projected = projectPoint(pixel.x, pixel.y, canvas.height, is3D);
        const dx = projected.x - point.x;
        const dy = projected.y - point.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < closestDist) {
          closestDist = dist;
          closest = p.train_id;
        }
      }

      if (closest !== null) {
        onSelectRef.current?.(closest === selId ? null : closest);
      }
    };

    map.on('click', onMapClick);

    const draw = () => {
      rafIdRef.current = requestAnimationFrame(draw);
      if (document.hidden) return;

      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const zoom = map.getZoom();
      if (zoom < minZoom) return;

      const scale = zoomScale(zoom);
      const locomotiveWidth = 28 * scale;
      const locomotiveHeight = 14 * scale;
      const wagonWidth = 14 * scale;
      const wagonHeight = 8 * scale;
      const leadSpacing = 18 * scale;
      const carSpacing = 12 * scale;

      const trajs = trajectoriesRef.current;
      const currentPositions = positionsRef.current;
      const selId = selectedIdRef.current;
      const animStates = animStatesRef.current;
      const nowMs = Date.now();
      const nowPerf = performance.now();

      for (const pos of currentPositions) {
        if (pos.train_id === selId) continue;

        let lat: number;
        let lon: number;
        let rotation: number;
        let consistTargets: { x: number; y: number; rotation: number }[] = [];

        const traj = trajs.get(pos.train_id);
        const locomotiveState = traj
          ? getVehicleTrajectoryState(nowMs, traj)
          : null;

        if (traj && locomotiveState) {
          lat = locomotiveState.lat;
          lon = locomotiveState.lon;
          rotation = locomotiveState.rotation;

          consistTargets = buildConsistScreenPoints(
            (traj.geometry.coordinates as [number, number][])
              .map(([coordLon, coordLat]) =>
                map.latLngToContainerPoint([coordLat, coordLon])
              )
              .map((point) => ({ x: point.x, y: point.y })),
            locomotiveState.geomFraction,
            locomotiveState.rotation,
            Array.from(
              { length: TRAIN_CAR_COUNT },
              (_, index) => leadSpacing + index * carSpacing
            )
          );
        } else {
          const state = animStates.get(pos.train_id);
          if (!state) continue;
          const t = Math.min((nowPerf - state.startTime) / ANIM_DURATION, 1);
          lat = state.prevLat + (state.targetLat - state.prevLat) * t;
          lon = state.prevLon + (state.targetLon - state.prevLon) * t;
          rotation = pos.heading ?? 0;

          const radians =
            ((rotation + DISPLAY_ROTATION_OFFSET_DEG) * Math.PI) / 180;
          consistTargets = Array.from({ length: TRAIN_CAR_COUNT }, (_, car) => {
            const spacing = leadSpacing + car * carSpacing;
            return {
              x: 0 + Math.cos(radians + Math.PI) * spacing,
              y: 0 + Math.sin(radians + Math.PI) * spacing,
              rotation,
            };
          });
        }

        const pixel = map.latLngToContainerPoint([lat, lon]);
        const projectedHead = projectPoint(
          pixel.x,
          pixel.y,
          canvas.height,
          is3D
        );
        const px = projectedHead.x;
        const py = projectedHead.y;

        if (
          px < -80 ||
          px > canvas.width + 80 ||
          py < -80 ||
          py > canvas.height + 80
        )
          continue;

        const delayColor = getDelayColor(pos.delay_minutes);
        const baseColor = TYPE_COLORS[pos.train_type as TrainType] ?? '#2196F3';

        let consistState = consistStateRef.current.get(pos.train_id);
        if (
          !consistState ||
          Math.abs(consistState.lastSpacingPx - carSpacing) > 2.5
        ) {
          consistState = {
            wagons: consistTargets.map((target) => ({
              x: px + target.x,
              y: py + target.y,
              prevX: px + target.x,
              prevY: py + target.y,
            })),
            lastPerfMs: nowPerf,
            lastSpacingPx: carSpacing,
          };
          consistStateRef.current.set(pos.train_id, consistState);
        }

        const dt = (nowPerf - consistState.lastPerfMs) / 1000;
        consistState.lastPerfMs = nowPerf;

        const targets = consistTargets.map((target) => ({
          ...projectPoint(
            target.x + pixel.x,
            target.y + pixel.y,
            canvas.height,
            is3D
          ),
          rotation: target.rotation,
        }));

        const solvedWagons = solveConsistPhysics(
          consistState.wagons,
          { x: px, y: py },
          targets,
          carSpacing,
          dt
        );

        for (let car = solvedWagons.length - 1; car >= 0; car -= 1) {
          const wagon = solvedWagons[car];
          const alpha = Math.max(0.48, 0.94 - car * 0.04);
          drawTrainCar(
            ctx,
            wagon.x,
            wagon.y + projectedHead.depth,
            wagonWidth,
            wagonHeight,
            baseColor,
            wagon.rotation,
            `rgba(255,255,255,${Math.min(alpha + 0.1, 0.9)})`
          );
        }

        if (is3D) {
          ctx.beginPath();
          ctx.ellipse(
            px + projectedHead.depth * 0.6,
            py + locomotiveHeight * 0.75 + projectedHead.depth,
            locomotiveWidth * 0.7,
            locomotiveHeight * 0.38,
            0,
            0,
            Math.PI * 2
          );
          ctx.fillStyle = 'rgba(15,23,42,0.22)';
          ctx.fill();
        }

        drawTrainCar(
          ctx,
          px,
          py + projectedHead.depth,
          locomotiveWidth,
          locomotiveHeight,
          baseColor,
          rotation,
          delayColor,
          true
        );
      }
    };

    rafIdRef.current = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(rafIdRef.current);
      map.off('resize', resizeCanvas);
      map.off('click', onMapClick);
      canvas.remove();
    };
  }, [is3D, map, minZoom]);

  return null;
}
