'use client';

import { useEffect, useRef } from 'react';
import type { TrainPositionUpdate, TrainTrajectory, TrainType } from '@/types';
import { getVehicleTrajectoryState } from '@/lib/trajectory-interpolation';

interface CesiumTrainMapProps {
  positions: TrainPositionUpdate[];
  trajectories: Map<number, TrainTrajectory>;
  selectedTrainId?: number | null;
  onTrainSelect?: (id: number | null) => void;
  onViewportChange?: (bbox: string) => void;
}

interface CesiumEntityPack {
  locomotive: any;
  wagons: any[];
}

const TRAIN_CAR_COUNT = 10;
const LEAD_SPACING_METERS = 72;
const CAR_SPACING_METERS = 52;

const TYPE_COLORS: Partial<Record<TrainType, [number, number, number]>> = {
  special_express: [229, 57, 53],
  rapid: [30, 136, 229],
  ordinary: [67, 160, 71],
  local: [109, 76, 65],
};

function getColor(type: TrainType): [number, number, number] {
  return TYPE_COLORS[type] ?? [33, 150, 243];
}

function toRad(value: number) {
  return (value * Math.PI) / 180;
}

function haversineMeters(a: [number, number], b: [number, number]) {
  const [lon1, lat1] = a;
  const [lon2, lat2] = b;
  const R = 6371000;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const lat1r = toRad(lat1);
  const lat2r = toRad(lat2);
  const sinLat = Math.sin(dLat / 2);
  const sinLon = Math.sin(dLon / 2);
  const x =
    sinLat * sinLat + Math.cos(lat1r) * Math.cos(lat2r) * sinLon * sinLon;
  return 2 * R * Math.asin(Math.sqrt(x));
}

function lerpCoord(
  a: [number, number],
  b: [number, number],
  t: number
): [number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

function getPointAlongLine(
  coords: [number, number][],
  distanceFromStartMeters: number
): [number, number] {
  if (coords.length === 0) return [0, 0];
  if (coords.length === 1) return coords[0];

  let passed = 0;
  for (let i = 0; i < coords.length - 1; i += 1) {
    const start = coords[i];
    const end = coords[i + 1];
    const seg = haversineMeters(start, end);
    if (passed + seg >= distanceFromStartMeters) {
      const local = Math.max(0, distanceFromStartMeters - passed);
      const t = seg <= 0.01 ? 0 : local / seg;
      return lerpCoord(start, end, t);
    }
    passed += seg;
  }

  return coords[coords.length - 1];
}

function getPointBehindHead(
  coords: [number, number][],
  headFraction: number,
  behindMeters: number
): [number, number] {
  if (coords.length < 2) return coords[0] ?? [0, 0];
  const segments = coords
    .slice(0, -1)
    .map((_, i) => haversineMeters(coords[i], coords[i + 1]));
  const total = segments.reduce((sum, v) => sum + v, 0);
  if (total <= 0.01) return coords[0];

  const headMeters = Math.max(0, Math.min(1, headFraction)) * total;
  const wagonMeters = Math.max(0, headMeters - behindMeters);
  return getPointAlongLine(coords, wagonMeters);
}

async function ensureCesiumLoaded(): Promise<void> {
  if (typeof window === 'undefined') return;
  if ((window as any).Cesium) return;

  await new Promise<void>((resolve, reject) => {
    const cssId = 'cesium-widget-css';
    if (!document.getElementById(cssId)) {
      const link = document.createElement('link');
      link.id = cssId;
      link.rel = 'stylesheet';
      link.href =
        'https://cesium.com/downloads/cesiumjs/releases/1.122/Build/Cesium/Widgets/widgets.css';
      document.head.appendChild(link);
    }

    const script = document.createElement('script');
    script.src =
      'https://cesium.com/downloads/cesiumjs/releases/1.122/Build/Cesium/Cesium.js';
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Failed to load Cesium from CDN'));
    document.head.appendChild(script);
  });
}

export default function CesiumTrainMap({
  positions,
  trajectories,
  selectedTrainId,
  onTrainSelect,
  onViewportChange,
}: CesiumTrainMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<any>(null);
  const entitiesRef = useRef<Map<number, CesiumEntityPack>>(new Map());
  const rafRef = useRef<number>(0);

  useEffect(() => {
    let mounted = true;
    const entitiesStore = entitiesRef.current;

    const setup = async () => {
      await ensureCesiumLoaded();
      if (!mounted || !containerRef.current) return;

      const Cesium = (window as any).Cesium;
      const viewer = new Cesium.Viewer(containerRef.current, {
        animation: false,
        timeline: false,
        baseLayerPicker: true,
        sceneModePicker: false,
        geocoder: false,
        homeButton: false,
        fullscreenButton: false,
        infoBox: false,
        selectionIndicator: false,
        shouldAnimate: true,
      });

      viewer.scene.globe.depthTestAgainstTerrain = false;
      viewer.scene.screenSpaceCameraController.minimumZoomDistance = 700;
      viewer.scene.camera.setView({
        destination: Cesium.Cartesian3.fromDegrees(100.99, 15.87, 1_700_000),
        orientation: {
          heading: Cesium.Math.toRadians(0),
          pitch: Cesium.Math.toRadians(-50),
          roll: 0,
        },
      });

      const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
      handler.setInputAction((movement: any) => {
        const picked = viewer.scene.pick(movement.position);
        const trainId = picked?.id?.properties?.trainId?.getValue?.();
        if (typeof trainId === 'number') {
          onTrainSelect?.(trainId === selectedTrainId ? null : trainId);
        }
      }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

      const emitBbox = () => {
        try {
          const rect = viewer.camera.computeViewRectangle();
          if (!rect) return;
          const west = Cesium.Math.toDegrees(rect.west);
          const south = Cesium.Math.toDegrees(rect.south);
          const east = Cesium.Math.toDegrees(rect.east);
          const north = Cesium.Math.toDegrees(rect.north);
          onViewportChange?.(
            `${west.toFixed(4)},${south.toFixed(4)},${east.toFixed(4)},${north.toFixed(4)}`
          );
        } catch {
          // ignore camera edge cases during first frames
        }
      };

      viewer.camera.moveEnd.addEventListener(emitBbox);
      viewerRef.current = viewer;

      const animate = () => {
        rafRef.current = requestAnimationFrame(animate);
        const now = Date.now();
        const activeIds = new Set<number>();

        for (const pos of positions) {
          const traj = trajectories.get(pos.train_id);
          if (!traj) continue;
          const state = getVehicleTrajectoryState(now, traj);
          if (!state) continue;

          activeIds.add(pos.train_id);
          const CesiumLocal = (window as any).Cesium;
          const color = getColor(pos.train_type as TrainType);

          let pack = entitiesStore.get(pos.train_id);
          if (!pack) {
            const loco = viewer.entities.add({
              id: `train-${pos.train_id}`,
              position: CesiumLocal.Cartesian3.fromDegrees(
                state.lon,
                state.lat,
                20
              ),
              point: {
                pixelSize: 12,
                color: CesiumLocal.Color.fromBytes(
                  color[0],
                  color[1],
                  color[2],
                  255
                ),
                outlineWidth: 2,
                outlineColor: CesiumLocal.Color.WHITE,
                disableDepthTestDistance: Number.POSITIVE_INFINITY,
                scaleByDistance: undefined,
              },
              properties: { trainId: pos.train_id },
            });

            const wagons = Array.from({ length: TRAIN_CAR_COUNT }, (_, idx) =>
              viewer.entities.add({
                id: `train-${pos.train_id}-wagon-${idx}`,
                position: CesiumLocal.Cartesian3.fromDegrees(
                  state.lon,
                  state.lat,
                  18
                ),
                point: {
                  pixelSize: 8,
                  color: CesiumLocal.Color.fromBytes(
                    color[0],
                    color[1],
                    color[2],
                    215
                  ),
                  outlineWidth: 1,
                  outlineColor: CesiumLocal.Color.WHITE,
                  disableDepthTestDistance: Number.POSITIVE_INFINITY,
                  scaleByDistance: undefined,
                },
                properties: { trainId: pos.train_id },
              })
            );
            pack = { locomotive: loco, wagons };
            entitiesStore.set(pos.train_id, pack);
          }

          pack.locomotive.position = CesiumLocal.Cartesian3.fromDegrees(
            state.lon,
            state.lat,
            20
          );

          const coords = traj.geometry.coordinates as [number, number][];
          for (let car = 0; car < TRAIN_CAR_COUNT; car += 1) {
            const distance = LEAD_SPACING_METERS + car * CAR_SPACING_METERS;
            const [lon, lat] = getPointBehindHead(
              coords,
              state.geomFraction,
              distance
            );
            pack.wagons[car].position = CesiumLocal.Cartesian3.fromDegrees(
              lon,
              lat,
              18
            );
          }
        }

        for (const [trainId, pack] of entitiesStore.entries()) {
          if (activeIds.has(trainId)) continue;
          viewer.entities.remove(pack.locomotive);
          pack.wagons.forEach((wagon) => viewer.entities.remove(wagon));
          entitiesStore.delete(trainId);
        }
      };

      rafRef.current = requestAnimationFrame(animate);

      return () => {
        cancelAnimationFrame(rafRef.current);
        viewer.camera.moveEnd.removeEventListener(emitBbox);
        handler.destroy();
      };
    };

    let cleanup: (() => void) | undefined;
    setup().then((maybeCleanup) => {
      cleanup = maybeCleanup;
    });

    return () => {
      mounted = false;
      cleanup?.();
      cancelAnimationFrame(rafRef.current);
      if (viewerRef.current) {
        viewerRef.current.destroy();
        viewerRef.current = null;
      }
      entitiesStore.clear();
    };
  }, [
    onTrainSelect,
    onViewportChange,
    positions,
    selectedTrainId,
    trajectories,
  ]);

  return <div ref={containerRef} className="h-full w-full" />;
}
