import bearing from '@turf/bearing';
import { lineString, point } from '@turf/helpers';
import lineSliceAlong from '@turf/line-slice-along';

import type { ConsistSpec } from './trajectory-interpolation';

export interface ConsistPoint {
  lon: number;
  lat: number;
  rotation: number;
  body_index: number;
  body_type: 'locomotive' | 'carriage';
}

function pointAlong(routeCoords: [number, number][], distanceM: number): [number, number] {
  const route = lineString(routeCoords);
  const seg = lineSliceAlong(route, Math.max(0, distanceM - 1) / 1000, Math.max(0, distanceM) / 1000, {
    units: 'kilometers',
  });
  const coords = seg.geometry.coordinates;
  return (coords[coords.length - 1] as [number, number]) ?? routeCoords[0];
}

export function buildConsistGeoPoints(
  polyline: [number, number][],
  headDistanceM: number,
  consist: ConsistSpec,
): ConsistPoint[] {
  if (polyline.length < 2) return [];

  const points: ConsistPoint[] = [];
  const offsets: Array<{ offset: number; type: 'locomotive' | 'carriage'; idx: number }> = [
    { offset: 0, type: 'locomotive', idx: 0 },
  ];

  for (let i = 0; i < consist.car_count; i++) {
    offsets.push({
      offset: consist.locomotive_length_m + i * consist.car_length_m,
      type: 'carriage',
      idx: i + 1,
    });
  }

  for (const body of offsets) {
    const d = Math.max(0, headDistanceM - body.offset);
    const a = pointAlong(polyline, d);
    const b = pointAlong(polyline, d + 3);
    points.push({
      lon: a[0],
      lat: a[1],
      rotation: bearing(point(a), point(b)),
      body_index: body.idx,
      body_type: body.type,
    });
  }

  return points;
}
