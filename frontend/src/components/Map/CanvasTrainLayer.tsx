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

interface AnimState {
  prevLat: number;
  prevLon: number;
  targetLat: number;
  targetLon: number;
  startTime: number;
}

interface ConsistRenderState {
  wagons: ConsistPhysicsNode[];
  lastPerfMs: number;
}

const ANIM_DURATION = 1900;
const TRAIN_CAR_COUNT = 10;
const DISPLAY_ROTATION_OFFSET_DEG = -90;
const LOCO_WIDTH = 28;
const LOCO_HEIGHT = 14;
const WAGON_WIDTH = 14;
const WAGON_HEIGHT = 8;
const LEAD_SPACING = 18;
const CAR_SPACING = 12;

function getDelayColor(delayMinutes: number): string {
  if (delayMinutes <= 0) return DELAY_COLORS.onTime;
  if (delayMinutes <= 5) return DELAY_COLORS.slight;
  if (delayMinutes <= 15) return DELAY_COLORS.moderate;
  return DELAY_COLORS.severe;
}

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

interface CanvasTrainLayerProps {
  positions: TrainPositionUpdate[];
  trajectories?: Map<number, TrainTrajectory>;
  selectedTrainId?: number | null;
  onTrainSelect?: (id: number | null) => void;
  minZoom?: number;
}

export default function CanvasTrainLayer({
  positions,
  trajectories,
  selectedTrainId,
  onTrainSelect,
  minZoom = 5,
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
      } else {
        states.set(pos.train_id, {
          prevLat: lat,
          prevLon: lon,
          targetLat: lat,
          targetLon: lon,
          startTime: performance.now(),
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

    const HIT_RADIUS_PX = 14;
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
        const dx = pixel.x - point.x;
        const dy = pixel.y - point.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < closestDist) {
          closestDist = dist;
          closest = p.train_id;
        }
      }

      if (closest !== null)
        onSelectRef.current?.(closest === selId ? null : closest);
    };
    map.on('click', onMapClick);

    const draw = () => {
      rafIdRef.current = requestAnimationFrame(draw);
      if (document.hidden) return;

      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      if (map.getZoom() < minZoom) return;

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
              (_, index) => LEAD_SPACING + index * CAR_SPACING
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
            const spacing = LEAD_SPACING + car * CAR_SPACING;
            return {
              x: Math.cos(radians + Math.PI) * spacing,
              y: Math.sin(radians + Math.PI) * spacing,
              rotation,
            };
          });
        }

        const pixel = map.latLngToContainerPoint([lat, lon]);
        const px = pixel.x;
        const py = pixel.y;
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
        if (!consistState) {
          consistState = {
            wagons: consistTargets.map((target) => ({
              x: px + target.x,
              y: py + target.y,
              prevX: px + target.x,
              prevY: py + target.y,
            })),
            lastPerfMs: nowPerf,
          };
          consistStateRef.current.set(pos.train_id, consistState);
        }

        const dt = (nowPerf - consistState.lastPerfMs) / 1000;
        consistState.lastPerfMs = nowPerf;

        const targets = consistTargets.map((target) => ({
          x: target.x + pixel.x,
          y: target.y + pixel.y,
          rotation: target.rotation,
        }));
        const solvedWagons = solveConsistPhysics(
          consistState.wagons,
          { x: px, y: py },
          targets,
          CAR_SPACING,
          dt
        );

        for (let car = solvedWagons.length - 1; car >= 0; car -= 1) {
          const wagon = solvedWagons[car];
          drawTrainCar(
            ctx,
            wagon.x,
            wagon.y,
            WAGON_WIDTH,
            WAGON_HEIGHT,
            baseColor,
            wagon.rotation,
            'rgba(255,255,255,0.8)'
          );
        }

        drawTrainCar(
          ctx,
          px,
          py,
          LOCO_WIDTH,
          LOCO_HEIGHT,
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
  }, [map, minZoom]);

  return null;
}
