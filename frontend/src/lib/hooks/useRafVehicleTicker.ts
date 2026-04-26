/**
 * requestAnimationFrame ticker that renders live vehicles onto the MapLibre
 * `vehicles` source. On every frame we:
 *
 *   1. Pick up the latest trajectory dictionary from the Zustand store.
 *   2. For each trajectory, interpolate the head frame at `Date.now()`.
 *   3. Spread the consist along the polyline with `buildConsistGeoPoints`.
 *   4. Flatten everything into a single `FeatureCollection` and push it via
 *      `map.getSource('vehicles').setData(fc)` — MapLibre diffs the buffer
 *      internally, so we can happily rebuild the FC from scratch each frame.
 */

import { useEffect } from 'react';
import type { MapRef } from 'react-map-gl/maplibre';
import type { GeoJSONSource } from 'maplibre-gl';

import type { FeatureCollection, Feature, Point } from 'geojson';

import { getTrajectoryFrameAt, isTrajectoryValid } from '@/lib/trajectory-interpolation';
import { buildConsistGeoPoints } from '@/lib/wagon-placement';
import { useRailwayStore } from '@/lib/stores/railway-store';

export const VEHICLE_SOURCE_ID = 'vehicles';

export interface VehicleFeatureProps {
  train_id: number;
  body_kind: 'locomotive' | 'carriage';
  body_index: number;
  rotation: number;
  /**
   * 'left'  — body bearing ∈ [180°, 360°), use horizontally-mirrored icon.
   * 'right' — body bearing ∈ [0°,   180°), use standard east-facing icon.
   */
  facing: 'left' | 'right';
  speed_kmh: number;
  status: string;
  color: string;
  train_number: string;
  train_type: string;
  is_selected: boolean;
  length_m: number;
}

function buildFeatureCollection(
  trajectories: Map<number, import('@/types').Trajectory>,
  selectedTrainId: number | null,
  nowMs: number,
): FeatureCollection<Point, VehicleFeatureProps> {
  const features: Feature<Point, VehicleFeatureProps>[] = [];

  trajectories.forEach((trajectory) => {
    if (!isTrajectoryValid(trajectory, nowMs)) return;

    const frame = getTrajectoryFrameAt(nowMs, trajectory);
    if (!frame) return;

    const placements = buildConsistGeoPoints(
      trajectory.route_coords,
      frame.headDistanceM,
      trajectory.consist,
      frame.travelForward,
    );

    for (const body of placements) {
      features.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [body.lon, body.lat] },
        properties: {
          train_id: trajectory.train_id,
          body_kind: body.kind,
          body_index: body.index,
          rotation: body.rotationDeg,
          facing: body.facingLeft ? 'left' : 'right',
          speed_kmh: frame.speedKmh,
          status: frame.status,
          color: trajectory.meta.color,
          train_number: trajectory.meta.train_number,
          train_type: trajectory.meta.train_type as string,
          is_selected: selectedTrainId === trajectory.train_id,
          length_m: body.lengthM,
        },
      });
    }
  });

  return { type: 'FeatureCollection', features };
}

export function useRafVehicleTicker(mapRef: React.RefObject<MapRef | null>): void {
  useEffect(() => {
    let frameId: number | null = null;
    let cancelled = false;

    const tick = () => {
      if (cancelled) return;

      const map = mapRef.current?.getMap();
      const source = map?.getSource(VEHICLE_SOURCE_ID) as
        | GeoJSONSource
        | undefined;

      if (source) {
        const { trajectories, selectedTrainId } = useRailwayStore.getState();
        const fc = buildFeatureCollection(
          trajectories,
          selectedTrainId,
          Date.now(),
        );
        source.setData(fc);
      }

      frameId = window.requestAnimationFrame(tick);
    };

    frameId = window.requestAnimationFrame(tick);

    return () => {
      cancelled = true;
      if (frameId !== null) window.cancelAnimationFrame(frameId);
    };
  }, [mapRef]);
}
