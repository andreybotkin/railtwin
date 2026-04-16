import type { GeoJSONSource, Map as MaplibreMap } from 'maplibre-gl';
import { useEffect } from 'react';

import { buildConsistGeoPoints } from '@/lib/wagon-placement';
import { getTrajectoryFrameAt } from '@/lib/trajectory-interpolation';
import { useRailwayStore } from '@/lib/stores/useRailwayStore';

export function useRafVehicleTicker(map: MaplibreMap | null) {
  const trajectories = useRailwayStore((s) => s.trajectories);
  const selectedTrainId = useRailwayStore((s) => s.selectedTrainId);

  useEffect(() => {
    if (!map) return;
    let raf = 0;

    const tick = () => {
      const source = map.getSource('vehicles') as GeoJSONSource | undefined;
      if (!source) {
        raf = requestAnimationFrame(tick);
        return;
      }

      const features: Array<Record<string, unknown>> = [];
      const now = Date.now();

      trajectories.forEach((trajectory) => {
        const frame = getTrajectoryFrameAt(now, trajectory);
        if (!frame) return;
        const headDistanceM = frame.geom_fraction * trajectory.route_length_m;
        const bodies = buildConsistGeoPoints(trajectory.route_coords as [number, number][], headDistanceM, trajectory.consist);
        bodies.forEach((body) => {
          features.push({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [body.lon, body.lat] },
            properties: {
              train_id: trajectory.train_id,
              body_type: body.body_type,
              body_index: body.body_index,
              rotation: body.rotation,
              is_selected: trajectory.train_id === selectedTrainId,
            },
          });
        });
      });

      source.setData({ type: 'FeatureCollection', features });
      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [map, trajectories, selectedTrainId]);
}
